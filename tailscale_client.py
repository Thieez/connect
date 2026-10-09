"""Utilities for joining a Headscale mesh from the Connect client."""

import base64
import ctypes
import ipaddress
import json
import os
import shutil
import subprocess
from urllib.parse import urlsplit

DEFAULT_HEADSCALE_URL = "https://connect-headscale.onrender.com"


def _find_tailscale():
    executable = shutil.which("tailscale")
    if executable:
        return executable

    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = os.path.join(program_files, "Tailscale", "tailscale.exe")
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        "Nie znaleziono tailscale. Zainstaluj klienta Tailscale "
        "z https://tailscale.com/download/windows i uruchom ponownie."
    )


def _run_tailscale(executable, *args):
    result = subprocess.run(
        [executable, *args],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"Polecenie tailscale {' '.join(args[:2])} nie powiodło się"
            + (f": {detail}" if detail else ".")
        )
    return result.stdout.strip()


def _is_connected_to_server(executable, server_url):
    try:
        prefs = json.loads(_run_tailscale(executable, "debug", "prefs"))
        status = json.loads(_run_tailscale(executable, "status", "--json"))
    except (RuntimeError, json.JSONDecodeError):
        return False
    if not isinstance(prefs, dict) or not isinstance(status, dict):
        return False
    control_url = prefs.get("ControlURL")
    if not isinstance(control_url, str):
        return False

    expected = urlsplit(server_url)
    configured = urlsplit(control_url)
    return (
        status.get("BackendState") == "Running"
        and configured.scheme == expected.scheme
        and configured.netloc.lower() == expected.netloc.lower()
    )


def connect_to_headscale(server_url, auth_key=None):
    parsed = urlsplit(server_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("--headscale musi być adresem HTTPS serwera Headscale")

    executable = _find_tailscale()
    if not _is_connected_to_server(executable, server_url):
        if not auth_key:
            from getpass import getpass

            auth_key = getpass("Wklej jednorazowy klucz Headscale: ").strip()
        if not auth_key:
            raise ValueError("Klucz Headscale nie może być pusty.")

        _run_tailscale(
            executable,
            "up",
            "--login-server",
            server_url.rstrip("/"),
            "--authkey",
            auth_key,
            "--accept-routes=false",
            "--accept-dns=false",
            "--shields-up=false",
        )
    else:
        _run_tailscale(executable, "set", "--shields-up=false")

    addresses = _run_tailscale(executable, "ip", "-4").splitlines()
    if not addresses:
        raise RuntimeError("Tailscale nie zwrócił adresu IPv4.")
    address = addresses[0].strip()
    try:
        parsed_address = ipaddress.ip_address(address)
    except ValueError as error:
        raise RuntimeError(
            f"Tailscale zwrócił nieprawidłowy adres IPv4: {address}"
        ) from error
    if parsed_address.version != 4 or parsed_address not in ipaddress.ip_network(
        "100.64.0.0/10"
    ):
        raise RuntimeError(
            f"Adres {address} nie należy do podsieci Headscale 100.64.0.0/10."
        )
    print(f"Połączono z Headscale: {address}")
    print("Tailscale domyślnie próbuje trasy direct; DERP pozostaje awaryjnym relayem.")
    return address


def _firewall_rule_script(port):
    if not 1 <= port <= 65535:
        raise ValueError("Port musi być z zakresu 1-65535.")
    rules = [
        {
            "name": f"Connect Headscale TCP {port}",
            "direction": "Inbound",
            "protocol": "TCP",
            "local_port": str(port),
            "remote_address": "100.64.0.0/10",
        },
        {
            "name": "Connect Tailscale direct UDP inbound",
            "direction": "Inbound",
            "protocol": "UDP",
            "local_port": "41641",
        },
        {
            "name": "Connect Tailscale direct UDP outbound",
            "direction": "Outbound",
            "protocol": "UDP",
            "local_port": "41641",
        },
        {
            "name": "Connect Tailscale STUN UDP outbound",
            "direction": "Outbound",
            "protocol": "UDP",
            "remote_port": "3478",
        },
        {
            "name": "Connect Tailscale HTTPS outbound",
            "direction": "Outbound",
            "protocol": "TCP",
            "remote_port": "443",
        },
    ]
    commands = ["$ErrorActionPreference = 'Stop';", "$rules = @("]
    for index, rule in enumerate(rules):
        fields = [
            f"DisplayName='{rule['name']}'",
            f"Direction='{rule['direction']}'",
            "Action='Allow'",
            f"Protocol='{rule['protocol']}'",
            "Profile='Any'",
        ]
        for field in ("local_port", "remote_port", "remote_address"):
            if field in rule:
                field_name = {
                    "local_port": "LocalPort",
                    "remote_port": "RemotePort",
                    "remote_address": "RemoteAddress",
                }[field]
                fields.append(f"{field_name}='{rule[field]}'")
        suffix = "," if index < len(rules) - 1 else ""
        commands.append("  @{" + ";".join(fields) + "}" + suffix)
    commands.extend(
        [
            "); foreach ($rule in $rules) {",
            "if (-not (Get-NetFirewallRule -DisplayName $rule.DisplayName "
            "-ErrorAction SilentlyContinue)) {",
            "$params = @{DisplayName=$rule.DisplayName; Direction=$rule.Direction; "
            "Action=$rule.Action; Protocol=$rule.Protocol; Profile=$rule.Profile};",
            "if ($rule.ContainsKey('LocalPort')) "
            "{$params.LocalPort=$rule.LocalPort};",
            "if ($rule.ContainsKey('RemotePort')) "
            "{$params.RemotePort=$rule.RemotePort};",
            "if ($rule.ContainsKey('RemoteAddress')) "
            "{$params.RemoteAddress=$rule.RemoteAddress};",
            "New-NetFirewallRule @params | Out-Null; } }",
        ]
    )
    return " ".join(commands)


def _powershell_encoded(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _is_windows_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def allow_mesh_inbound(port):
    if os.name != "nt":
        return

    script = _firewall_rule_script(port)
    encoded_script = _powershell_encoded(script)
    powershell = shutil.which("powershell.exe") or "powershell.exe"
    if _is_windows_admin():
        command = encoded_script
    else:
        elevated_script = (
            "$ErrorActionPreference = 'Stop'; "
            "$p = Start-Process -FilePath $PSHOME\\powershell.exe "
            f"-ArgumentList @('-NoProfile','-EncodedCommand','{encoded_script}') "
            "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        )
        command = _powershell_encoded(elevated_script)

    result = subprocess.run(
        [powershell, "-NoProfile", "-EncodedCommand", command],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            "Nie udało się ustawić reguły Zapory Windows dla sieci Headscale"
            + (f": {detail}" if detail else ". Zaakceptuj monit UAC.")
        )
    print(
        f"Zapora Windows zezwala na TCP/{port} z sieci Headscale oraz UDP "
        "41641/3478 i TCP 443 dla bezpośredniego Tailscale."
    )

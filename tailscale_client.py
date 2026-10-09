"""Utilities for joining a Headscale mesh from the Connect client."""

import base64
import ctypes
import ipaddress
import json
import logging
import os
import shutil
import subprocess
import threading
from urllib.parse import urlsplit
from logging.handlers import RotatingFileHandler

DEFAULT_HEADSCALE_URL = "https://connect-headscale.onrender.com"
DIAGNOSTICS_INTERVAL_SECONDS = 15


def _diagnostics_logger(log_path):
    logger = logging.getLogger("connect.mesh")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=2,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


def _format_peer_routes(status, peer_address=None):
    peers = status.get("Peer") or {}
    if not isinstance(peers, dict):
        return ["status contains no peer list"]

    wanted = str(peer_address) if peer_address else None
    results = []
    for peer in peers.values():
        if not isinstance(peer, dict):
            continue
        addresses = peer.get("TailscaleIPs") or []
        if wanted and wanted not in addresses:
            continue
        name = peer.get("HostName") or peer.get("DNSName") or "peer"
        current_address = peer.get("CurAddr") or ""
        relay = peer.get("Relay") or ""
        peer_relay = peer.get("PeerRelay") or ""
        if current_address:
            route = f"direct endpoint={current_address}"
        elif peer_relay:
            route = f"peer-relay={peer_relay}"
        elif relay:
            route = f"DERP({relay})"
        else:
            route = "route=not-established"
        results.append(
            f"peer={name} ips={','.join(addresses)} route={route} "
            f"active={peer.get('Active', False)} online={peer.get('Online', False)} "
            f"tx={peer.get('TxBytes', 0)} rx={peer.get('RxBytes', 0)}"
        )
    if not results and wanted:
        return [f"peer={wanted} is not present in the Tailscale peer map"]
    if not results:
        return ["Tailscale peer map is empty"]
    return results


def _read_mesh_status(executable, peer_address=None):
    status = json.loads(_run_tailscale(executable, "status", "--json"))
    if not isinstance(status, dict):
        raise RuntimeError("tailscale status returned an unexpected JSON value")
    return status.get("BackendState", "unknown"), _format_peer_routes(
        status, peer_address
    )


def _write_mesh_diagnostics(logger, executable, peer_address=None, include_netcheck=False):
    try:
        backend_state, routes = _read_mesh_status(executable, peer_address)
        logger.info("Tailscale backend=%s; %s", backend_state, "; ".join(routes))
    except (RuntimeError, json.JSONDecodeError) as error:
        logger.error("Could not read Tailscale peer route status: %s", error)

    if include_netcheck:
        try:
            result = subprocess.run(
                [executable, "netcheck"],
                capture_output=True,
                check=False,
                text=True,
                timeout=20,
            )
            output = (result.stdout or result.stderr).strip()
            if result.returncode:
                logger.error("tailscale netcheck failed: %s", output)
            else:
                logger.info("Tailscale netcheck:\n%s", output or "(no output)")
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.error("Could not run tailscale netcheck: %s", error)


class MeshDiagnostics:
    def __init__(self, executable, peer_address=None, log_path="connect-mesh.log"):
        self.executable = executable
        self.peer_address = peer_address
        self.logger = _diagnostics_logger(log_path)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.logger.info(
            "Starting mesh diagnostics; log file=%s; peer=%s",
            os.path.abspath(self.logger.handlers[0].baseFilename),
            self.peer_address or "all peers",
        )
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _run(self):
        _write_mesh_diagnostics(
            self.logger, self.executable, self.peer_address, include_netcheck=True
        )
        while not self.stopped.wait(DIAGNOSTICS_INTERVAL_SECONDS):
            _write_mesh_diagnostics(self.logger, self.executable, self.peer_address)


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


def start_mesh_diagnostics(peer_address=None):
    diagnostics = MeshDiagnostics(_find_tailscale(), peer_address)
    diagnostics.start()
    return diagnostics


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

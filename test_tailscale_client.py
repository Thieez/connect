import json
import sys
import unittest
from unittest.mock import patch

from connect import parse_args
from tailscale_client import (
    _firewall_rule_script,
    _is_connected_to_server,
    connect_to_headscale,
)


class TailscaleClientTests(unittest.TestCase):
    def test_headscale_is_enabled_by_default(self):
        with patch.object(sys, "argv", ["connect.py"]):
            args = parse_args()

        self.assertEqual(args.headscale, "https://connect-headscale.onrender.com")

    def test_legacy_mode_can_disable_default_mesh(self):
        with patch.object(sys, "argv", ["connect.py", "--no-headscale"]):
            args = parse_args()

        self.assertIsNone(args.headscale)

    def test_skips_login_for_existing_headscale_connection(self):
        with (
            patch("tailscale_client._find_tailscale", return_value="tailscale.exe"),
            patch(
                "tailscale_client._run_tailscale",
                side_effect=[
                    json.dumps(
                        {"ControlURL": "https://connect-headscale.onrender.com"}
                    ),
                    json.dumps({"BackendState": "Running"}),
                    "",
                    "100.64.0.1",
                ],
            ) as run,
        ):
            address = connect_to_headscale(
                "https://connect-headscale.onrender.com",
                auth_key=None,
            )

        self.assertEqual(address, "100.64.0.1")
        self.assertEqual(run.call_count, 4)
        self.assertEqual(run.call_args.args[1:], ("ip", "-4"))
        self.assertEqual(run.call_args_list[2].args[1:], ("set", "--shields-up=false"))

    def test_join_disables_shields_up(self):
        with (
            patch("tailscale_client._find_tailscale", return_value="tailscale.exe"),
            patch(
                "tailscale_client._is_connected_to_server",
                return_value=False,
            ),
            patch(
                "tailscale_client._run_tailscale",
                side_effect=["", "100.64.0.1"],
            ) as run,
            patch("getpass.getpass", return_value="one-time-key"),
        ):
            connect_to_headscale("https://connect-headscale.onrender.com")

        self.assertEqual(
            run.call_args_list[0].args[1:],
            (
                "up",
                "--login-server",
                "https://connect-headscale.onrender.com",
                "--authkey",
                "one-time-key",
                "--accept-routes=false",
                "--accept-dns=false",
                "--shields-up=false",
            ),
        )

    def test_requires_auth_key_when_not_connected(self):
        with (
            patch("tailscale_client._find_tailscale", return_value="tailscale.exe"),
            patch("tailscale_client._run_tailscale", return_value=""),
            patch("getpass.getpass", return_value=""),
        ):
            with self.assertRaisesRegex(ValueError, "nie może być pusty"):
                connect_to_headscale("https://connect-headscale.onrender.com")

    def test_firewall_rule_is_limited_to_mesh_subnet_and_port(self):
        script = _firewall_rule_script(8765)

        self.assertIn("LocalPort='8765'", script)
        self.assertIn("RemoteAddress='100.64.0.0/10'", script)
        self.assertIn("Direction='Inbound'", script)
        self.assertIn("Protocol='UDP';Profile='Any';LocalPort='41641'", script)
        self.assertIn("Protocol='UDP';Profile='Any';RemotePort='3478'", script)
        self.assertIn("Protocol='TCP';Profile='Any';RemotePort='443'", script)
        self.assertIn("Get-NetFirewallRule", script)
        self.assertIn("New-NetFirewallRule @params", script)

    def test_rejects_invalid_port(self):
        with self.assertRaises(ValueError):
            _firewall_rule_script(0)

    def test_detects_control_server(self):
        with patch(
            "tailscale_client._run_tailscale",
            side_effect=[
                json.dumps({"ControlURL": "https://connect-headscale.onrender.com/"}),
                json.dumps({"BackendState": "Running"}),
            ],
        ):
            self.assertTrue(
                _is_connected_to_server(
                    "tailscale.exe", "https://connect-headscale.onrender.com"
                )
            )


if __name__ == "__main__":
    unittest.main()

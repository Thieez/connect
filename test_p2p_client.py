import os
import unittest
from unittest.mock import patch

from p2p_client import DEFAULT_STUN_SERVERS, _stun_server_urls


class StunServerUrlsTests(unittest.TestCase):
    def test_uses_default_servers_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_stun_server_urls(), list(DEFAULT_STUN_SERVERS))

    def test_uses_configured_servers_and_ignores_empty_entries(self):
        with patch.dict(
            os.environ,
            {"CONNECT_STUN_SERVERS": " stun:first.example:3478, ,stun:second.example "},
            clear=True,
        ):
            self.assertEqual(
                _stun_server_urls(),
                ["stun:first.example:3478", "stun:second.example"],
            )


if __name__ == "__main__":
    unittest.main()

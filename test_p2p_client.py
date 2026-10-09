import json
import os
import unittest
from unittest.mock import Mock, patch

from p2p_client import (
    DEFAULT_STUN_SERVER,
    _cloudflare_turn_credentials,
    _stun_server_url,
)


class StunServerUrlsTests(unittest.TestCase):
    def test_uses_default_servers_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_stun_server_url(), DEFAULT_STUN_SERVER)

    def test_uses_configured_server(self):
        with patch.dict(
            os.environ,
            {"CONNECT_STUN_SERVER": " stun:custom.example:3478 "},
            clear=True,
        ):
            self.assertEqual(_stun_server_url(), "stun:custom.example:3478")

    def test_fetches_temporary_cloudflare_turn_credentials(self):
        ice_servers = [
            {
                "urls": ["turn:turn.example:3478"],
                "username": "temporary-user",
                "credential": "temporary-password",
            }
        ]
        response = Mock()
        response.read.return_value = json.dumps({"iceServers": ice_servers}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)

        with patch("p2p_client.urlopen", return_value=response) as urlopen:
            result = _cloudflare_turn_credentials("key/id", "api-token")

        self.assertEqual(result, ice_servers)
        request = urlopen.call_args.args[0]
        self.assertIn("/keys/key%2Fid/credentials/", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer api-token")
        self.assertEqual(json.loads(request.data), {"ttl": 3600})


if __name__ == "__main__":
    unittest.main()

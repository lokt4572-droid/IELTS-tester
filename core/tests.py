import socket

import requests
from django.test import SimpleTestCase


class NetworkIsolationTests(SimpleTestCase):
    def test_http_requests_are_blocked_before_network_access(self):
        with self.assertRaisesRegex(AssertionError, "Network requests are disabled"):
            requests.get("https://example.invalid/")

    def test_raw_network_sockets_are_blocked_before_connection(self):
        with self.assertRaisesRegex(AssertionError, "Network access is disabled"):
            socket.create_connection(("203.0.113.1", 443), timeout=0.01)

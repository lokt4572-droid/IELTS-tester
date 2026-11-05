import ipaddress
import socket
from unittest import mock

from django.conf import settings
from django.test.runner import DiscoverRunner


class NoNetworkDiscoverRunner(DiscoverRunner):
    """Allow only the local test database socket; block other test networking."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        database = settings.DATABASES["default"]
        database_port = int(database.get("PORT") or 5432)
        self._original_socket_connect = socket.socket.connect
        self._original_socket_connect_ex = socket.socket.connect_ex

        def guard_socket(sock, address, original):
            try:
                host, port = address[:2]
                is_loopback = ipaddress.ip_address(host).is_loopback
            except (TypeError, ValueError, IndexError):
                is_loopback = False
                port = None
            if is_loopback and int(port) == database_port:
                return original(sock, address)
            raise AssertionError(
                "Network access is disabled during tests; only the local test "
                "database connection is allowed."
            )

        self._network_guards = [
            mock.patch(
                "requests.sessions.Session.request",
                side_effect=AssertionError(
                    "Network requests are disabled during tests; mock the HTTP call."
                ),
            ),
            mock.patch.object(
                socket.socket,
                "connect",
                lambda sock, address: guard_socket(
                    sock, address, self._original_socket_connect
                ),
            ),
            mock.patch.object(
                socket.socket,
                "connect_ex",
                lambda sock, address: guard_socket(
                    sock, address, self._original_socket_connect_ex
                ),
            ),
            mock.patch.object(
                socket.socket,
                "sendto",
                side_effect=AssertionError("Network access is disabled during tests."),
            ),
        ]
        for network_guard in self._network_guards:
            network_guard.start()

    def teardown_test_environment(self, **kwargs):
        try:
            for network_guard in reversed(self._network_guards):
                network_guard.stop()
        finally:
            super().teardown_test_environment(**kwargs)

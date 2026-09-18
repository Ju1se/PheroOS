"""All policy, execution and replay tests run without network access."""
import socket
import pytest

_CONNECT, _CREATE_CONNECTION = socket.socket.connect, socket.create_connection
_LOOPBACK = ('127.0.0.1', '::1', 'localhost')


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Network is forbidden in interaction tests')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)


@pytest.fixture
def loopback(monkeypatch):
    """Permit connections to the loopback interface only, for in-process fixture servers."""
    def guard(address):
        if type(address) is not tuple or address[0] not in _LOOPBACK:
            raise AssertionError('Only loopback connections are allowed in interaction tests')

    def connect(sock, address, *args, **kwargs):
        guard(address)
        return _CONNECT(sock, address, *args, **kwargs)

    def create_connection(address, *args, **kwargs):
        guard(address)
        return _CREATE_CONNECTION(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket, 'create_connection', create_connection)

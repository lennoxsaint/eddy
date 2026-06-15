"""v1.0 GA: VERIFIABLE no-egress. The privacy promise ("nothing leaves your machine" under
--local-only) is enforced at the syscall boundary, not just intended. These tests prove the guard
blocks outbound TCP, allows loopback (local Ollama), and that resolving the offline editorial brain
attempts zero egress. Hermetic — no real external network is ever contacted."""

import socket

import pytest

import eddy.netguard as ng
from eddy.netguard import EgressBlocked, _check, _is_loopback, install_egress_guard


@pytest.fixture
def restore_socket():
    """Save/restore the global socket hooks so the guard can't leak into other tests."""
    c, cc, inst = socket.socket.connect, socket.create_connection, ng._installed[0]
    ng._installed[0] = False
    yield
    socket.socket.connect = c
    socket.create_connection = cc
    ng._installed[0] = inst


def test_loopback_classification():
    assert _is_loopback("127.0.0.1") and _is_loopback("::1") and _is_loopback("localhost")
    assert _is_loopback("127.5.5.5")  # all of 127/8 is loopback
    assert not _is_loopback("8.8.8.8")
    assert not _is_loopback("api.anthropic.com")  # a hostname (not a bare IP) is treated as egress


def test_check_allows_loopback_blocks_egress():
    _check(("127.0.0.1", 11434))  # local Ollama — no raise
    _check(("::1", 80))
    with pytest.raises(EgressBlocked):
        _check(("140.82.112.3", 443))
    with pytest.raises(EgressBlocked):
        _check(("api.anthropic.com", 443))


def test_guard_blocks_non_loopback_connect(restore_socket):
    install_egress_guard()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(EgressBlocked):
        s.connect(("8.8.8.8", 53))  # raises BEFORE any real network attempt


def test_guard_blocks_create_connection(restore_socket):
    install_egress_guard()
    with pytest.raises(EgressBlocked):
        socket.create_connection(("example.com", 80))


def test_guard_allows_loopback_through_to_real_connect(restore_socket):
    # bind a real loopback listener, then prove the guarded connect delegates (no EgressBlocked)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        install_egress_guard()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(1.0)
        client.connect(("127.0.0.1", port))  # must succeed — loopback allowed
        client.close()
    finally:
        server.close()


def test_offline_brain_resolution_attempts_zero_egress(monkeypatch, restore_socket):
    """The headline proof: with the guard armed, resolving the offline editorial brain must not try
    to reach the network. If it did, EgressBlocked would fail this test."""
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    install_egress_guard()
    from eddy.config import load_config
    from eddy.providers.base import FallbackProvider, get_editorial_provider

    prov = get_editorial_provider(load_config())
    assert not isinstance(prov, FallbackProvider)  # offline never returns a cloud-backed brain


def test_maybe_install_only_when_offline(monkeypatch, restore_socket):
    monkeypatch.delenv("EDDY_OFFLINE", raising=False)
    assert ng.maybe_install_egress_guard() is False  # online: no guard
    monkeypatch.setenv("EDDY_OFFLINE", "1")
    assert ng.maybe_install_egress_guard() is True

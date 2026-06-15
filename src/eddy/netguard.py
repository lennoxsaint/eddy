"""Active egress tripwire for --local-only / EDDY_OFFLINE.

Offline mode routes the editorial brain to the local model and tells Whisper not to download — but
that is *intent*, not *enforcement*. This installs a process-wide guard that makes any OUTBOUND
(non-loopback) TCP connection raise, so the "nothing leaves your machine" promise is enforced at the
syscall boundary rather than trusted to careful routing. Loopback (127.0.0.0/8, ::1, localhost) is
allowed so a local Ollama still works; unix-domain sockets are left alone."""

from __future__ import annotations

import ipaddress
import socket

_LOOPBACK_HOSTNAMES = {"localhost", "ip6-localhost", "ip6-loopback", ""}


class EgressBlocked(RuntimeError):
    """Raised when --local-only blocks an outbound connection to a non-loopback address."""


def _is_loopback(host: object) -> bool:
    if host in _LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False  # a hostname that isn't a bare IP — treat as potential egress, block it


def _host_of(address: object) -> object:
    return address[0] if isinstance(address, tuple) and address else address


def _check(address: object) -> None:
    host = _host_of(address)
    if not _is_loopback(host):
        raise EgressBlocked(
            f"--local-only: blocked outbound connection to {host!r}. Offline mode guarantees nothing "
            f"leaves your machine; remove --local-only (and EDDY_OFFLINE) to allow network access."
        )


_installed = [False]


def install_egress_guard() -> None:
    """Idempotently wrap socket connect paths so non-loopback TCP connections raise EgressBlocked."""
    if _installed[0]:
        return
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def guarded_connect(self, address, *a, **k):  # type: ignore[no-untyped-def]
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _check(address)
        return real_connect(self, address, *a, **k)

    def guarded_create(address, *a, **k):  # type: ignore[no-untyped-def]
        _check(address)
        return real_create(address, *a, **k)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign,assignment]
    socket.create_connection = guarded_create  # type: ignore[assignment]
    _installed[0] = True


def maybe_install_egress_guard() -> bool:
    """Install the guard iff this run is offline. Returns whether it's now active."""
    from eddy.privacy import is_offline

    if is_offline():
        install_egress_guard()
    return _installed[0]

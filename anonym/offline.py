"""Blocco delle connessioni di rete in uscita verso host non locali.

Si attiva una volta per processo: da quel momento qualsiasi libreria che provi a
collegarsi a un host esterno (telemetria, download, chiamate API) riceve un errore.
Le connessioni verso localhost restano permesse perche' servono a Streamlit.
"""

from __future__ import annotations

import ipaddress
import socket

_HOST_LOCALI = {"localhost", "localhost.localdomain", "ip6-localhost", ""}
_originali: dict[str, object] = {}
_tentativi_bloccati: list[str] = []


class ReteBloccata(OSError):
    """Errore sollevato quando il codice tenta di uscire dal Mac."""


def _e_locale(host: object) -> bool:
    """Vero se l'host e' il computer stesso (loopback) o un socket Unix."""
    if not isinstance(host, str):
        return False
    h = host.strip("[]").split("%")[0].lower()
    if h in _HOST_LOCALI:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _controlla_indirizzo(sock: socket.socket, address: object) -> None:
    """Solleva ReteBloccata se l'indirizzo non e' locale."""
    if getattr(socket, "AF_UNIX", None) is not None and sock.family == socket.AF_UNIX:
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if not _e_locale(host):
        _tentativi_bloccati.append(str(host))
        raise ReteBloccata(f"Connessione verso '{host}' bloccata: anonym-data lavora solo in locale.")


def _connect(self: socket.socket, address: object):  # type: ignore[no-untyped-def]
    _controlla_indirizzo(self, address)
    return _originali["connect"](self, address)  # type: ignore[operator]


def _connect_ex(self: socket.socket, address: object):  # type: ignore[no-untyped-def]
    _controlla_indirizzo(self, address)
    return _originali["connect_ex"](self, address)  # type: ignore[operator]


def _sendto(self: socket.socket, data: bytes, *args):  # type: ignore[no-untyped-def]
    address = args[-1]
    _controlla_indirizzo(self, address)
    return _originali["sendto"](self, data, *args)  # type: ignore[operator]


def _getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    # blocca anche la risoluzione DNS di nomi esterni, che di per se' e' traffico di rete
    if host is not None and not _e_locale(host if isinstance(host, str) else host.decode()):
        _tentativi_bloccati.append(str(host))
        raise ReteBloccata(f"Risoluzione di '{host}' bloccata: anonym-data lavora solo in locale.")
    return _originali["getaddrinfo"](host, *args, **kwargs)  # type: ignore[operator]


def attiva() -> None:
    """Attiva il blocco per l'intero processo. Chiamarla piu' volte non ha effetti."""
    if _originali:
        return
    _originali["connect"] = socket.socket.connect
    _originali["connect_ex"] = socket.socket.connect_ex
    _originali["sendto"] = socket.socket.sendto
    _originali["getaddrinfo"] = socket.getaddrinfo
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
    socket.socket.sendto = _sendto  # type: ignore[method-assign]
    socket.getaddrinfo = _getaddrinfo  # type: ignore[assignment]


def attivo() -> bool:
    """Dice se il blocco e' in funzione."""
    return bool(_originali)


def tentativi_bloccati() -> list[str]:
    """Host verso cui qualcosa ha provato a collegarsi da quando il blocco e' attivo."""
    return list(_tentativi_bloccati)

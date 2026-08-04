"""Minimal SNMPv1 GET client.

The station exposes a handful of values over SNMP that its ``status.xml``
leaves out. Pulling in a full SNMP stack for two OIDs would be a heavy
dependency, so this module speaks just enough BER to issue a GetRequest and
read the answer back. It has no third-party requirements.

Everything here is blocking; call it from an executor.
"""

from __future__ import annotations

import logging
import socket

_LOGGER = logging.getLogger(__name__)

# SNMP error-status values that mean "the OID simply is not there", as opposed
# to a transport failure.
_ERROR_STATUS = {
    0: None,
    1: "tooBig",
    2: "noSuchName",
    3: "badValue",
    4: "readOnly",
    5: "genErr",
}

# BER tags whose payload we know how to turn into a string.
_TAG_INTEGER = 0x02
_TAG_OCTET_STRING = 0x04
_TAG_NULL = 0x05
_TAG_OID = 0x06
_TAG_SEQUENCE = 0x30
_TAG_GET_REQUEST = 0xA0
_NUMERIC_TAGS = (0x02, 0x41, 0x42, 0x43)  # INTEGER, Counter, Gauge, TimeTicks
_NO_VALUE_TAGS = (0x80, 0x81, 0x82)  # noSuchObject / noSuchInstance / endOfMib


class SnmpError(Exception):
    """Raised when the station cannot be reached over SNMP."""


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_int(value: int) -> bytes:
    if value == 0:
        return _tlv(_TAG_INTEGER, b"\x00")
    return _tlv(_TAG_INTEGER, value.to_bytes((value.bit_length() // 8) + 1, "big"))


def _base128(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _encode_oid(oid: str) -> bytes:
    arcs = [int(arc) for arc in oid.strip(".").split(".")]
    body = _base128(arcs[0] * 40 + arcs[1])
    for arc in arcs[2:]:
        body += _base128(arc)
    return _tlv(_TAG_OID, body)


def _parse_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    tag = data[offset]
    offset += 1
    length = data[offset]
    offset += 1
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    return tag, data[offset : offset + length], offset + length


def _decode_value(tag: int, body: bytes) -> str | None:
    if tag == _TAG_OCTET_STRING:
        return body.decode("utf-8", "replace").strip()
    if tag in _NUMERIC_TAGS:
        return str(int.from_bytes(body, "big"))
    if tag == _TAG_NULL or tag in _NO_VALUE_TAGS:
        return None
    return None


def _build_request(oid: str, community: str, request_id: int) -> bytes:
    varbind = _tlv(_TAG_SEQUENCE, _encode_oid(oid) + _tlv(_TAG_NULL, b""))
    pdu = _tlv(
        _TAG_GET_REQUEST,
        _encode_int(request_id)
        + _encode_int(0)  # error-status
        + _encode_int(0)  # error-index
        + _tlv(_TAG_SEQUENCE, varbind),
    )
    return _tlv(
        _TAG_SEQUENCE,
        _encode_int(0)  # version 1
        + _tlv(_TAG_OCTET_STRING, community.encode())
        + pdu,
    )


def _parse_response(data: bytes) -> str | None:
    _, message, _ = _parse_tlv(data)
    _, _, offset = _parse_tlv(message)  # version
    _, _, offset = _parse_tlv(message, offset)  # community
    _, pdu, _ = _parse_tlv(message, offset)

    _, _, offset = _parse_tlv(pdu)  # request-id
    _, error_body, offset = _parse_tlv(pdu, offset)
    error = int.from_bytes(error_body, "big") if error_body else 0
    if _ERROR_STATUS.get(error, f"error {error}") is not None:
        return None

    _, _, offset = _parse_tlv(pdu, offset)  # error-index
    _, varbind_list, _ = _parse_tlv(pdu, offset)
    _, varbind, _ = _parse_tlv(varbind_list)
    _, _, offset = _parse_tlv(varbind)  # OID
    tag, body, _ = _parse_tlv(varbind, offset)
    return _decode_value(tag, body)


def _open_socket(family: int, timeout: float) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        # On Windows an ICMP port-unreachable from an earlier datagram would
        # otherwise surface as a reset on the next recvfrom.
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:  # pragma: no cover - platform dependent
            pass
    return sock


def _strip_brackets(host: str) -> str:
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def get(
    host: str,
    oid: str,
    community: str,
    port: int = 161,
    timeout: float = 4.0,
    request_id: int = 1,
) -> str | None:
    """Fetch a single OID.

    Returns the value as a string, or ``None`` when the station answers but
    does not know the OID. Raises :class:`SnmpError` if it cannot be reached.
    """
    try:
        info = socket.getaddrinfo(
            _strip_brackets(host),
            port,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP,
        )
    except socket.gaierror as err:
        raise SnmpError(f"cannot resolve {host}: {err}") from err

    family, _, _, _, sockaddr = info[0]
    sock = _open_socket(family, timeout)
    try:
        sock.sendto(_build_request(oid, community, request_id), sockaddr)
        data, _ = sock.recvfrom(4096)
    except socket.timeout as err:
        raise SnmpError(f"no SNMP answer from {host}") from err
    except OSError as err:
        raise SnmpError(f"SNMP transport error talking to {host}: {err}") from err
    finally:
        sock.close()

    try:
        return _parse_response(data)
    except (IndexError, ValueError) as err:
        _LOGGER.debug("Malformed SNMP response from %s: %s", host, err)
        return None


def get_float(
    host: str, oid: str, community: str, request_id: int = 1
) -> float | None:
    """Fetch an OID and coerce it to a float, or ``None`` if not numeric."""
    raw = get(host, oid, community, request_id=request_id)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ".").strip())
    except ValueError:
        return None

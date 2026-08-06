"""Tests for the hand-rolled BER encoder/decoder in snmp.py."""

from unittest.mock import patch

import pytest

from custom_components.giom import snmp
from custom_components.giom.snmp import (
    _build_request,
    _encode_int,
    _encode_length,
    _encode_oid,
    _parse_response,
    _tlv,
    get_float,
)

_TAG_INTEGER = 0x02
_TAG_OCTET_STRING = 0x04
_TAG_OID = 0x06
_TAG_SEQUENCE = 0x30
_TAG_GET_RESPONSE = 0xA2


def test_encode_length_short_and_long_form():
    assert _encode_length(5) == b"\x05"
    assert _encode_length(0x7F) == b"\x7f"
    assert _encode_length(200) == b"\x81\xc8"
    assert _encode_length(0x1234) == b"\x82\x12\x34"


def test_encode_oid_multibyte_arc():
    # 21287 needs three base-128 bytes; the first two arcs pack into one.
    body = _encode_oid("1.3.6.1.4.1.21287.15.2.0")
    assert body[0] == _TAG_OID
    assert body[2:] == bytes(
        [0x2B, 0x06, 0x01, 0x04, 0x01, 0x81, 0xA6, 0x27, 0x0F, 0x02, 0x00]
    )


def test_encode_oid_leading_zero_tree():
    # The station's quirk: OIDs live under 0.1.3... First two arcs 0.1 -> 1.
    body = _encode_oid("0.1.3.6.1.4.1.21287.15.14.0")
    assert body[2] == 0x01
    assert body[3] == 0x03


def _response(value_tlv: bytes, error_status: int = 0, oid: str = "0.1.3.6.1.4.1.21287.15.2.0") -> bytes:
    """Assemble a GetResponse the way the station would."""
    varbind = _tlv(_TAG_SEQUENCE, _encode_oid(oid) + value_tlv)
    pdu = _tlv(
        _TAG_GET_RESPONSE,
        _encode_int(1)
        + _encode_int(error_status)
        + _encode_int(0)
        + _tlv(_TAG_SEQUENCE, varbind),
    )
    return _tlv(
        _TAG_SEQUENCE,
        _encode_int(0) + _tlv(_TAG_OCTET_STRING, b"public") + pdu,
    )


def test_parse_response_octet_string():
    data = _response(_tlv(_TAG_OCTET_STRING, b"25.3"))
    assert _parse_response(data) == "25.3"


def test_parse_response_integer():
    data = _response(_tlv(_TAG_INTEGER, b"\x00\xfd"))
    assert _parse_response(data) == "253"


def test_parse_response_no_such_name():
    data = _response(_tlv(_TAG_OCTET_STRING, b"ignored"), error_status=2)
    assert _parse_response(data) is None


def test_parse_response_no_such_object():
    data = _response(bytes([0x80, 0x00]))
    assert _parse_response(data) is None


def test_request_response_round_trip():
    # The encoder must produce something its own decoder can walk.
    request = _build_request("0.1.3.6.1.4.1.21287.15.14.0", "public", request_id=7)
    assert request[0] == _TAG_SEQUENCE
    # Swap the PDU tag to GetResponse and it parses as an empty (Null) answer.
    mutated = bytearray(request)
    mutated[mutated.index(0xA0)] = _TAG_GET_RESPONSE
    assert _parse_response(bytes(mutated)) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("25.3", 25.3), ("25,3", 25.3), (" 1013 ", 1013.0), ("abc", None), (None, None)],
)
def test_get_float_coercion(raw, expected):
    with patch.object(snmp, "get", return_value=raw):
        assert get_float("host", "0.1.3", "public") == expected

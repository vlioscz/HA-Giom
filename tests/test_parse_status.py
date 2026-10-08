"""Tests for the pure helpers in coordinator.py."""

import pytest

from custom_components.giom.coordinator import (
    beaufort,
    data_xml_url,
    device_title,
    parse_data_xml,
    parse_status,
    status_url,
    url_host,
)


def test_parse_3000_payload(status_3000):
    data = parse_status(status_3000)

    assert data["temperature"] == 30.6
    assert data["pressure"] == 1011.7
    assert data["windspeed"] == 2.5
    assert data["devname"] == "GIOM 3000AE"  # trailing spaces stripped

    # winddir 3 on a 16-point rose
    assert data["wind_bearing"] == 67.5
    assert data["wind_direction"] == "ene"

    # derived locally from windspeed
    assert data["beaufort"] == 2

    # 4000-only fields must not materialise out of nothing
    for key in ("spower", "uf", "illuminance", "lpd", "sdist", "senr"):
        assert key not in data


def test_parse_4000_payload(status_4000):
    data = parse_status(status_4000)

    assert data["spower"] == 512.3
    assert data["uf"] == 3.2
    assert data["sdist"] == 12.0
    assert data["senr"] == 8541.0
    assert data["wind_bearing"] == 292.5
    assert data["wind_direction"] == "wnw"

    # Derived the same way the station's web UI does: spower x 126.7,
    # rounded to two decimals.
    assert data["illuminance"] == round(512.3 * 126.7, 2)

    # Lightning strikes per day - the manufacturer's own comment for lpd.
    assert data["lpd"] == 1018.0


def test_comma_decimals_tolerated():
    data = parse_status("<r><temperature>21,4</temperature><winddir>3</winddir></r>")
    assert data["temperature"] == 21.4
    assert data["wind_bearing"] == 67.5


def test_empty_and_garbage_fields_are_skipped():
    data = parse_status(
        "<r><temperature></temperature><pressure>n/a</pressure>"
        "<windspeed>1.0</windspeed><winddir>bad</winddir></r>"
    )
    assert "temperature" not in data
    assert "pressure" not in data
    assert "wind_bearing" not in data
    assert data["windspeed"] == 1.0


def test_malformed_xml_raises():
    with pytest.raises(ValueError):
        parse_status("this is not xml")


def test_winddir_index_wraps():
    data = parse_status("<r><winddir>16</winddir></r>")
    assert data["wind_direction"] == "n"


@pytest.mark.parametrize(
    ("speed", "force"),
    [(0.0, 0), (0.2, 0), (0.3, 1), (2.5, 2), (10.8, 6), (35.0, 12)],
)
def test_beaufort_boundaries(speed, force):
    assert beaufort(speed) == force


@pytest.mark.parametrize(
    ("devname", "title"),
    [
        (None, "GIOM"),
        ("", "GIOM"),
        ("   ", "GIOM"),
        ("GIOM 3000AE    ", "GIOM"),
        ("giom 4000", "GIOM"),
        ("IQWS-4000", "GIOM"),
        ("Zahrada", "Zahrada"),
    ],
)
def test_device_title(devname, title):
    assert device_title(devname) == title


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("192.168.0.100", "192.168.0.100"),
        ("station.local", "station.local"),
        ("fe80::1", "[fe80::1]"),
        ("[fe80::1]", "[fe80::1]"),
    ],
)
def test_url_host(host, expected):
    assert url_host(host) == expected


def test_status_url():
    assert status_url("192.168.0.100") == "http://192.168.0.100/status.xml"
    assert status_url("fe80::1") == "http://[fe80::1]/status.xml"
    assert data_xml_url("192.168.0.100") == "http://192.168.0.100/data.xml"


def test_parse_data_xml(data_4000):
    data = parse_data_xml(data_4000)

    assert data["windspeed_average"] == 0.6
    assert data["status_pressure"] == "OK"
    assert data["status_temperature"] == "OK"
    assert data["status_light"] == "OK"
    assert data["status_lightning"] == "OK"

    # Everything else in data.xml duplicates status.xml and must be ignored,
    # or it would silently override the primary endpoint's readings.
    assert len(data) == 5


def test_parse_data_xml_passes_failure_codes_through():
    data = parse_data_xml("<status><SSS>ERR 3</SSS><IAS>n/a</IAS></status>")
    assert data["status_light"] == "ERR 3"
    assert "windspeed_average" not in data


def test_parse_data_xml_malformed_raises():
    with pytest.raises(ValueError):
        parse_data_xml("not xml at all")

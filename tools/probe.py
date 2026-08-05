#!/usr/bin/env python3
"""Find a GIOM weather station and dump everything it will tell you.

Needs nothing but a Python 3 interpreter - the SNMPv1 GetRequest is assembled
by hand, so there is no pysnmp to install. That also means it runs unchanged
inside a Home Assistant terminal add-on, which is often the only machine that
sits on the same network as the station.

    # find a station
    python tools/probe.py --scan 192.168.0.0/24

    # interrogate one
    python tools/probe.py 192.168.0.100
    python tools/probe.py "[fd00::1]" --community public

It reports which OID prefix the station answers on, every value it exposes,
and whether status.xml is served with a content type Home Assistant's REST
integration can parse.
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Minimal BER / SNMPv1
# --------------------------------------------------------------------------


def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_int(value: int) -> bytes:
    if value == 0:
        return _tlv(0x02, b"\x00")
    return _tlv(0x02, value.to_bytes((value.bit_length() // 8) + 1, "big"))


def _base128(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def _encode_oid(oid: str) -> bytes:
    arcs = [int(a) for a in oid.strip(".").split(".")]
    body = _base128(arcs[0] * 40 + arcs[1])
    for arc in arcs[2:]:
        body += _base128(arc)
    return _tlv(0x06, body)


def _parse_tlv(data: bytes, i: int = 0) -> tuple[int, bytes, int]:
    tag = data[i]
    i += 1
    length = data[i]
    i += 1
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[i : i + count], "big")
        i += count
    return tag, data[i : i + length], i + length


def _decode_value(tag: int, body: bytes) -> str | None:
    if tag == 0x04:  # OCTET STRING
        return body.decode("utf-8", "replace").strip()
    if tag in (0x02, 0x41, 0x42, 0x43):  # INTEGER / Counter / Gauge / TimeTicks
        return str(int.from_bytes(body, "big"))
    return None  # NULL, noSuchObject, noSuchInstance, endOfMibView


ERRORS = {0: None, 1: "tooBig", 2: "noSuchName", 3: "badValue", 4: "readOnly", 5: "genErr"}


def build_get(oid: str, community: str, request_id: int = 1) -> bytes:
    """Assemble an SNMPv1 GetRequest packet."""
    varbind = _tlv(0x30, _encode_oid(oid) + _tlv(0x05, b""))
    pdu = _tlv(
        0xA0,
        _encode_int(request_id) + _encode_int(0) + _encode_int(0) + _tlv(0x30, varbind),
    )
    return _tlv(0x30, _encode_int(0) + _tlv(0x04, community.encode()) + pdu)


def parse_response(data: bytes) -> tuple[str | None, str | None]:
    """Return (value, error) from an SNMP reply."""
    try:
        _, message, _ = _parse_tlv(data)
        _, _, i = _parse_tlv(message)  # version
        _, _, i = _parse_tlv(message, i)  # community
        _, pdu, _ = _parse_tlv(message, i)

        _, _, j = _parse_tlv(pdu)  # request-id
        _, err_body, j = _parse_tlv(pdu, j)
        err = int.from_bytes(err_body, "big") if err_body else 0
        if ERRORS.get(err, f"error {err}") is not None:
            return None, ERRORS.get(err, f"error {err}")
        _, _, j = _parse_tlv(pdu, j)  # error-index
        _, varbinds, _ = _parse_tlv(pdu, j)

        _, varbind, _ = _parse_tlv(varbinds)
        _, _, k = _parse_tlv(varbind)  # OID
        tag, body, _ = _parse_tlv(varbind, k)
        return _decode_value(tag, body), None
    except (IndexError, ValueError) as exc:
        return None, f"parse: {exc}"


def _clean_host(host: str) -> str:
    return host[1:-1] if host.startswith("[") and host.endswith("]") else host


def _url_host(host: str) -> str:
    bare = _clean_host(host)
    return f"[{bare}]" if ":" in bare else bare


def _udp_socket(timeout: float, family: int = socket.AF_INET) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        # Windows: without this, an ICMP port-unreachable caused by an earlier
        # datagram surfaces as a reset on the next recvfrom, which breaks the
        # subnet scan.
        try:
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        except OSError:
            pass
    return sock


def snmp_get(
    host: str,
    oid: str,
    community: str = "public",
    port: int = 161,
    timeout: float = 2.0,
    request_id: int = 1,
) -> tuple[str | None, str | None]:
    """Fetch one OID. Returns (value, error); value is None when unavailable."""
    try:
        family, _, _, _, sockaddr = socket.getaddrinfo(
            _clean_host(host), port, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
        )[0]
    except socket.gaierror as exc:
        return None, f"dns: {exc}"

    sock = _udp_socket(timeout, family)
    try:
        sock.sendto(build_get(oid, community, request_id), sockaddr)
        data, _ = sock.recvfrom(4096)
    except socket.timeout:
        return None, "timeout"
    except OSError as exc:
        return None, f"socket: {exc}"
    finally:
        sock.close()
    return parse_response(data)


# --------------------------------------------------------------------------
# What the hardware exposes
# --------------------------------------------------------------------------

# The station answers only on OIDs carrying a leading zero. The conventional
# 1.3.6.1.4.1.21287... form returns noSuchName - verified on firmware 1.0.3.
PREFIXES = ["0.1.3.6.1.4.1.21287", "1.3.6.1.4.1.21287"]

OIDS = [
    ("15.1", "Barometric altitude", "m"),
    ("15.2", "Absolute pressure", "hPa"),
    ("15.3", "Relative pressure (QNH)", "hPa"),
    ("15.4", "Wind speed", "m/s"),
    ("15.5", "Wind gust", "m/s"),
    ("15.6", "Wind speed average", "m/s"),
    ("15.7", "Wind direction index", ""),
    ("15.8", "Wind direction text", ""),
    ("15.9", "Wind direction degrees", "deg"),
    ("15.10", "Beaufort", "Bft"),
    ("15.11", "Saturated steam pressure", "hPa"),
    ("15.12", "Relative humidity", "%"),
    ("15.13", "Dew point", "degC"),
    ("15.14", "Temperature", "degC"),
    ("15.15", "Wind chill", "degC"),
    ("15.16", "Absolute humidity", "g/m3"),
    ("15.17", "Absolute humidity", "g/kg"),
    ("15.18", "Device name", ""),
    # IQWS-4000 / GIOM 4000NG only; a GIOM 3000 answers noSuchName.
    ("15.19", "Sunlight intensity", "W/m2"),
    ("15.20", "UV factor", ""),
    ("15.21", "Last lightning time", "UTC hex"),
    ("15.22", "Lightning distance", "km"),
    ("15.23", "Lightning energy", ""),
]

HTTP_PATHS = ["/status.xml", "/data.xml", "/values.xml", "/xml", "/index.xml", "/"]


# --------------------------------------------------------------------------
# Subnet scan
# --------------------------------------------------------------------------


def scan_subnet(
    subnet: str, community: str = "public", port: int = 161, wait: float = 4.0
) -> list[str]:
    """Blast a temperature query across a subnet and collect the answers.

    Only a device that knows the IQtronic enterprise OID replies, so this
    identifies GIOM stations specifically rather than "something on port 80".
    """
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError as exc:
        print(f"  Not a valid range: {exc}")
        return []

    hosts = list(net.hosts())
    print("=" * 72)
    print(f"SCAN  {net}  ({len(hosts)} addresses, community={community})")
    print("=" * 72)
    if len(hosts) > 4096:
        print("  Range too large, use /20 or smaller.")
        return []

    sock = _udp_socket(0.5)
    sent = 0
    for host in hosts:
        for idx, prefix in enumerate(PREFIXES):
            try:
                sock.sendto(
                    build_get(f"{prefix}.15.14.0", community, idx + 1),
                    (str(host), port),
                )
                sent += 1
            except OSError:
                pass

    print(f"  Sent {sent} queries, listening for {wait:.0f}s ...\n")

    found: dict[str, str] = {}
    quiet = 0
    while quiet < int(wait / 0.5):
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            quiet += 1
            continue
        except OSError:
            continue
        value, _ = parse_response(data)
        if value is not None and addr[0] not in found:
            found[addr[0]] = value
            print(f"  FOUND  {addr[0]:<16} temperature = {value}")
    sock.close()

    print()
    if not found:
        print("  Nothing answered. Check that:")
        print("    - you are actually on that network")
        print("    - SNMP is enabled on the station (its net.html page)")
        print("    - the community string matches (--community)")
        print("    - the range is right")
    else:
        print(f"  Stations found: {len(found)}")
        for ip in found:
            print(f"    python tools/probe.py {ip}")
    return list(found)


# --------------------------------------------------------------------------
# Single-station probe
# --------------------------------------------------------------------------


def probe_snmp(host: str, community: str, port: int) -> str | None:
    """Work out the OID prefix, then read every known value."""
    print("=" * 72)
    print(f"SNMP  (v1, community={community}, port={port})")
    print("=" * 72)

    working = None
    for prefix in PREFIXES:
        value, err = snmp_get(host, f"{prefix}.15.14.0", community, port)
        print(f"  prefix {prefix:<22} -> {value if value is not None else f'-- {err} --'}")
        if value is not None and working is None:
            working = prefix

    if working is None:
        print("\n  No prefix answered.")
        print("  Is SNMP enabled on the station? Does the community match?")
        print("  Is UDP/161 reachable from here?")
        return None

    print(f"\n  USE PREFIX: {working}\n")
    print(f"  {'value':<26} {'reading':<12} {'OID':<30} unit")
    print("  " + "-" * 74)

    request_id = 100
    for suffix, label, unit in OIDS:
        request_id += 1
        oid = f"{working}.{suffix}.0"
        value, err = snmp_get(host, oid, community, port, request_id=request_id)
        print(f"  {label:<26} {value if value is not None else f'({err})':<12} {oid:<30} {unit}")

    return working


def probe_http(host: str, http_port: int) -> None:
    """Look for status.xml and report its content type."""
    print("\n" + "=" * 72)
    print(f"HTTP  (port {http_port})")
    print("=" * 72)

    found: list[tuple[str, str]] = []
    for path in HTTP_PATHS:
        url = f"http://{_url_host(host)}:{http_port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                ctype = response.headers.get("Content-Type", "?")
                body = response.read(1200).decode("utf-8", "replace")
                print(f"  {path:<16} {response.status}  [{ctype}]")
                if "<status" in body or "<windspeed" in body:
                    found.append((path, ctype))
                    print("      ^^^ looks like the XML status file")
                print(f"      {' '.join(body.split())[:300]}")
        except urllib.error.HTTPError as exc:
            print(f"  {path:<16} {exc.code}")
        except Exception as exc:  # noqa: BLE001 - a probe wants to see anything
            print(f"  {path:<16} error: {exc}")

    print()
    if found:
        for path, ctype in found:
            print(f"  XML STATUS: http://{_url_host(host)}:{http_port}{path}  ({ctype})")
            if "xml" not in ctype.lower():
                print("      NOTE: content type is not XML, so Home Assistant's REST")
                print("      integration will not parse it. Use SNMP instead.")
    else:
        print("  No XML status file. Use SNMP.")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Probe a GIOM weather station")
    parser.add_argument("host", nargs="?", help="station address, e.g. 192.168.0.100")
    parser.add_argument("--scan", metavar="CIDR", help="search a subnet, e.g. 192.168.0.0/24")
    parser.add_argument("--community", default="public", help="SNMP community (default: public)")
    parser.add_argument("--snmp-port", type=int, default=161)
    parser.add_argument("--http-port", type=int, default=80)
    parser.add_argument("--skip-http", action="store_true")
    parser.add_argument("--wait", type=float, default=4.0, help="seconds to listen while scanning")
    args = parser.parse_args()

    print()

    if args.scan:
        found = scan_subnet(args.scan, args.community, args.snmp_port, args.wait)
        if not args.host:
            if len(found) == 1:
                args.host = found[0]
                print("\n  One station found, continuing with it.")
            else:
                return 0 if found else 1

    if not args.host:
        parser.error("give a station address, or --scan a subnet")

    print(f"\nGIOM probe -> {args.host}\n")

    prefix = probe_snmp(args.host, args.community, args.snmp_port)
    if not args.skip_http:
        probe_http(args.host, args.http_port)

    print("\n" + "=" * 72)
    if prefix:
        print(f"Station reachable. OID prefix in use: {prefix}")
        if not prefix.startswith("0."):
            print("Unusual - this hardware normally answers only on the 0.-prefixed form.")
    else:
        print("SNMP did not answer; see the notes above.")
    print("=" * 72)
    return 0 if prefix else 1


if __name__ == "__main__":
    sys.exit(main())

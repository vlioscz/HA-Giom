# GIOM weather station — Home Assistant integration

[![hacs][hacs-badge]][hacs-url]
[![validate][validate-badge]][validate-url]
[![license][license-badge]](LICENSE)

Home Assistant integration for **GIOM** Ethernet weather stations, made by
[Mikrovlny s.r.o.][mikrovlny] and also sold through ELKO EP as part of the
iNELS range.

Local polling only — no cloud, no account, nothing leaves your network.

## Supported hardware

| Model | Status |
|---|---|
| GIOM 3000 / 3000AE | ✅ verified on firmware 1.0.3 |
| GIOM 4000NG / IQWS-4000 | 🟡 expected to work — [reports welcome][issues] |

The 4000 series shares the same interface: its manual states *"M2M protocol
compatibility with previous model GIOM 3000"*, and both models serve the same
`status.xml`. The integration reads whatever the station reports and creates
entities only for the values actually present, so a 3000 simply ends up with
fewer sensors than a 4000.

> Despite the iNELS branding on the box, these stations are standalone
> Ethernet devices. They need no iNELS bus, no Connection Server and no
> gateway.

## What you get

One device with up to nineteen sensors, all with proper device classes and
long-term statistics.

| Sensor | Unit | Source |
|---|---|---|
| Temperature | °C | HTTP |
| Dew point | °C | HTTP |
| Wind chill | °C | HTTP |
| Humidity | % | HTTP |
| Absolute humidity | g/m³ | HTTP |
| Pressure *(relative, QNH)* | hPa | HTTP |
| Wind speed | m/s | HTTP |
| Wind gust | m/s | HTTP |
| Wind bearing | ° | HTTP |
| Wind direction | N…NNW | derived |
| Beaufort force | Bft | derived |
| Barometric altitude | m | HTTP, diagnostic |
| Electronics temperature | °C | HTTP, diagnostic |
| Average wind speed | m/s | SNMP |
| Absolute pressure | hPa | SNMP, diagnostic |
| Sunlight intensity | W/m² | HTTP, 4000 only |
| UV factor | — | HTTP, 4000 only |
| Lightning distance | km | HTTP, 4000 only |
| Lightning energy | — | HTTP, 4000 only |

Readings come from a single HTTP request to `status.xml`. Two values that file
does not carry are fetched over SNMP; that is detected automatically during
setup and can be switched off later. SNMP failures never take the HTTP
readings down with them.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories**
2. Add `https://github.com/vlioscz/HA-Giom`, category **Integration**
3. Install **GIOM weather station**, then restart Home Assistant
4. **Settings → Devices & services → Add integration → GIOM**

### Manual

Copy `custom_components/giom` into your `config/custom_components/` directory
and restart Home Assistant.

## Configuration

Everything happens in the UI. You are asked for the station's address — an IP
or hostname, IPv6 in square brackets — and optionally the SNMP community
string, which defaults to `public`.

Options you can change later:

| Option | Default | Notes |
|---|---|---|
| Polling interval | 30 s | 10–3600 s |
| Read extra values over SNMP | auto-detected | Needs SNMP enabled on the station |
| SNMP community | `public` | Only used when SNMP is on |

## Things worth knowing

**Pressure is relative, not absolute.** The `pressure` value is QNH,
recomputed by the station for the altitude set in its own web interface
(*Device configuration → Altitude*). If that altitude is wrong, the reading is
offset. Verified by experiment: changing the configured altitude moved
`pressure` by ~15 hPa while the barometer's actual reading stayed put. The
absolute figure is available as a separate sensor when SNMP is enabled.

**Wind gust is not a rolling window.** The station reports the maximum since
the previous read and then resets. At a 30-second interval you get the maximum
over the last 30 seconds.

**Mount the station facing magnetic north**, otherwise wind direction is
meaningless.

**SNMP OIDs carry a leading zero.** This hardware answers on
`0.1.3.6.1.4.1.21287.15.x.0`; the conventional form without the zero returns
`noSuchName`. It looks like a typo in the manufacturer's manual, but it is
real — worth knowing if you query the station with your own tools.

**If you set a password on the station**, tick the *Except → status.xml*
checkbox in its network configuration, or this integration loses access.

## Protocol reference

For anyone building their own tooling, `status.xml` is served on port 80 with
`Content-Type: text/xml`:

```xml
<status>
  <windspeed>0.8</windspeed>      <winddir>3</winddir>
  <windgust>0.8</windgust>        <pressure>997.7</pressure>
  <systemp>45.8</systemp>         <temperature>30.5</temperature>
  <baraltitude>407.0</baraltitude><windchill>30.5</windchill>
  <relhumidity>57.0</relhumidity> <abshumidity>17.6</abshumidity>
  <dewpoint>21.0</dewpoint>       <devname>GIOM 3000AE</devname>
</status>
```

`winddir` is an index 0–15 on a 16-point compass rose, not a bearing —
degrees are `winddir × 22.5`, with 0 pointing north. The 4000 series adds
`spower`, `uf`, `stime`, `sdist`, `senr` and `lpd`.

SNMP v1, prefix `0.1.3.6.1.4.1.21287.15.`, suffix `.0`:

| OID | Value | | OID | Value |
|---|---|---|---|---|
| `.1` | Barometric altitude | | `.12` | Relative humidity |
| `.2` | Absolute pressure | | `.13` | Dew point |
| `.3` | Relative pressure (QNH) | | `.14` | Temperature |
| `.4` | Wind speed | | `.15` | Wind chill |
| `.5` | Wind gust | | `.16` | Absolute humidity g/m³ |
| `.6` | Average wind speed | | `.17` | Absolute humidity g/kg |
| `.7` | Wind direction index | | `.18` | Device name |
| `.8` | Wind direction text | | `.19`–`.23` | Light, UV, lightning *(4000)* |
| `.9` | Wind direction degrees | | | |
| `.10` | Beaufort | | | |
| `.11` | Saturated steam pressure | | | |

On a GIOM 3000AE the labels in `.8` are mangled — `NEE` for index 3, `NWW`
for index 13, where `ENE` and `WNW` are meant. `.11` does vary, but its
readings match neither saturated vapour pressure for the reported temperature
nor any consistent scaling of it. This integration uses neither OID; wind
direction is derived from the index instead.

## Without HACS, without a custom component

If you would rather not install anything, [`yaml-package/giom.yaml`](yaml-package/giom.yaml)
does most of the same job with the built-in `rest` and `snmp` integrations.
You lose the UI setup, the device grouping and the automatic model detection.

## Česky

Integrace pro meteostanice GIOM. Instalace přes HACS jako vlastní repozitář,
pak **Nastavení → Zařízení a služby → Přidat integraci → GIOM**. Zadáš adresu
stanice a hotovo — zbytek se rozpozná sám, včetně toho, jestli má stanice
zapnuté SNMP.

Rozhraní je česky. Za pozornost stojí, že údaj *Tlak* je přepočtený na
nadmořskou výšku nastavenou ve stanici, ne to, co barometr naměřil — pokud ji
tam nemáš správně, hodnota je posunutá. Absolutní tlak je samostatný senzor,
dostupný při zapnutém SNMP.

## Development

Hardware findings, design rationale and what is still unverified are written up
in [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

`tools/probe.py` finds a station on the network and dumps every value it
exposes. It needs no dependencies, so it also runs inside a Home Assistant
terminal add-on:

```bash
python tools/probe.py --scan 192.168.0.0/24
python tools/probe.py 192.168.0.100
```

## Disclaimer

Not affiliated with, endorsed by or supported by Mikrovlny s.r.o. or ELKO EP.
Device names are trademarks of their respective owners.

[mikrovlny]: https://www.mikrovlny.cz/
[issues]: https://github.com/vlioscz/HA-Giom/issues
[hacs-badge]: https://img.shields.io/badge/HACS-custom-41BDF5.svg
[hacs-url]: https://hacs.xyz/
[validate-badge]: https://github.com/vlioscz/HA-Giom/actions/workflows/validate.yml/badge.svg
[validate-url]: https://github.com/vlioscz/HA-Giom/actions/workflows/validate.yml
[license-badge]: https://img.shields.io/badge/license-MIT-blue.svg

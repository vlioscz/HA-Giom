# Development notes

Everything a future session needs that the code itself does not say: what was
measured against real hardware, what is still guesswork, why the design looks
the way it does, and what is left to do.

Written after the initial release. Firmware under test: **GIOM 3000AE, 1.0.3**.

---

## Picking up on another machine

```bash
git clone https://github.com/vlioscz/HA-Giom
cd HA-Giom
```

That is the whole setup. The integration declares no requirements, so there is
nothing to install to read or edit it.

Two optional extras:

| Task | Needs |
|---|---|
| Re-render brand assets | Pillow, plus Arial Black (`C:\Windows\Fonts\ariblk.ttf`) |
| Probe a station | nothing — `tools/probe.py` is pure stdlib |

The station's address lives nowhere in this repository, on purpose. It is
entered in the Home Assistant UI and stored in `.storage`. If you need it on a
new machine, read it off the station or scan for it:

```bash
python tools/probe.py --scan 192.168.0.0/24
```

### What CI checks

`.github/workflows/validate.yml` runs **hassfest** (manifest, translations,
structure), the **HACS action** (repository layout, brands) and **pytest**
over `tests/`. All must stay green; the HACS brands check in particular is
what the bundled `custom_components/giom/brand/` assets exist to satisfy.

To run the tests locally:

```bash
pip install -r requirements-test.txt
pytest
```

`pytest-homeassistant-custom-component` pulls in a matching Home Assistant, so
the first install is large. The fixtures in `tests/fixtures/` are the
reference `status.xml` documents — one 3000-series, one 4000-series — that
lock in the entity-from-payload behaviour.

---

## Verified vs assumed

Be careful not to present the second column as fact.

| Claim | Status |
|---|---|
| `status.xml` served with `Content-Type: text/xml` | ✅ measured |
| SNMP answers only on the `0.`-prefixed OID tree | ✅ measured |
| `<pressure>` is relative (QNH), not absolute | ✅ measured, see below |
| `winddir` is an index 0–15, degrees = `× 22.5` | ✅ measured against OID `.9` |
| Values use a decimal point on fw 1.0.3 | ✅ measured |
| OIDs `.19`–`.23` absent on a GIOM 3000 | ✅ measured (`noSuchName`) |
| GIOM 4000 / IQWS-4000 works | ✅ verified live on an IQWS-4000 (2026-10) |
| `spower`, `uf`, `sdist`, `senr` field names | ✅ seen live on an IQWS-4000 |
| Web-UI lux = `spower` × 126.7, no light sensor involved | ✅ read from the page source |
| `lpd` = `LD` = lightning strikes per day | ✅ matched live + manufacturer's comment |
| `/data.xml` on the 4000: IAS average, PSS/THS/SSS/TS health flags | ✅ measured live |
| data.xml `PRS` is the relative pressure, not the absolute | ✅ measured (1006.5 vs 952) |
| Beaufort bounds 0.5/1.5/3.3/… strict, north = 360.0° not 0° | ✅ from the web UI source |
| `stime`/`ST`/`systm` are hexadecimal **unix** time | ✅ matched against the clock |
| 4000 XML speeds are always m/s; unit switching is client-side JS | ✅ from the web UI source |
| Config flow behaves in a running Home Assistant | 🟡 covered by tests, never run against real hardware |
| Options flow, reload-on-change | 🟡 covered by tests, never run against real hardware |

The tests in `tests/` exercise the config flow, options flow, setup and
entity creation inside a simulated Home Assistant, but no part of this
integration has been run in a production instance by its author.

---

## Hardware findings

These cost the most to discover and are invisible in the code.

### SNMP OIDs need a leading zero

`0.1.3.6.1.4.1.21287.15.14.0` works. `1.3.6.1.4.1.21287.15.14.0` returns
`noSuchName`. The manufacturer's manual prints the zero-prefixed form, which
reads like a typo but is not. Verified in both directions on real hardware.

### `<pressure>` is QNH, not what the barometer read

The station recomputes pressure for the altitude configured in its own web UI
(*net.html → Altitude[m]*, alongside a gravitational constant and a QNH/QFF
selector).

Proven by accident during development: the altitude was changed from 300 m to
423 m mid-session, and

| | at 300 m | at 423 m |
|---|---|---|
| SNMP absolute `.2` | 961.7 | 962.2 |
| SNMP relative `.3` | 996.8 | 1011.9 |
| XML `<pressure>` | 997.0 | 1011.7 |

`<pressure>` tracked the relative figure while the absolute one stayed put.
That is why the absolute reading is an SNMP-only sensor: `status.xml` has no
field for it.

Consequence for users: a wrong altitude silently offsets the pressure sensor.

### Wind direction is an index

`<winddir>` is 0–15 on a 16-point rose, not a bearing. Confirmed twice against
OID `.9`, which reports proper degrees:

| index | `.9` says |
|---|---|
| 3 | 67.5° |
| 10 | 225.0° |
| 13 | 292.5° |

So `degrees = index × 22.5`, north at zero. The station's web UI picks arrow
images `img/ar0.gif` … `ar15.gif`, which is how the 16-point rose was
established — `ar16.gif` is a 404.

### Two OIDs not to trust

- **`.8`, wind direction as text**, mangles the labels: `NEE` for index 3 and
  `NWW` for index 13, where `ENE` and `WNW` are meant. The integration derives
  the compass point from the index instead. The 4000's web UI uses the same
  firmware table (`NEE`/`EES`/`SWW`/`NWW` for indices 3/5/11/13), so this is
  a manufacturer-wide quirk, not an SNMP bug — expect the station page to
  show different letters than Home Assistant for those four directions.
- **`.11`, "saturated steam pressure"**, varies but does not match saturated
  vapour pressure for the reported temperature, nor any consistent scale of it
  (2501.5 at 30.6 °C, 1880.1 at 28.8 °C, where the physical values are about
  44 and 40 hPa). Unused, and unexplained.

### Wind gust resets on read

`<windgust>` is the maximum since the previous query, not a rolling window.
The polling interval therefore *is* the gust window.

### Other small traps

- `<devname>` comes back padded with trailing spaces — `"GIOM 3000AE    "`.
- Setting a login password on the station hides `status.xml` unless the
  *Except → status.xml* checkbox in `net.html` is ticked.
- Firmware 1.0.3 uses a decimal point, but the parser still tolerates a comma;
  a Czech-locale build was reported on older units and it costs nothing to
  handle.
- Speed units are switchable between m/s and km/h in the station. The
  integration assumes **m/s** and does not read the setting back. If someone
  reports wind speeds that are 3.6× too high, that is why.

---

## Design decisions

### HTTP first, SNMP only for the gaps

`status.xml` covers the core readings in a single request; on the 4000
series a second GET to `data.xml` adds the average wind speed and the
sensor-health flags. That leaves *absolute pressure* as the only reading
that still needs SNMP (plus the wind average on stations without data.xml).
SNMP is probed once during setup, can be switched off in options, and the
redundant wind-average request is skipped whenever data.xml supplied it.

**SNMP failure must never fail the update.** `_async_fetch_snmp` swallows
`SnmpError` and returns an empty dict, so the HTTP readings survive a station
with SNMP switched off mid-life. It warns on the 1st and 10th consecutive
failure only, to avoid filling the log.

### No third-party requirements

`manifest.json` has an empty `requirements` list, and it should stay that way.
The SNMP client in `snmp.py` is hand-assembled BER — roughly 150 lines to
avoid depending on a full SNMP stack for two OIDs. It is blocking and runs via
`async_add_executor_job`.

If SNMP ever grows beyond a couple of OIDs, revisit that trade — but weigh it
against how often SNMP libraries break on Home Assistant upgrades.

### Entities come from the payload, not from a model table

`sensor.py` creates an entity only when its `source_key` appeared in the first
poll. That is what lets one codebase serve a GIOM 3000 and a 4000 without
branching on model strings, and it is why the 4000-only fields can ship
unverified: on hardware that does not report them, nothing is created.

The trade-off: a station that is briefly unhealthy at setup time could come up
with sensors missing until the entry is reloaded.

### Device name is deliberately shortened

Home Assistant composes entity names as `<device> <entity>`. Using the raw
`devname` produced *"GIOM 3000AE Temperature"* everywhere, which pushes the
useful half out of narrow columns.

`device_title()` collapses a factory model string to `GIOM` but keeps a name
the owner actually chose in the station's web UI. The full text stays visible
as the device model.

### Privacy

The station address and SNMP community are treated as secrets:

- never written to a file in this repository
- `diagnostics.py` redacts both, since diagnostics get pasted into issues
- the YAML alternative pulls them from `secrets.yaml`

---

## Repository layout

```
custom_components/giom/     the integration
  snmp.py                   stdlib SNMPv1 client, no dependencies
  coordinator.py            polling, XML parsing, pure helpers
  config_flow.py            setup and options
  sensor.py                 entity descriptions
  brand/                    what HACS displays
brands/                     icon sources + make_icons.py
tests/                      pytest suite, fixtures in tests/fixtures/
tools/probe.py              standalone diagnostic, runs anywhere
yaml-package/               the no-custom-component alternative
docs/DEVELOPMENT.md         this file
```

`brands/*.png` and `custom_components/giom/brand/*.png` are the same images.
Re-run `python brands/make_icons.py` and copy them across after a design
change; `brands/README.md` says so too.

---

## Open items

**Confirm the config flow on real hardware.** Highest priority — it is the
only significant path never executed. Watch for: the duplicate-host abort, the
SNMP auto-probe verdict, and whether the entry title comes out as `GIOM`.

**Read the 3000's speed-unit setting** rather than assuming m/s. On the
4000 this is settled: the XML always carries m/s and the unit switch lives
purely in the web UI's JavaScript. Whether the 3000's firmware behaves the
same is still unverified.

**Health-flag failure codes are unknown.** The four status fields read `OK`
on a healthy station and are passed through verbatim; what a broken sensor
sends has never been observed (the station's own JS just prints it as-is).
When a report with a failure code arrives, consider mapping the flags to
binary sensors.

**`systm`** (the station's own clock, hex unix time in data.xml) is the only
field left unimplemented — useful at most for detecting clock drift.

### The data.xml endpoint (4000 series)

Besides `status.xml`, the 4000 series serves `/data.xml` — the endpoint its
own web UI actually polls (a GIOM 3000 has no such endpoint; the integration
treats it like SNMP, a bonus that never fails the update). Short keys, same
readings, plus four things `status.xml` does not have, measured live on an
IQWS-4000 (fixtures in `tests/fixtures/`):

| status.xml | data.xml | note |
|---|---|---|
| windspeed | IWS | |
| — | **IAS** | **average wind speed — no SNMP needed for it anymore** |
| windgust / winddir | WG / WD | |
| pressure | PRS | relative (QNH) — the absolute value stays SNMP-only |
| temperature / relhumidity / abshumidity | TM / RH / AH | |
| windchill / dewpoint | WC / DP | |
| baraltitude / systemp | BA / systp | |
| spower / uf | SP / UF | |
| stime / sdist / senr | ST / SD / SE | |
| lpd | LD | **lightning strikes per day** (manufacturer's comment) |
| — | systm | system time, UTC hex |
| — | **PSS THS SSS TS** | **sensor-health flags**, free text, `OK` when healthy |

The health flags (pressure, temperature/humidity, light, lightning) are how
a dead sensor is told apart from a genuine zero — exposed as diagnostic
sensors, passed through verbatim since the failure codes are unknown.

**The web UI's lux is `spower` × 126.7** — a coefficient hard-wired in the
page (`get lux(){ return +(this.value * 126.7).toFixed(2); }`), no light
sensor involved. The Illuminance sensor derives its value the same way.
`lpd` looked like lux at low sun (53 vs 50.7) — it is not; it is the daily
strike counter, now its own sensor.

**HACS default submission** is done — [hacs/default#9780](https://github.com/hacs/default/pull/9780),
awaiting a maintainer. No PR to home-assistant/brands was needed: the in-repo
`custom_components/giom/brand/` assets satisfy the HACS brand check.

### Releasing

Bump `version` in `custom_components/giom/manifest.json`, commit, push. HACS
reads GitHub releases, so cut a tag and a release when the version changes —
that is what users' HACS update prompts key off.

---

## Reference

- [iqws4000-protocol.md](iqws4000-protocol.md) — both endpoints, every field
  with the manufacturer's own comments, and the exact unit-conversion
  coefficients, extracted live from an IQWS-4000 (fw 2.0.3) and its web UI
  source. The authoritative companion to this file for the 4000 series.
- [IQWS-4000 manual (PDF)](http://www.iqtronic.com/wp-content/uploads/2021/07/IQWS4000_manual_en.pdf)
  — the successor's manual, source of the OID map, the XML field list and the
  M2M compatibility claim. The most useful document that exists; the GIOM 3000's
  own manual is far thinner.
- [ELKO EP product page](https://www.elkoep.com/-giom-3000)
- [Mikrovlny s.r.o.](https://www.mikrovlny.cz/) — the actual manufacturer

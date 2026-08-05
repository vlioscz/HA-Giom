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
structure) and the **HACS action** (repository layout, brands). Both must stay
green; the HACS brands check in particular is what the bundled
`custom_components/giom/brand/` assets exist to satisfy.

There are no unit tests yet — see *Open items*.

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
| GIOM 4000 / IQWS-4000 works | 🟡 from the manufacturer's manual only |
| `spower`, `uf`, `sdist`, `senr` field names | 🟡 from the manual, never seen live |
| Config flow behaves in a running Home Assistant | 🟡 **never executed** |
| Options flow, reload-on-change | 🟡 **never executed** |

The last two matter most. Everything in `coordinator.py` was exercised against
a live station by extracting the pure functions and calling them directly, but
no part of this integration has been run inside Home Assistant by its author.

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
  the compass point from the index instead.
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

### One HTTP poll, SNMP only for the gaps

`status.xml` covers eleven readings in a single request. Only *average wind
speed* and *absolute pressure* need SNMP, so SNMP is a top-up rather than the
transport. It is probed once during setup and can be switched off in options.

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

**Add tests.** `parse_status`, `beaufort`, `device_title`, `status_url` and the
BER encoder in `snmp.py` are all pure and trivially testable. A fixture pair of
`status.xml` documents — one 3000, one 4000 — would lock in the
entity-from-payload behaviour.

**Find a 4000-series unit.** Would move four sensors and the compatibility
claim from assumed to verified.

**Read the station's speed-unit setting** rather than assuming m/s.

**Consider `stime` and `lpd`.** Both appear in the 4000's XML; `stime` is a
lightning timestamp documented as "UTC hex" and `lpd` is unexplained. Neither
is implemented.

**Submitting to HACS default** would need a PR to
[home-assistant/brands](https://github.com/home-assistant/brands). The files in
`brands/` are already the right sizes.

### Releasing

Bump `version` in `custom_components/giom/manifest.json`, commit, push. HACS
reads GitHub releases, so cut a tag and a release when the version changes —
that is what users' HACS update prompts key off.

---

## Reference

- [IQWS-4000 manual (PDF)](http://www.iqtronic.com/wp-content/uploads/2021/07/IQWS4000_manual_en.pdf)
  — the successor's manual, source of the OID map, the XML field list and the
  M2M compatibility claim. The most useful document that exists; the GIOM 3000's
  own manual is far thinner.
- [ELKO EP product page](https://www.elkoep.com/-giom-3000)
- [Mikrovlny s.r.o.](https://www.mikrovlny.cz/) — the actual manufacturer

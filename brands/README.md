# Brand assets

`make_icons.py` renders the icon and logo PNGs directly into
`custom_components/giom/brand/` — the in-tree copy HACS reads, and the only
place they exist (the HACS maintainers asked for the former duplicates in
this directory to go). It needs Pillow and Arial Black, so it is a
Windows-oriented convenience script rather than part of the build:

```bash
python brands/make_icons.py
```

The design follows the other vlios.cz integrations — a red wordmark above
`vlios.cz` — with the shutter slats swapped for the quantities this station
measures: wind speed, temperature, humidity, pressure, gusts and direction.

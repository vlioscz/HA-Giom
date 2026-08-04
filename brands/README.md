# Brand assets

Source of the icon and logo used by HACS, and the files to submit to the
[Home Assistant brands repository][brands] should this integration ever be
added to the default HACS list.

`make_icons.py` renders all four PNGs. It needs Pillow and Arial Black, so it
is a Windows-oriented convenience script rather than part of the build:

```bash
python brands/make_icons.py
```

The design follows the other vlios.cz integrations — a red wordmark above
`vlios.cz` — with the shutter slats swapped for the quantities this station
measures: wind speed, temperature, humidity, pressure, gusts and direction.

The rendered copies under `custom_components/giom/brand/` are what HACS reads.
Re-run the script and copy them across if the design changes.

[brands]: https://github.com/home-assistant/brands

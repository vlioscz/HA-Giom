# IQWS 4000 — co stanice posílá a jak to přepočítává její web

Vytěženo 2026-10-08 přímo ze živé stanice (firmware **v2.0.3**) a z jejího
javascriptu `res/e727e.js`. Komentáře u klíčů jsou **původní, od výrobce** (česky, včetně
jeho překlepů). Slouží jako podklad pro integraci `vlioscz/HA-Giom`.

## Dva různé endpointy

| | `/status.xml` | `/data.xml` |
|---|---|---|
| názvy | dlouhé (`windspeed`) | krátké (`IWS`) |
| čte to | integrace HA, M2M | **web stanice** |
| stavy čidel | **nejsou** | **jsou** |
| průměrná rychlost větru | **není** | **je** (`IAS`) |

**Stavy čidel a průměrná rychlost větru jsou jen v `data.xml`.** Kvůli průměrné rychlosti
dřív integrace sahala na SNMP — z `data.xml` ji dostane obyčejným HTTP GETem.
**Absolutní tlak tím ale nevyřešíš:** `PRS` (1006,5) odpovídá `pressure` ze `status.xml`,
kdežto absolutní je 952. Ten na SNMP zůstává.

## Klíče v `data.xml`

| klíč | třída | komentář výrobce |
|---|---|---|
| `IWS` | Speed | rychlost vetru aktualni m/s |
| `IAS` | Speed | rychlost prumer m/s |
| `WG` | Speed | naraz m/s |
| `WD` | Direction | smer 16 stupnu |
| `PSS` | Textual | **stav sensoru tlaku** |
| `PRS` | Pressure | tlak v Hpa |
| `BA` | Length | nadmořská výška v m |
| `THS` | Textual | **stav sensoru teploty a vlhkosti** |
| `TM` | Temperature | teplota v deg C |
| `RH` | Numeric | relativni vlkost v % |
| `AH` | Numeric | abolutni g/m3 |
| `DP` | Temperature | rozny bod deg C |
| `WC` | Temperature | windchil deg C |
| `SSS` | Textual | **statu sensoru svetla** |
| `SP` | Lighting | solar power W/m2 |
| `UF` | Numeric | uv factor |
| `TS` | Textual | **stav sensoru blesku** |
| `ST` | Time | cas (posilano v UCT ticksem 0x00000000) |
| `SD` | Numeric | vzdalenost v km |
| `SE` | Numeric | energie bezrozmerna |
| `LD` | Numeric | pocet blesku |
| `devname`, `systp`, `systm` | | jméno, teplota elektroniky, systémový čas |

Stavy čidel vracejí **text**; při měření 2026-10-08 měly všechny čtyři `OK`.
**Co vracejí při poruše, nevíme** — javascript hodnotu jen vypíše, jak přijde,
a prázdnou nebo `N/A` nahradí textem `N/A`.

## Přepočty jednotek (přesné koeficienty z JS)

**Speed** — základ m/s
`kmh = v × 3,6` · `mph = v × 2,236936` · `knots = v × 1,943844` · `fts = v × 3,280839`

**Beaufort** (horní meze v m/s, ostře menší)
`0,5 → 0` · `1,5 → 1` · `3,3 → 2` · `5,5 → 3` · `7,9 → 4` · `10,7 → 5` · `13,8 → 6`
`17,1 → 7` · `20,7 → 8` · `24,4 → 9` · `28,4 → 10` · `32,6 → 11` · výš → 12

**Pressure** — základ hPa
`kpa = v / 10` · `bar = v / 1000` · `psi = v × 0,014504` · `mmhg = tor = v × 0,750062`
· `inchhg = v × 0,029530`

**Temperature** — základ °C
`f = v × 1,8 + 32` · `k = v + 273,15` · `de = (100 − v) × 1,5` · `n = v × 0,33`
· `r = (v + 273,15) × 1,8`

**Length** — základ m
`km = v / 1000` · `mile = v / 1609,344` · `feet = v × 3,2808399`

**Lighting** — základ W/m²
`lux = v × 126,7`

> 🔴 **Lux není druhé čidlo.** Web ukazuje `SP` dvakrát — jednou ve W/m², jednou
> přenásobené 126,7. V dešti je tedy nula v obou jednotkách. Na detekci soumraku
> se proto nedá spolehnout; spolehlivější je poloha slunce, kterou HA počítá.

**Time** — hexadecimální unixový čas, např. `0x6AC7C278`. JS přijímá řetězec i číslo.

Všechny přepočty web zaokrouhluje na **dvě desetinná místa** (`toFixed(2)`).

## Směr větru — index 0–15

| idx | ° | stanice | správně |
|---|---|---|---|
| 0 | 360,0 | N | N |
| 1 | 22,5 | NNE | NNE |
| 2 | 45,0 | NE | NE |
| 3 | 67,5 | **NEE** | ENE |
| 4 | 90,0 | E | E |
| 5 | 112,5 | **EES** | ESE |
| 6 | 135,0 | SE | SE |
| 7 | 157,5 | SSE | SSE |
| 8 | 180,0 | S | S |
| 9 | 202,5 | SSW | SSW |
| 10 | 225,0 | SW | SW |
| 11 | 247,5 | **SWW** | WSW |
| 12 | 270,0 | W | W |
| 13 | 292,5 | **NWW** | WNW |
| 14 | 315,0 | NW | NW |
| 15 | 337,5 | NNW | NNW |

> **Čtyři zkratky má stanice po svém.** U indexů 3, 5, 11 a 13 používá `NEE`, `EES`,
> `SWW`, `NWW` místo standardních `ENE`, `ESE`, `WSW`, `WNW`. **Stupně jsou shodné**,
> liší se jen popisek. Integrace má správné názvy a měnit se nemají — jen ať nikoho
> nepřekvapí, že web stanice ukazuje jiná písmena.
> Pozor i na to, že **index 0 vrací 360,0°, ne 0°**.

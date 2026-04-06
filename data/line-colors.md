# Couleurs des lignes de métro

Source of truth for line colors. Edit the **Google Calendar** column to override the auto-computed nearest-palette color.

> The script currently computes the Google Calendar color automatically via `_nearest_google_color()`.
> Manual overrides are not yet wired in — edit this file and update `METRO_LINE_COLORS` / `_nearest_google_color` in `scripts/fetch.py` accordingly.

## Mapping RATP → Google Calendar

| Ligne | RATP (iCal) | Texte | Google Calendar | Palette name |
|-------|-------------|-------|-----------------|--------------|
| M1 | `#FFCD00` | `#000000` | `#ffad46` | Mango |
| M2 | `#003CA6` | `#FFFFFF` | `#4986e7` | Blueberry |
| M3 | `#837902` | `#FFFFFF` | `#ac725e` | Cocoa |
| M3B | `#6EC4E8` | `#000000` | `#9fc6e7` | Cobalt |
| M4 | `#CF009E` | `#FFFFFF` | `#d06b64` | Flamingo |
| M5 | `#FF7E2E` | `#000000` | `#ff7537` | Pumpkin |
| M6 | `#6ECA97` | `#000000` | `#42d692` | Eucalyptus |
| M7 | `#FA9ABA` | `#000000` | `#f691b2` | Cherry Blossom |
| M7B | `#83C491` | `#000000` | `#92e1c0` | Sage |
| M8 | `#E19BDF` | `#000000` | `#cd74e6` | Grape |
| M9 | `#B6BD00` | `#000000` | `#7bd148` | Pistachio |
| M10 | `#C9910D` | `#000000` | `#ff7537` | Pumpkin |
| M11 | `#704B1C` | `#FFFFFF` | `#ac725e` | Cocoa |
| M12 | `#007852` | `#FFFFFF` | `#16a765` | Basil |
| M13 | `#98D4E2` | `#000000` | `#9fe1e7` | Peacock |
| M14 | `#62259D` | `#FFFFFF` | `#ac725e` | Cocoa |

## Google Calendar palette

| Name | Hex |
|------|-----|
| Amethyst | `#a47ae2` |
| Avocado | `#b3dc6c` |
| Banana | `#fad165` |
| Basil | `#16a765` |
| Beetroot | `#cca6ac` |
| Birch | `#cabdbf` |
| Blueberry | `#4986e7` |
| Cherry Blossom | `#f691b2` |
| Citron | `#fbe983` |
| Cobalt | `#9fc6e7` |
| Cocoa | `#ac725e` |
| Eucalyptus | `#42d692` |
| Flamingo | `#d06b64` |
| Grape | `#cd74e6` |
| Graphite | `#c2c2c2` |
| Lavender | `#9a9cff` |
| Mango | `#ffad46` |
| Peacock | `#9fe1e7` |
| Pistachio | `#7bd148` |
| Pumpkin | `#ff7537` |
| Sage | `#92e1c0` |
| Tangerine | `#fa573c` |
| Tomato | `#f83a22` |
| Wisteria | `#b99aff` |

## Travaux métro — 04-04-2026

**Lignes concernées :** 6

| Ligne | Perturbations |
|-------|--------------|
| ![M3](https://img.shields.io/badge/M3-837902?style=flat-square) | 1 |
| ![M3B](https://img.shields.io/badge/M3B-6EC4E8?style=flat-square) | 3 |
| ![M4](https://img.shields.io/badge/M4-CF009E?style=flat-square) | 1 |
| ![M12](https://img.shields.io/badge/M12-007852?style=flat-square) | 3 |
| ![M13](https://img.shields.io/badge/M13-98D4E2?style=flat-square) | 9 |
| ![M14](https://img.shields.io/badge/M14-62259D?style=flat-square) | 1 |

---

#### ![M3](https://img.shields.io/badge/M3-837902?style=flat-square) Ligne 3
- Métro 3 : Travaux - Trafic interrompu (08-04-2026 → 13-05-2026)

#### ![M3B](https://img.shields.io/badge/M3B-6EC4E8?style=flat-square) Ligne 3B
- Métro 3B : Travaux - Trafic interrompu (12-04-2026 → 11-05-2026)
- Métro 3B : Travaux - Trafic interrompu (16-05-2026 → 22-05-2026)
- Métro 3B : Travaux - Trafic interrompu (16-05-2026 → 22-05-2026)

#### ![M4](https://img.shields.io/badge/M4-CF009E?style=flat-square) Ligne 4
- Métro 4 : Travaux d'entretien - Trafic interrompu (20-04-2026 → 02-05-2026)

#### ![M12](https://img.shields.io/badge/M12-007852?style=flat-square) Ligne 12
- Métro 12 : Travaux de modernisation - Autre (09-03-2026 → 13-04-2026)
- Métro 12 : Travaux de modernisation - Trafic interrompu (01-04-2026 → 09-04-2026)
- Métro 12 : Travaux de modernisation - Trafic interrompu (05-04-2026 → 13-04-2026)

#### ![M13](https://img.shields.io/badge/M13-98D4E2?style=flat-square) Ligne 13
- Métro 13 : Travaux - Trafic interrompu (03-05-2026 → 03-05-2026)
- Métro 13 : Travaux - Trafic interrompu (28-06-2026 → 28-06-2026)
- Métro 13 : Travaux de modernisation - Arrêt non desservi (09-04-2026 → 13-04-2026)
- Métro 13 : Travaux - Trafic interrompu (07-06-2026 → 07-06-2026)
- Métro 13 : Travaux - Trafic interrompu (17-05-2026 → 17-05-2026)
- Métro 13 : Travaux - Trafic interrompu (28-06-2026 → 28-06-2026)
- Métro 13 : Travaux - Trafic interrompu (07-06-2026 → 07-06-2026)
- Métro 13 : Travaux - Trafic interrompu (03-05-2026 → 03-05-2026)
- Métro 13 : Travaux - Trafic interrompu (17-05-2026 → 17-05-2026)

#### ![M14](https://img.shields.io/badge/M14-62259D?style=flat-square) Ligne 14
- Métro 14 : Travaux de modernisation - Trafic interrompu (05-04-2026 → 05-04-2026)

---
**Source :** [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)

```bash
curl -s -H "apikey: $PRIM_TOKEN" \
  "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2" \
  | jq '[.disruptions[] | select(.cause == "TRAVAUX")]'
```
## Travaux métro — 04-04-2026

**Lignes concernées :** 6

| Ligne | Perturbations |
|-------|--------------|
| M3 | 1 |
| M3B | 3 |
| M4 | 1 |
| M12 | 3 |
| M13 | 9 |
| M14 | 1 |

---

#### Ligne 3
- Métro 3 : Travaux - Trafic interrompu (08-04-2026 → 13-05-2026)

#### Ligne 3B
- Métro 3B : Travaux - Trafic interrompu (12-04-2026 → 11-05-2026)
- Métro 3B : Travaux - Trafic interrompu (16-05-2026 → 22-05-2026)
- Métro 3B : Travaux - Trafic interrompu (16-05-2026 → 22-05-2026)

#### Ligne 4
- Métro 4 : Travaux d'entretien - Trafic interrompu (20-04-2026 → 02-05-2026)

#### Ligne 12
- Métro 12 : Travaux de modernisation - Trafic interrompu (05-04-2026 → 13-04-2026)
- Métro 12 : Travaux de modernisation - Trafic interrompu (01-04-2026 → 09-04-2026)
- Métro 12 : Travaux de modernisation - Autre (09-03-2026 → 13-04-2026)

#### Ligne 13
- Métro 13 : Travaux - Trafic interrompu (03-05-2026 → 03-05-2026)
- Métro 13 : Travaux - Trafic interrompu (07-06-2026 → 07-06-2026)
- Métro 13 : Travaux - Trafic interrompu (03-05-2026 → 03-05-2026)
- Métro 13 : Travaux - Trafic interrompu (17-05-2026 → 17-05-2026)
- Métro 13 : Travaux - Trafic interrompu (28-06-2026 → 28-06-2026)
- Métro 13 : Travaux - Trafic interrompu (17-05-2026 → 17-05-2026)
- Métro 13 : Travaux - Trafic interrompu (28-06-2026 → 28-06-2026)
- Métro 13 : Travaux de modernisation - Arrêt non desservi (09-04-2026 → 13-04-2026)
- Métro 13 : Travaux - Trafic interrompu (07-06-2026 → 07-06-2026)

#### Ligne 14
- Métro 14 : Travaux de modernisation - Trafic interrompu (05-04-2026 → 05-04-2026)

---
**Source :** [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)

```bash
curl -s -H "apikey: $PRIM_TOKEN" \
  "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2" \
  | jq '[.disruptions[] | select(.cause == "TRAVAUX")]'
```
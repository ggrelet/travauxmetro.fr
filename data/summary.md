## Travaux métro — 08-04-2026

### Changements

![M3](https://img.shields.io/badge/-M3-837902?style=flat) +1 -1
![M9](https://img.shields.io/badge/-M9-B6BD00?style=flat) +2

---

**Lignes concernées :** 6

| Ligne | Interruptions |
|-------|--------------|
| ![M3](https://img.shields.io/badge/-M3-837902?style=flat) | 1 |
| ![M3B](https://img.shields.io/badge/-M3B-6EC4E8?style=flat) | 6 |
| ![M4](https://img.shields.io/badge/-M4-CF009E?style=flat) | 1 |
| ![M9](https://img.shields.io/badge/-M9-B6BD00?style=flat) | 2 |
| ![M12](https://img.shields.io/badge/-M12-007852?style=flat) | 3 |
| ![M13](https://img.shields.io/badge/-M13-98D4E2?style=flat) | 5 |

---

#### ![M3](https://img.shields.io/badge/-M3-837902?style=flat)
- **Métro 3 : Travaux - Trafic interrompu** — 08-04-2026 → 13-05-2026
  - 🚉 Porte de Bagnolet, Gallieni, Gambetta
  - Trafic interrompu
  - Jusqu'au 12 mai inclus, le trafic est interrompu entre Gallieni et Gambetta en raison de travaux. Bus de remplacement.

#### ![M3B](https://img.shields.io/badge/-M3B-6EC4E8?style=flat)
- **Métro 3B : Travaux - Trafic interrompu** — 12-04-2026 → 11-05-2026
  - Trafic interrompu
  - Du 12 avril au 10 mai inclus, le dimanche dès 22:15, le trafic sera interrompu sur toute la ligne en raison de travaux.
- **Métro 3B : Travaux - Trafic interrompu** — 16-05-2026 → 22-05-2026
  - Trafic interrompu
  - Du 16 mai au 21 mai inclus, le trafic sera interrompu sur toute la ligne en raison de travaux.

#### ![M4](https://img.shields.io/badge/-M4-CF009E?style=flat)
- **Métro 4 : Travaux d'entretien - Trafic interrompu** — 20-04-2026 → 02-05-2026
  - Trafic interrompu
  - Du 20 avril au 1er mai inclus, le trafic sera interrompu entre Châtelet et Barbès - Rochechouart en raison de travaux d'entretien.

#### ![M9](https://img.shields.io/badge/-M9-B6BD00?style=flat)
- **Alma - Marceau / Iéna / Saint-Philippe-du-Roule : Rallongement de durée de chantier - Station fermée (sans correspondances)** — 08-04-2026 → 08-04-2026
  - 🚉 Saint-Philippe-du-Roule, Alma - Marceau, Iéna
  - Station fermée (sans correspondances)
  - Les accès aux stations Alma – Marceau, Iéna et Saint-Philippe-du-Roule sont fermés en raison d'un rallongement de durée de chantier
- **Métro 9 : Rallongement de durée de chantier - Trafic perturbé** — 08-04-2026 → 09-04-2026
  - Trafic perturbé
  - Le trafic est perturbé sur toute la ligne en répercussion d'un rallongement de durée de chantier .

#### ![M12](https://img.shields.io/badge/-M12-007852?style=flat)
- **Métro 12 : Travaux de modernisation - Trafic interrompu** — 08-04-2026 → 09-04-2026
  - Trafic interrompu
  - Jusqu'au 8 avril, le mercredi dès 22:00, le trafic est interrompu sur toute la ligne en raison de travaux de modernisation.
- **Métro 12 : Travaux de modernisation - Trafic interrompu** — 05-04-2026 → 13-04-2026
  - Trafic interrompu
  - Jusqu'au 12 avril inclus, le dimanche dès 22:00, le trafic est interrompu sur toute la ligne en raison de travaux de modernisation.

#### ![M13](https://img.shields.io/badge/-M13-98D4E2?style=flat)
- **Métro 13 : Travaux - Trafic interrompu** — 03-05-2026 → 03-05-2026
  - Trafic interrompu
  - Les dimanches 3 et 17 mai ainsi que les 7 et 28 juin, jusqu'à 12 heures, le trafic est interrompu sur l'ensemble de la ligne en raison de travaux de modernisation.
- **Métro 13 : Travaux de modernisation - Arrêt non desservi** — 09-04-2026 → 13-04-2026
  - 🚉 Plaisance
  - Arrêt non desservi
  - Du 9 avril au 12 avril inclus, l'arrêt ne sera pas desservi à Plaisance en raison de travaux de modernisation
- **Métro 13 : Travaux - Trafic interrompu** — 28-06-2026 → 28-06-2026
  - Trafic interrompu
  - Le 28 juin jusqu'à 12:00, le trafic sera interrompu sur toute la ligne en raison de travaux.
- **Métro 13 : Travaux - Trafic interrompu** — 17-05-2026 → 17-05-2026
  - Trafic interrompu
  - Le dimanche 17 mai ainsi que les 7 et 28 juin, jusqu'à 12 heures, le trafic est interrompu sur l'ensemble de la ligne en raison de travaux de modernisation.
- **Métro 13 : Travaux - Trafic interrompu** — 07-06-2026 → 07-06-2026
  - Trafic interrompu
  - Les dimanches 7 et 28 juin, jusqu'à 12 heures, le trafic est interrompu sur l'ensemble de la ligne en raison de travaux de modernisation.

---
**Source :** [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)

```bash
curl -s -H "apikey: $PRIM_TOKEN" \
  "https://prim.iledefrance-mobilites.fr/marketplace/disruptions_bulk/disruptions/v2" \
  | jq '[.disruptions[] | select(.cause == "TRAVAUX")]'
```
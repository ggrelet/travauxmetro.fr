# Travaux Métro Paris

Calendriers ICS des travaux planifiés sur le réseau métro parisien, mis à jour quotidiennement.

**Site :** https://ggrelet.github.io/travaux-metro

## Utilisation

Copiez l'URL du calendrier souhaité et abonnez-vous depuis votre application (Google Calendar, Apple Calendar, Outlook…) :

| Calendrier | URL |
|------------|-----|
| Toutes les lignes | `https://ggrelet.github.io/travaux-metro/all.ics` |
| Ligne X | `https://ggrelet.github.io/travaux-metro/ligne-X.ics` |

## Fonctionnement

- Source : [Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk)
- Un workflow GitHub Actions tourne chaque jour à 05h00 UTC
- Si les données changent, une PR est ouverte automatiquement pour validation avant mise en ligne

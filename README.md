# `travauxmetro.fr`

[iCalendar](https://fr.wikipedia.org/wiki/ICalendar) des travaux planifiés sur le réseau de métro parisien, mis à jour quotidiennement.

## Utilisation

Abonnez-vous depuis votre appli de calendrier préférée (Google Calendar, Apple Calendar, Outlook…).  
Les calendriers sont mis à jour quotidiennement s'il y a du neuf côté API.
Votre application de calendrier, elle, les synchronise automatiquement.

## Fonctionnement

1. Une GitHub Actions s'exécute chaque jour à 05h00
2. Elle récupère les données d'API [PRIM d'Île-de-France Mobilités](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk) : interruptions de type `TRAVAUX` sur le réseau métro/RER
3. Si les données ont changé, une PR est ouverte automatiquement
4. Suite au merge, les calendriers et la page d'accueil sont regénérés et déployés

## Stack technique

| Composant | Tech stack |
|-----------|-------------|
| ICS and static site| Python / Jinja |
| Refresh API | GitHub Actions |
| Hosting | GitHub Pages |
| DNS and proxy | Cloudflare |

## Source des données

[Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk) — API publique des interruptions en temps réel.

## Format

Les calendriers utilisent le protocole [iCalendar](https://fr.wikipedia.org/wiki/ICalendar) (RFC 5545), servis avec l'extension `.ics`, utilisable avec la plupart des applications de calendrier (mobile/desktop).

## Vibe-coding

Autant être transparent : le projet a été en grande partie développé avec **Claude Sonnet 4.6 et Opus 4.6**.

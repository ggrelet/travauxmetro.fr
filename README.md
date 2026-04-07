# Travaux Métro Paris

Calendriers [iCalendar](https://fr.wikipedia.org/wiki/ICalendar) des travaux planifiés sur le réseau métro parisien, mis à jour quotidiennement.

**Site :** https://travauxmetro.fr

## Utilisation

Abonnez-vous depuis votre application de calendrier (Google Calendar, Apple Calendar, Outlook…) :

| Calendrier | URL |
|------------|-----|
| Toutes les lignes | `https://travauxmetro.fr/tousmetros.ics` |
| Ligne X | `https://travauxmetro.fr/ligne-X.ics` |

Les calendriers sont mis à jour quotidiennement et votre application les synchronise automatiquement.

## Fonctionnement

1. Un workflow GitHub Actions s'exécute chaque jour à 05h00 UTC
2. Il interroge l'API [PRIM d'Île-de-France Mobilités](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk) pour récupérer les interruptions de type `TRAVAUX` sur le réseau métro
3. Si les données ont changé, une Pull Request est ouverte automatiquement pour validation avant mise en ligne
4. Au merge, les calendriers et la page d'accueil sont regénérés et déployés

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Génération des calendriers et du HTML | Python ([`scripts/fetch.py`](scripts/fetch.py)) |
| Automatisation | GitHub Actions |
| Hébergement | GitHub Pages |
| DNS & proxy | Cloudflare |
| Serveur de développement local | Python ([`scripts/serve.py`](scripts/serve.py)) |

## Développement local

Requiert [uv](https://github.com/astral-sh/uv) et un token PRIM.

```bash
# Récupérer les données et regénérer la page et les calendriers
PRIM_TOKEN=xxx uv run python scripts/fetch.py

# Serveur local avec rechargement automatique (utilise le dernier snapshot)
uv run python scripts/serve.py
```

## Source des données

[Île-de-France Mobilités — PRIM](https://prim.iledefrance-mobilites.fr/en/apis/idfm-disruptions_bulk) — API publique des interruptions en temps réel.

## Format

Les calendriers utilisent le protocole [iCalendar](https://fr.wikipedia.org/wiki/ICalendar) (RFC 5545), servis avec l'extension `.ics`, reconnue par l'ensemble des applications de calendrier.

## Développé avec Claude

L'ensemble du projet — scripts Python, workflows GitHub Actions, page web et infrastructure — a été développé en collaboration avec [Claude](https://claude.ai) (Anthropic), via [Claude Code](https://claude.ai/code).

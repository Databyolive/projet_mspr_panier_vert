# Panier Vert – Collecte et fouille de données (MSPR 5.1)

Chaîne de valeur data pour Panier Vert (réseau de 42 épiceries bio) : collecte automatisée de
4 sources, stockage Parquet, puis (jalons suivants) qualité, mining, MLOps et dashboard.
Ce dépôt correspond au **jalon J1 (tag `j1-collecte`)** : cadrage, architecture, collecte v1.

Architecture : voir [`docs/architecture.md`](docs/architecture.md) · Conformité : [`docs/conformite.md`](docs/conformite.md)

## Sources

| # | Source | Accès | Sortie brute |
|---|---|---|---|
| 1 | Instacart Market Basket (historique reconstitué) | CSV fournis | `data/raw/instacart/*.parquet` |
| 2 | Open Food Facts (ODbL) | API REST | `data/raw/openfoodfacts/products_AAAAMMJJ.parquet` |
| 3 | RappelConso V2 | API open data | `data/raw/rappelconso/rappelconso.parquet` (incrémental) |
| 4 | ecologie.gouv.fr, alimentation et agriculture durables (scraping, Licence Ouverte 2.0) | HTML | `data/raw/scraping/articles_AAAAMMJJ.parquet` |

Données issues d'Open Food Facts, licence ODbL – https://world.openfoodfacts.org
Contenus issus de ecologie.gouv.fr, Licence Ouverte 2.0 (Etalab) : source et date de mise à jour conservées.

## Démarrage rapide (relancer la collecte en une commande)

Prérequis : Python 3.10+.

```bash
git clone <url-du-depot> && cd panier-vert
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
make install                                           # ou : pip install -e ".[dev]"
cp .env.example .env                                   # renseigner CONTACT_EMAIL
# Déposer les CSV Instacart fournis dans data/external/instacart/
make collect                                           # collecte des 4 sources
```

Sans les CSV Instacart, `make sample` génère un mini jeu synthétique de même schéma.
`make smoke` lance un test rapide (quelques pages, sortie isolée dans `data/raw/_smoke`).
Une seule source : `python -m panier_vert.run_collect --sources rappelconso`.

Chaque exécution écrit un rapport `data/raw/_runs/run_*.json` (statut, lignes, durée par source).
Le code de sortie est non nul si une source échoue.

## Fiabilité de la collecte

- **Rate limiting** : intervalle minimal entre requêtes, réglé par source (`config/sources.yaml`).
- **Retries** : 5 tentatives, backoff exponentiel, sur erreurs réseau, 429 et 5xx (en-tête `Retry-After` respecté). Les erreurs 4xx ne sont pas retentées.
- **Logs** : console + `logs/collect.log` (rotation) ; alertes dans `logs/alerts.jsonl` et, si `ALERT_WEBHOOK_URL` est défini, vers un webhook.
- **Parquet atomique** : écriture dans un fichier temporaire puis renommage ; brut (`data/raw`) séparé du nettoyé (`data/clean`).
- **Incrémental** : RappelConso ne rajoute que les rappels dont l'identifiant est inconnu (état dans `_state.json`).

## Planification quotidienne (RappelConso)

Exemple cron dans [`scripts/crontab.example`](scripts/crontab.example) (`make collect-rappelconso`).
La centralisation de la planification (orchestrateur ou GitHub Actions + stockage persistant DVC) arrive aux jalons suivants.

## Structure

```
config/sources.yaml     paramètres des sources (URLs, débit, pagination)
src/panier_vert/        collecteurs (instacart, openfoodfacts, rappelconso, scraping), common, run_collect
tests/                  tests unitaires (retries, débit, incrémental, robots.txt, schéma)
docs/                   architecture et registre de conformité
scripts/                échantillon Instacart, exemple cron
data/{external,raw,clean}  données (non versionnées dans Git)
```

## Conformité

Aucune donnée personnelle n'est collectée par scraping ; `robots.txt` est vérifié avant chaque URL ; identifiants clients pseudonymisés ; aucun secret dans Git. Détails dans `docs/conformite.md`.

## À valider avant la première collecte réelle

- Cible de scraping (ecologie.gouv.fr) : relever son `robots.txt`, relire les mentions légales, ajuster `link_selector` / `content_selector` et `allowed_path_prefixes` dans `config/sources.yaml`, puis renseigner `docs/conformite.md`.
- Noms de champs RappelConso (`id_field`, `date_field`) : à confirmer sur la fiche du jeu `rappelconso-v2-gtin-trie` ; le code lève une erreur explicite si le schéma diffère.
- Paramètres de l'API Open Food Facts (`countries_tags_en`) : vérifier sur la documentation officielle.

## Limites connues (J1)

- Instacart n'a pas de code-barres : l'appariement avec Open Food Facts (par nom/catégorie) est traité au jalon J2.
- RappelConso V2 ne couvre que les produits avec GTIN.
- Nettoyage, contrôles qualité, mining, MLOps et dashboard : jalons J2 à J4.

## Tag Git du jalon

```bash
git add -A && git commit -m "J1 : cadrage et collecte v1"
git tag j1-collecte && git push origin main --tags
```

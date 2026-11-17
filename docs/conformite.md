# Registre de conformité des sources

Relevé effectué le **17/11/2026**, avant la collecte complète. Les pièces justificatives (copies du
`robots.txt` et des mentions légales) sont archivées dans ce dossier `docs/`.

| Source | Licence / conditions | Données personnelles | robots.txt / CGU | Attribution | Vérifié par / le |
|---|---|---|---|---|---|
| Instacart (CSV Kaggle fournis par l'encadrant) | Jeu public, usage pédagogique ; conditions Kaggle à citer | Identifiants clients déjà pseudonymisés ; aucune ré-identification tentée | n/a (fichiers fournis) | Citer Instacart / Kaggle | [Prénom Nom], 17/11/2026 |
| Open Food Facts | Base : ODbL (attribution + partage à l'identique). Contenus : DbCL. Images : CC BY-SA (**non collectées**) | Aucune | API publique ; User-Agent personnalisé, limite documentée de 10 requêtes/min respectée | « Données Open Food Facts, licence ODbL » (dashboard et README) | [Prénom Nom], 17/11/2026 |
| RappelConso (V2, jeu `rappelconso-v2-gtin-trie`) | Données ouvertes data.economie.gouv.fr ; licence à confirmer sur la fiche du jeu | Colonne `numero_contact` (téléphone du fabricant ou distributeur) : supprimée au nettoyage | API open data | Citer DGCCRF / data.economie.gouv.fr | [Prénom Nom], 17/11/2026 |
| ecologie.gouv.fr (alimentation et agriculture durables) | Licence Ouverte Etalab 2.0, sauf mention de propriété intellectuelle de tiers | Aucune donnée personnelle conservée (voir ci-dessous) | robots.txt relevé le 17/11/2026 ; mentions légales relevées le 17/11/2026 | « Source : ministères Écologie Énergie Territoires (ecologie.gouv.fr), Licence Ouverte 2.0 » + date de mise à jour | [Prénom Nom], 17/11/2026 |

## Relevé ecologie.gouv.fr (17/11/2026)

- **Licence** (page « Mentions légales ») : contenus sous licence ouverte Etalab 2.0, sauf mention explicite de propriété intellectuelle de tiers. Reproduction, extraction et réutilisation autorisées sous réserve de mentionner la source, la date de dernière mise à jour et de ne pas induire en erreur. Le scraper collecte la date de mise à jour, à défaut la date de publication, à défaut la date de collecte (colonnes `date_reference` et `date_reference_type`) ; le dashboard affichera la source.
- **robots.txt** : un seul bloc `User-agent: *`, aucune règle sur `/politiques-publiques/` ni `/dossiers/`. Interdits respectés : `/recherche*`, `/ressources*`, `/search`, `/core/`, `/profiles/`, `/admin/`, et toute URL contenant `?type`, `?theme`, `?sort`, `?order`, `?region`, `q=`, `keys=` ou `field_*_tref`. Pas de `Crawl-delay` : délai de 3 s appliqué par politesse. Le vérificateur du code gère les jokers (tests unitaires).
- **Données personnelles** : le scraper ne collecte ni auteur ni image ; la rubrique `/presse/` est exclue ; les blocs « Contacts presse » sont écartés ; e-mails et téléphones sont remplacés avant stockage. Les noms d'institutions ou de responsables publics cités dans un texte éditorial restent présents : informations publiques liées à leur fonction. Limite à mentionner dans le dossier.
- **Photographies** : les mentions légales indiquent des sources variées ; aucune image n'est collectée.
- **Pièces archivées** : `docs/robots_ecologie_gouv_2026-11-17.txt` et `docs/mentions_legales_ecologie_gouv_2026-11-17.txt`.

## Points d'attention (à reprendre dans le dossier)

- **ODbL et partage à l'identique** : si une base dérivée croisant Open Food Facts avec d'autres données est publiée, elle doit rester ouverte. Notre usage reste interne et pédagogique, ce qui est à préciser.
- **Open Food Facts** : l'API de recherche s'arrête à 1 000 résultats sans authentification (10 pages de 100). Volume limité en v1 ; piste d'évolution : export officiel pour le catalogue complet.
- **RappelConso** : une ligne par produit rappelé (clé `id` + `gtin`), pas une ligne par rappel.

## Sources écartées

- **Agence Bio** : le `robots.txt` est permissif, mais la charte d'utilisation du site soumet à autorisation l'extraction systématique de contenu. Source non retenue faute d'autorisation.
- **ADEME** : réutilisation des communiqués non interdite, mais aucune licence ouverte explicite trouvée. Source non retenue ; son `robots.txt` (jokers, deux blocs `User-agent: *`) a servi à renforcer le vérificateur du code.

## Règles appliquées dans le code

- `robots.txt` interrogé avant chaque URL scrapée ; fichier illisible = abstention.
- User-Agent identifiable avec contact (`CONTACT_EMAIL`) ; délai entre requêtes configurable par source.
- Aucune clé ni mot de passe dans Git (`.env` ignoré, `.env.example` fourni).
- Traitements et stockages en France ou dans l'UE (poste local).

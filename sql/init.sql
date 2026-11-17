-- Exécuté une seule fois, à la création du volume PostgreSQL.
CREATE SCHEMA IF NOT EXISTS staging;   -- données nettoyées
CREATE SCHEMA IF NOT EXISTS mart;      -- tables prêtes pour la modélisation et le reporting
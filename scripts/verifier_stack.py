"""Vérifie que RustFS et PostgreSQL répondent : python scripts/verifier_stack.py"""
import time

import psycopg2

from panier_vert import lake, settings

lake.creer_bucket()
print("RustFS OK :", lake.client_s3().list_buckets()["Buckets"][0]["Name"])

derniere_erreur = None
for _ in range(15):
    try:
        with psycopg2.connect(host=settings.PG_HOST, port=settings.PG_PORT, dbname=settings.PG_DB,
                              user=settings.PG_USER, password=settings.PG_PASSWORD) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT schema_name FROM information_schema.schemata "
                            "WHERE schema_name IN ('staging','mart')")
                print("PostgreSQL OK, schémas :", sorted(r[0] for r in cur.fetchall()))
        break
    except (psycopg2.OperationalError, UnicodeDecodeError) as e:
        derniere_erreur = type(e).__name__
        time.sleep(2)
else:
    raise SystemExit(f"PostgreSQL ne répond pas ({derniere_erreur}). "
                     "Vérifier : docker compose ps (état healthy) et docker compose logs postgres")
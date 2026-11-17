"""Crée data/sample/ : petit échantillon commitable de chaque Parquet brut.

Le jeu complet (Instacart : ~35 M de lignes) ne va pas dans Git ; il se régénère avec
`python -m panier_vert.run_collect`. L'échantillon Instacart est cohérent : il garde toutes
les commandes et tous les paniers d'un petit groupe de clients (pas un tirage de lignes isolées).

Usage : python scripts/make_sample_raw.py [--users 500]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from panier_vert.common import ROOT

RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "sample"


def latest(folder: Path, pattern: str) -> Path:
    files = sorted(folder.glob(pattern))
    if not files:
        raise FileNotFoundError(f"Aucun fichier {pattern} dans {folder} : lancer la collecte d'abord.")
    return files[-1]


def write(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="snappy")
    print(f"  {path.relative_to(ROOT)} : {table.num_rows} lignes, {path.stat().st_size / 1e6:.2f} Mo")


def sample_instacart(n_users: int) -> None:
    print("Instacart")
    src = RAW / "instacart"
    for name in ("aisles", "departments", "products"):
        write(pq.read_table(src / f"{name}.parquet"), OUT / "instacart" / f"{name}.parquet")
    orders = pq.read_table(src / "orders.parquet")
    users = pc.unique(orders["user_id"]).sort()[:n_users]
    orders = orders.filter(pc.is_in(orders["user_id"], value_set=users))
    write(orders, OUT / "instacart" / "orders.parquet")
    order_ids = orders["order_id"]
    for name in ("order_products__prior", "order_products__train"):
        table = ds.dataset(src / f"{name}.parquet").to_table(
            filter=ds.field("order_id").isin(order_ids.to_pylist()))
        write(table, OUT / "instacart" / f"{name}.parquet")


def sample_head(folder: str, pattern: str, n: int, sort_desc: str | None = None) -> None:
    print(folder)
    table = pq.read_table(latest(RAW / folder, pattern))
    if sort_desc:
        table = table.sort_by([(sort_desc, "descending")])
    write(table.slice(0, n), OUT / folder / f"{folder}_sample.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=500, help="clients Instacart conservés")
    args = parser.parse_args()
    sample_instacart(args.users)
    sample_head("openfoodfacts", "products_*.parquet", 200)
    sample_head("rappelconso", "rappelconso.parquet", 500, sort_desc="date_publication")
    sample_head("scraping", "articles_*.parquet", 50)
    print(f"Échantillon écrit dans {OUT}")


if __name__ == "__main__":
    main()

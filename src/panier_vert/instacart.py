"""Source 1 : historique de commandes Instacart (CSV fournis) -> Parquet brut, en flux."""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .common import ROOT, log, raw_dir

_ORDER_PRODUCTS = {"order_id": pa.int64(), "product_id": pa.int64(),
                   "add_to_cart_order": pa.int32(), "reordered": pa.int8()}

SCHEMAS = {
    "aisles": {"aisle_id": pa.int32(), "aisle": pa.string()},
    "departments": {"department_id": pa.int32(), "department": pa.string()},
    "products": {"product_id": pa.int64(), "product_name": pa.string(),
                 "aisle_id": pa.int32(), "department_id": pa.int32()},
    "orders": {"order_id": pa.int64(), "user_id": pa.int64(), "eval_set": pa.string(),
               "order_number": pa.int32(), "order_dow": pa.int8(),
               "order_hour_of_day": pa.int8(), "days_since_prior_order": pa.float64()},
    "order_products__prior": _ORDER_PRODUCTS,
    "order_products__train": _ORDER_PRODUCTS,
}


def convert_file(src: Path, dst: Path, column_types: dict) -> int:
    """Convertit un CSV en Parquet par blocs (mémoire constante, même pour ~32 M de lignes)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    reader = pacsv.open_csv(src, convert_options=pacsv.ConvertOptions(column_types=column_types))
    writer, rows = None, 0
    try:
        for batch in reader:
            if writer is None:
                writer = pq.ParquetWriter(tmp, batch.schema, compression="snappy")
            writer.write_batch(batch)
            rows += batch.num_rows
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise ValueError(f"CSV vide : {src}")
    tmp.replace(dst)
    return rows


def collect(cfg: dict, smoke: bool = False) -> dict:
    input_dir = ROOT / cfg["instacart"]["input_dir"]
    missing = [n for n in SCHEMAS if not (input_dir / f"{n}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"CSV Instacart manquants dans {input_dir} : {missing}. "
            "Déposer les fichiers fournis par l'encadrant (ou lancer `make sample`).")
    out_dir = raw_dir(smoke) / "instacart"
    total = 0
    for name, types in SCHEMAS.items():
        rows = convert_file(input_dir / f"{name}.csv", out_dir / f"{name}.parquet", types)
        log.info("Instacart %s : %d lignes", name, rows)
        total += rows
    return {"rows": total, "path": str(out_dir)}

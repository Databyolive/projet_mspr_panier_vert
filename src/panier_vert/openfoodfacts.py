"""Source 2 : Open Food Facts (API REST JSON, licence ODbL : citer la source)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from .common import HttpClient, add_metadata, log, raw_dir, send_alert, write_parquet

FIELDS = ["code", "product_name", "brands", "categories_tags", "countries_tags",
          "nutriscore_grade", "nutriscore_score", "ecoscore_grade", "nova_group",
          "ingredients_text", "allergens_tags", "labels_tags", "last_modified_t"]
LIST_COLS = ["categories_tags", "countries_tags", "allergens_tags", "labels_tags"]
TEXT_COLS = ["code", "product_name", "brands", "nutriscore_grade", "ecoscore_grade",
             "ingredients_text"]


def normalise(products: list[dict]) -> pd.DataFrame:
    """Colonnes et types stables d'une exécution à l'autre (Parquet reproductible)."""
    df = pd.DataFrame(products).reindex(columns=FIELDS)
    for col in LIST_COLS:
        df[col] = df[col].map(lambda v: v if isinstance(v, list) else [])
    for col in TEXT_COLS:
        df[col] = df[col].astype("string")
    for col in ["nutriscore_score", "nova_group", "last_modified_t"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset="code").reset_index(drop=True)


def collect(cfg: dict, smoke: bool = False, client: HttpClient | None = None) -> dict:
    c = cfg["openfoodfacts"]
    client = client or HttpClient(min_interval=c.get("min_interval_s", 6.5))
    max_pages = 2 if smoke else c["max_pages"]
    products: list[dict] = []
    partial = False
    for page in range(1, max_pages + 1):
        try:
            resp = client.get(c["base_url"], params={
                "countries_tags_en": c["country_tag"], "fields": ",".join(FIELDS),
                "page_size": c["page_size"], "page": page})
        except requests.RequestException as exc:
            if not products:
                raise
            # L'API limite le débit : on conserve ce qui est déjà collecté plutôt que tout perdre.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            partial = True
            send_alert("Open Food Facts : collecte partielle",
                       f"arrêt à la page {page} (HTTP {status or 'réseau'}) ; "
                       f"{len(products)} produits conservés")
            break
        batch = resp.json().get("products", [])
        log.info("Open Food Facts page %d : %d produits", page, len(batch))
        if not batch:
            break
        products.extend(batch)
    if not products:
        raise RuntimeError("Open Food Facts n'a retourné aucun produit.")
    df = add_metadata(normalise(products), "openfoodfacts")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = write_parquet(df, raw_dir(smoke) / "openfoodfacts" / f"products_{stamp}.parquet")
    return {"rows": len(df), "path": str(path), "partial": partial}
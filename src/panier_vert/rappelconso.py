"""Source 3 : RappelConso V2 (data.economie.gouv.fr). Collecte quotidienne incrémentale."""
from __future__ import annotations

import json

import pandas as pd
import requests

from .common import HttpClient, add_metadata, log, raw_dir, stringify_nested, write_parquet


def _norm(value) -> str:
    """Texte stable d'un run à l'autre (un GTIN lu en float ne doit pas devenir '3.2e+12')."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def row_keys(df: pd.DataFrame, key_fields: list[str]) -> pd.Series:
    """Clé unique d'une ligne = rappel (id) + produit (gtin) : un rappel couvre plusieurs produits."""
    fields = [f for f in key_fields if f in df.columns]
    return df[fields].apply(lambda col: col.map(_norm)).agg("|".join, axis=1)


def _load_state(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def collect(cfg: dict, smoke: bool = False, client: HttpClient | None = None) -> dict:
    c = cfg["rappelconso"]
    client = client or HttpClient(min_interval=c.get("min_interval_s", 1.0))
    out_dir = raw_dir(smoke) / "rappelconso"
    data_path, state_path = out_dir / "rappelconso.parquet", out_dir / "_state.json"
    id_field, date_field = c["id_field"], c["date_field"]
    key_fields = c.get("key_fields", [id_field, "gtin"])

    state = _load_state(state_path)
    existing = pd.read_parquet(data_path) if data_path.exists() else pd.DataFrame()
    known_keys = set(row_keys(existing, key_fields)) if not existing.empty else set()

    url = f"{c['base_url']}/catalog/datasets/{c['dataset']}/exports/json"
    params: dict = {"order_by": f"{date_field} desc"}
    if smoke:
        params["limit"] = 50
    last = state.get("last_date")
    if last:  # >= puis dédoublonnage par identifiant : aucun rappel du jour n'est manqué
        params["where"] = f"{date_field} >= date'{last}'"
    try:
        resp = client.get(url, params=params)
    except requests.HTTPError as exc:
        if "where" not in params:
            raise
        log.warning("Filtre incrémental refusé (%s) : export complet puis filtrage local", exc)
        params.pop("where")
        resp = client.get(url, params=params)

    df = pd.DataFrame(resp.json())
    if df.empty:
        log.info("RappelConso : aucun enregistrement retourné")
        return {"rows": 0, "new_rows": 0, "path": str(data_path)}
    if id_field not in df.columns or date_field not in df.columns:
        raise KeyError(f"Champs {id_field!r}/{date_field!r} absents. Colonnes : {list(df.columns)}"
                       " -> vérifier config/sources.yaml (le schéma du jeu a pu évoluer).")

    keys = row_keys(df, key_fields)
    new = df[~keys.isin(known_keys) & ~keys.duplicated()]
    if new.empty:
        log.info("RappelConso : aucun nouveau rappel")
        return {"rows": len(existing), "new_rows": 0, "path": str(data_path)}

    new = add_metadata(stringify_nested(new), "rappelconso")
    full = pd.concat([existing, new], ignore_index=True) if not existing.empty else new
    write_parquet(full, data_path)
    state["last_date"] = str(full[date_field].dropna().astype(str).max())[:10]
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    log.info("RappelConso : %d nouveaux rappels (total %d)", len(new), len(full))
    return {"rows": len(full), "new_rows": len(new), "path": str(data_path)}
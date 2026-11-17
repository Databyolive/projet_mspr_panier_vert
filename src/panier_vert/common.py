"""Briques communes : configuration, journalisation, client HTTP, Parquet, alertes."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd
import requests
import yaml
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

ROOT = Path(os.getenv("PV_ROOT", Path(__file__).resolve().parents[2]))
LOG_DIR = ROOT / "logs"

log = logging.getLogger("panier_vert")


def setup_logging(level: int = logging.INFO) -> None:
    """Logs console + fichier tournant logs/collect.log (idempotent)."""
    if log.handlers:
        return
    log.setLevel(level)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(console)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fileh = RotatingFileHandler(LOG_DIR / "collect.log", maxBytes=5_000_000, backupCount=3,
                                encoding="utf-8")
    fileh.setFormatter(fmt)
    log.addHandler(fileh)


def load_env(path: Path | None = None) -> None:
    """Charge .env (sans dépendance externe) ; les variables déjà définies sont conservées."""
    env_file = path or ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config" / "sources.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def raw_dir(smoke: bool = False) -> Path:
    """Données brutes. Le mode smoke écrit à part pour ne jamais polluer le brut."""
    return ROOT / "data" / ("raw/_smoke" if smoke else "raw")


def default_user_agent() -> str:
    contact = os.getenv("CONTACT_EMAIL", "contact-non-renseigne")
    return f"PanierVert-MSPR/1.0 (projet pedagogique Sup de Vinci; {contact})"


class TransientHTTPError(requests.RequestException):
    """Erreur temporaire (429, 5xx) : la requête sera retentée."""


class HttpClient:
    """Client HTTP avec limitation de débit, reprises (backoff exponentiel) et logs."""

    def __init__(self, min_interval: float = 1.0, timeout: int = 60, max_attempts: int = 5,
                 retry_wait: float = 2.0, user_agent: str | None = None):
        self.min_interval = min_interval
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or default_user_agent()
        self._last_call: float | None = None
        self._retrying_get = retry(
            retry=retry_if_exception_type(
                (requests.ConnectionError, requests.Timeout, TransientHTTPError)),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=retry_wait, min=retry_wait, max=60),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )(self._get_once)

    def _throttle(self) -> None:
        if self._last_call is not None:  # pas d'attente avant la toute première requête
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
        self._last_call = time.monotonic()

    def _get_once(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        log.debug("GET %s %s", url, kwargs.get("params", ""))
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                time.sleep(min(int(retry_after), 120))
            raise TransientHTTPError(f"HTTP {resp.status_code} sur {url}", response=resp)
        resp.raise_for_status()  # 4xx : erreur définitive, pas de nouvelle tentative
        return resp

    def get(self, url: str, **kwargs) -> requests.Response:
        return self._retrying_get(url, **kwargs)


def stringify_nested(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit listes/dicts en JSON texte (évite les schémas Parquet instables)."""
    out = df.copy()
    for col in out.columns:
        if out[col].map(lambda v: isinstance(v, (list, dict))).any():
            out[col] = out[col].map(
                lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
    return out


def add_metadata(df: pd.DataFrame, source: str) -> pd.DataFrame:
    out = df.copy()
    out["_source"] = source
    out["_ingested_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Écriture atomique (fichier temporaire puis renommage)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False, compression="snappy")
    tmp.replace(path)
    log.info("Parquet écrit : %s (%d lignes)", path, len(df))
    return path


def send_alert(title: str, message: str) -> None:
    """Alerte : log ERROR + logs/alerts.jsonl (+ webhook si ALERT_WEBHOOK_URL est défini)."""
    log.error("ALERTE %s : %s", title, message)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "title": title, "message": message}
    with open(LOG_DIR / "alerts.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    webhook = os.getenv("ALERT_WEBHOOK_URL")
    if webhook:
        try:
            requests.post(webhook, json={"text": f"[Panier Vert] {title} : {message}"}, timeout=10)
        except requests.RequestException as exc:  # l'alerte ne doit jamais faire planter le run
            log.warning("Webhook d'alerte injoignable : %s", exc)

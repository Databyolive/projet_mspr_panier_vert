"""Point d'entrée unique : `python -m panier_vert.run_collect` (ou `make collect`)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from . import instacart, openfoodfacts, rappelconso, scraping
from .common import ROOT, load_config, load_env, log, raw_dir, send_alert, setup_logging

COLLECTORS = {
    "instacart": instacart.collect,
    "openfoodfacts": openfoodfacts.collect,
    "rappelconso": rappelconso.collect,
    "scraping": scraping.collect,
}


def run(sources: list[str], smoke: bool = False) -> dict:
    cfg = load_config()
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "smoke": smoke, "sources": {}}
    for name in sources:
        start = time.monotonic()
        try:
            result = COLLECTORS[name](cfg, smoke=smoke)
            status = "partial" if result.get("partial") else "ok"
            report["sources"][name] = {"status": status, **result,
                                       "duration_s": round(time.monotonic() - start, 1)}
        except Exception as exc:  # noqa: BLE001 - une source en échec ne bloque pas les autres
            log.exception("Source %s en échec", name)
            report["sources"][name] = {"status": "error", "error": str(exc),
                                       "duration_s": round(time.monotonic() - start, 1)}
            send_alert(f"Collecte {name} en échec", str(exc))
    out = raw_dir(smoke) / "_runs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (out / f"run_{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collecte des 4 sources Panier Vert")
    parser.add_argument("--sources", default="all",
                        help=f"all ou liste séparée par des virgules parmi {list(COLLECTORS)}")
    parser.add_argument("--smoke", action="store_true",
                        help="test rapide (peu de pages, sortie dans data/raw/_smoke)")
    args = parser.parse_args(argv)
    load_env()
    setup_logging()
    names = list(COLLECTORS) if args.sources == "all" else args.sources.split(",")
    unknown = [n for n in names if n not in COLLECTORS]
    if unknown:
        parser.error(f"source(s) inconnue(s) : {unknown}")
    log.info("Collecte démarrée (racine %s) : %s", ROOT, names)
    report = run(names, smoke=args.smoke)
    failed = [n for n, r in report["sources"].items() if r["status"] == "error"]
    partial = [n for n, r in report["sources"].items() if r["status"] == "partial"]
    log.info("Collecte terminée : %d ok, %d partielle(s) %s, %d en échec",
             len(names) - len(failed) - len(partial), len(partial), partial, len(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
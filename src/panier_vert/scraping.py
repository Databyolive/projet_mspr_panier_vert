"""Source 4 : scraping d'actualités publiques du secteur bio (aucune donnée personnelle).

Garde-fous : robots.txt vérifié avant CHAQUE URL (avec jokers), User-Agent explicite, délai entre requêtes,
aucun champ d'auteur collecté.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from protego import Protego

from .common import HttpClient, add_metadata, log, raw_dir, write_parquet


class RobotsChecker:
    """Vérifie le robots.txt de chaque hôte (mis en cache), jokers `*` et `$` compris.

    Protego (analyseur de Scrapy) fusionne les blocs `User-agent: *` multiples, ce que
    urllib.robotparser ne fait pas. En cas de doute (fichier illisible), on s'abstient.
    """

    def __init__(self, client: HttpClient):
        self.client = client
        self._cache: dict[str, Protego | None] = {}  # None = aucune restriction

    def _load(self, host: str) -> Protego | None:
        try:
            return Protego.parse(self.client.get(f"{host}/robots.txt").text)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None  # pas de robots.txt : aucune restriction déclarée
        except requests.RequestException:
            pass
        return Protego.parse("User-agent: *\nDisallow: /")  # illisible : abstention

    def allowed(self, url: str) -> bool:
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._cache:
            self._cache[host] = self._load(host)
        rules = self._cache[host]
        return True if rules is None else rules.can_fetch(
            url, self.client.session.headers["User-Agent"])


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:(?:\+|00)33|0)\s?[1-9](?:[\s.-]?\d{2}){4}")
META_RE = re.compile(r"^\s*(publié|mis à jour)\s+le\b", re.IGNORECASE)
CONTACT_RE = re.compile(r"^\s*(contacts?\s+presse|service\s+presse)", re.IGNORECASE)
PUBLISHED_RE = re.compile(r"Publié le\s+(\d{1,2}(?:er)?\s+\w+\s+\d{4})", re.IGNORECASE)
UPDATED_RE = re.compile(r"Mis à jour le\s+(\d{1,2}(?:er)?\s+\w+\s+\d{4})", re.IGNORECASE)


def scrub_personal_data(text: str) -> str:
    """Supprime e-mails et téléphones (minimisation RGPD) avant tout stockage."""
    return PHONE_RE.sub("[tel supprimé]", EMAIL_RE.sub("[email supprimé]", text))


def keep_article(article: dict, min_chars: int = 0, keywords: list[str] | None = None) -> bool:
    """Écarte les pages-thèmes (peu de texte) et les pages hors sujet (mots-clés)."""
    if len(article["text"]) < min_chars:
        return False
    if keywords:
        haystack = f"{article['title'] or ''} {article['text']}".lower()
        return any(k.lower() in haystack for k in keywords)
    return True


def add_reference_date(df: pd.DataFrame) -> pd.DataFrame:
    """Date à citer (Etalab 2.0) : mise à jour, sinon publication, sinon date de collecte."""
    out = df.copy()
    out["date_reference"] = (out["updated"].fillna(out["published_text"])
                             .fillna(out["scraped_at"].str[:10]))
    out["date_reference_type"] = "collecte"
    out.loc[out["published_text"].notna(), "date_reference_type"] = "publication"
    out.loc[out["updated"].notna(), "date_reference_type"] = "mise_a_jour"
    return out


def parse_article(html: str, url: str, content_selector: str) -> dict:
    """Titre, dates et texte uniquement. Jamais d'auteur ; contacts presse écartés."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1")
    time_tag = soup.find("time")
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    published = (time_tag.get("datetime") if time_tag and time_tag.get("datetime")
                 else meta.get("content") if meta else None)
    page_text = soup.get_text(" ", strip=True)
    updated = UPDATED_RE.search(page_text)
    published_text = PUBLISHED_RE.search(page_text)
    paragraphs = [p.get_text(" ", strip=True) for p in soup.select(content_selector)]
    text = "\n".join(scrub_personal_data(p) for p in paragraphs if not CONTACT_RE.match(p) and not META_RE.match(p))
    return {"url": url, "title": title.get_text(strip=True) if title else None,
            "published": published, "updated": updated.group(1) if updated else None,
            "published_text": published_text.group(1) if published_text else None,
            "text": text}


def collect(cfg: dict, smoke: bool = False, client: HttpClient | None = None) -> dict:
    c = cfg["scraping"]
    client = client or HttpClient(min_interval=c.get("min_interval_s", 3.0))
    robots = RobotsChecker(client)
    limit = 3 if smoke else c["max_articles_per_listing"]
    rows: list[dict] = []
    for listing in c["listing_urls"]:
        if not robots.allowed(listing):
            log.warning("robots.txt interdit %s : source ignorée", listing)
            continue
        soup = BeautifulSoup(client.get(listing).text, "html.parser")
        domain = urlparse(listing).netloc
        links = []
        for a in soup.select(c["link_selector"]):
            href = urljoin(listing, a["href"]).split("#")[0]
            parsed = urlparse(href)
            prefixes = c.get("allowed_path_prefixes")
            if prefixes and not parsed.path.startswith(tuple(prefixes)):
                continue
            if parsed.netloc == domain and href != listing and href not in links:
                links.append(href)
        kept = 0
        for url in links[:limit * 4]:  # plafond de requêtes : 4 fois le quota d'articles
            if kept >= limit:
                break
            if not robots.allowed(url):
                log.warning("robots.txt interdit %s : ignoré", url)
                continue
            try:
                article = parse_article(client.get(url).text, url, c["content_selector"])
            except requests.RequestException as exc:
                log.warning("Article ignoré (%s) : %s", url, exc)
                continue
            if keep_article(article, c.get("min_text_chars", 0), c.get("keywords")):
                rows.append(article)
                kept += 1
            else:
                log.info("Page écartée (trop courte ou hors sujet) : %s", url)
    if not rows:
        raise RuntimeError("Scraping : aucun article collecté (cible, sélecteurs ou robots.txt ?)")
    df = pd.DataFrame(rows).drop_duplicates(subset="url")
    df["scraped_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    df = add_reference_date(df)
    # Etalab 2.0 : citer la source et la date de mise à jour
    df["licence"] = c.get("licence", "Licence Ouverte Etalab 2.0")
    df["attribution"] = c.get("attribution", "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = write_parquet(add_metadata(df, "scraping_web"),
                         raw_dir(smoke) / "scraping" / f"articles_{stamp}.parquet")
    return {"rows": len(df), "path": str(path)}
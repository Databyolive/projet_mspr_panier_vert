import json
from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from panier_vert import instacart, openfoodfacts, rappelconso, scraping
from panier_vert.common import HttpClient, TransientHTTPError


def fake_response(status=200, payload=None, text=""):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.headers = {}
    resp.text = text
    resp.json.return_value = payload
    if status >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    for mod in (instacart, rappelconso, openfoodfacts, scraping):
        monkeypatch.setattr(mod, "raw_dir", lambda smoke=False, p=tmp_path: p / "raw", raising=False)
    monkeypatch.setattr(instacart, "ROOT", tmp_path)
    return tmp_path


def test_retry_then_success():
    client = HttpClient(min_interval=0, retry_wait=0, max_attempts=3)
    client.session.get = MagicMock(side_effect=[fake_response(503), fake_response(200)])
    assert client.get("http://x").status_code == 200
    assert client.session.get.call_count == 2


def test_retry_gives_up_after_max_attempts():
    client = HttpClient(min_interval=0, retry_wait=0, max_attempts=2)
    client.session.get = MagicMock(return_value=fake_response(500))
    with pytest.raises(TransientHTTPError):
        client.get("http://x")
    assert client.session.get.call_count == 2


def test_client_error_is_not_retried():
    client = HttpClient(min_interval=0, retry_wait=0, max_attempts=3)
    client.session.get = MagicMock(return_value=fake_response(404))
    with pytest.raises(requests.HTTPError):
        client.get("http://x")
    assert client.session.get.call_count == 1


def test_rate_limit_spaces_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr("panier_vert.common.time.sleep", sleeps.append)
    client = HttpClient(min_interval=5)
    client.session.get = MagicMock(return_value=fake_response(200))
    client.get("http://x")
    client.get("http://x")
    assert len(sleeps) == 1 and sleeps[0] > 4  # 1re requête sans attente, 2e espacée


def test_openfoodfacts_normalise_stable_schema():
    df = openfoodfacts.normalise([{"code": "1", "nova_group": "4"},
                                  {"code": "1"}, {"code": "2", "categories_tags": ["en:milk"]}])
    assert list(df.columns) == openfoodfacts.FIELDS
    assert len(df) == 2 and df.loc[0, "nova_group"] == 4


def test_rappelconso_is_incremental(isolated_root):
    cfg = {"rappelconso": {"base_url": "http://api", "dataset": "d", "id_field": "id",
                           "date_field": "date_publication"}}
    client = MagicMock()
    batch1 = [{"id": "a", "date_publication": "2026-11-10", "x": ["l"]},
              {"id": "b", "date_publication": "2026-11-12", "x": []}]
    client.get.return_value = fake_response(payload=batch1)
    assert rappelconso.collect(cfg, client=client)["new_rows"] == 2
    batch2 = batch1 + [{"id": "c", "date_publication": "2026-11-15", "x": []}]
    client.get.return_value = fake_response(payload=batch2)
    res = rappelconso.collect(cfg, client=client)
    assert res["new_rows"] == 1 and res["rows"] == 3
    assert "where" in client.get.call_args.kwargs["params"]
    assert rappelconso.collect(cfg, client=client)["new_rows"] == 0  # idempotent
    state = json.loads((isolated_root / "raw/rappelconso/_state.json").read_text())
    assert state["last_date"] == "2026-11-15"


def test_instacart_conversion(isolated_root):
    src = isolated_root / "in"
    src.mkdir()
    (src / "orders.csv").write_text(
        "order_id,user_id,eval_set,order_number,order_dow,order_hour_of_day,"
        "days_since_prior_order\n1,1,prior,1,2,8,\n2,1,prior,2,3,9,7.0\n")
    n = instacart.convert_file(src / "orders.csv", isolated_root / "o.parquet",
                               instacart.SCHEMAS["orders"])
    df = pd.read_parquet(isolated_root / "o.parquet")
    assert n == 2 and df["days_since_prior_order"].isna().sum() == 1


def test_instacart_missing_files_message(isolated_root):
    with pytest.raises(FileNotFoundError, match="manquants"):
        instacart.collect({"instacart": {"input_dir": "nope"}})


def test_robots_blocks_disallowed_path():
    client = MagicMock()
    client.session.headers = {"User-Agent": "bot"}
    client.get.return_value = fake_response(text="User-agent: *\nDisallow: /prive/")
    robots = scraping.RobotsChecker(client)
    assert robots.allowed("https://site.fr/actualites/a")
    assert not robots.allowed("https://site.fr/prive/b")


def test_robots_unreadable_means_abstain():
    client = MagicMock()
    client.session.headers = {"User-Agent": "bot"}
    client.get.side_effect = requests.ConnectionError("down")
    assert not scraping.RobotsChecker(client).allowed("https://site.fr/a")


def test_parse_article_has_no_author_field():
    html = ("<main><h1>Titre</h1><time datetime='2026-11-01'></time>"
            "<p>Texte</p><span class='author'>Jean</span></main>")
    art = scraping.parse_article(html, "http://x", "main p")
    assert set(art) == {"url", "title", "published", "updated", "published_text", "text"}
    assert art["text"] == "Texte"


def test_scrub_removes_contacts_and_extracts_update_date():
    html = ("<main><h1>T</h1><p>Mis à jour le 06 février 2025</p><p>Info utile</p>"
            "<p>Contacts presse</p><p>Service presse de X, tél : 01 40 81 78 65</p>"
            "<p>Écrire à presse.mtebnicn@ecologie.gouv.fr ou au 01 40 81 78 65</p></main>")
    art = scraping.parse_article(html, "http://x", "main p")
    assert art["updated"] == "06 février 2025"
    assert "@" not in art["text"] and "01 40" not in art["text"]
    assert "Info utile" in art["text"] and "Service presse" not in art["text"]


ROBOTS_WILDCARDS = """User-agent: *
Disallow: /wp-admin/
Disallow: /*?keywords=

User-agent: *
Disallow: /search/
Disallow: /page/*/?s=
"""


def test_robots_wildcards_and_merged_groups():
    client = MagicMock()
    client.session.headers = {"User-Agent": "PanierVert-MSPR/1.0"}
    client.get.return_value = fake_response(text=ROBOTS_WILDCARDS)
    robots = scraping.RobotsChecker(client)
    assert robots.allowed("https://site.fr/presse/communique")
    assert not robots.allowed("https://site.fr/liste?keywords=bio")   # joker
    assert not robots.allowed("https://site.fr/search/x")             # 2e bloc User-agent: *
    assert not robots.allowed("https://site.fr/page/2/?s=bio")        # joker au milieu


def test_keep_article_filters_hubs_and_off_topic():
    long_food = {"title": "Gaspillage alimentaire", "text": "x" * 600}
    short_hub = {"title": "Mieux produire", "text": "Publié"}
    off_topic = {"title": "Transports", "text": "route " * 200}
    kw = ["alimentaire", "bio"]
    assert scraping.keep_article(long_food, 500, kw)
    assert not scraping.keep_article(short_hub, 500, kw)
    assert not scraping.keep_article(off_topic, 500, kw)


def test_meta_lines_removed_from_text():
    html = "<main><h1>T</h1><p>Publié le 10 mai 2024 Mis à jour le 08 janvier 2026</p><p>Contenu</p></main>"
    art = scraping.parse_article(html, "http://x", "main p")
    assert art["text"] == "Contenu" and art["updated"] == "08 janvier 2026"


def test_rappelconso_keeps_every_product_of_a_recall(isolated_root):
    cfg = {"rappelconso": {"base_url": "http://api", "dataset": "d", "id_field": "id",
                           "date_field": "date_publication"}}
    rows = [{"id": 1, "gtin": 3258561419718, "date_publication": "2026-11-10"},
            {"id": 1, "gtin": 3258561419695, "date_publication": "2026-11-10"},
            {"id": 2, "gtin": None, "date_publication": "2026-11-11"}]
    client = MagicMock()
    client.get.return_value = fake_response(payload=rows)
    assert rappelconso.collect(cfg, client=client)["new_rows"] == 3      # 2 produits du rappel 1
    assert rappelconso.collect(cfg, client=client)["new_rows"] == 0      # relance idempotente
    rows.append({"id": 1, "gtin": 3258561419701, "date_publication": "2026-11-10"})
    assert rappelconso.collect(cfg, client=client)["new_rows"] == 1      # nouveau produit, même rappel


def test_reference_date_fallbacks():
    html_pub = "<main><h1>T</h1><p>Publié le 20 février 2026</p><p>Texte</p></main>"
    art = scraping.parse_article(html_pub, "http://x", "main p")
    assert art["updated"] is None and art["published_text"] == "20 février 2026"
    df = pd.DataFrame([
        {"updated": "08 janvier 2026", "published_text": "10 mai 2024", "scraped_at": "2026-11-17T09:00:00"},
        {"updated": None, "published_text": "20 février 2026", "scraped_at": "2026-11-17T09:00:00"},
        {"updated": None, "published_text": None, "scraped_at": "2026-11-17T09:00:00"},
    ])
    out = scraping.add_reference_date(df)
    assert out["date_reference"].tolist() == ["08 janvier 2026", "20 février 2026", "2026-11-17"]
    assert out["date_reference_type"].tolist() == ["mise_a_jour", "publication", "collecte"]


def test_openfoodfacts_keeps_partial_data_when_blocked(isolated_root, monkeypatch):
    alerts = []
    monkeypatch.setattr(openfoodfacts, "send_alert", lambda t, m: alerts.append((t, m)))
    cfg = {"openfoodfacts": {"base_url": "http://off", "country_tag": "france",
                             "page_size": 2, "max_pages": 5}}
    page = lambda n: fake_response(payload={"products": [
        {"code": f"{n}a", "product_name": "x"}, {"code": f"{n}b", "product_name": "y"}]})
    client = MagicMock()
    client.get.side_effect = [page(1), page(2), fake_http_error(401)]
    res = openfoodfacts.collect(cfg, client=client)
    assert res["partial"] is True and res["rows"] == 4
    assert alerts and "partielle" in alerts[0][0]
    assert len(pd.read_parquet(res["path"])) == 4


def test_openfoodfacts_fails_if_nothing_collected(isolated_root):
    cfg = {"openfoodfacts": {"base_url": "http://off", "country_tag": "france",
                             "page_size": 2, "max_pages": 5}}
    client = MagicMock()
    client.get.side_effect = fake_http_error(401)
    with pytest.raises(requests.HTTPError):
        openfoodfacts.collect(cfg, client=client)


def fake_http_error(status):
    return requests.HTTPError(response=fake_response(status))
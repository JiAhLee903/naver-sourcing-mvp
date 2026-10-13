"""SQLite 저장소: 발견 스토어, 수집 스토어, 상품, 수집 로그."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlsplit

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS discovered_stores (
  id INTEGER PRIMARY KEY, keyword TEXT NOT NULL, store_name TEXT, store_url TEXT,
  source TEXT NOT NULL, product_title TEXT, product_link TEXT, product_type TEXT,
  found_at TEXT NOT NULL, UNIQUE(keyword, store_url)
);
CREATE TABLE IF NOT EXISTS stores (
  id INTEGER PRIMARY KEY, name TEXT, url TEXT NOT NULL UNIQUE, keyword TEXT,
  badge_status TEXT NOT NULL DEFAULT 'unchecked', badge_note TEXT,
  collected_at TEXT NOT NULL, best_status TEXT NOT NULL DEFAULT 'not_collected',
  best_note TEXT, best_updated_at TEXT
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
  name TEXT NOT NULL, url TEXT, price INTEGER, thumb_path TEXT, thumb_url TEXT,
  detail_text TEXT, detail_html_raw TEXT, detail_html_original TEXT, detail_html_edited TEXT,
  rights_confirmed INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL,
  collected_at TEXT NOT NULL, edited_at TEXT, UNIQUE(store_id, url)
);
CREATE TABLE IF NOT EXISTS banned_words (word TEXT PRIMARY KEY, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS blocked_stores (url TEXT PRIMARY KEY, name TEXT, reason TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS crawl_log (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, level TEXT NOT NULL, target TEXT, message TEXT NOT NULL
);
"""

BADGE_LABELS = {"unchecked": "미확인(수동 확인 필요)", "has_badge": "뱃지 있음(제외)",
                "no_badge": "뱃지 없음(대상)", "unknown": "판별 실패(수동 확인)"}
BEST_LABELS = {"not_collected": "미수집", "collected": "수집 완료", "failed": "실패", "partial": "일부 수집"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect():
    config.ensure_dirs()
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


_STORE_HOSTS = {"smartstore.naver.com", "brand.naver.com"}


def normalize_store_url(url: str) -> str:
    """스토어 URL 비교용 정규화: 호스트 소문자, 스마트스토어/브랜드스토어는 첫 경로(스토어명)까지만, 쿼리 제거."""
    u = (url or "").strip()
    if u and "://" not in u:
        u = "https://" + u
    p = urlsplit(u)
    host = p.netloc.lower()
    seg = [x for x in p.path.split("/") if x]
    if host in _STORE_HOSTS and seg:
        return f"https://{host}/{seg[0].lower()}"
    return f"https://{host}{p.path.rstrip('/')}"


def block_store(url: str, name: str = "", reason: str = "") -> bool:
    n = normalize_store_url(url)
    if not urlsplit(n).netloc:
        raise ValueError("올바른 스토어 URL이 아닙니다.")
    with connect() as con:
        return con.execute("INSERT OR IGNORE INTO blocked_stores(url,name,reason,created_at) VALUES(?,?,?,?)",
                           (n, name, reason, now())).rowcount > 0


def unblock_store(url: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM blocked_stores WHERE url=?", (normalize_store_url(url),))


def list_blocked() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute("SELECT * FROM blocked_stores ORDER BY created_at DESC").fetchall()


def is_blocked(url: str | None) -> bool:
    if not url:
        return False
    with connect() as con:
        return con.execute("SELECT 1 FROM blocked_stores WHERE url=?", (normalize_store_url(url),)).fetchone() is not None


def add_banned_word(word: str) -> bool:
    w = word.strip()
    if not w:
        raise ValueError("금지어가 비어 있습니다.")
    with connect() as con:
        return con.execute("INSERT OR IGNORE INTO banned_words(word,created_at) VALUES(?,?)", (w, now())).rowcount > 0


def remove_banned_word(word: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM banned_words WHERE word=?", (word,))


def list_banned_words() -> list[str]:
    with connect() as con:
        return [r["word"] for r in con.execute("SELECT word FROM banned_words ORDER BY created_at")]


def find_banned_word(text: str | None) -> str | None:
    """상품명에 포함된 첫 금지어(대소문자 무시, 부분 일치). 없으면 None."""
    t = (text or "").lower()
    return next((w for w in list_banned_words() if w.lower() in t), None)


def log(level: str, target: str, message: str) -> None:
    with connect() as con:
        con.execute("INSERT INTO crawl_log(at,level,target,message) VALUES(?,?,?,?)", (now(), level, target, message))


def add_discovered(rows: list[dict]) -> int:
    n = 0
    rows = [r for r in rows if not is_blocked(r.get("store_url"))]
    with connect() as con:
        for r in rows:
            cur = con.execute(
                "INSERT OR IGNORE INTO discovered_stores(keyword,store_name,store_url,source,product_title,"
                "product_link,product_type,found_at) VALUES(?,?,?,?,?,?,?,?)",
                (r["keyword"], r.get("store_name"), r.get("store_url"), r["source"], r.get("product_title"),
                 r.get("product_link"), r.get("product_type"), now()))
            n += cur.rowcount
    return n


def list_discovered(keyword: str | None = None) -> list[sqlite3.Row]:
    with connect() as con:
        if keyword:
            rows = con.execute("SELECT * FROM discovered_stores WHERE keyword=? ORDER BY id", (keyword,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM discovered_stores ORDER BY id DESC").fetchall()
    return [r for r in rows if not is_blocked(r["store_url"])]


def collect_store(name: str, url: str, keyword: str, badge_status: str, badge_note: str = "") -> bool:
    """스토어를 저장. 이미 있으면 False(중복 방지), 새로 저장하면 True."""
    if badge_status == "has_badge":
        raise ValueError("뱃지가 있는 스토어는 수집 대상에서 제외됩니다.")
    if is_blocked(url):
        raise ValueError("수집 제외(차단) 스토어입니다.")
    url = normalize_store_url(url)
    with connect() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO stores(name,url,keyword,badge_status,badge_note,collected_at) VALUES(?,?,?,?,?,?)",
            (name, url, keyword, badge_status, badge_note, now()))
        return cur.rowcount > 0


def list_stores() -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute("SELECT s.*, (SELECT COUNT(*) FROM products p WHERE p.store_id=s.id) AS product_count "
                           "FROM stores s ORDER BY s.id DESC").fetchall()


def set_badge(store_id: int, status: str, note: str = "") -> None:
    with connect() as con:
        con.execute("UPDATE stores SET badge_status=?, badge_note=? WHERE id=?", (status, note, store_id))


def set_best_status(store_id: int, status: str, note: str = "") -> None:
    with connect() as con:
        con.execute("UPDATE stores SET best_status=?, best_note=?, best_updated_at=? WHERE id=?",
                    (status, note, now(), store_id))


def upsert_product(store_id: int, p: dict) -> int:
    """(store_id, url) 기준 중복 방지. 기존 편집본은 보존하고 id를 반환."""
    with connect() as con:
        row = con.execute("SELECT id FROM products WHERE store_id=? AND url IS ?", (store_id, p.get("url"))).fetchone()
        if row:
            return row["id"]
        cur = con.execute(
            "INSERT INTO products(store_id,name,url,price,thumb_path,thumb_url,detail_text,detail_html_raw,"
            "detail_html_original,detail_html_edited,rights_confirmed,source,collected_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store_id, p["name"], p.get("url"), p.get("price"), p.get("thumb_path"), p.get("thumb_url"),
             p.get("detail_text"), p.get("detail_html_raw"), p.get("detail_html_original"),
             p.get("detail_html_edited") or p.get("detail_html_original"), int(p.get("rights_confirmed", 0)),
             p["source"], now()))
        return cur.lastrowid


def list_products(store_id: int | None = None) -> list[sqlite3.Row]:
    q = "SELECT p.*, s.name AS store_name, s.url AS store_url FROM products p JOIN stores s ON s.id=p.store_id"
    with connect() as con:
        if store_id:
            return con.execute(q + " WHERE p.store_id=? ORDER BY p.id", (store_id,)).fetchall()
        return con.execute(q + " ORDER BY p.id DESC").fetchall()


def get_product(pid: int) -> sqlite3.Row | None:
    with connect() as con:
        return con.execute("SELECT p.*, s.name AS store_name, s.url AS store_url FROM products p "
                           "JOIN stores s ON s.id=p.store_id WHERE p.id=?", (pid,)).fetchone()


def save_edited(pid: int, html: str) -> None:
    with connect() as con:
        con.execute("UPDATE products SET detail_html_edited=?, edited_at=? WHERE id=?", (html, now(), pid))


def reset_edited(pid: int) -> None:
    with connect() as con:
        con.execute("UPDATE products SET detail_html_edited=detail_html_original, edited_at=NULL WHERE id=?", (pid,))


def set_rights(pid: int, confirmed: bool) -> None:
    with connect() as con:
        con.execute("UPDATE products SET rights_confirmed=? WHERE id=?", (int(confirmed), pid))


def recent_logs(n: int = 100) -> list[sqlite3.Row]:
    with connect() as con:
        return con.execute("SELECT * FROM crawl_log ORDER BY id DESC LIMIT ?", (n,)).fetchall()

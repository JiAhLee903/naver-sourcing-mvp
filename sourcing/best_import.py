"""기능 D: BEST 상품 데이터 반입.

스마트스토어(robots.txt Disallow)를 자동으로 크롤링하지 않는다. 대신 사용자가 합법적으로 확보한
상품 데이터(JSON/CSV/ZIP 또는 붙여넣은 상세 HTML)를 가져와 DB에 저장한다.
BEST 여부는 임의 판단하지 않고, 입력 데이터의 `is_best` 값(없으면 사용자가 제공한 목록 전체)을 따른다.

item 필드: name*, url, price, thumb_url, detail_html, is_best
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile

from . import db, html_tools, images


def _price(v) -> int | None:
    if v in (None, ""):
        return None
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def add_product(store_id: int, item: dict, local_images: dict[str, bytes] | None = None,
                source: str = "import", rights_confirmed: bool = False) -> int:
    raw = item.get("detail_html") or ""
    base = {"name": item["name"].strip(), "url": item.get("url") or None, "price": _price(item.get("price")),
            "thumb_url": item.get("thumb_url") or None, "detail_html_raw": raw, "detail_html_original": "",
            "detail_text": "", "source": source, "rights_confirmed": rights_confirmed}
    pid = db.upsert_product(store_id, base)
    existing = db.get_product(pid)
    if existing["detail_html_original"]:  # 중복 → 기존 데이터(편집본 포함) 보존
        return pid
    html = raw
    for src, data in (local_images or {}).items():
        try:
            html = html.replace(src, images.save_image_bytes(pid, data))
        except ValueError as e:
            db.log("warn", item["name"], f"이미지 저장 실패 {src}: {e}")
    prepared = html_tools.prepare(html)
    first = html_tools.list_images(prepared)
    with db.connect() as con:
        con.execute("UPDATE products SET detail_html_original=?, detail_html_edited=?, detail_text=?, "
                    "thumb_url=COALESCE(thumb_url, ?) WHERE id=?",
                    (prepared, prepared, html_tools.extract_text(prepared),
                     first[0]["src"] if first and first[0]["src"].startswith("http") else None, pid))
    return pid


def import_items(store_id: int, items: list[dict], limit: int | None = None, local_images=None,
                 source: str = "import", rights_confirmed: bool = False) -> dict:
    picked = [i for i in items if i.get("name") and str(i.get("is_best", True)).lower() not in ("false", "0", "n", "no", "")]
    if limit:
        picked = picked[:limit]
    ok, fail = 0, 0
    for it in picked:
        try:
            add_product(store_id, it, local_images, source, rights_confirmed)
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            db.log("error", it.get("name", "?"), f"상품 반입 실패: {type(e).__name__}: {e}")
    status = "collected" if fail == 0 and ok else ("partial" if ok else "failed")
    db.set_best_status(store_id, status, f"반입 {ok}건 / 실패 {fail}건 / 입력 {len(items)}건")
    return {"ok": ok, "fail": fail, "total": len(items)}


def parse_upload(filename: str, data: bytes) -> tuple[list[dict], dict[str, bytes]]:
    """JSON / CSV / ZIP(products.json + 이미지) 파싱 → (items, local_images)."""
    name = filename.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            pj = next((n for n in names if n.endswith("products.json")), None)
            if not pj:
                raise ValueError("ZIP 안에 products.json 이 없습니다.")
            items = json.loads(z.read(pj).decode("utf-8"))
            base = pj[: -len("products.json")]
            imgs = {n[len(base):]: z.read(n) for n in names
                    if n.startswith(base) and not n.endswith("/") and n != pj and n[len(base):].startswith("images/")}
        return items, imgs
    if name.endswith(".json"):
        items = json.loads(data.decode("utf-8-sig"))
        return (items if isinstance(items, list) else items.get("items", [])), {}
    if name.endswith(".csv"):
        return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")))), {}
    raise ValueError("지원 형식: .json, .csv, .zip")

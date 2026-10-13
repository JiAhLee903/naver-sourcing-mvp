"""기능 F: 결과물 저장 — CSV / 편집된 HTML / 이미지 / 전체 ZIP.

이미지와 상세 HTML은 '사용 권한 확인(rights_confirmed)'된 상품만 내보낸다. CSV(메타데이터)는 항상 가능.
"""
from __future__ import annotations

import csv
import io
import zipfile

from . import html_tools, images

CSV_COLS = ["id", "store_name", "store_url", "name", "price", "url", "rights_confirmed", "source",
            "collected_at", "edited_at", "image_count"]

DOC = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{max-width:860px;margin:0 auto;font-family:sans-serif}}img{{max-width:100%;height:auto}}</style>
</head><body>
{body}
</body></html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def products_csv(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in rows:
        n = len(html_tools.list_images(r["detail_html_edited"] or ""))
        w.writerow([r["id"], r["store_name"], r["store_url"], r["name"], r["price"], r["url"],
                    r["rights_confirmed"], r["source"], r["collected_at"], r["edited_at"], n])
    return buf.getvalue().encode("utf-8-sig")


def edited_html_doc(row) -> str:
    """편집본을 단독 실행 가능한 문서로. 이미지 경로는 'images/…' 상대경로(ZIP 구조와 동일)."""
    html = html_tools.sanitize(row["detail_html_edited"] or "")
    return DOC.format(title=_esc(row["name"]), body=html)


def product_bundle(row) -> tuple[bytes, dict[str, bytes], list[str]]:
    """(html 바이트, {상대경로: 이미지 바이트}, 경고 목록)."""
    warns = []
    files: dict[str, bytes] = {}
    for im in html_tools.list_images(row["detail_html_edited"] or ""):
        f = images.local_file(row["id"], im["src"])
        if f:
            files[im["src"]] = f.read_bytes()
        else:
            warns.append(f"외부 URL 이미지(로컬 저장 안 됨, 만료될 수 있음): {im['src'][:100]}")
    return edited_html_doc(row).encode("utf-8"), files, warns


def single_zip(row) -> bytes:
    if not row["rights_confirmed"]:
        raise PermissionError("사용 권한이 확인되지 않은 상품은 HTML/이미지를 내보낼 수 없습니다.")
    html, files, warns = product_bundle(row)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("detail.html", html)
        for rel, data in files.items():
            z.writestr(rel, data)
        if warns:
            z.writestr("WARNINGS.txt", "\n".join(warns))
    return buf.getvalue()


def all_zip(rows) -> bytes:
    buf = io.BytesIO()
    skipped, warns = [], []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("products.csv", products_csv(rows))
        for r in rows:
            if not r["rights_confirmed"]:
                skipped.append(f"{r['id']}\t{r['name']}")
                continue
            html, files, w = product_bundle(r)
            z.writestr(f"products/{r['id']}/detail.html", html)
            for rel, data in files.items():
                z.writestr(f"products/{r['id']}/{rel}", data)
            warns += [f"[{r['id']}] {x}" for x in w]
        if skipped:
            z.writestr("SKIPPED_no_rights.txt", "사용 권한 미확인으로 HTML/이미지 제외:\n" + "\n".join(skipped))
        if warns:
            z.writestr("WARNINGS.txt", "\n".join(warns))
    return buf.getvalue()

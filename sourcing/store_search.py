"""기능 A: 키워드 기반 스토어 발굴 — 네이버 검색 Open API(shop.json) 사용.

※ 검색결과 페이지(search.shopping.naver.com)는 robots.txt/봇 차단(HTTP 418)으로 직접 수집하지 않는다.
※ [미검증] 이 모듈은 실제 API 키로 호출해 본 적이 없다. 응답 필드(mallName, link, productType)는
   공식 문서 기준 기억에 의존하며, scripts/verify_access.py 로 로컬에서 먼저 확인해야 한다.
※ [제약] Open API는 가격비교 상품의 '판매처 전체 목록'을 제공하지 않는 것으로 알려져 있다(미검증).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

from . import config, robots

API_URL = "https://openapi.naver.com/v1/search/shop.json"
STORE_HOSTS = {"smartstore.naver.com", "brand.naver.com"}


class ApiError(RuntimeError):
    pass


def store_url_from_link(link: str) -> str | None:
    """https://smartstore.naver.com/<store>/products/<id> → https://smartstore.naver.com/<store>.

    스토어명을 URL에서 알 수 없는 형태(리다이렉트, /main/products 등)는 None.
    """
    parts = urlsplit(link or "")
    if parts.netloc not in STORE_HOSTS:
        return None
    seg = [s for s in parts.path.split("/") if s]
    if not seg or seg[0] in ("main", "products", "i"):
        return None
    return f"https://{parts.netloc}/{seg[0]}"


def parse_items(keyword: str, items: list[dict]) -> list[dict]:
    """API item 목록 → 발견 스토어 레코드. 스토어 URL별 중복 제거."""
    seen: set[str] = set()
    out = []
    for it in items:
        url = store_url_from_link(it.get("link", ""))
        key = url or f"nolink:{it.get('mallName')}:{it.get('productId')}"
        if key in seen:
            continue
        seen.add(key)
        title = (it.get("title") or "").replace("<b>", "").replace("</b>", "")
        out.append({"keyword": keyword, "store_name": it.get("mallName") or None, "store_url": url,
                    "source": "openapi:shop.json", "product_title": title,
                    "product_link": it.get("link"), "product_type": str(it.get("productType", ""))})
    return out


def search(keyword: str, client_id: str, client_secret: str, display: int = 100, start: int = 1,
           exclude: str | None = None) -> list[dict]:
    if not (client_id and client_secret):
        raise ApiError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 설정되지 않았습니다.")
    q = {"query": keyword, "display": min(display, 100), "start": start}
    if exclude:
        q["exclude"] = exclude
    req = urllib.request.Request(API_URL + "?" + urllib.parse.urlencode(q), headers={
        "X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret, "User-Agent": config.USER_AGENT})
    robots.throttle()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError(f"API HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}") from e
    except Exception as e:  # noqa: BLE001
        raise ApiError(f"API 호출 실패({type(e).__name__}): {e}") from e
    return parse_items(keyword, data.get("items", []))

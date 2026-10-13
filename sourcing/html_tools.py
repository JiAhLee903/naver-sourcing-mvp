"""상세페이지 HTML 정제(sanitize)와 이미지 편집(삭제/교체/순서 변경).

모든 <img>에 data-img-id를 부여해 HTML 요소와 이미지를 연결한다.
삭제/이동 단위는 '슬롯'(이미지만 담은 가장 바깥 래퍼)이라 빈 <p>/<a> 같은 잔해가 남지 않는다.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

ID_ATTR = "data-img-id"
ALLOWED_TAGS = {"p", "div", "span", "br", "img", "a", "b", "strong", "i", "em", "u", "h1", "h2", "h3", "h4",
                "h5", "h6", "ul", "ol", "li", "table", "thead", "tbody", "tr", "td", "th", "center", "font",
                "figure", "figcaption", "section", "small", "hr", "blockquote", "body"}
DROP_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "button", "textarea", "select",
             "link", "meta", "base", "noscript", "svg", "video", "audio", "template", "frame", "frameset", "head", "title"}
ALLOWED_ATTRS = {"img": {"src", "alt", "width", "height", ID_ATTR}, "a": {"href", "title"},
                 "td": {"colspan", "rowspan", "align"}, "th": {"colspan", "rowspan", "align"},
                 "p": {"align"}, "div": {"align"}, "font": {"color", "size"}}
SLOT_WRAPPERS = {"a", "p", "div", "span", "center", "figure", "section"}
_SAFE_URL = re.compile(r"^(https?:|//|images/|data:image/(png|jpe?g|gif|webp);base64,)", re.I)


def _parse(html: str) -> tuple[BeautifulSoup, Tag]:
    soup = BeautifulSoup(html or "", "lxml")
    body = soup.body or soup.new_tag("body")
    if soup.body is None:
        soup.append(body)
    return soup, body


def _dump(body: Tag) -> str:
    return "".join(str(c) for c in body.contents).strip()


def sanitize(html: str) -> str:
    """스크립트·이벤트 핸들러·위험 URL을 제거한 안전한 HTML 조각을 반환."""
    soup, body = _parse(html)
    for t in body.find_all(DROP_TAGS):
        t.decompose()
    for t in body.find_all(True):
        if t.name not in ALLOWED_TAGS:
            t.unwrap()
    for t in body.find_all(True):
        if t.name == "img":  # 지연 로딩 이미지 대응
            src = t.get("src") or t.get("data-src") or t.get("data-lazy-src") or t.get("data-original") or ""
            t.attrs = {k: v for k, v in t.attrs.items() if k in ALLOWED_ATTRS["img"]}
            if src:
                t["src"] = src.strip()
        keep = ALLOWED_ATTRS.get(t.name, set())
        t.attrs = {k: v for k, v in t.attrs.items() if k in keep}
        for url_attr in ("src", "href"):
            v = t.get(url_attr)
            if v is not None and not _SAFE_URL.match(v.strip()):
                if url_attr == "href" and not re.match(r"^\s*(javascript|data|vbscript):", v, re.I):
                    continue  # '#', 상대 링크 등은 위험하지 않음
                del t.attrs[url_attr]
        if t.name == "a" and t.get("href"):
            t["rel"] = "noopener noreferrer nofollow"
            t["target"] = "_blank"
    for img in body.find_all("img"):
        if not img.get("src"):
            img.decompose()
    return _dump(body)


def prepare(html: str) -> str:
    """sanitize 후 모든 이미지에 안정적인 id(i1, i2, ...)를 부여."""
    soup, body = _parse(sanitize(html))
    for n, img in enumerate(body.find_all("img"), 1):
        img[ID_ATTR] = f"i{n}"
    return _dump(body)


def list_images(html: str) -> list[dict]:
    _, body = _parse(html)
    return [{"id": i.get(ID_ATTR), "src": i.get("src", ""), "alt": i.get("alt", "")} for i in body.find_all("img")]


def _slot(img: Tag) -> Tag:
    node = img
    while node.parent is not None and node.parent.name in SLOT_WRAPPERS:
        p = node.parent
        if p.get_text(strip=True) == "" and len(p.find_all("img")) == 1:
            node = p
        else:
            break
    return node


def _find(body: Tag, img_id: str) -> Tag:
    img = body.find("img", attrs={ID_ATTR: img_id})
    if img is None:
        raise KeyError(f"이미지 id 없음: {img_id}")
    return img


def delete_images(html: str, img_ids: list[str]) -> str:
    soup, body = _parse(html)
    for i in img_ids:
        _slot(_find(body, i)).decompose()
    return _dump(body)


def replace_image(html: str, img_id: str, new_src: str) -> str:
    if not _SAFE_URL.match(new_src):
        raise ValueError("허용되지 않는 이미지 경로")
    soup, body = _parse(html)
    img = _find(body, img_id)
    img["src"] = new_src
    return _dump(body)


def reorder_images(html: str, new_order: list[str]) -> str:
    """이미지 슬롯의 문서 내 위치는 유지하고, 그 위치에 들어가는 이미지 순서만 바꾼다."""
    soup, body = _parse(html)
    imgs = body.find_all("img")
    current = [i.get(ID_ATTR) for i in imgs]
    if sorted(current) != sorted(new_order):
        raise ValueError("new_order는 현재 이미지 id 전체의 순열이어야 합니다.")
    slots = {i.get(ID_ATTR): _slot(i) for i in imgs}
    markers = []
    for img_id in current:
        m = soup.new_tag("span")
        slots[img_id].insert_before(m)
        markers.append(m)
    for img_id in current:
        slots[img_id].extract()
    for m, img_id in zip(markers, new_order):
        m.replace_with(slots[img_id])
    return _dump(body)


def move_image(html: str, img_id: str, delta: int) -> str:
    order = [i["id"] for i in list_images(html)]
    k = order.index(img_id)
    j = max(0, min(len(order) - 1, k + delta))
    order.insert(j, order.pop(k))
    return reorder_images(html, order)


def extract_text(html: str) -> str:
    _, body = _parse(html)
    return re.sub(r"\s+", " ", body.get_text(" ", strip=True))

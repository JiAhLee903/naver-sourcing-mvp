"""이미지 저장/검증/조회. 외부 이미지는 robots.txt 확인 + 간격 제한 후에만 내려받는다."""
from __future__ import annotations

import base64
import hashlib
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

from . import config, robots

_EXT = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp"}
_MIME = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def product_dir(pid: int) -> Path:
    return config.PRODUCT_DIR / str(pid)


def save_image_bytes(pid: int, data: bytes) -> str:
    """이미지 바이트를 검증 후 저장하고 HTML에서 쓸 상대경로('images/<hash>.<ext>')를 반환."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            im.verify()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"이미지 파일이 아니거나 손상됨: {e}") from e
    if fmt not in _EXT:
        raise ValueError(f"지원하지 않는 이미지 형식: {fmt}")
    name = f"{hashlib.sha1(data).hexdigest()[:12]}.{_EXT[fmt]}"
    path = product_dir(pid) / "images" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"images/{name}"


def fetch_remote(url: str) -> bytes:
    """robots.txt 허용 시에만 다운로드. 실패 시 RuntimeError(사유 포함)."""
    ok, why = robots.can_fetch(url)
    if not ok:
        raise RuntimeError(f"수집 불가: {why} ({url})")
    robots.throttle()
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(config.MAX_IMAGE_BYTES + 1)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"다운로드 실패({type(e).__name__}): {url}") from e
    if len(data) > config.MAX_IMAGE_BYTES:
        raise RuntimeError(f"이미지가 너무 큼: {url}")
    return data


def local_file(pid: int, rel: str) -> Path | None:
    if not rel or rel.startswith(("http://", "https://", "//", "data:")):
        return None
    p = (product_dir(pid) / rel).resolve()
    return p if p.is_file() and product_dir(pid).resolve() in p.parents else None


def to_data_uri(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower()
    return f"data:{_MIME.get(ext, 'image/png')};base64," + base64.b64encode(path.read_bytes()).decode()


def make_placeholder(text: str, size=(800, 400), color=(120, 160, 200)) -> bytes:
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(255, 255, 255), width=4)
    d.text((size[0] // 2 - 6 * len(text), size[1] // 2 - 6), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()

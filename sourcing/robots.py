"""robots.txt 준수 확인. 외부 URL을 요청하기 전에 반드시 통과해야 한다.

판단이 불확실하면(robots.txt를 못 읽음, 봇 차단 페이지 등) 차단으로 간주한다.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from . import config

_cache: dict[str, tuple[RobotFileParser | None, str]] = {}
_last_request = 0.0


def throttle() -> None:
    """요청 간 최소 간격 보장 (단일 스레드 순차 요청)."""
    global _last_request
    wait = config.MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _load(origin: str) -> tuple[RobotFileParser | None, str]:
    if origin in _cache:
        return _cache[origin]
    req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": config.USER_AGENT})
    result: tuple[RobotFileParser | None, str]
    try:
        throttle()
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
        if "<html" in body[:500].lower():
            result = (None, "robots.txt 대신 HTML(차단/오류 페이지)이 반환됨 → 차단으로 간주")
        else:
            rp = RobotFileParser()
            rp.parse(body.splitlines())
            result = (rp, "ok")
    except urllib.error.HTTPError as e:
        # 404/410: robots.txt 없음 → 제한 없음. 그 외(418, 403, 5xx)는 차단으로 간주.
        result = (RobotFileParser(), "robots.txt 없음") if e.code in (404, 410) else (None, f"robots.txt HTTP {e.code} → 차단으로 간주")
        if e.code in (404, 410):
            result[0].parse([])
    except Exception as e:  # noqa: BLE001
        result = (None, f"robots.txt 조회 실패({type(e).__name__}) → 차단으로 간주")
    _cache[origin] = result
    return result


def can_fetch(url: str, user_agent: str | None = None) -> tuple[bool, str]:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False, "http(s) URL이 아님"
    rp, note = _load(f"{parts.scheme}://{parts.netloc}")
    if rp is None:
        return False, note
    ua = user_agent or config.USER_AGENT
    ok = rp.can_fetch(ua, url)
    return ok, "허용" if ok else "robots.txt가 이 경로의 수집을 금지함"

"""기능 B: 스마트스토어 뱃지 필터링.

스마트스토어 페이지는 robots.txt(User-agent: * → Disallow: /)로 일반 크롤러의 접근이 금지되어 있어
뱃지를 자동으로 판별하지 않는다(임의 선택자로 판별한 것처럼 처리하지 않음).
사용자가 스토어를 직접 열어 확인한 결과를 입력하는 '수동 검수' 방식이다.
"""
from __future__ import annotations

from .db import BADGE_LABELS

STATUSES = list(BADGE_LABELS)  # unchecked, has_badge, no_badge, unknown


def label(status: str) -> str:
    return BADGE_LABELS.get(status, status)


def status_from_label(text: str) -> str:
    for k, v in BADGE_LABELS.items():
        if v == text:
            return k
    raise ValueError(f"알 수 없는 뱃지 상태: {text}")


def is_collectable(status: str) -> bool:
    """뱃지 있음만 제외. 미확인/판별 실패는 사용자가 명시적으로 선택했을 때만 수집."""
    return status != "has_badge"


def default_selected(status: str) -> bool:
    return status == "no_badge"

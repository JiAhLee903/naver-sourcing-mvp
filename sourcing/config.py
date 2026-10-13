"""경로와 환경 설정."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SOURCING_DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "sourcing.db"
PRODUCT_DIR = DATA_DIR / "products"  # products/<id>/images/<file>

USER_AGENT = "NaverSourcingMVP/0.1 (personal sourcing tool)"
MIN_REQUEST_INTERVAL = 1.5  # 초. 외부 요청 사이 최소 간격 (동시 요청 없음)
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# 네이버 검색 Open API (https://developers.naver.com 에서 사용자가 직접 발급)
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCT_DIR.mkdir(parents=True, exist_ok=True)

"""1단계 기술 검증 스크립트 (로컬 실행용, 표준 라이브러리만 사용).

  python scripts/verify_access.py
  NAVER_CLIENT_ID=... NAVER_CLIENT_SECRET=... python scripts/verify_access.py 나무

1) 대상 호스트의 robots.txt 가 우리 User-Agent(와 '*')에 대해 해당 경로를 허용하는지 확인
2) (키가 있으면) 공식 Open API shop.json 호출 → 응답 필드/스토어 URL 추출 가능 여부 출력
이 스크립트는 차단된 페이지를 우회하거나 직접 크롤링하지 않는다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sourcing import robots, store_search  # noqa: E402

TARGETS = [
    ("해외직구 검색결과", "https://search.shopping.naver.com/search/all?query=%EB%82%98%EB%AC%B4"),
    ("가격비교(catalog)", "https://search.shopping.naver.com/catalog/1234567"),
    ("스마트스토어 홈", "https://smartstore.naver.com/example"),
    ("스마트스토어 BEST", "https://smartstore.naver.com/example/best"),
    ("스마트스토어 상품", "https://smartstore.naver.com/example/products/1"),
    ("shopping.naver.com", "https://shopping.naver.com/"),
]


def main() -> None:
    print("== 1. robots.txt 확인 ==")
    for label, url in TARGETS:
        for ua in (None, "*"):
            ok, why = robots.can_fetch(url, ua)
            print(f"{'허용' if ok else '금지'} | {label:<18} | UA={ua or 'NaverSourcingMVP':<17} | {why}")
    print("\n== 2. 공식 Open API ==")
    cid, sec = os.environ.get("NAVER_CLIENT_ID", ""), os.environ.get("NAVER_CLIENT_SECRET", "")
    if not (cid and sec):
        print("NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 미설정 → 건너뜀 (https://developers.naver.com 에서 '검색' API 등록)")
        return
    kw = sys.argv[1] if len(sys.argv) > 1 else "나무"
    try:
        found = store_search.search(kw, cid, sec, display=100)
    except store_search.ApiError as e:
        print("API 실패:", e)
        return
    with_url = [f for f in found if f["store_url"]]
    print(f"결과 {len(found)}건 (중복 제거 후), 그중 스마트스토어 URL 추출 {len(with_url)}건")
    print("productType 분포:", {t: sum(1 for f in found if f['product_type'] == t) for t in {f['product_type'] for f in found}})
    for f in found[:5]:
        print(json.dumps(f, ensure_ascii=False))
    print("※ 해외직구 상품만 골라내는 필드/조건이 응답에 있는지는 위 출력을 직접 확인하세요.")


if __name__ == "__main__":
    main()

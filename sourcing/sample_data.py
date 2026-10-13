"""샘플 데이터: 네이버에 접속하지 않고 UI/편집/내보내기 전체 흐름을 시험하기 위한 가짜 데이터.

상품 이미지는 Pillow로 생성한 단색 이미지이며 실제 판매자 콘텐츠가 아니다 → 권한 확인 완료로 표시한다.
"""
from __future__ import annotations

from . import best_import, db, images

SAMPLE_KEYWORD = "나무(샘플)"


def sample_discovered() -> list[dict]:
    return [
        {"keyword": SAMPLE_KEYWORD, "store_name": "샘플 목재상회", "store_url": "https://smartstore.naver.com/sample-wood",
         "source": "sample", "product_title": "샘플 원목 도마", "product_link": "https://example.com/p/1", "product_type": "1"},
        {"keyword": SAMPLE_KEYWORD, "store_name": "샘플 가구공방", "store_url": "https://smartstore.naver.com/sample-furniture",
         "source": "sample", "product_title": "샘플 원목 선반", "product_link": "https://example.com/p/2", "product_type": "1"},
        {"keyword": SAMPLE_KEYWORD, "store_name": "뱃지 있는 샘플몰", "store_url": "https://smartstore.naver.com/sample-badged",
         "source": "sample", "product_title": "샘플 나무 장난감", "product_link": "https://example.com/p/3", "product_type": "1"},
    ]


def _detail(n: int) -> str:
    parts = ["<h2>샘플 상세페이지</h2>", "<script>alert('xss')</script>",
             "<p onclick=\"alert(1)\">상품 설명 텍스트입니다.</p>"]
    for k in range(1, n + 1):
        parts.append(f'<p><a href="https://example.com"><img src="local:{k}.png" alt="img{k}"></a></p>')
        if k == 2:
            parts.append("<p>중간 안내 문구 — 이미지 삭제 시에도 유지되어야 합니다.</p>")
    return "\n".join(parts)


def load_sample_products(store_id: int, count: int = 3, limit: int | None = None) -> dict:
    palette = [(200, 120, 90), (90, 160, 120), (110, 120, 200), (210, 180, 80), (160, 100, 180)]
    items = [{"name": f"샘플 상품 {i}", "url": f"https://example.com/sample/{store_id}/{i}", "price": 10000 * i,
              "is_best": True, "detail_html": _detail(4)} for i in range(1, count + 1)]
    imgs = {f"local:{k}.png": images.make_placeholder(f"SAMPLE IMAGE {k}", color=palette[(k - 1) % 5]) for k in range(1, 5)}
    return best_import.import_items(store_id, items, limit=limit, local_images=imgs, source="sample", rights_confirmed=True)

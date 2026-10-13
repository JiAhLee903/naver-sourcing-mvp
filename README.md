# 해외직구 상품 소싱 MVP

네이버 공식 Open API·수동 검수·권한 있는 데이터 반입으로 동작하는 소싱/상세페이지 편집 도구 (Streamlit + SQLite).

## 중요: 왜 Playwright 크롤러가 없는가
2026-10-13 확인 결과:
- `smartstore.naver.com/robots.txt`, `shopping.naver.com/robots.txt` → `User-agent: *` 에 `Disallow: /` (Googlebot 등 일부만 허용, ClaudeBot/AI 수집 명시 금지)
- `search.shopping.naver.com` → 일반 요청에 HTTP 418 차단 페이지

요구사항의 "robots.txt 준수 / 차단 회피 금지"에 따라 검색결과·가격비교·스마트스토어(뱃지, BEST, 상세)를 **자동 수집하지 않습니다.**
(`scripts/verify_access.py` 로 본인 환경에서 다시 확인할 수 있습니다. 정책이 바뀌었다면 알려 주세요.)

## 설치/실행 (Python 3.12+)
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/verify_access.py          # 1단계 검증 (API 키가 있으면 NAVER_CLIENT_ID/SECRET 환경변수 지정)
streamlit run app.py
pytest -q
```
데이터는 `data/`(SQLite + 이미지)에 저장됩니다. `SOURCING_DATA_DIR`로 위치 변경 가능.

## 기능과 검증 현황
| 기능 | 방식 | 상태 |
|---|---|---|
| A 키워드 스토어 발굴 | Open API `shop.json` (`sourcing/store_search.py`) | **미검증** (API 키로 호출해 본 적 없음). 해외직구 전용 필터, 가격비교 판매처 전체 목록이 API에 있는지 불명 |
| A 샘플 모드 | 내장 샘플 | 검증됨 (AppTest) |
| B 뱃지 필터 | **수동 지정** (`badge_filter.py`) — 자동 판별 없음 | 수동 로직 검증됨. 자동 판별은 미구현(접근 금지) |
| C 스토어 수집/중복 방지/목록 | SQLite | 검증됨 (pytest) |
| D BEST 상품 | JSON/CSV/ZIP 반입 (`best_import.py`), 개수 제한, `is_best` 존중 | 반입 로직 검증됨. 스토어 BEST 자동 읽기는 미구현 |
| E 편집 (삭제/교체/순서/미리보기/저장/원본 보존) | `html_tools.py` | 로직 검증됨(pytest, AppTest). 브라우저 iframe 미리보기 렌더링은 눈으로 미확인 |
| E 외부 이미지 로컬화 | robots.txt 허용 시에만 | **미검증** |
| F CSV / HTML / ZIP | `export.py` | 검증됨. HTML·이미지는 "권한 확인" 체크된 상품만 |

## 반입 형식
`products.json`(ZIP이면 `images/` 폴더 동봉) 또는 CSV: `name, url, price, thumb_url, detail_html, is_best`.
ZIP 안 HTML의 `images/xxx.png` 참조는 자동으로 연결됩니다.

## 구조
`sourcing/` — config, db, robots(준수·간격 제한), store_search, badge_filter, best_import, html_tools(sanitize·편집), images, export, sample_data / `app.py` UI / `tests/`

## 공개 배포(데모) 시
환경변수/Secrets에 `DEMO_MODE=1` 을 설정하면 샘플 데이터 전용으로 동작합니다(API 키 입력, 외부 이미지 요청 비활성화).
다른 판매자의 상세페이지·이미지는 저작권자의 허락 없이 재사용할 수 없습니다. "사용 권한 확인" 체크는 사용자 본인의 책임 표시입니다.

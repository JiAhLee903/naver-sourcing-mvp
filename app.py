"""Streamlit 관리자 UI.  실행: streamlit run app.py"""
from __future__ import annotations

import os

import pandas as pd  # streamlit 의존성으로 함께 설치됨
import streamlit as st
import streamlit.components.v1 as components

from sourcing import badge_filter, best_import, config, db, export, html_tools, images, sample_data, store_search

st.set_page_config(page_title="해외직구 소싱 MVP", layout="wide")
DEMO = os.environ.get("DEMO_MODE") == "1"  # 공개 배포용: 샘플 데이터만, API 키 입력/외부 요청 비활성화
PAGES = ["1. 스토어 검색", "2. 수집된 스토어", "3. 수집된 상품", "4. 상세페이지 편집", "5. 수집 설정", "로그/상태"]
st.session_state.setdefault("page", PAGES[0])
if "_nav" in st.session_state:  # 라디오 위젯 생성 전에만 page 값을 바꿀 수 있다
    st.session_state["page"] = st.session_state.pop("_nav")
page = st.sidebar.radio("화면", PAGES, key="page")
if DEMO:
    st.sidebar.warning("데모 모드: 샘플 데이터 전용입니다. 서버 재시작 시 데이터가 초기화됩니다. 실제 사용은 로컬에서 하세요.")
st.sidebar.caption("사용 조건: 다른 판매자의 상세페이지·이미지는 저작권자 허락 없이 재사용할 수 없습니다.")
st.sidebar.caption("네이버 쇼핑/스마트스토어는 robots.txt로 자동 수집이 금지되어 있어, 이 도구는 공식 Open API·"
                   "수동 검수·권한 있는 데이터 반입 방식으로 동작합니다. README의 '검증 현황' 참고.")


def go(p: str, **state) -> None:
    st.session_state.update(state)
    st.session_state["_nav"] = p


def render_preview(pid: int, html: str) -> str:
    """로컬 이미지는 data URI로 인라인, 스크립트는 정제 + CSP로 이중 차단."""
    soup_html = html_tools.sanitize(html)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(soup_html, "lxml")
    for im in soup.find_all("img"):
        f = images.local_file(pid, im.get("src", ""))
        if f:
            im["src"] = images.to_data_uri(f)
    body = "".join(str(c) for c in (soup.body.contents if soup.body else []))
    return ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data: https: http:; "
            "style-src 'unsafe-inline'\"><style>body{font-family:sans-serif}img{max-width:100%}</style>" + body)


# ---------------------------------------------------------------- 화면 1
if page == PAGES[0]:
    st.header("스토어 검색")
    c1, c2 = st.columns([3, 1])
    keyword = c1.text_input("키워드", placeholder="예: 나무")
    mode = c2.radio("데이터 소스", ["샘플 데이터"] if DEMO else ["네이버 Open API", "샘플 데이터"], horizontal=False)
    if mode == "네이버 Open API":
        with st.expander("API 키 (developers.naver.com에서 발급한 본인 키)", expanded=not config.NAVER_CLIENT_ID):
            cid = st.text_input("Client ID", value=config.NAVER_CLIENT_ID)
            sec = st.text_input("Client Secret", value=config.NAVER_CLIENT_SECRET, type="password")
        excl = st.checkbox("중고/렌탈 제외(exclude=used:rental)", value=False)
        st.warning("미검증: 실제 API 키로 호출해 본 적 없음. 해외직구 전용 필터·가격비교 판매처 목록은 API로 제공되는지 "
                   "확인되지 않았습니다. 먼저 scripts/verify_access.py 를 실행하세요.")
    if st.button("검색", type="primary"):
        try:
            if mode == "샘플 데이터":
                keyword = sample_data.SAMPLE_KEYWORD
                rows = sample_data.sample_discovered()
            else:
                if not keyword.strip():
                    raise ValueError("키워드를 입력하세요.")
                rows = store_search.search(keyword.strip(), cid, sec, exclude="used:rental" if excl else None)
            n = db.add_discovered(rows)
            db.log("info", keyword, f"검색 {len(rows)}건, 신규 저장 {n}건 ({mode})")
            st.session_state["kw"] = keyword
        except Exception as e:  # noqa: BLE001
            db.log("error", keyword, f"검색 실패: {e}")
            st.error(f"검색 실패: {e}")

    kw = st.session_state.get("kw")
    if kw:
        found = db.list_discovered(kw)
        st.subheader(f"'{kw}' 발견 스토어 {len(found)}곳")
        st.info("뱃지는 자동 판별하지 않습니다(스마트스토어 접근이 robots.txt로 금지). 스토어를 직접 열어 확인한 뒤 "
                "'뱃지 상태'를 지정하세요. '뱃지 있음'은 수집하지 않고 제외 목록에 등록됩니다. 제외 스토어는 결과에 나타나지 않습니다.")
        existing = {s["url"] for s in db.list_stores()}
        df = pd.DataFrame([{
            "선택": False, "스토어명": r["store_name"], "스토어 URL": r["store_url"] or "(URL 미확인)",
            "뱃지 상태": badge_filter.label("unchecked"), "대표 상품": r["product_title"],
            "발견 경로": r["source"], "이미 수집": (r["store_url"] in existing)} for r in found])
        edited = st.data_editor(df, hide_index=True, use_container_width=True, disabled=["스토어명", "스토어 URL", "대표 상품", "발견 경로", "이미 수집"],
                                column_config={"뱃지 상태": st.column_config.SelectboxColumn(options=list(db.BADGE_LABELS.values()))})
        if st.button("선택한 스토어 수집"):
            added = 0
            # 뱃지 있음 → 수집하지 않고 차단 목록에 올려 이후 검색 결과에서도 숨긴다
            for _, r in edited.iterrows():
                if badge_filter.status_from_label(r["뱃지 상태"]) == "has_badge" and r["스토어 URL"].startswith("http"):
                    db.block_store(r["스토어 URL"], r["스토어명"], "뱃지 있음")
            for _, r in edited[edited["선택"]].iterrows():
                status = badge_filter.status_from_label(r["뱃지 상태"])
                if (not r["스토어 URL"].startswith("http") or not badge_filter.is_collectable(status)
                        or db.is_blocked(r["스토어 URL"])):
                    continue
                added += db.collect_store(r["스토어명"], r["스토어 URL"], kw, status)
            st.success(f"신규 저장 {added}곳. 뱃지 있음 스토어는 제외 목록에 등록했습니다(수집 설정에서 해제 가능).")

# ---------------------------------------------------------------- 화면 2
elif page == PAGES[1]:
    st.header("수집된 스토어")
    stores = db.list_stores()
    if not stores:
        st.info("수집된 스토어가 없습니다. 화면 1에서 수집하세요.")
    for s in stores:
        with st.container(border=True):
            a, b, c = st.columns([3, 2, 2])
            a.markdown(f"**{s['name']}**  \n{s['url']}  \n키워드: {s['keyword']} · 수집: {s['collected_at']}")
            b.markdown(f"뱃지: {badge_filter.label(s['badge_status'])}  \nBEST 상태: **{db.BEST_LABELS[s['best_status']]}**"
                       f" ({s['product_count']}개)  \n{s['best_note'] or ''}")
            new = c.selectbox("뱃지 상태 수정", list(db.BADGE_LABELS.values()), key=f"bd{s['id']}",
                              index=list(db.BADGE_LABELS).index(s["badge_status"]))
            if badge_filter.status_from_label(new) != s["badge_status"]:
                db.set_badge(s["id"], badge_filter.status_from_label(new))
                st.rerun()
            with st.expander("상품 수집(반입)"):
                limit = st.number_input("상품 수 제한 (0=전체)", 0, 500, 20, key=f"lim{s['id']}")
                rights = st.checkbox("이 데이터의 상세페이지/이미지 재사용 권한을 확인했음", key=f"rt{s['id']}")
                up = st.file_uploader("상품 데이터 (.json / .csv / .zip)", ["json", "csv", "zip"], key=f"up{s['id']}")
                if st.button("가져오기", key=f"imp{s['id']}", disabled=up is None):
                    try:
                        items, imgs = best_import.parse_upload(up.name, up.getvalue())
                        r = best_import.import_items(s["id"], items, limit or None, imgs, rights_confirmed=rights)
                        st.success(f"반입 {r['ok']}건 · 금지어 제외 {r['banned']}건 · 실패 {r['fail']}건")
                    except Exception as e:  # noqa: BLE001
                        db.log("error", s["url"], f"반입 실패: {e}")
                        st.error(f"반입 실패: {e}")
                if st.button("샘플 상품 불러오기(테스트용)", key=f"smp{s['id']}"):
                    r = sample_data.load_sample_products(s["id"], 3, limit or None)
                    st.success(f"반입 {r['ok']}건 · 금지어 제외 {r['banned']}건")
                st.caption("스마트스토어 BEST 목록을 자동으로 읽지 않습니다(robots.txt 금지). 'BEST 여부'는 데이터의 is_best 값을 따릅니다.")
            if st.button("상품 보기", key=f"vw{s['id']}"):
                go(PAGES[2], store_filter=s["id"])
                st.rerun()

# ---------------------------------------------------------------- 화면 3
elif page == PAGES[2]:
    st.header("수집된 상품")
    stores = {s["id"]: s["name"] for s in db.list_stores()}
    sel = st.selectbox("스토어", [0] + list(stores), format_func=lambda i: "전체" if i == 0 else stores[i],
                       index=([0] + list(stores)).index(st.session_state.get("store_filter", 0)))
    prods = db.list_products(sel or None)
    if not prods:
        st.info("상품이 없습니다.")
    for p in prods:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 1])
            thumb = None
            ims = html_tools.list_images(p["detail_html_edited"] or "")
            if ims:
                thumb = images.local_file(p["id"], ims[0]["src"]) or (ims[0]["src"] if ims[0]["src"].startswith("http") else None)
            thumb = thumb or p["thumb_url"]
            if thumb:
                c1.image(str(thumb), width=110)
            c2.markdown(f"**{p['name']}**  \n가격: {p['price']:,}원  \n" if p["price"] else f"**{p['name']}**  \n")
            c2.markdown(f"스토어: {p['store_name']} · 원본: {p['url'] or '-'}  \n권한 확인: {'✅' if p['rights_confirmed'] else '❌ 미확인'} · "
                        f"출처: {p['source']} · 수집: {p['collected_at']}")
            if c3.button("상세페이지 편집", key=f"ed{p['id']}"):
                go(PAGES[3], pid=p["id"])
                st.rerun()

# ---------------------------------------------------------------- 화면 4
elif page == PAGES[3]:
    st.header("상세페이지 편집")
    pid = st.session_state.get("pid")
    p = db.get_product(pid) if pid else None
    if not p:
        st.info("화면 3에서 상품을 선택하세요.")
        st.stop()
    wk = f"work_{pid}"
    if wk not in st.session_state:
        st.session_state[wk] = p["detail_html_edited"] or ""
    html = st.session_state[wk]
    st.subheader(p["name"])
    rights = st.checkbox("상세페이지/이미지 재사용 권한을 확인했음 (내보내기 조건)", value=bool(p["rights_confirmed"]))
    if rights != bool(p["rights_confirmed"]):
        db.set_rights(pid, rights)
        st.rerun()

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**이미지 목록**")
        ims = html_tools.list_images(html)
        picked = []
        for k, im in enumerate(ims):
            with st.container(border=True):
                a, b = st.columns([1, 2])
                f = images.local_file(pid, im["src"])
                a.image(str(f) if f else im["src"], use_container_width=True)
                if b.checkbox(f"선택 {k + 1} ({im['id']})", key=f"ck{pid}{im['id']}"):
                    picked.append(im["id"])
                b.caption("로컬 저장됨" if f else f"외부 URL(만료 가능): {im['src'][:60]}")
                u, d, _ = b.columns(3)
                if u.button("↑", key=f"up{pid}{im['id']}", disabled=k == 0):
                    st.session_state[wk] = html_tools.move_image(html, im["id"], -1); st.rerun()
                if d.button("↓", key=f"dn{pid}{im['id']}", disabled=k == len(ims) - 1):
                    st.session_state[wk] = html_tools.move_image(html, im["id"], 1); st.rerun()
                rep = b.file_uploader("교체", ["png", "jpg", "jpeg", "gif", "webp"], key=f"rp{pid}{im['id']}")
                if rep and b.button("교체 적용", key=f"rpb{pid}{im['id']}"):
                    try:
                        rel = images.save_image_bytes(pid, rep.getvalue())
                        st.session_state[wk] = html_tools.replace_image(html, im["id"], rel); st.rerun()
                    except ValueError as e:
                        b.error(str(e))
        if st.button(f"선택 삭제 ({len(picked)})", disabled=not picked):
            st.session_state[wk] = html_tools.delete_images(html, picked)
            st.rerun()
        if not DEMO and any(not images.local_file(pid, i["src"]) for i in ims):
            if st.button("외부 이미지를 로컬로 저장 (robots.txt 허용 시)"):
                cur, msgs = html, []
                for im in ims:
                    if im["src"].startswith(("http://", "https://")):
                        try:
                            cur = html_tools.replace_image(cur, im["id"], images.save_image_bytes(pid, images.fetch_remote(im["src"])))
                        except Exception as e:  # noqa: BLE001
                            db.log("warn", p["name"], str(e)); msgs.append(str(e))
                st.session_state[wk] = cur
                if msgs:
                    st.warning("\n\n".join(msgs))
                else:
                    st.rerun()
    with right:
        st.markdown("**미리보기** (스크립트 제거 + CSP, 저장 전 변경 포함)")
        components.html(render_preview(pid, html), height=700, scrolling=True)

    st.divider()
    s1, s2, s3 = st.columns(3)
    if s1.button("저장", type="primary"):
        db.save_edited(pid, html)
        st.success("편집본을 저장했습니다 (원본은 별도 보존).")
    if s2.button("원본으로 되돌리기"):
        db.reset_edited(pid)
        st.session_state.pop(wk, None)
        st.rerun()
    st.caption("다운로드는 저장된 편집본 기준입니다. 먼저 저장하세요.")
    p = db.get_product(pid)
    d1, d2, d3, d4 = st.columns(4)
    d1.download_button("상품 CSV", export.products_csv([p]), f"product_{pid}.csv", "text/csv")
    if p["rights_confirmed"]:
        d2.download_button("편집 HTML", export.edited_html_doc(p), f"product_{pid}.html", "text/html")
        d3.download_button("상품 ZIP(HTML+이미지)", export.single_zip(p), f"product_{pid}.zip", "application/zip")
        d4.download_button("전체 결과 ZIP", export.all_zip(db.list_products()), "all_products.zip", "application/zip")
    else:
        st.warning("사용 권한 확인 체크 전에는 HTML/이미지/ZIP 다운로드가 비활성화됩니다.")

# ---------------------------------------------------------------- 수집 설정
elif page == PAGES[4]:
    st.header("수집 설정")
    st.subheader("금지어")
    st.caption("상품명에 금지어가 들어 있으면 상품 수집(반입)에서 제외됩니다. 대소문자 구분 없이 부분 일치합니다. 예: '여성' → '여성 블라우스' 제외")
    c1, c2 = st.columns([4, 1])
    word = c1.text_input("금지어 추가 (쉼표로 여러 개)", key="bw_in", label_visibility="collapsed", placeholder="예: 여성, 아동")
    if c2.button("추가"):
        for w in word.split(","):
            if w.strip():
                db.add_banned_word(w)
        st.rerun()
    for w in db.list_banned_words():
        a, b = st.columns([6, 1])
        a.write(f"🚫 {w}")
        if b.button("삭제", key=f"bw_{w}"):
            db.remove_banned_word(w)
            st.rerun()
    st.divider()
    st.subheader("수집 제외 스토어")
    st.caption("여기 등록된 스토어는 검색 결과에 표시되지 않고 수집되지 않습니다. 뱃지 있는 스토어는 자동 등록됩니다.")
    c1, c2 = st.columns([4, 1])
    link = c1.text_input("스토어 링크", key="bs_in", label_visibility="collapsed", placeholder="https://smartstore.naver.com/스토어명")
    if c2.button("제외 등록"):
        try:
            db.block_store(link, reason="수동 등록")
            st.rerun()
        except ValueError as e:
            st.error(str(e))
    for r in db.list_blocked():
        a, b = st.columns([6, 1])
        a.write(f"⛔ {r['name'] or ''} {r['url']}  · {r['reason'] or ''}")
        if b.button("해제", key=f"bs_{r['url']}"):
            db.unblock_store(r["url"])
            st.rerun()

# ---------------------------------------------------------------- 로그
else:
    st.header("로그/상태")
    st.dataframe(pd.DataFrame([dict(r) for r in db.recent_logs()]), use_container_width=True)

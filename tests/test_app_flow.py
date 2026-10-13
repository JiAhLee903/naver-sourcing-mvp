"""Streamlit AppTest: 샘플 데이터로 화면 2→3→4 흐름 (네이버 접속 없음)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from sourcing import db, html_tools, sample_data


def _app():
    return AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app.py"), default_timeout=30)


def test_screens_with_sample_data():
    db.add_discovered(sample_data.sample_discovered())
    db.collect_store("샘플 목재상회", "https://smartstore.naver.com/sample-wood", "나무", "no_badge")
    sid = db.list_stores()[0]["id"]

    at = _app().run()
    at.session_state["page"] = "2. 수집된 스토어"
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "샘플 상품 불러오기(테스트용)").click().run()
    assert len(db.list_products(sid)) == 3

    at.session_state["page"] = "3. 수집된 상품"
    at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "상세페이지 편집").click().run()
    assert at.session_state["page"] == "4. 상세페이지 편집" and not at.exception

    pid = at.session_state["pid"]
    at.checkbox(key=f"ck{pid}i1").check().run()
    next(b for b in at.button if b.label.startswith("선택 삭제")).click().run()
    next(b for b in at.button if b.label == "저장").click().run()
    p = db.get_product(pid)
    assert len(html_tools.list_images(p["detail_html_edited"])) == 3
    assert len(html_tools.list_images(p["detail_html_original"])) == 4
    assert not at.exception

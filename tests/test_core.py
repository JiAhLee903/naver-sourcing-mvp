import io
import zipfile

import pytest

from sourcing import best_import, db, export, html_tools, images, sample_data, store_search

HTML = ('<h2>t</h2><script>alert(1)</script><p onclick="x()">hi</p>'
        '<p><a href="javascript:evil()"><img src="https://a/1.png"></a></p><p>mid</p>'
        '<div><img data-src="https://a/2.png"></div><img src="https://a/3.png"><iframe src="x"></iframe>')


def test_sanitize_removes_dangerous():
    out = html_tools.sanitize(HTML)
    for bad in ("<script", "onclick", "javascript:", "<iframe"):
        assert bad not in out
    assert 'src="https://a/2.png"' in out  # 지연 로딩 src 복원


def test_delete_keeps_structure():
    h = html_tools.prepare(HTML)
    out = html_tools.delete_images(h, ["i1"])
    assert "a/1.png" not in out and "<a" not in out and "<p></p>" not in out and "mid" in out


def test_reorder_and_move():
    h = html_tools.prepare(HTML)
    out = html_tools.reorder_images(h, ["i3", "i2", "i1"])
    assert [i["id"] for i in html_tools.list_images(out)] == ["i3", "i2", "i1"]
    assert [i["id"] for i in html_tools.list_images(html_tools.move_image(h, "i1", 1))] == ["i2", "i1", "i3"]
    with pytest.raises(ValueError):
        html_tools.reorder_images(h, ["i1"])


def test_replace_rejects_unsafe():
    h = html_tools.prepare(HTML)
    with pytest.raises(ValueError):
        html_tools.replace_image(h, "i1", "javascript:alert(1)")
    assert "images/x.png" in html_tools.replace_image(h, "i1", "images/x.png")


def test_store_url_parse_and_dedupe():
    assert store_search.store_url_from_link("https://smartstore.naver.com/abc/products/1") == "https://smartstore.naver.com/abc"
    assert store_search.store_url_from_link("https://smartstore.naver.com/main/products/1") is None
    assert store_search.store_url_from_link("https://cr.shopping.naver.com/x") is None
    items = [{"link": "https://smartstore.naver.com/abc/products/1", "mallName": "A", "title": "<b>x</b>"},
             {"link": "https://smartstore.naver.com/abc/products/2", "mallName": "A"}]
    assert len(store_search.parse_items("k", items)) == 1


def test_store_dedupe_and_badge_block():
    assert db.collect_store("A", "https://s/a", "k", "no_badge") is True
    assert db.collect_store("A", "https://s/a", "k", "no_badge") is False
    with pytest.raises(ValueError):
        db.collect_store("B", "https://s/b", "k", "has_badge")


def test_sample_flow_and_export():
    db.collect_store("S", "https://s/s", "k", "no_badge")
    sid = db.list_stores()[0]["id"]
    assert sample_data.load_sample_products(sid, 3, limit=2) == {"ok": 2, "banned": 0, "fail": 0, "total": 3}
    assert db.list_stores()[0]["best_status"] == "collected"
    rows = db.list_products(sid)
    assert len(rows) == 2 and "<script" not in rows[0]["detail_html_original"]
    p = rows[0]
    ims = html_tools.list_images(p["detail_html_edited"])
    assert len(ims) == 4 and all(images.local_file(p["id"], i["src"]) for i in ims)
    # 편집 → 저장 → 원본 보존
    db.save_edited(p["id"], html_tools.delete_images(p["detail_html_edited"], ["i1"]))
    p = db.get_product(p["id"])
    assert len(html_tools.list_images(p["detail_html_edited"])) == 3
    assert len(html_tools.list_images(p["detail_html_original"])) == 4
    z = zipfile.ZipFile(io.BytesIO(export.all_zip(db.list_products(sid))))
    names = z.namelist()
    assert "products.csv" in names and f"products/{p['id']}/detail.html" in names
    assert sum(n.endswith(".png") for n in names if n.startswith(f"products/{p['id']}/images/")) >= 1
    # 권한 미확인 상품은 이미지/HTML 제외
    db.set_rights(p["id"], False)
    z = zipfile.ZipFile(io.BytesIO(export.all_zip(db.list_products(sid))))
    assert f"products/{p['id']}/detail.html" not in z.namelist() and "SKIPPED_no_rights.txt" in z.namelist()
    with pytest.raises(PermissionError):
        export.single_zip(db.get_product(p["id"]))


def test_import_dedupe_keeps_edits_and_limit():
    db.collect_store("S", "https://s/s", "k", "unchecked")
    sid = db.list_stores()[0]["id"]
    items = [{"name": f"p{i}", "url": f"https://x/{i}", "price": "1,234원", "detail_html": '<img src="https://a/1.png">'} for i in range(5)]
    items.append({"name": "no", "url": "https://x/no", "is_best": "false"})
    assert best_import.import_items(sid, items, limit=3)["ok"] == 3
    p = db.list_products(sid)[0]
    assert p["price"] == 1234
    db.save_edited(p["id"], "<p>edited</p>")
    best_import.import_items(sid, items, limit=3)
    assert len(db.list_products(sid)) == 3 and db.get_product(p["id"])["detail_html_edited"] == "<p>edited</p>"


def test_image_validation():
    with pytest.raises(ValueError):
        images.save_image_bytes(1, b"not an image")


def test_banned_words_skip_products():
    db.collect_store("S", "https://s/s", "k", "no_badge")
    sid = db.list_stores()[0]["id"]
    db.add_banned_word("여성")
    items = [{"name": "여성 블라우스", "url": "https://x/1"}, {"name": "남성 셔츠", "url": "https://x/2"},
             {"name": "Women 여성용 원피스", "url": "https://x/3"}]
    r = best_import.import_items(sid, items)
    assert r["ok"] == 1 and r["banned"] == 2
    assert [p["name"] for p in db.list_products(sid)] == ["남성 셔츠"]
    db.remove_banned_word("여성")
    assert db.find_banned_word("여성 블라우스") is None


def test_blocked_store_not_discovered_or_collected():
    assert db.block_store("https://smartstore.naver.com/Bad/products/12?x=1", reason="수동") is True
    assert db.block_store("https://smartstore.naver.com/bad", reason="중복") is False  # 정규화로 같은 스토어
    assert db.is_blocked("smartstore.naver.com/bad/")
    assert db.add_discovered([{"keyword": "k", "store_name": "B", "store_url": "https://smartstore.naver.com/bad",
                               "source": "t"}, {"keyword": "k", "store_name": "G", "store_url": "https://smartstore.naver.com/good",
                                                "source": "t"}]) == 1
    with pytest.raises(ValueError):
        db.collect_store("B", "https://smartstore.naver.com/bad", "k", "no_badge")
    db.unblock_store("https://smartstore.naver.com/bad")
    assert db.collect_store("B", "https://smartstore.naver.com/bad", "k", "no_badge") is True

"""End-to-end conversion, PPTX generation, download and slide editing."""
import io

from pptx import Presentation as PptxPresentation

from tests.conftest import upload, wait_for_job


def _pres(client, job, kind):
    pid = next(p["id"] for p in job["presentations"] if p["kind"] == kind)
    return client.get(f"/api/presentations/{pid}").json()


def _download(client, pid):
    r = client.get(f"/api/presentations/{pid}/download")
    assert r.status_code == 200
    return r, PptxPresentation(io.BytesIO(r.content))


def _all_text(prs):
    out = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                out.append(shape.text_frame.text)
            if shape.has_table:
                out += [c.text for row in shape.table.rows for c in row.cells]
    return "\n".join(out)


def test_job_completes_with_two_presentations(completed_job):
    kinds = sorted(p["kind"] for p in completed_job["presentations"])
    assert kinds == ["detailed", "summary"]
    assert completed_job["progress"] == 100
    assert completed_job["provider_used"] == "mock"


def test_summary_presentation_structure(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    slides = pres["slides"]
    assert 8 <= len(slides) <= 12
    types = [s["type"] for s in slides]
    assert types[0] == "title"
    assert types[-1] == "conclusion"
    assert "takeaways" in types
    assert "definition" in types
    for s in slides:
        assert len(s["bullets"]) <= 5  # no overcrowded slides
    content = [s for s in slides if s["type"] in ("content", "process", "comparison", "definition")]
    assert all(s["source_pages"] for s in content if s["title"] != "What This Presentation Covers")


def test_detailed_presentation_structure(client, completed_job):
    summary = _pres(client, completed_job, "summary")
    pres = _pres(client, completed_job, "detailed")
    slides = pres["slides"]
    assert 18 <= len(slides) <= 24
    assert len(slides) > len(summary["slides"])
    types = [s["type"] for s in slides]
    assert types.count("section") >= 2
    assert "process" in types
    assert "comparison" in types
    assert "definition" in types
    terms = {d["term"] for s in slides for d in s["definitions"]}
    assert {"Photosynthesis", "Chlorophyll", "RuBisCO"} <= terms
    comp = next(s for s in slides if s["type"] == "comparison")
    assert comp["comparison"]["left"] and comp["comparison"]["right"]


def test_generated_content_is_grounded_in_source(client, completed_job, samples):
    import pymupdf

    import unicodedata

    raw = " ".join(p.get_text() for p in pymupdf.open(samples["text"]))
    source = " ".join(unicodedata.normalize("NFKC", raw).split()).lower()
    pres = _pres(client, completed_job, "detailed")
    for s in pres["slides"]:
        for d in s["definitions"]:
            assert d["term"].lower() in source, d["term"]
        assert all(1 <= p <= 3 for p in s["source_pages"])


def test_pptx_download_is_valid_and_editable(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    r, prs = _download(client, pres["id"])
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.presentationml")
    assert "summary.pptx" in r.headers["content-disposition"]
    assert len(prs.slides) == len(pres["slides"])
    text = _all_text(prs)
    assert pres["slides"][0]["title"] in text
    # slide numbers + source references in the footer
    assert f"2 / {len(pres['slides'])}" in text
    assert "Source:" in text
    # editable shapes, not pictures
    for slide in prs.slides:
        assert not any(sh.shape_type == 13 for sh in slide.shapes)  # 13 = PICTURE
    assert any(s.has_notes_slide and s.notes_slide.notes_text_frame.text for s in prs.slides)


def test_detailed_pptx_has_table_for_comparison(client, completed_job):
    pres = _pres(client, completed_job, "detailed")
    _, prs = _download(client, pres["id"])
    assert any(sh.has_table for slide in prs.slides for sh in slide.shapes)


def test_edit_slide_reflected_in_download(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    target = next(s for s in pres["slides"] if s["type"] == "content")
    r = client.patch(f"/api/presentations/{pres['id']}/slides/{target['id']}",
                     json={"title": "My Edited Title", "bullets": ["First custom point", "Second custom point"]})
    assert r.status_code == 200
    assert r.json()["title"] == "My Edited Title"
    _, prs = _download(client, pres["id"])
    text = _all_text(prs)
    assert "My Edited Title" in text
    assert "Second custom point" in text


def test_delete_and_reorder_slides(client, completed_job):
    pres = _pres(client, completed_job, "detailed")
    ids = [s["id"] for s in pres["slides"]]
    r = client.delete(f"/api/presentations/{pres['id']}/slides/{ids[2]}")
    assert r.status_code == 200
    assert len(r.json()["slides"]) == len(ids) - 1
    remaining = [s["id"] for s in r.json()["slides"]]
    new_order = [remaining[0], remaining[-1]] + remaining[1:-1]
    r = client.put(f"/api/presentations/{pres['id']}/slides/order", json={"order": new_order})
    assert r.status_code == 200
    assert [s["id"] for s in r.json()["slides"]] == new_order
    _, prs = _download(client, pres["id"])
    assert len(prs.slides) == len(new_order)
    # invalid order is rejected
    bad = client.put(f"/api/presentations/{pres['id']}/slides/order", json={"order": new_order[:-1]})
    assert bad.status_code == 422


def test_update_presentation_template_and_full_slide_list(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    slides = pres["slides"]
    slides[1]["bullets"] = ["Replaced via full update"]
    r = client.patch(f"/api/presentations/{pres['id']}", json={"template": "dark_academic", "slides": slides})
    assert r.status_code == 200
    assert r.json()["template"] == "dark_academic"
    assert r.json()["version"] > pres["version"]
    _, prs = _download(client, pres["id"])
    assert "Replaced via full update" in _all_text(prs)
    assert client.patch(f"/api/presentations/{pres['id']}", json={"template": "bogus"}).status_code == 422
    assert client.patch(f"/api/presentations/{pres['id']}", json={"slides": []}).status_code == 422


def test_regenerate_slide(client, completed_job):
    pres = _pres(client, completed_job, "detailed")
    target = next(s for s in pres["slides"] if s["type"] == "content" and s["source_pages"])
    r = client.post(f"/api/presentations/{pres['id']}/slides/{target['id']}/regenerate")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["id"] == target["id"]
    assert new["source_pages"] == target["source_pages"]
    assert new["bullets"]
    title_slide = pres["slides"][0]
    r = client.post(f"/api/presentations/{pres['id']}/slides/{title_slide['id']}/regenerate")
    assert r.status_code == 422


def test_add_slide(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    after = pres["slides"][1]["id"]
    r = client.post(f"/api/presentations/{pres['id']}/slides", params={"after": after},
                    json={"type": "content", "title": "Added slide", "bullets": ["Hello"]})
    assert r.status_code == 201
    assert r.json()["slides"][2]["title"] == "Added slide"


def test_cannot_delete_last_slide(client, samples):
    doc = upload(client, samples["text"]).json()
    job = wait_for_job(client, client.post("/api/jobs", json={"document_id": doc["id"], "kinds": ["summary"]}).json()["id"])
    assert len(job["presentations"]) == 1
    pid = job["presentations"][0]["id"]
    slides = client.get(f"/api/presentations/{pid}").json()["slides"]
    for s in slides[:-1]:
        assert client.delete(f"/api/presentations/{pid}/slides/{s['id']}").status_code == 200
    assert client.delete(f"/api/presentations/{pid}/slides/{slides[-1]['id']}").status_code == 422


def test_unknown_presentation_404(client):
    assert client.get("/api/presentations/nope").status_code == 404
    assert client.get("/api/presentations/nope/download").status_code == 404

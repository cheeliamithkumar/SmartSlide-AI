"""Diagrams: roadmap, concept maps, cycles - composition, rendering and editing."""
import io

from pptx import Presentation as PptxPresentation

from app.schemas import Diagram, DiagramNode, KeyPoint, Slide, SlideType, Topic
from app.services.content_processor import key_terms, short_label
from app.services.pptx_builder import render_presentation


def _pres(client, job, kind):
    pid = next(p["id"] for p in job["presentations"] if p["kind"] == kind)
    return client.get(f"/api/presentations/{pid}").json()


def _connectors(prs):
    return sum(1 for s in prs.slides for sh in s.shapes if sh.shape_type == 9 or sh.__class__.__name__ == "Connector")


def test_summary_has_roadmap_big_picture_and_concept_maps(client, completed_job):
    slides = _pres(client, completed_job, "summary")["slides"]
    diagrams = [s for s in slides if s["type"] == "diagram"]
    kinds = {s["diagram"]["kind"] for s in diagrams}
    assert {"timeline", "mindmap"} <= kinds
    roadmap = next(s for s in diagrams if s["diagram"]["kind"] == "timeline")
    assert len(roadmap["diagram"]["nodes"]) >= 3
    assert any(s["type"] == "content" and s["diagram"] for s in slides)


def test_cyclic_process_rendered_as_cycle(client, completed_job):
    slides = _pres(client, completed_job, "detailed")["slides"]
    calvin = next(s for s in slides if s["type"] == "process" and "Calvin" in s["title"])
    assert calvin["diagram"]["kind"] == "cycle"
    light = next(s for s in slides if s["type"] == "process" and "Light" in s["title"])
    assert light["diagram"]["kind"] == "flow"


def test_diagrams_are_native_editable_shapes(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    r = client.get(f"/api/presentations/{pres['id']}/download")
    prs = PptxPresentation(io.BytesIO(r.content))
    assert _connectors(prs) >= 5  # connector lines of concept maps / cycles
    roadmap_idx = next(i for i, s in enumerate(pres["slides"]) if s["type"] == "diagram")
    texts = [sh.text_frame.text for sh in prs.slides[roadmap_idx].shapes if sh.has_text_frame]
    for node in pres["slides"][roadmap_idx]["diagram"]["nodes"]:
        assert node["label"] in texts
    assert not any(sh.shape_type == 13 for s in prs.slides for sh in s.shapes)  # no pictures


def test_edit_diagram_reflected_in_download(client, completed_job):
    pres = _pres(client, completed_job, "summary")
    target = next(s for s in pres["slides"] if s["type"] == "diagram")
    diagram = {"kind": "mindmap", "center": "Edited Centre", "nodes": [{"label": "Alpha"}, {"label": "Beta"}, {"label": "Gamma"}]}
    r = client.patch(f"/api/presentations/{pres['id']}/slides/{target['id']}", json={"diagram": diagram})
    assert r.status_code == 200 and r.json()["diagram"]["center"] == "Edited Centre"
    prs = PptxPresentation(io.BytesIO(client.get(f"/api/presentations/{pres['id']}/download").content))
    texts = {sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame}
    assert {"Edited Centre", "Alpha", "Beta", "Gamma"} <= texts
    # removing a concept map from a content slide
    content = next(s for s in pres["slides"] if s["type"] == "content" and s["diagram"])
    r = client.patch(f"/api/presentations/{pres['id']}/slides/{content['id']}", json={"diagram": None})
    assert r.json()["diagram"] is None


def test_key_terms_prefer_definitions_and_skip_title():
    t = Topic(title="The Chloroplast", definitions=[
        {"term": "Chloroplast", "definition": "organelle", "pages": [1]},
        {"term": "Granum", "definition": "a stack of thylakoids", "pages": [1]}],
        key_points=[KeyPoint(text="Thylakoid membranes hold chlorophyll pigment."),
                    KeyPoint(text="Chlorophyll pigment absorbs light in thylakoid membranes.")])
    terms = key_terms(t)
    assert terms[0] == "Granum"
    assert "Chloroplast" not in terms
    assert any("Thylakoid" in x or "Chlorophyll" in x for x in terms)
    assert short_label("Factors Affecting the Rate of Photosynthesis").endswith("…")


def test_render_all_diagram_kinds(tmp_path):
    nodes = [DiagramNode(label=f"Node {i}", detail="detail") for i in range(5)]
    slides = [
        Slide(type=SlideType.diagram, title="Map", diagram=Diagram(kind="mindmap", center="Centre", nodes=nodes)),
        Slide(type=SlideType.diagram, title="Road", diagram=Diagram(kind="timeline", nodes=nodes)),
        Slide(type=SlideType.diagram, title="Loop", diagram=Diagram(kind="cycle", nodes=nodes)),
        Slide(type=SlideType.process, title="Cycle", steps=["a", "b", "c", "d"], diagram=Diagram(kind="cycle")),
        Slide(type=SlideType.content, title="Split", bullets=["x", "y"], diagram=Diagram(kind="mindmap", center="C", nodes=nodes[:3])),
    ]
    for theme in ("modern_education", "dark_academic"):
        prs = PptxPresentation(str(render_presentation(slides, theme, "d.pdf", "summary", tmp_path / f"{theme}.pptx")))
        assert len(prs.slides) == 5

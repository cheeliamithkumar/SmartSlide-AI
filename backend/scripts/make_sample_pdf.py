"""Generate sample educational PDFs used for demos and tests.

Usage:
    python scripts/make_sample_pdf.py            # writes samples/*.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"

CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 24pt; color: #1e3a8a; margin-bottom: 6pt; }
h2 { font-size: 16pt; color: #1e3a8a; margin-top: 14pt; }
p { margin-bottom: 7pt; text-align: justify; }
li { margin-bottom: 3pt; }
"""

PHOTOSYNTHESIS_HTML = """
<h1>Photosynthesis: How Plants Make Food</h1>
<p>This chapter introduces photosynthesis, the process that supports almost all life on Earth.
We examine where it happens, the two main stages, the factors that affect its rate and how it differs
between plant groups. By the end of the chapter, students should be able to describe each stage and explain
why photosynthesis is important for ecosystems.</p>

<h2>What Is Photosynthesis?</h2>
<p>Photosynthesis is the process by which green plants, algae and some bacteria convert light energy into
chemical energy stored in glucose. The overall reaction uses carbon dioxide and water as raw materials and
releases oxygen as a by-product. The simplified equation is 6CO2 + 6H2O + light energy → C6H12O6 + 6O2.</p>
<p>Photosynthesis is important because it produces the oxygen that most organisms need for respiration.
It also forms the base of nearly every food chain, since plants are primary producers. In addition,
photosynthesis removes carbon dioxide from the atmosphere, which helps regulate the global climate.</p>
<p>A producer is an organism that makes its own food from simple inorganic substances. For example, grass in a
meadow and phytoplankton in the ocean are both producers that rely on photosynthesis.</p>

<h2>The Chloroplast</h2>
<p>A chloroplast is an organelle found in plant cells where photosynthesis takes place. Each chloroplast is
surrounded by a double membrane and contains stacks of disc-shaped sacs called thylakoids. A stack of thylakoids
is called a granum, and the fluid surrounding the grana is known as the stroma.</p>
<p>Chlorophyll is a green pigment that absorbs light energy, mainly in the blue and red parts of the spectrum.
Chlorophyll reflects green light, which is why leaves appear green. Chlorophyll molecules are embedded in the
thylakoid membranes, where the light-dependent reactions occur.</p>
<p>Leaves are well adapted for photosynthesis. They are broad and thin to absorb light and allow gases to
diffuse quickly. Tiny pores called stomata on the underside of the leaf allow carbon dioxide to enter and
oxygen to leave.</p>

<h2>Light-Dependent Reactions</h2>
<p>The light-dependent reactions take place in the thylakoid membranes and require direct light energy.
These reactions convert light energy into chemical energy in the form of ATP and NADPH. Water molecules are
split during this stage, which releases oxygen gas.</p>
<p>The light-dependent reactions follow a clear sequence of steps:</p>
<ol>
<li>Chlorophyll in photosystem II absorbs light and excites electrons to a higher energy level.</li>
<li>Water molecules are split by photolysis, releasing oxygen, hydrogen ions and electrons.</li>
<li>Excited electrons move along the electron transport chain, pumping hydrogen ions into the thylakoid.</li>
<li>ATP synthase uses the flow of hydrogen ions to produce ATP.</li>
<li>Photosystem I re-energises the electrons, which are used to reduce NADP+ to NADPH.</li>
</ol>
<p>Photolysis is defined as the splitting of water molecules using light energy. It is the source of all the
oxygen released by photosynthesis.</p>

<h2>The Calvin Cycle</h2>
<p>The Calvin cycle, also called the light-independent reactions, takes place in the stroma. It does not need
light directly, but it depends on the ATP and NADPH produced by the light-dependent reactions. The cycle fixes
carbon dioxide into organic molecules that are used to build glucose.</p>
<p>First, the enzyme RuBisCO combines carbon dioxide with a five-carbon molecule called RuBP. Then the unstable
product splits into two three-carbon molecules. Next, ATP and NADPH are used to convert these molecules into
G3P, a simple sugar. Finally, most of the G3P is recycled to regenerate RuBP so the cycle can continue.</p>
<p>RuBisCO is an enzyme that catalyses the first step of carbon fixation. It is thought to be the most abundant
protein on Earth. Carbon fixation is the process of converting inorganic carbon dioxide into organic compounds.</p>

<h2>Factors Affecting the Rate of Photosynthesis</h2>
<p>Several environmental factors affect how quickly photosynthesis takes place. A limiting factor is a factor
that restricts the rate of a process when it is in short supply. Increasing a limiting factor increases the
rate until another factor becomes limiting.</p>
<ul>
<li>Light intensity: higher light intensity increases the rate until the plant reaches its maximum capacity.</li>
<li>Carbon dioxide concentration: more carbon dioxide speeds up the Calvin cycle up to a certain point.</li>
<li>Temperature: enzymes work faster when warmer, but very high temperatures denature them.</li>
<li>Water availability: lack of water causes stomata to close, reducing carbon dioxide uptake.</li>
</ul>
<p>For instance, greenhouse farmers often increase carbon dioxide levels and use artificial lighting to raise
crop yields. Such controlled conditions show how understanding limiting factors has practical value in
agriculture.</p>

<h2>Differences Between C3 and C4 Plants</h2>
<p>Plants can be grouped by the way they fix carbon. This section compares C3 plants and C4 plants.</p>
<p>C3 plants fix carbon dioxide directly through the Calvin cycle in mesophyll cells. C3 plants include wheat,
rice and soybeans. C3 plants lose efficiency in hot, dry conditions because of photorespiration.
C3 plants are most common in cool and moist climates.</p>
<p>C4 plants first fix carbon dioxide into a four-carbon compound in mesophyll cells. C4 plants include maize,
sugarcane and sorghum. C4 plants concentrate carbon dioxide in bundle-sheath cells, which reduces
photorespiration. C4 plants grow efficiently in hot and sunny environments.</p>
<p>Photorespiration is a wasteful process in which RuBisCO binds oxygen instead of carbon dioxide.
It reduces the efficiency of photosynthesis, especially at high temperatures.</p>

<h2>Photosynthesis and Cellular Respiration</h2>
<p>Photosynthesis and cellular respiration are complementary processes. Photosynthesis stores energy in
glucose, while cellular respiration releases that energy as ATP for the cell. The products of one process are
the raw materials of the other: oxygen and glucose from photosynthesis are used in respiration, and the carbon
dioxide and water from respiration are used in photosynthesis.</p>
<p>Together, these two processes form a cycle that moves carbon and energy through ecosystems. Understanding
this relationship helps explain the carbon cycle and the balance of gases in the atmosphere.</p>

<h2>Summary</h2>
<p>Photosynthesis converts light energy into chemical energy in chloroplasts. The light-dependent reactions
produce ATP, NADPH and oxygen, while the Calvin cycle uses that energy to fix carbon dioxide into sugars.
The rate of photosynthesis depends on limiting factors such as light, carbon dioxide and temperature.
C4 plants are adapted to hot climates, while C3 plants dominate cooler regions. Photosynthesis is essential
for food production, oxygen supply and climate regulation.</p>
"""


def html_to_pdf(html: str, path: Path, title: str) -> Path:
    story = pymupdf.Story(html=html, user_css=CSS)
    writer = pymupdf.DocumentWriter(str(path))
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (60, 60, -60, -60)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    # add metadata + page numbers
    doc = pymupdf.open(path)
    doc.set_metadata({"title": title, "author": "SmartSlide AI Samples"})
    for i, page in enumerate(doc, start=1):
        page.insert_text((page.rect.width / 2 - 10, page.rect.height - 30), str(i), fontsize=9)
    doc.saveIncr()
    doc.close()
    return path


def make_scanned(src: Path, dest: Path, pages: int = 2) -> Path:
    """Rasterise pages into images (simulates a scanned document without a text layer)."""
    with pymupdf.open(src) as doc, pymupdf.open() as out:
        for i in range(min(pages, doc.page_count)):
            pix = doc[i].get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
            page = out.new_page(width=doc[i].rect.width, height=doc[i].rect.height)
            page.insert_image(page.rect, stream=pix.tobytes("jpeg", jpg_quality=70))
        out.save(dest)
    return dest


def make_empty(dest: Path, pages: int = 2) -> Path:
    with pymupdf.open() as out:
        for _ in range(pages):
            out.new_page()
        out.save(dest)
    return dest


def main(out_dir: Path = OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = html_to_pdf(PHOTOSYNTHESIS_HTML, out_dir / "photosynthesis.pdf", "Photosynthesis: How Plants Make Food")
    make_scanned(p, out_dir / "photosynthesis_scanned.pdf")
    make_empty(out_dir / "empty.pdf")
    print("Wrote samples to", out_dir)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)

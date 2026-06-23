"""Build the local-LLM deck natively into the Data Society pptx template.

Opens the brand template (keeps its masters/layouts/theme/logo), clears the 4 sample
slides, then emits our deck using the template's own layouts so everything inherits the
Data Society fonts/colors. Tables are styled with the brand palette; the two side-by-side
animations embed as gifs (animate in Google Slides; static first-frame in PowerPoint).

Run: python3 build_pptx.py
Out: local-llm-datasociety.pptx
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pathlib import Path

TPL = "/Users/john.connolly/Downloads/Data Society slide template.pptx"
REPO = Path("/Users/john.connolly/tmp-projects/local-llm")
OUT = REPO / "local-llm-datasociety.pptx"

# brand palette (from theme1.xml)
DK     = RGBColor(0x25, 0x11, 0x44)
PURPLE = RGBColor(0x83, 0x5B, 0xA3)
DK2    = RGBColor(0x41, 0x2B, 0x71)
RED    = RGBColor(0xFF, 0x35, 0x0E)
YELLOW = RGBColor(0xFF, 0xED, 0x4C)
LIGHT  = RGBColor(0xF1, 0xF1, 0xF4)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
GREEN  = RGBColor(0x2E, 0x7D, 0x32)

prs = Presentation(TPL)
SW, SH = prs.slide_width, prs.slide_height
LAY = {l.name: l for l in prs.slide_masters[0].slide_layouts}        # white content master
PURPLE_LAY = {l.name: l for l in prs.slide_masters[1].slide_layouts}  # purple section master (#251144)

# clear the 4 sample slides, drop the relationship too, else the orphaned slide
# parts stay in the package and collide with new slideN.xml names (duplicate zip entries).
sldIdLst = prs.slides._sldIdLst
for sldId in list(sldIdLst):
    rId = sldId.get(qn("r:id"))
    sldIdLst.remove(sldId)
    prs.part.drop_rel(rId)


def _md_runs(p, text):
    """Add runs to paragraph p, honoring **bold** and `code` markers."""
    import re
    parts = re.split(r"(\*\*.+?\*\*|`.+?`)", text)
    for part in parts:
        if not part:
            continue
        r = p.add_run()
        if part.startswith("**") and part.endswith("**"):
            r.text = part[2:-2]; r.font.bold = True
        elif part.startswith("`") and part.endswith("`"):
            r.text = part[1:-1]; r.font.name = "Consolas"
        else:
            r.text = part


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def _no_autofit(tf):
    """Kill TEXT_TO_FIT_SHAPE autofit so every app renders the same explicit size."""
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE


def _style_title(ph, size=30):
    _no_autofit(ph.text_frame)
    for p in ph.text_frame.paragraphs:
        p.font.size = Pt(size)
        for r in p.runs:
            r.font.size = Pt(size)


def _fmt_body(tf, lvl_sizes={0: 18, 1: 15}):
    _no_autofit(tf)
    for p in tf.paragraphs:
        sz = Pt(lvl_sizes.get(p.level, 15))
        p.font.size = sz
        p.space_after = Pt(6)
        for r in p.runs:
            r.font.size = sz


def title_slide(title, subtitle, byline="", tldr="", notes=""):
    s = prs.slides.add_slide(LAY["Title Slide No Image"])
    def place(ph, left, top, w, h):
        ph.left, ph.top, ph.width, ph.height = Inches(left), Inches(top), Inches(w), Inches(h)
    # title
    s.placeholders[0].text = title
    place(s.placeholders[0], 0.9, 1.9, 10.2, 1.5)
    _style_title(s.placeholders[0], size=36)
    # snappy one-line subtitle
    if len(s.placeholders) > 1:
        s.placeholders[1].text = subtitle
        place(s.placeholders[1], 0.9, 3.4, 10.2, 0.6)
        tf = s.placeholders[1].text_frame
        _no_autofit(tf)
        for p in tf.paragraphs:
            p.font.size = Pt(20); p.space_after = Pt(0)
            for r in p.runs:
                r.font.size = Pt(20); r.font.color.rgb = DK2
    # TL;DR as a separate styled callout box (brand tint, red label, bold verdicts)
    if tldr:
        box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                 Inches(0.9), Inches(4.2), Inches(10.2), Inches(1.15))
        box.fill.solid(); box.fill.fore_color.rgb = RGBColor(0xF1, 0xEC, 0xF7)
        box.line.fill.background()
        box.shadow.inherit = False
        tf = box.text_frame; _no_autofit(tf)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.3); tf.margin_right = Inches(0.3)
        p = tf.paragraphs[0]
        lab = p.add_run(); lab.text = "TL;DR   "
        lab.font.bold = True; lab.font.size = Pt(19); lab.font.color.rgb = RED
        _md_runs(p, tldr)
        for r in p.runs[1:]:
            r.font.size = Pt(18); r.font.color.rgb = DK
    # byline: bottom-RIGHT (opposite the bottom-left footer logo), right-aligned, small.
    # multi-line via \n.
    if byline:
        tb = s.shapes.add_textbox(Inches(4.6), Inches(5.7), Inches(6.5), Inches(0.85))
        tf = tb.text_frame; _no_autofit(tf)
        for i, line in enumerate(byline.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.RIGHT
            r = p.add_run(); r.text = line
            r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = DK2
    _notes(s, notes)
    return s


def bullets_slide(title, items, notes=""):
    """items: list of (text, level)."""
    s = prs.slides.add_slide(LAY["OBJECT"])  # white content layout WITH the DS logo
    s.placeholders[0].text = title
    _style_title(s.placeholders[0])
    tf = s.placeholders[1].text_frame
    tf.clear()
    for i, (text, lvl) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = lvl
        _md_runs(p, text)
    _fmt_body(tf)
    _notes(s, notes)
    return s


def _title_only(title):
    s = prs.slides.add_slide(LAY["TITLE_ONLY"])  # white title-only layout WITH the DS logo
    s.placeholders[0].text = title
    _style_title(s.placeholders[0])
    return s


def table_slide(title, headers, rows, caption="", notes="", col_w=None,
                top=1.7, font=13):
    s = _title_only(title)
    nrow, ncol = len(rows) + 1, len(headers)
    width = SW - Inches(1.2)
    left = Inches(0.6)
    height = Inches(0.5) * nrow
    gfx = s.shapes.add_table(nrow, ncol, left, Inches(top), width, height)
    tbl = gfx.table
    if col_w:
        total = sum(col_w)
        for ci, w in enumerate(col_w):
            tbl.columns[ci].width = int((SW - Inches(1.2)) * w / total)
    # header
    for ci, h in enumerate(headers):
        c = tbl.cell(0, ci)
        c.fill.solid(); c.fill.fore_color.rgb = PURPLE
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = c.text_frame; tf.clear(); p = tf.paragraphs[0]
        r = p.add_run(); r.text = h
        r.font.bold = True; r.font.color.rgb = WHITE; r.font.size = Pt(font + 1)
        r.font.name = "Arial"
    # body
    for ri, row in enumerate(rows, start=1):
        for ci, val in enumerate(row):
            c = tbl.cell(ri, ci)
            c.fill.solid(); c.fill.fore_color.rgb = WHITE if ri % 2 else LIGHT
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = c.text_frame; tf.clear(); p = tf.paragraphs[0]
            bold = val.startswith("**") and val.endswith("**")
            txt = val[2:-2] if bold else val
            r = p.add_run(); r.text = txt
            r.font.size = Pt(font); r.font.color.rgb = DK; r.font.name = "Arial"
            r.font.bold = bold
    if caption:
        tb = s.shapes.add_textbox(Inches(0.6), Inches(top) + height + Inches(0.2),
                                  SW - Inches(1.2), Inches(1.1))
        _no_autofit(tb.text_frame)
        p = tb.text_frame.paragraphs[0]
        _md_runs(p, caption)
        for r in p.runs:
            r.font.size = Pt(13); r.font.color.rgb = DK2
    _notes(s, notes)
    return s


def image_slide(title, img, notes="", width_in=9.0, sub=""):
    s = _title_only(title)
    pic = s.shapes.add_picture(str(img), 0, 0, width=Inches(width_in))
    # clamp so it never overflows the content band (1.55in down to ~6.5in)
    max_h = Inches(4.55)
    if pic.height > max_h:
        scale = max_h / pic.height
        pic.width = int(pic.width * scale); pic.height = int(pic.height * scale)
    pic.left = int((SW - pic.width) / 2)
    pic.top = Inches(1.55)
    if sub:
        sub_top = pic.top + pic.height + Inches(0.06)
        tb = s.shapes.add_textbox(Inches(0.6), sub_top, SW - Inches(1.2), Inches(0.4))
        p = tb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        _md_runs(p, sub)
        for r in p.runs:
            r.font.size = Pt(13); r.font.color.rgb = DK2
    _notes(s, notes)
    return s


def section_slide(kicker, title, notes=""):
    """Full-purple section divider (uses the purple master) with a yellow kicker + white title.
    Weaves the template's white/purple/white rhythm between acts."""
    lay = PURPLE_LAY.get("TITLE_ONLY") or PURPLE_LAY.get("Title Only - No Logo") \
        or list(PURPLE_LAY.values())[1]
    s = prs.slides.add_slide(lay)
    kb = s.shapes.add_textbox(Inches(0.9), Inches(2.55), Inches(10.2), Inches(0.6))
    _no_autofit(kb.text_frame)
    kr = kb.text_frame.paragraphs[0].add_run()
    kr.text = kicker; kr.font.size = Pt(20); kr.font.bold = True; kr.font.color.rgb = YELLOW
    tb = s.shapes.add_textbox(Inches(0.9), Inches(3.15), Inches(10.2), Inches(1.9))
    _no_autofit(tb.text_frame)
    tr = tb.text_frame.paragraphs[0].add_run()
    tr.text = title; tr.font.size = Pt(40); tr.font.bold = True; tr.font.color.rgb = WHITE
    _notes(s, notes)
    return s


B = lambda t: (t, 0)   # level-0 bullet
B1 = lambda t: (t, 1)  # level-1 bullet

# ============================ THE DECK ============================
title_slide(
    "Can a local LLM replace cloud Claude Code?",
    "Three weeks, three machines: from a Raspberry Pi to a $4,676 Mac Studio.",
    tldr="bounded coding **ties the frontier, free**. Open-ended repos: **still cloud**.",
    byline="John Connolly, Lead Product Engineer & tinkerer\nJune 2026",
    notes="0:30 | Open cold, don't read the title. Say: 'Three weeks ago I asked a simple question, could I stop paying for cloud Claude Code and run the whole thing on hardware in my house. I spent $4,676 finding out.' Then point at the TL;DR box: the answer is a qualified yes, and the qualification is the entire talk. For bounded coding, local ties the frontier and it's free. For open-ended repo work, you still want cloud. Everything after this slide is me earning that one sentence with data. Set the tone: this is a measurement talk, not a vibes talk, every claim has a benchmark behind it.")

table_slide("Agenda, where we're going (~29 min)",
    ["Act", "Topic", "~min"],
    [["1", "The trip: Raspberry Pi, Air, Studio (and why each failed or worked)", "7"],
     ["2", "Reality check: you can't buy parity. The $4,676 call", "5"],
     ["3", "The measured verdict: one-shot, agent loop, the build test", "12"],
     ["4", "Economics, recommendation, honest caveats", "5"]],
    notes="0:30 | Don't dwell. Four acts. Act 1 is the journey across three machines, that's the story. Act 2 is the uncomfortable truth that you can't buy your way to parity. Act 3 is the heart, the actual benchmarks, and it's where the surprise lives, so flag it now: 'Act 3 is the part that changed my mind.' Act 4 is the money and the recommendation. Tell them you'll leave time for Q&A. If you're running long, Act 1 is the part to compress.",
    col_w=[1, 7, 1.4])

section_slide("ACT ONE", "The route: three machines",
    notes="5 sec | Quick beat, don't linger on dividers. Say: 'Act One, the route. How I got from a thirty-five-dollar Raspberry Pi to a forty-six-hundred-dollar Mac Studio, and what each machine taught me.' Then move.")

bullets_slide("The question",
    [B("Can I run a 'SOTA' local LLM at home, usable as my Claude Code backend, and stop paying for cloud?"),
     B("Two things to find out:"),
     B1("Is it possible, and at what hardware/cost?"),
     B1("Is it good enough, measured, not vibes?")],
    "1:00 | Two real questions here. 'Possible' turned out to be the easy one, spoiler, yes, it works on modest hardware. The hard one is 'good enough,' and the whole talk hinges on the fact that good-enough splits in two: good enough for a single bounded task, versus good enough for a long multi-turn agent loop. Those give opposite answers. Plant the seed: 'hold onto the idea that good enough depends on which good.' And the last bullet is the north star, measured, not vibes. Every number you'll see came from a script, not a feeling.")

table_slide("The route: three machines, three verdicts",
    ["Stop", "Hardware", "Verdict"],
    [["1", "Raspberry Pi 5 + AI HAT+ 2 (Hailo-10H)", "Dead end: no API for Claude Code to connect to (~2B / small context anyway)"],
     ["2", "MacBook Air M2 16GB ('Maral')", "Did the grunt work (~5 hrs). qwen3:14b ~10 tok/s, kinda slow"],
     ["3", "The tuning wall", "think:false = ~3x; quant sweep; prompt slim"],
     ["4", "Reality check", "Frontier parity NOT purchasable locally at any price"],
     ["5", "Mac Studio M3 Ultra 96GB ($4,676)", "Ties Opus on coding @ 68 tok/s, $0/mo"]],
    notes="1:30 | This is the map, don't read every cell, walk it. Stop one, the Raspberry Pi, total dead end, I'll explain why in two slides. Stop two, a spare MacBook Air I call Maral, that's where I learned everything even though it only ran a few hours. Stop three, I hit a tuning wall and found the single best speedup of the whole project. Stop four, the reality check, the thing you cannot buy at any price. Stop five, the Mac Studio, which finally ties Opus on coding at sixty-eight tokens a second for zero dollars a month. The takeaway line: the lessons are in the trip, not just the destination.",
    col_w=[0.7, 3.2, 5.5], font=12)

bullets_slide("Dead end #1: the AI HAT+ 2 couldn't talk to Claude Code",
    [B("The AI HAT+ 2 (Hailo-10H, 40-TOPS (tera-operations per second) NPU (neural processing unit), 8GB on-board) is a real generative-AI accelerator, it runs small LLMs on-chip, not just vision."),
     B("**The wall:** it speaks Hailo's own runtime, not an Anthropic- or Ollama-style endpoint. Claude Code had nothing to connect to, so the tool-use loop never wired up."),
     B("Even past that: Hailo's supported models are ~1-2B class with a small context, far short of the 64k+ a coding agent needs."),
     B("**Lesson:** the blocker was the API surface, not the silicon. A brilliant accelerator with no drop-in endpoint is still a dead end for an agent.")],
    "1:00 | The cautionary tale, and get the framing right because it's a common mistake. The board is genuinely capable: the AI HAT+ 2 with a Hailo-10H is a real generative-AI accelerator, forty TOPS, eight gigs of its own memory, it runs small language models on-chip. So why a dead end? Not the silicon, the plumbing. It only speaks Hailo's own runtime, there's no Anthropic- or Ollama-style endpoint, so Claude Code had literally nothing to connect to, the tool-use loop never wired up. And even if you solved that, the models Hailo supports are tiny, one-to-two-billion class with a small context, nowhere near the sixty-four-thousand-plus a coding agent needs. The lesson that travels: the blocker was the API surface, not the chip. A brilliant accelerator with no door in is still a dead end. Tee up the next slide: even if it had an endpoint, here's why it'd still be too small.")

bullets_slide("Showing the work: it'd be too small anyway",
    [B("Integration was the real wall (last slide). But say it had an endpoint, the ceiling is still low. Napkin math:"),
     B("The model lives in the Hailo-10H's 8GB on-board memory. Max model size is roughly on-board RAM / bytes-per-parameter."),
     B1("At Q4 (4-bit quantization) that's ~0.5 bytes/param: 8GB caps you near ~10B in theory, and Hailo's supported set is smaller in practice, ~1-2B class."),
     B1("Decode speed follows the same rule: tok/s ~ memory bandwidth / active model bytes (the same formula that makes the Mac Studio fast later)."),
     B("**Bottom line:** a ~1-2B model with a small context can't be a 64k-context coding agent. Right silicon, wrong job."),
     B("Honest caveat: I didn't push further, the Mac path was clearly better, so this is back-of-envelope, not an exhaustive benchmark.")],
    "1:30 | The show-our-work slide, but be honest about what it is. The real wall was integration, last slide, so this is the 'even if I'd solved that' argument. The model has to live in the Hailo's eight gigs of on-board memory, and a rough ceiling is on-board RAM divided by bytes-per-parameter. At four-bit that's about half a byte per parameter, so eight gigs tops out near a ten-billion model on paper, but Hailo's actually-supported set is smaller, one-to-two-billion class. Speed follows the same memory-bandwidth rule you'll see again for the Mac Studio. Bottom line, a one-to-two-billion model with a small context just can't be a sixty-four-thousand-context coding agent, right silicon, wrong job. Then say the honest part out loud: I didn't exhaustively benchmark this, the Mac path was obviously better, so this is napkin math, not a deep study.")

bullets_slide("Maral: a spare 16GB Air, doing the most",
    [B("qwen3:8b / :14b via Ollama's Anthropic endpoint, wired into Claude Code with one env block"),
     B("Plot twists:"),
     B1("Tool-use was already at parity with cloud. The worry? Misplaced."),
     B1("Real pain wasn't the model, it was memory bandwidth and the WiFi driver crashing under load (rude)"),
     B("16GB is the floor, not a platform. Ran on vibes and about 5 hours of uptime.")],
    "1:30 | The workhorse chapter, keep it light. A spare sixteen-gig MacBook Air, I call it Maral, carried the whole proof of concept, and honestly it only ran about five hours total. Two surprises worth landing. One, tool-use, the thing I was most worried about, just worked, parity with cloud out of the box. Two, the pain was never the model's intelligence, it was the memory bus being slow and the WiFi driver literally crashing under memory pressure. So the lesson: sixteen gigs is the floor where you can prove the idea, but it is not a platform you can live on, it ran on vibes. That sets up the obvious question: okay, what do I actually buy?")

bullets_slide("The single best tuning knob: kill the thinking tax",
    [B("Qwen3 emits a <think> trace before every answer."),
     B("A coding answer needing 80 tokens cost 600, 8x the work."),
     B("`CLAUDE_CODE_DISABLE_THINKING=1`   (or {\"think\": false})"),
     B("**~3x speedup from one env var.** Everything else I tuned for a week? Secondary.")],
    "1:30 | If they remember one config line from the whole talk, it's this one. Qwen3 is a reasoning model, it writes a hidden think trace before every answer. For chat that's great, for an agent doing lots of tiny tool calls it's pure overhead, an eighty-token edit was costing six hundred tokens. One environment variable turns it off and you get roughly a three-times real-world speedup. Audience beat: 'guess how much speedup all my fancy tuning, the quant sweeps, the cache settings, actually bought me. Now guess how much this one line bought me.' Everything else was a rounding error next to this.")

section_slide("ACT TWO", "Reality check & the $4,676 call",
    notes="5 sec | Quick beat. Say: 'Act Two. I've got a working setup, now the uncomfortable part, how good can local actually get, and can you just buy your way to the top? Short answer, no.' Move.")

table_slide("Reality check: you can't buy frontier parity",
    ["Tier", "Best model", "SWE-bench", "Gap to Opus 4.8"],
    [["96GB Mac", "qwen3-coder:30b", "~77%", "−12"],
     ["192GB", "qwen3-235b Q4", "~86%", "−3"],
     ["**512GB ($11.5K)**", "**DeepSeek-V3 Q4**", "**~88%**", "**−4 (still short!)**"],
     ["Cloud", "**Opus 4.8**", "**88.6%**", "0"]],
    "Open weights trail the closed frontier by 6-12 months. **The only thing that gives you Opus quality is Opus.**",
    "2:00 | Slow down, this is the intellectual hinge of the talk. The myth I'm busting: 'just buy a big enough Mac and you'll match Opus.' It's false. Walk the table from the bottom. Even an eleven-and-a-half-thousand-dollar, five-hundred-twelve-gig machine running the best open model on earth is still four points behind Opus on the benchmark. You cannot spend your way to parity at home, full stop. The structural reason: open-weight models trail the closed frontier by roughly six to twelve months, it's a moving target, by the time open catches today's Opus, Opus has moved. So the line to land, slowly: the only thing that gives you Opus quality is Opus. This reframes the whole buying decision, which is the next slide.",
    col_w=[2, 2.6, 1.6, 2.4], font=13)

bullets_slide("So the decision is about how close, not parity",
    [B("Don't chase a number that isn't for sale"),
     B("**Buy hardware for the 80%; keep an explicit `claude-cloud` for the 20%**"),
     B("Denominate the choice in your actual task mix, not dollars or principle"),
     B("Sweet spot for one dev: **~$4-5K, one Mac Studio, 96GB**")],
    "1:00 | The reframe. Once parity is off the table, the question changes from 'can I match it' to 'how close can I get for sensible money, and what do I do about the gap.' The answer is hybrid: buy hardware for the eighty percent of work you do every day, keep a cloud escape hatch for the hard twenty percent. The discipline: decide on your actual task mix, not on ideology and not on the sticker price. Don't buy local because it's cool, don't avoid it because cloud is easier. And I'll say the number out loud now so it's not a surprise later: for one developer, the sweet spot is about four to five thousand dollars, a single ninety-six-gig Mac Studio.")

_buy = bullets_slide("The buy: $4,676 for a used M3 Ultra 96GB",
    [B("Apple-direct was 4 months backordered (M3 Ultra was EOL'd)"),
     B("Every reseller went dry within days, only the grey market left"),
     B("Verified a sealed eBay unit (buyer protection, 99.3% seller); $4,299 + tax. Wiring $4,676 to a stranger is its own personality test."),
     B("**Lesson:** a just-discontinued machine vanishes from every channel at once. Buy current-gen before the refresh rumor.")],
    "1:00 | Breather, tell it like a story. Right as I decided to buy, Apple discontinued the M3 Ultra, so Apple-direct was four months backordered and every reseller drained within days. I ended up on the grey market, a sealed unit on eBay, ninety-nine-point-three percent seller, strong buyer protection. Be honest about the feeling: wiring four thousand six hundred dollars to a stranger on eBay is its own little personality test. The transferable lesson: a just-discontinued Apple machine vanishes from every channel at once, so if you want a specific config, buy it before the refresh rumor hits. And gesture at the photo: that's the box, that's what's running the LLM.")
# narrow the bullets and drop the Mac Studio photo on the right (the box in question)
_buy.placeholders[1].width = Inches(6.3)
_mac = REPO / "viz" / ("mac-studio-ebay.jpg" if (REPO / "viz" / "mac-studio-ebay.jpg").exists() else "mac-studio.jpg")
_buy.shapes.add_picture(str(_mac), Inches(7.15), Inches(2.4), width=Inches(4.4))
_cap = _buy.shapes.add_textbox(Inches(7.15), Inches(4.85), Inches(4.4), Inches(0.4))
_cr = _cap.text_frame.paragraphs[0].add_run()
_cr.text = "the box running the LLM"; _cr.font.size = Pt(12); _cr.font.italic = True; _cr.font.color.rgb = DK2

section_slide("ACT THREE", "The measured verdict",
    notes="5 sec | Quick beat, but build energy here, this is the best part. Say: 'Act Three. Enough story, enough vibes. Here are the actual benchmarks, and this is where it surprised me.' Move.")

table_slide("The verdict: local ties cloud on coding",
    ["Model", "Score", "Speed"],
    [["**qwen3-coder:30b (local)**", "**24 / 24**", "**68 tok/s**"],
     ["Opus 4.8 (cloud)", "24 / 24", "-"],
     ["qwen3:32b dense", "16 / 18", "20 tok/s (skip)"]],
    "Mini-bench: 24 algorithmic problems, easy to LeetCode-hard, deterministic pytest scoring. Local understood the assignment: tied Opus on every one.",
    "1:30 | Open Act Three on the win, this is the 'yes' half of the answer. Stress the rigor before the result: twenty-four coding problems, easy up to LeetCode-hard, scored deterministically with pytest, no model judging itself. The result, the local thirty-billion coder tied Opus on every single problem, at sixty-eight tokens a second, for free. But plant the honesty that's coming: this bench saturated, my local model couldn't lose on it, and a benchmark your best model can't lose on has stopped measuring anything. That's exactly why I had to build harder tests, which is the rest of this act. Don't oversell, the next two slides deliberately complicate this win.",
    col_w=[4, 2, 2.5])

bullets_slide("What the tie means",
    [B("**Local owns:** self-contained coding, functions, scripts, algorithms, single and moderate multi-file"),
     B("**Cloud still wins:** open-ended, multi-file, sprawling-context repo work (real SWE-bench, the software-engineering benchmark)"),
     B("The gap is real but lives on a different axis than most benchmarks test."),
     B("A bench your best model can't lose on has stopped measuring.")],
    "1:30 | The precision slide, this is what keeps the whole talk honest, so slow down and make eye contact. The win is real but bounded. Local owns self-contained coding, functions, scripts, algorithms, single and moderate multi-file work. Cloud still wins the open-ended, sprawling-context stuff, a vague bug report across a huge unfamiliar repo, that's real SWE-bench. The insight to deliver: most benchmarks test the axis local already wins on, isolated problems, and they under-test the axis that actually matters day to day, navigating a big codebase. So leaderboard parity overstates real-world parity. Naming this honestly is what earns you credibility for the rest of the talk.")

table_slide("Why the Studio is fast: bandwidth, not parameters",
    ["Box", "Memory bandwidth", "coder-30b speed"],
    [["MacBook Air M2 16GB", "~100 GB/s", "16 tok/s"],
     ["**Mac Studio M3 Ultra 96GB**", "**~800 GB/s**", "**68 tok/s**"]],
    "Same model, 4x faster, entirely the memory bus. **MoE (mixture of experts) beats dense:** dense 32B is mid; the 3B-active MoE ate, 3x faster and higher-scoring.",
    "1:30 | The one genuinely technical slide, and a callback to the napkin math from Act One. Same model, same quant, eight times the memory bandwidth gives you about four times the tokens per second. The Mac Studio's eight-hundred-gigabyte-a-second memory bus is the entire story, it is not about raw compute. Then the mixture-of-experts punchline: a thirty-billion MoE model that only activates three billion parameters per token beats a dense thirty-two-billion model, faster AND higher-scoring, because only the active experts have to be streamed from memory each token. Practical advice for anyone buying: optimize for memory bandwidth and run MoE models, don't chase GPU teraflops.",
    col_w=[3.2, 3, 3])

bullets_slide("Bonus: one box = a full local AI server",
    [B("With OLLAMA_MAX_LOADED_MODELS=3, all resident at once (~38GB, 50GB free):"),
     B1("coder-30b, the coding agent"),
     B1("qwen2.5-VL, vision / OCR"),
     B1("nomic-embed, RAG (retrieval-augmented generation) embeddings"),
     B("Plus qwen3-next:80b (80B, 64 tok/s, bigger brain, same speed)")],
    "1:00 | Keep it brisk, this is a value-add, not the core argument. Ninety-six gigs holds the coding agent, a vision model, and an embedding model for search, all resident at the same time, thirty-eight gigs used, fifty free. So one box becomes the coding, vision, and retrieval backend for the whole house, the cloud bill you're replacing isn't only Claude Code. The kicker, and it ties back to the bandwidth point: the eighty-billion model runs at the same speed as the thirty-billion, because both only activate three billion parameters per token, so it's a free quality upgrade with no speed penalty. Don't dwell, it's a bonus slide.")

table_slide("But the agent loop is where local gets cooked",
    ["", "pass", "avg wall-clock", "turns (range)"],
    [["**Cloud (Opus)**", "**5 / 5**", "**31 s**", "5-9 (stable)"],
     ["**Local (coder-30b)**", "4 / 5", "**248 s**", "**4-41 (wild)**"]],
    "5 multi-file bug-fixes through the real Claude Code agent loop. **Local 8x slower, a one-line `>` to `>=` fix took it 41 turns / 584 s.**",
    "2:00 | This is THE turning point of the talk, the moment that changed my mind, so give it room. The one-shot benchmarks said tie. But I wanted to measure what I actually feel day to day, so I drove the real Claude Code agent loop on five multi-file bug fixes, local versus Opus, measuring wall-clock, turns, everything. Cloud, five out of five, about thirty-one seconds average, rock-steady five to nine turns. Local, four out of five, but two hundred forty-eight seconds average, eight times slower, and wildly unstable, anywhere from four to forty-one turns. Then land the killer detail and pause: one of these was a one-line fix, changing a greater-than to a greater-than-or-equal, and the local model took forty-one turns and almost ten minutes flailing on it. Let that hang. The lesson the whole talk builds to: measure the agent loop, not tokens per second.",
    col_w=[3.4, 1.5, 2.6, 2.6])

image_slide("Watch it: the agent loop side by side",
    REPO / "viz" / "agent-race.gif", width_in=10.2,
    sub="Recording of the real runs at 8x speed, left flails to 9 turns/110s, right is clean at 5 turns/17s.",
    notes="1:00 | The table you just saw, now in motion, let it play without talking for the first few seconds. Left is the local model flailing, reading the wrong file, failing the test twice, re-reading, finally fixing at turn nine. Right is cloud going straight to the fix, done in five turns. Point at the exact moment the right side freezes green while the left is still grinding and say: 'same one-line bug, the cloud agent has been done for ninety seconds.' Stress that this is a recording of the actual runs, sped up eight times, not a mockup, that badge in the corner is the real-time multiplier.")

bullets_slide("It's not caching, it's convergence",
    [B("Ollama DOES prefix-cache (the big local token counts are CC's accounting, not the box re-computing)"),
     B("The real cost is turn-count instability: the 30B fumbles, sometimes spiraling to 41 turns, sometimes giving up at 4"),
     B("Cloud converges in 5 turns every time. Local swings 4-41."),
     B("The one-shot '68 tok/s, ties Opus' number was single-turn, it hid all of this.")],
    "1:30 | The diagnosis, and use the honest 'I was wrong' beat, it builds trust. My first theory was 'local has no prompt caching, so it re-computes everything, that's why it's slow.' I dug in. Wrong. Ollama does cache, the logs show about thirty thousand tokens cached and only two hundred fifty new per turn. The scary big token numbers were Claude Code's accounting display, not the machine re-crunching. The real culprit is convergence instability, the thirty-billion model just can't reliably drive a tool-use loop to the finish, it fumbles, sometimes spiraling to forty-one turns, sometimes quitting early at four. Cloud nails five turns every time. The meta-point: that headline sixty-eight-tokens-a-second, ties-Opus number was a single-turn measurement, and single-turn benchmarks structurally hide multi-turn instability. That's why you measure the loop.")

table_slide("Tested it: the instability was the model",
    ["same agent loop, same box", "pass", "turns", "avg time"],
    [["coder-30b (the deck's baseline)", "4 / 5", "**4-41 (wild)**", "248 s"],
     ["Qwen 3.6 27b (q8)", "5 / 5", "7-9", "161 s"],
     ["**gpt-oss 20b**", "**5 / 5**", "**7-9 (stable)**", "**48 s**"],
     ["gemma4 26b", "5 / 5", "8-20", "69 s"],
     ["Opus 4.8 (cloud)", "5 / 5", "5-9", "31 s"]],
    "Every current model is stable and 5/5, the 41-turn coder spiral was a stale model, not local inference. **gpt-oss 20b lands within ~1.5x of cloud**, stable, on a 20B model. The fix was a newer model, not a bigger box.",
    "1:30 | The payoff, and it overturns my own headline, so own it. A few slides back the agent loop was spiraling to forty-one turns. Hypothesis from Boykis and Hacker News: that's the model, not local inference. So I re-ran the exact same five tasks on the same box across four current models. Result: every one is five-out-of-five and stable, the wild four-to-forty-one swing is gone. The standout, gpt-oss, a twenty-billion model, does it in forty-eight seconds, within about one-and-a-half times of cloud, stable. So the real story is sharper than the deck I built: the instability AND most of the speed gap were a stale model, not a hardware limit. The fix was a newer model, not a bigger box.",
    col_w=[3.6, 1.1, 1.8, 1.6], font=12)

table_slide("The reconciliation",
    ["Workload", "Local verdict"],
    [["One-shot bounded coding", "**Ties Opus**, fast, free"],
     ["Multi-turn agent loops", "**Current models: stable, 5/5. gpt-oss 20b within ~1.5x of cloud**"],
     ["Open-ended multi-file repos", "**Loses on capability too**"]],
    "The instability was a stale-model artifact, a current model is stable and 5/5. What's left is wall-clock (~5x) and big-context repo work. **Measure the agent loop, and keep your model current.**",
    "1:00 | This collapses the whole act into one honest table, the 'what's actually true' summary. One-shot bounded coding, ties Opus. Multi-turn agent loops, it works, four out of five, but eight times slower and unstable. Open-ended repos, it loses outright. The line that is the spine of the entire talk: local is genuinely capable, AND the daily experience is worse than the raw speed implies, and both of those are true at the same time. Resist the urge to pick a side, the nuance is the finding. This is usually where a skeptic's question lands, so own the complexity out loud before they get the chance.",
    col_w=[4, 5])

table_slide("But on open-ended building, the gap collapses",
    ["backend", "playable", "build time", "turns", "cost"],
    [["Opus 4.8 (cloud)", "**7 / 7**", "50 s", "2", "$0.40"],
     ["qwen3-next:80b (local)", "**7 / 7**", "98 s", "2", "**$0**"],
     ["qwen3-coder:30b (local)", "6 / 7", "166 s", "2", "**$0**"]],
    "Task: 'build playable Space Invaders as one index.html', scored by a Playwright 7-check rubric. **No failing test to spiral on, so local 80B ties cloud, within 2x on speed.**",
    "1:30 | The counterweight, and the most hopeful data in the talk, so lift the energy back up. Remember the eight-times tax was specifically about debugging, chasing a failing test, where the instability compounds. So I tried the opposite, an open-ended build, 'make a playable Space Invaders in one HTML file,' scored by an automated browser rubric. On a build-from-scratch task the gap nearly closes: the local eighty-billion model gets a perfect seven out of seven, same as Opus, at twice the wall-clock and zero dollars. Two sub-points worth making: the bigger local model beat the smaller one on speed AND quality AND used half the tokens, so convergence improves with size; and all three did it in just two turns. The takeaway: route by task type, build-from-scratch is great for local, debug-an-existing-repo is where cloud earns its keep.",
    col_w=[3.4, 1.6, 1.8, 1.2, 1.4])

image_slide("Same task, three models, all playable",
    REPO / "viz" / "appbench" / "side_by_side_2x.gif", width_in=11.2,
    sub="The actual games the three agents built, being played. Polish climbs left to right. coder-30b gatekept its own game behind a START menu.",
    notes="1:00 | Show, don't tell, let it loop. These are the actual games the three agents built, being played by a script. Left, the small local model, it works, emoji invaders, scoring, a game-over screen, but it shipped the game behind a START menu, which was its one rubric miss. Middle, the eighty-billion, clean and auto-running. Right, Opus, the richest, sprite invaders, a lives counter, restart hints. The polish climbs left to right and maps exactly to the table, but the point is all three are real, runnable, in the repo, and the local ones cost zero dollars. Invite them: clone it and play them yourself.")

section_slide("ACT FOUR", "Economics & the call",
    notes="5 sec | Quick beat. Say: 'Act Four. So what does this actually cost, and what should you do on Monday morning?' Move.")

bullets_slide("The economics",
    [B("Cloud: ~$200/mo, about $2,400/yr, indefinitely"),
     B("Local: $4,676 once, then **$0/mo** after"),
     B("**Breakeven ~2 years**, then it's basically free real estate, for the work local handles well"),
     B("Privacy bonus: code never leaves the LAN"),
     B("The catch: it's a supplement, not a full replacement. Hard repo work still routes to cloud.")],
    "1:00 | The money slide, this is what a decision-maker actually wants. Cloud is about two hundred a month forever, the box is four thousand six hundred once and then zero. Breakeven is roughly two years, and after that it's pure savings, but be honest, only for the slice of work local handles well, it shrinks the cloud bill, it doesn't zero it. The non-money win that often matters more: code never leaves your network, and for client or regulated work, privacy can justify the box on its own regardless of breakeven. Keep saying 'supplement, not replacement,' that honesty is exactly what keeps this from sounding like a sales pitch.")

bullets_slide("Recommendation",
    [B("**Hybrid, not either/or:**"),
     B1("`claude` routes to the local Studio (the 80%: daily coding, free, private, fast)"),
     B1("`claude-cloud` routes to Opus 4.8 (the 20%: hard cross-file repo work)"),
     B("One toggle, per task. Denominated in your real workload."),
     B("**Single-dev sweet spot:** Mac Studio, 64-96GB, MoE coder model, ~$4-5K")],
    "1:00 | The actionable takeaway, what someone does Monday morning. The whole talk reduces to one architecture, hybrid. Two shell aliases, one routes to the local Studio, one routes to Opus, you pick per task, no lock-in, no ideology. The concrete buying advice: a single developer wants a Mac Studio, sixty-four to ninety-six gigs, an MoE coder model, about four to five thousand dollars. Not the eleven-and-a-half-thousand parity-chase box I debunked in Act Two, and not the sixteen-gig toy from Act One. If someone photographs one slide of this whole talk, it should be this one, so hold it an extra beat.")

bullets_slide("Caveats that matter",
    [B("'Local SOTA at home' is real in 2026, narrowly, on bounded coding"),
     B("On open-ended engineering it is not, and no honest setup pretends otherwise"),
     B("16GB is too small; >96GB is overkill for one person"),
     B("Benchmarks saturate, measure your task mix, not a leaderboard")],
    "1:00 | This is Q&A insurance, name your own weaknesses first so you control the framing. 'Local SOTA at home' is a true headline only if you append 'narrowly, on bounded coding,' anyone selling it without that asterisk is overselling. The sizing guidance kills two bad instincts at once: sixteen gigs is too small to live on, and more than ninety-six is overkill for one person, the sweet spot is narrow and I've bracketed it. And the recurring theme one last time: benchmarks saturate, the only benchmark that matters is your own task mix. By saying all this before they can, you've pre-answered the hostile questions.")

bullets_slide("What's next (this is being measured)",
    [B("Cut my agents fully over to local"),
     B("Measure local vs Opus 4.8 on real tasks: token usage, latency, TTFT (time to first token), success"),
     B("Add verification-loop scaffolding, guardrails took an 8B from 53% to 99% on agentic workflows"),
     B("The instability may be a software problem, not a model-size one. The fix might be code, not a $10k box.")],
    "1:00 | End on momentum, this is live research, not a post-mortem. Three threads: cut my real agents fully over to local and live on it, keep the measurement rig running on real daily tasks not synthetic benches, and the exciting one, add verification-loop scaffolding. Land this hard: published results show guardrails took an eight-billion-parameter model from fifty-three percent to ninety-nine percent on agentic workflows. So the instability we measured a few slides ago might be a software problem, not a model-size problem, the fix could be code, not a ten-thousand-dollar box. That single reframe turns the whole weakness into something solvable, and it leaves the room optimistic instead of resigned.")

title_slide("Thank you",
    "The win is real. So is the caveat.\n"
    "Repo + full write-up (19 acts, 41 lessons): github.com/jconnolly/local-llm-pi5\n"
    "Benchmarks: minibench, repobench, appbench",
    notes="0:30 | Close on the one-line thesis, and say it slowly: the win is real, and the caveat is real too. Point them at the repo, everything is reproducible, the benchmarks are real code they can clone and run. Then open the floor. The questions to be ready for: why not vLLM or MLX for more speed, what about just always running the eighty-billion, would guardrails really fix the instability, and what's the ROI if I'm already paying for cloud anyway. The answers all live in Acts Three and Four, point back to the relevant slide. Time check: if you hit this slide around twenty-nine minutes, you nailed the pacing.")

bullets_slide("PS: the field moved while I built this deck",
    [B("Mid-build, Vicki Boykis published 'Running local models is good now' (Jun 15), and Hacker News piled on with a 1,589-point discussion of it."),
     B("They corroborate the core finding: context is the wall, ~30B MoE is the sweet spot, agentic local is real but model-dependent."),
     B("But my models are already last-gen. The community has moved to **Qwen 3.6** (27b / 35b-a3b) and **Gemma 4**; my coder-30b is a step behind."),
     B("**Already tested:** re-ran the agent loop across Qwen 3.6, gpt-oss, and Gemma 4 (same box). All 5/5, all stable, no spirals. **gpt-oss 20b landed within ~1.5x of cloud.** The instability was the stale model."),
     B("**Still open:** the quant angle (q6 vs q4 on the 80B), and living on it daily. The verdict holds; the specific models won't, this moves weekly."),
     B("Sources: vickiboykis.com/2026/06/15 + Hacker News item 48555993")],
    "0:30 | The honest closer-after-the-closer. While I was literally building this deck, Vicki Boykis published almost exactly this argument, and Hacker News spent fifteen hundred points debating it the same week. Two points. One, it corroborates the structure, context is the wall, thirty-billion MoE is the sweet spot, that's not just me. Two, the humbling part, my specific models are already a step behind, the community is on Qwen three-six and Gemma four now, and several people flagged that low quantization weakens tool-calling, which might be the actual cause of the instability I measured, not the model size. So the verdict holds, but the numbers have a one-week shelf life, and I'm already re-running with newer models at higher quant. Ends on intellectual honesty and momentum.")

prs.save(str(OUT))
print(f"saved {OUT}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
print(f"slides: {len(list(prs.slides))}")

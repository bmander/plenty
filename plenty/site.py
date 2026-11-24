"""Render the static site (site/) from config/ and results/.

    python scripts/03_run.py     # refresh results/ first if config/ changed
    python -m plenty.site

Pages follow the planning loop: needs, capabilities, gaps, work; plus the sector table and the
method. Assets in plenty/web/ are copied as they are. Everything is plain HTML with relative links,
so the site works from any path (GitHub Pages serves it under /plenty/).
"""
from __future__ import annotations
import html
import math
import shutil
import urllib.parse
from pathlib import Path

import pandas as pd

from . import occupations as O

ROOT = Path(__file__).resolve().parent.parent
CONFIG, RESULTS, WEB, SITE = ROOT / "config", ROOT / "results", ROOT / "plenty" / "web", ROOT / "site"
REPO = "https://github.com/bmander/plenty"

NEED_NAME = {
    "food": "Food", "clothing": "Clothing", "shelter": "Shelter", "energy": "Energy",
    "water_sanitation": "Water and sanitation", "health": "Health", "education": "Education",
    "mobility": "Mobility", "communication": "Communication", "safety": "Safety",
    "meaning": "Meaning and recreation",
}
NAV = [  # (file, label, step number or None)
    ("needs.html", "Needs", 1), ("capabilities.html", "Capabilities", 2),
    ("gaps.html", "Gaps", 3), ("work.html", "Work", 4),
    ("sectors.html", "Sectors", None), ("method.html", "Method", None),
]
KIND_NAME = {"board": "Leaderboard", "measure": "Measurement", "review": "Review", "data": "Data"}

e = html.escape


ARCH_NAME = {
    "engineering_rd": "engineering and R&D services", "pharma_bio": "pharmaceuticals and biologics",
    "ships_rail_other": "ships and rail", "oil_gas_extraction": "oil and gas extraction",
    "warehousing_postal": "warehousing and post", "plastics_rubber": "plastics and rubber",
    "wood_furniture": "wood and furniture", "real_estate_housing": "real estate and housing",
    "professional_admin": "professional and administrative services", "paper_printing": "paper and printing",
    "textiles_apparel": "textiles and apparel", "finance_insurance": "finance and insurance",
    "media_publishing": "media and publishing", "software_data": "software and data services",
    "arts_recreation": "arts and recreation", "personal_civic": "personal and civic services",
    "misc_manufacturing": "miscellaneous manufacturing",
}


def words(s: str) -> str:
    return ARCH_NAME.get(s, s.replace("_", " "))


# ---------------------------------------------------------------- data

class Data:
    def __init__(self):
        self.caps = pd.read_csv(CONFIG / "capabilities.csv").set_index("capability")
        self.ct = pd.read_csv(RESULTS / "capability_table.csv", index_col=0)
        self.cbn = pd.read_csv(RESULTS / "capability_by_need.csv", index_col=0)
        self.needs_cfg = pd.read_csv(CONFIG / "needs.csv").set_index("need")
        self.needs = pd.read_csv(RESULTS / "needs.csv", index_col=0)
        self.sectors = pd.read_csv(RESULTS / "sectors.csv", index_col=0)
        self.physical = set(pd.read_csv(RESULTS / "physical_sectors.csv", index_col=0).index)
        self.upstream = pd.read_csv(RESULTS / "top_upstream_by_need.csv")
        self.thin = pd.read_csv(RESULTS / "bottleneck_candidates.csv", index_col=0)
        self.sens = pd.read_csv(RESULTS / "sensitivity.csv", index_col=0)
        self.arch = pd.read_csv(RESULTS / "archetypes.csv", index_col=0)
        self.scores = pd.read_csv(CONFIG / "archetype_capabilities.csv").set_index("archetype")
        self.work = pd.read_csv(CONFIG / "work.csv").fillna("")
        self.agree = pd.read_csv(RESULTS / "score_agreement.csv", index_col=0)
        self.occ_shares = pd.read_csv(RESULTS / "occupation_capability_shares.csv", index_col=0)
        self.has_board = self.caps.board.notna()

    def cap_name(self, k):
        return self.caps.at[k, "name"]

    def board_html(self, k):
        if not self.has_board[k]:
            return '<span class="tag gap">none yet</span>'
        name, url = self.caps.at[k, "board"], self.caps.at[k, "board_url"]
        return f'<a href="{e(url)}">{e(name)}</a>' if isinstance(url, str) else e(name)


# ---------------------------------------------------------------- pieces

def page(title: str, active: str, body: str, long_title: bool = False) -> str:
    links = []
    for i, (href, label, step) in enumerate(NAV):
        if step is None and NAV[i - 1][2] is not None:
            links.append('<span class="sep" aria-hidden="true"></span>')
        cur = ' aria-current="page"' if href == active else ""
        num = f'<span class="step">{step}</span>' if step else ""
        cls = "" if step else ' class="ref"'
        links.append(f'<a href="{href}"{cur}{cls}>{num}{label}</a>')
    doc_title = "Plenty" if active == "index.html" else f"{title} | Plenty"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(doc_title)}</title>
<meta name="description" content="A material balance for the machines behind human needs: what people need, the engineering capabilities that depends on, and which of them exist in the open.">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="sheet">
<header class="masthead">
<a class="wordmark" href="index.html">Plenty</a>
<nav aria-label="Sections">{''.join(links)}</nav>
</header>
<main>
{body}
</main>
<footer>
<p>Built from the U.S. Bureau of Economic Analysis 2017 benchmark input-output tables. Every judgment
call is a CSV you can edit: <a href="{REPO}">source and data on GitHub</a>.</p>
</footer>
</div>
<script src="site.js"></script>
</body>
</html>
"""


def bar(value: float, vmax: float, label: str, tip: str) -> str:
    pct = 0 if vmax <= 0 else max(0.0, min(100.0, 100 * value / vmax))
    return (f'<div class="barcell" data-tip="{e(tip)}"><div class="bar"><i style="width:{pct:.1f}%"></i></div>'
            f'<span class="v">{label}</span></div>')


def table(head: list[str], rows: list[str], caption: str = "", attrs: str = "", foot: str = "") -> str:
    # the caption sits outside the scrolling box so it wraps to the page, not to the table
    cap = f'<p class="note tablenote">{caption}</p>' if caption else ""
    tfoot = f"<tfoot>{foot}</tfoot>" if foot else ""
    return (f'{cap}<div class="scroll"><table class="ledger"{attrs}><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>{tfoot}</table></div>')


def th(label: str, cls: str = "", sort: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    s = f' data-sort="{sort}"' if sort else ""
    return f'<th scope="col"{c}{s}>{label}</th>'


def f3(x: float) -> str:
    return f"{x:.3f}"


def issue_link(title: str) -> str:
    return f"{REPO}/issues/new?title={urllib.parse.quote(title)}"


# ---------------------------------------------------------------- pages

def balance_rows(d: Data, order) -> list[str]:
    vmax, emax = d.ct["volume weight"].max(), d.ct["exposure"].max()
    rows = []
    for k in order:
        r = d.ct.loc[k]
        rows.append(
            f'<tr><th scope="row">{e(d.cap_name(k))}</th>'
            f'<td>{bar(r["volume weight"], vmax, f3(r["volume weight"]), f"{d.cap_name(k)}: {r['volume weight']:.1%} of the value added embodied in the basket, score-weighted")}</td>'
            f'<td>{bar(r["exposure"], emax, f3(r["exposure"]), f"{d.cap_name(k)}: {r['exposure'] * 100:.1f} cents of every basket dollar passes through sectors that cannot run without it")}</td>'
            f'<td>{d.board_html(k)}</td></tr>')
    return rows


def index(d: Data) -> str:
    order = d.ct.sort_values("volume weight", ascending=False).index
    total = d.needs.final_demand_musd.sum() / 1e6
    n_gap = int((~d.has_board).sum())
    s = d.sectors
    phys = s[s.index.isin(d.physical)]
    phys_share = phys.value_added_per_basket_dollar.sum() / s.value_added_per_basket_dollar.sum()
    top = d.ct[~d.has_board.reindex(d.ct.index)].sort_values(["worst_rank", "volume_rank"]).index[:2]
    body = f"""
<h1>A material balance for the machines behind human needs</h1>
<p class="lede">Plenty keeps an account of what people need, the engineering capabilities those
needs depend on, and which of those capabilities exist in the open. Where the two sides do not
balance, there is work to do.</p>
<p class="caveat">This is a first pass. The capability scores behind these numbers were written by an
AI model and have not been reviewed by people who work in each field. <a href="method.html">How far to trust it</a>.</p>

<h2>The balance today</h2>
{table(
    [th("Capability"), th("Demand: weight on the path to needs"), th("Demand: exposure"), th("Means: open leaderboard")],
    balance_rows(d, order),
    caption="Weight is the share of the basket's embodied value added arising in sectors that depend on the capability. "
            "Exposure is dollars of output from sectors that cannot run without it, per dollar of basket.")}
<p class="note">{n_gap} of {len(d.ct)} capabilities have no open leaderboard. The two that rank highest on both
measures are {e(d.cap_name(top[0]).lower())} and {e(d.cap_name(top[1]).lower())}. <a href="gaps.html">See the gaps</a>.</p>

<h2>How the account is kept</h2>
<ol class="loop">
<li><a href="needs.html">Collect needs</a><p>{len(d.needs)} needs, sized by what US households and governments spent
on them in 2017: ${total:.1f} trillion. Farming, extraction, utilities, construction and manufacturing carry
{phys_share:.0%} of the value added embodied in that basket.</p></li>
<li><a href="capabilities.html">Collect capabilities</a><p>{len(d.ct)} engineering capabilities, weighted by how much
of the basket passes through sectors that depend on them. What open tools can actually do today is not collected yet.</p></li>
<li><a href="gaps.html">Identify gaps</a><p>Capabilities people depend on that nobody is measuring in the open,
ranked by how much depends on them.</p></li>
<li><a href="work.html">Dispatch work</a><p>{len(d.work)} proposed leaderboards, measurements and reviews. Each one
can be claimed by opening an issue.</p></li>
</ol>
"""
    return page("Plenty", "index.html", body)


def needs_page(d: Data) -> str:
    T = d.needs
    rows = []
    for n, r in T.iterrows():
        rows.append(
            f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="wrap dim">{e(d.needs_cfg.at[n, "description"].replace("; ", ", "))}</td>'
            f'<td class="num">{r.final_demand_musd / 1e3:,.0f}</td>'
            f'<td>{bar(r.share, T.share.max(), f"{r.share:.0%}", f"{NEED_NAME[n]}: ${r.final_demand_musd / 1e3:,.0f} billion, {r.share:.1%} of the basket")}</td></tr>')
    foot = f'<tr><td>Basket</td><td></td><td class="num">{T.final_demand_musd.sum() / 1e3:,.0f}</td><td></td></tr>'

    # heat table: capability x need
    order = d.ct.sort_values("volume weight", ascending=False).index
    need_cols = list(T.index)
    vmax = d.cbn.values.max()
    head = [th("Capability")] + [th(e(NEED_NAME[n]).replace(" and ", " and<br>"), "num") for n in need_cols]
    hrows = []
    for k in order:
        cells = []
        for n in need_cols:
            v = d.cbn.at[k, n]
            cells.append(f'<td class="heat" style="background:color-mix(in srgb, var(--series) {55 * v / vmax:.0f}%, transparent)" '
                         f'data-tip="{e(d.cap_name(k))} in {e(NEED_NAME[n].lower())}: {v:.0%} of embodied value added, score-weighted">{v * 100:.0f}</td>')
        hrows.append(f'<tr><th scope="row">{e(d.cap_name(k))}</th>{"".join(cells)}</tr>')

    ups = []
    for n in need_cols:
        u = d.upstream[d.upstream.need == n].head(5)
        items = "; ".join(f"{e(x['name'].split(',')[0].lower())} ({x.output_per_need_dollar * 100:.1f}&cent;)" for _, x in u.iterrows())
        ups.append(f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="wrap">{items}</td></tr>')

    body = f"""
<h1>Needs</h1>
<p class="lede">The basket is what US households and governments spent in 2017 on eleven needs.
Everything else on this site is traced back from it.</p>
{table([th("Need"), th("What it covers"), th("Spending, $ billion", "num"), th("Share of basket")], rows, foot=foot)}
<p class="note">Left out by default: federal government, finance and legal services, and a discretionary group (alcohol,
tobacco, gambling, lodging, jewelry, pets, personal services). They still count wherever the needs above buy from them.
Edit <code>config/basket.csv</code> and <code>config/needs.csv</code> to change what counts.</p>
<p class="caveat">Spending is a poor measure of need. Health care is {T.share['health']:.0%} of this basket and restaurants
are over a third of food. A basket in physical units (calories, square meters, kilowatt-hours) is
<a href="work.html#sufficiency-basket">proposed work</a>.</p>

<h2>What each need draws on</h2>
{table(head, hrows, attrs=' id="heat"', caption="Percent of each need's embodied value added that arises in sectors depending on the capability, score-weighted. Stronger color is more.")}

<h2>Physical inputs behind each need</h2>
{table([th("Need"), th("Largest upstream physical sectors, in cents per dollar of the need")], ups,
       caption="Excludes what the need buys directly. Includes the equipment and buildings used up along the way.")}
"""
    return page("Needs", "needs.html", body)


def capabilities_page(d: Data) -> str:
    order = d.ct.sort_values("volume weight", ascending=False).index
    vmax, emax = d.ct["volume weight"].max(), d.ct["exposure"].max()
    omax = d.ct["occupational weight"].max()
    rows = []
    for k in order:
        r = d.ct.loc[k]
        critical = [words(a) for a in d.scores.index[d.scores[k] == 3]]
        crit = ", ".join(critical) if critical else "none scored as critical"
        otip = f"Occupational rank {int(r.occupational_rank)} of {len(d.ct)}"
        if d.agree.at[k, "thin"]:
            otip += " (too few occupations to measure: elicited scores, rescaled)"
        rows.append(
            f'<tr id="{k}"><th scope="row" class="cap">{e(d.cap_name(k))}<div class="dim" style="font-weight:400">{e(d.caps.at[k, "description"].replace("; ", ", "))}</div></th>'
            f'<td data-v="{r["volume weight"]}">{bar(r["volume weight"], vmax, f3(r["volume weight"]), f"Volume rank {int(r.volume_rank)} of {len(d.ct)}")}</td>'
            f'<td data-v="{r["occupational weight"]}">{bar(r["occupational weight"], omax, f3(r["occupational weight"]), otip)}</td>'
            f'<td data-v="{r["exposure"]}">{bar(r["exposure"], emax, f3(r["exposure"]), f"Exposure rank {int(r.exposure_rank)} of {len(d.ct)}")}</td>'
            f'<td class="num" data-v="{r["reach 1c"]}">{r["reach 1c"]:.0%}</td>'
            f'<td class="wrap dim">{e(crit)}</td>'
            f'<td>{d.board_html(k)}</td></tr>')
    body = f"""
<h1>Capabilities</h1>
<p class="lede">Eighteen kinds of engineering computation, weighted by how much of the basket of
needs passes through sectors that depend on them.</p>
<p class="caveat">This page shows demand for each capability. It does not yet show supply: how far today's open
tools are from the state of the art. <a href="work.html#inventory">Collecting that</a> is the next step of the loop.</p>
{table(
    [th("Capability"), th("Weight", sort="num"), th("Occupational weight", sort="num"), th("Exposure", sort="num"),
     th("Reach at 1&cent;", "num", "num"), th("Sectors that cannot run without it"), th("Open leaderboard")],
    rows,
    caption="Weight: score-weighted share of the basket's embodied value added. Occupational weight: the same measure with each "
            "sector's elicited score replaced by the share of its wage bill paid to occupations that use the capability's software "
            "(<a href=\"method.html#occupations\">how</a>); compare ranks, not levels. Exposure: dollars of output from sectors that "
            "cannot run without the capability, per dollar of basket. Reach at 1&cent;: share of the basket with at least one cent "
            "per dollar passing through those sectors. Click a column heading to sort.")}
<h2>Reading the two measures together</h2>
<p>Weight follows cost: a capability scores high when large sectors use it, even casually. Exposure counts
only sectors that cannot run without the capability. When the two agree, the result is sturdy. When they
disagree, look closer:</p>
<ul>
<li>Geospatial ranks {int(d.ct.at['gis', 'volume_rank'])} by weight and {int(d.ct.at['gis', 'exposure_rank'])} by exposure. Its weight comes from low scores on very large service sectors.</li>
<li>CAM and manufacturing process simulation rank {int(d.ct.at['cam', 'volume_rank'])} and {int(d.ct.at['mfgsim', 'volume_rank'])} by weight but {int(d.ct.at['cam', 'exposure_rank'])} and {int(d.ct.at['mfgsim', 'exposure_rank'])} by exposure. Many sectors cannot run without them, and each is small.</li>
<li>IC design is last on both, which is a limit of the method. Semiconductors reach the whole basket at a tenth of a cent
per dollar, and nothing in an input-output table says a missing chip stops a production line.</li>
</ul>
"""
    return page("Capabilities", "capabilities.html", body)


def gaps_page(d: Data) -> str:
    ct = d.ct.join(d.has_board.rename("has_board"))
    work_by_cap = {}
    for _, w in d.work.iterrows():
        if w.capability:
            work_by_cap.setdefault(w.capability, []).append(w)

    def rows_for(frame):
        rows = []
        for k, r in frame.iterrows():
            ws = work_by_cap.get(k, [])
            links = "; ".join(f'<a href="work.html#{e(w.id)}">{e(w.title)}</a>' for w in ws) or '<span class="dim">nothing proposed</span>'
            rows.append(
                f'<tr><th scope="row">{e(d.cap_name(k))}</th>'
                f'<td class="num">{int(r.volume_rank)}</td><td class="num">{int(r.exposure_rank)}</td>'
                f'<td>{e(NEED_NAME[r["most exposed need"]])}</td>'
                f'<td>{d.board_html(k)}</td><td class="wrap">{links}</td></tr>')
        return rows

    head = [th("Capability"), th("Rank by weight", "num", "num"), th("Rank by exposure", "num", "num"),
            th("Most exposed need"), th("Open leaderboard"), th("Proposed work")]
    open_gaps = ct[~ct.has_board].sort_values(["worst_rank", "volume_rank"])
    covered = ct[ct.has_board].sort_values(["worst_rank", "volume_rank"])
    thin_rows = [
        f'<tr><td class="name">{e(r["name"])}</td><td class="num">{r.output_per_basket_dollar * 100:.2f}&cent;</td>'
        f'<td class="num">{r.need_breadth_observed:.1f}</td></tr>' for _, r in d.thin.head(15).iterrows()]
    body = f"""
<h1>Gaps</h1>
<p class="lede">A gap is a capability people depend on that nobody is measuring in the open.
{len(open_gaps)} of {len(ct)} capabilities are in that state.</p>
<h2>No open leaderboard</h2>
{table(head, rows_for(open_gaps), caption=f"Ordered by the worse of the two ranks, so a capability has to matter on both measures to rise. Ranks are out of {len(ct)}.")}
<h2>Covered by a leaderboard</h2>
{table(head, rows_for(covered), caption="A board existing does not mean the gap is closed. It means the distance to the state of the art is being measured.")}
<p class="caveat">This page ranks gaps by demand alone. A real gap is demand times the distance between open tools and the
best available, and that distance is <a href="work.html#inventory">not collected yet</a>. Where open tools are already strong
(optimization solvers, water network hydraulics) the true gap is smaller than its rank here suggests.</p>

<h2>Narrow inputs</h2>
<p>A second kind of gap sits in the supply chain itself: sectors that cost little but that nearly every need buys from.
These are the ones a shortage would be felt through.</p>
{table([th("Sector"), th("Per basket dollar", "num"), th("Needs served, of 11", "num")], thin_rows,
       caption=f"The 15 smallest of {len(d.thin)} physical sectors whose sales are spread across nearly all needs. "
               "The measure cannot tell an input with substitutes from one without.")}
<p class="note"><a href="sectors.html">All sectors</a></p>
"""
    return page("Gaps", "gaps.html", body)


def work_page(d: Data) -> str:
    groups = [("board", "Leaderboards to start", "Each needs a defined output and a cheap way to check it."),
              ("measure", "Measurements", "Find out how large a gap is before proposing to close it."),
              ("review", "Reviews", "Judgments in the model that need people who know the field."),
              ("data", "Data", "Inputs that would make the account more honest.")]
    out = []
    for kind, title, sub in groups:
        items = d.work[d.work.kind == kind]
        if items.empty:
            continue
        arts = []
        for _, w in items.iterrows():
            rank = ""
            if w.capability:
                r = d.ct.loc[w.capability]
                rank = (f'<dt>Capability</dt><dd><a href="capabilities.html#{e(w.capability)}">{e(d.cap_name(w.capability))}</a>, '
                        f'rank {int(r.volume_rank)} by weight and {int(r.exposure_rank)} by exposure</dd>')
            prior = f"<dt>Prior art</dt><dd>{e(w.prior_art)}</dd>" if w.prior_art else ""
            arts.append(
                f'<article id="{e(w.id)}"><div><h3>{e(w.title)}</h3><p>{e(w.what)}</p>'
                f'<dl>{rank}<dt>Checked by</dt><dd>{e(w.scored_by)}</dd>{prior}</dl></div>'
                f'<a class="act" href="{issue_link(w.title)}">Open an issue</a></article>')
        out.append(f'<h2>{title}</h2><p class="note">{sub}</p><div class="work">{"".join(arts)}</div>')
    body = f"""
<h1>Work</h1>
<p class="lede">Proposals that would close a gap or make the account more accurate. Nothing here is
assigned. To take one, open an issue and say what you plan to do.</p>
{''.join(out)}
<p class="note" style="margin-top:36px">Proposals live in <code>config/work.csv</code>. Add a row to propose something else.</p>
"""
    return page("Work", "work.html", body)


def scatter(d: Data) -> str:
    s = d.sectors[d.sectors.index.isin(d.physical)]
    W, H, L, R, T, B = 1040, 520, 56, 20, 16, 46
    x0, x1 = math.log10(1e-5), math.log10(5e-2)
    def X(v): return L + (math.log10(max(v, 1.2e-5)) - x0) / (x1 - x0) * (W - L - R)
    def Y(v): return T + (11.5 - v) / 11.0 * (H - T - B)
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Scatter of physical sectors: volume against breadth">']
    for b in (2, 4, 6, 8, 10):
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{Y(b):.1f}" y2="{Y(b):.1f}"/><text x="{L - 8}" y="{Y(b) + 4:.1f}" text-anchor="end">{b}</text>')
    for v, lab in ((1e-4, "0.01¢"), (1e-3, "0.1¢"), (1e-2, "1¢")):
        parts.append(f'<line class="grid" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T}" y2="{H - B}"/><text x="{X(v):.1f}" y="{H - B + 18}" text-anchor="middle">{lab}</text>')
    parts.append(f'<text x="{(L + W - R) / 2:.0f}" y="{H - 6}" text-anchor="middle">Volume: sector output per dollar of basket (log scale)</text>')
    parts.append(f'<text transform="translate(14 {(T + H - B) / 2:.0f}) rotate(-90)" text-anchor="middle">Breadth: needs served, of 11</text>')
    picks = {"221100": ("Electric power", -10, 20, "end"), "211000": ("Oil and gas extraction", -10, -10, "end"),
             "331110": ("Iron and steel", 10, 4, "start"), "325412": ("Pharmaceuticals", -10, -10, "end"),
             "233411": ("Single-family houses", -10, 20, "end"), "333914": ("Pumps", 10, -6, "start"),
             "335314": ("Relays and industrial controls", -12, -12, "end"), "333517": ("Machine tools", -12, 14, "end"),
             "334413": ("Semiconductors", 10, 16, "start"), "332991": ("Bearings", -10, 4, "end"),
             "325310": ("Fertilizer", 10, 5, "start"), "1111B0": ("Grain farming", 10, 4, "start"),
             "336411": ("Aircraft", 10, 4, "start"), "333111": ("Farm machinery", 10, 4, "start")}
    for code, r in s.iterrows():
        if code in picks:
            continue
        parts.append(f'<circle class="dot" cx="{X(r.output_per_basket_dollar):.1f}" cy="{Y(r.need_breadth_observed):.1f}" r="4.5" '
                     f'data-tip="{e(r["name"])}: {r.output_per_basket_dollar * 100:.2f}¢ per basket dollar, serves {r.need_breadth_observed:.1f} needs"/>')
    for code, (lab, dx, dy, anchor) in picks.items():
        r = s.loc[code]
        x, y = X(r.output_per_basket_dollar), Y(r.need_breadth_observed)
        parts.append(f'<circle class="dot pick" cx="{x:.1f}" cy="{y:.1f}" r="5" '
                     f'data-tip="{e(r["name"])}: {r.output_per_basket_dollar * 100:.2f}¢ per basket dollar, serves {r.need_breadth_observed:.1f} needs"/>'
                     f'<text class="lab" x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}">{e(lab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def sectors_page(d: Data) -> str:
    s = d.sectors[d.sectors.archetype != "accounting"].sort_values("output_per_basket_dollar", ascending=False)
    rows = []
    for code, r in s.iterrows():
        phys = "1" if code in d.physical else "0"
        text = f"{r['name']} {words(r.archetype)} {code}".lower()
        rows.append(
            f'<tr data-phys="{phys}" data-text="{e(text)}"><td class="name">{e(r["name"])}</td><td class="dim">{e(words(r.archetype))}</td>'
            f'<td class="num" data-v="{r.output_per_basket_dollar}">{r.output_per_basket_dollar * 100:.2f}</td>'
            f'<td class="num" data-v="{r.value_added_per_basket_dollar}">{r.value_added_per_basket_dollar * 100:.2f}</td>'
            f'<td class="num" data-v="{r.need_breadth_observed}">{r.need_breadth_observed:.1f}</td>'
            f'<td class="num" data-v="{r["reach_0.001"]}">{r["reach_0.001"]:.0%}</td>'
            f'<td>{e(NEED_NAME.get(r.top_need, r.top_need))}</td></tr>')
    body = f"""
<h1>Sectors</h1>
<p class="lede">Every sector of the economy, by how much of the basket of needs passes through it
and how many of the needs depend on it.</p>
<figure>
{scatter(d)}
<figcaption>{len(d.physical)} farming, extraction, utility, construction and manufacturing sectors. Upper left is small in cost
but bought by nearly every need. Breadth uses observed purchases only. Hover a point for its name.</figcaption>
</figure>
<h2>All sectors</h2>
<div class="controls">
<input type="search" id="q" placeholder="Filter by name or kind, e.g. pump" aria-label="Filter sectors">
<label><input type="checkbox" id="phys"> Physical sectors only</label>
<span id="count" class="note" aria-live="polite"></span>
</div>
{table(
    [th("Sector", sort="text"), th("Kind", sort="text"), th("Output, &cent; per basket $", "num", "num"),
     th("Value added, &cent;", "num", "num"), th("Needs served", "num", "num"), th("Reach at 0.1&cent;", "num", "num"),
     th("Used most heavily by", sort="text")],
    rows, attrs=' id="sectors"',
    caption="Output and value added are per dollar of basket, counting equipment and buildings used up. Needs served is an effective "
            "count from 1 to 11. Reach is the share of the basket using at least a tenth of a cent of the sector per dollar. Click a heading to sort.")}
"""
    return page("Sectors", "sectors.html", body)


def occupations_section(d: Data) -> str:
    a, sh = d.agree, d.occ_shares
    n_all, n_meas = len(sh), int((sh.source == "oews").sum())
    fallback = sh.source[sh.source != "oews"].str.replace("fallback:", "").value_counts()
    thin = [d.cap_name(k) for k in a.index[a.thin]]
    rho = d.ct["volume weight"].corr(d.ct["occupational weight"], method="spearman")
    min_products = {2: "two", 3: "three", 4: "four", 5: "five"}.get(O.MIN_PRODUCTS, str(O.MIN_PRODUCTS))
    order = a.sort_values("rank_change").index
    rows = [f'<tr><td>{e(d.cap_name(k))}</td><td class="num">{int(a.at[k, "elicited_rank"])}</td>'
            f'<td class="num">{int(a.at[k, "occupational_rank"])}</td>'
            f'<td class="num">{"&ndash;" if a.at[k, "thin"] else f"{a.at[k, "spearman_across_sectors"]:.2f}"}</td></tr>'
            for k in order]

    def moves(k):
        r0, r1 = int(a.at[k, "elicited_rank"]), int(a.at[k, "occupational_rank"])
        return f"ranks {r0} in both" if r0 == r1 else f"{'falls' if r1 > r0 else 'rises'} from {r0} to {r1}"

    return f"""
<h2 id="occupations">Checking the scores against occupations</h2>
<p>The capability scores are judgment. As a check on the <em>usage</em> half of that judgment, each sector's score is
replaced by a measured proxy: the share of its wage bill paid to occupations that use the capability's software.</p>
<pre><code>share[j, k] = sum_o wagebill[j, o] uses[o, k] / sum_o wagebill[j, o]</code></pre>
<ul>
<li><b>Who uses what.</b> O*NET 31.0 lists the software each occupation uses on the job.
<a href="{REPO}/blob/main/config/software_capabilities.csv"><code>config/software_capabilities.csv</code></a> maps product
names (Ansys, Abaqus, HEC-RAS, RSLogix, ArcGIS...) and a few specific O*NET categories (CAM, GIS, map creation) to capabilities.
An occupation counts as using a capability when it lists at least {min_products} of its products. With one, generalists dominate:
software developers list 430 products, Verilog and a genome assembler among them, and their wages would put most
capabilities into every bank.</li>
<li><b>Who works where.</b> OEWS May 2021 gives employment and mean wage by occupation in each 4-digit NAICS industry,
joined to BEA sectors through the BEA-NAICS concordance. May 2021 is the first year on the same occupation codes as O*NET
and the last on 2017 industry codes; it is four years after the input-output tables.</li>
<li><b>Holes.</b> {n_meas} of {n_all} sectors are measured. The rest keep their elicited scores: farms
({fallback.get("farm", 0)}, which OEWS does not survey), government, housing and special accounts
({fallback.get("government_or_special", 0)}), and {fallback.get("no_oews_match", 0)} with no OEWS industry.
{"Too few occupations use " + " or ".join(thin) + " to measure them, so they also stay on elicited scores." if thin else ""}
Elicited scores are put on the occupational scale: a score of <i>s</i> becomes the average share of measured sectors
scored <i>s</i>.</li>
</ul>
{table([th("Capability"), th("Elicited rank", "num"), th("Occupational rank", "num"), th("Agreement across sectors", "num")], rows,
       caption=f"Rank correlation between the two capability rankings: {rho:.2f}. Agreement across sectors: rank correlation, over the "
               f"{n_meas} measured sectors, between the elicited weight and the occupational share. Sorted by how far the "
               "occupational measure moves the capability up. A dash marks a capability too thin to measure: its occupational rank comes "
               "from its elicited scores, rescaled with the pooled average of the other capabilities, and says nothing new.")}
<h3>Where they disagree</h3>
<ul>
<li><b>Process flowsheeting {moves("process")}.</b> Only chemical, mechanical and biomedical engineers list
flowsheeting tools; the operators who run the plants do not. As a measure of how much work goes through the software,
the occupational figure is right. As a measure of dependence it is wrong: a refinery or a chemical plant cannot be designed
without it. Believe the elicited score about dependence and the occupational one about volume.</li>
<li><b>Logistics {moves("logistics")}, and agreement across sectors is {a.at["logistics", "spearman_across_sectors"]:.2f}.</b> The scores call trade
critically dependent on logistics optimization, but stores and wholesalers employ almost no logisticians, dispatchers or
planners; warehousing has the highest share at {sh.loc["493000", "logistics"]:.0%}. Retail routing and inventory
optimization is bought as software or service, not staffed. The occupational figure is the more believable account of
where the work happens; the elicited "trade = 3" overstates it.</li>
<li><b>IC design {moves("ic")}.</b> The scores give IC design only to semiconductors, but electrical and
computer hardware engineers who list HDL, FPGA and circuit-simulation tools work across aerospace, defense, computers and
instruments. The occupational figure is more believable: FPGA and ASIC design happens well outside chip makers, though
O*NET does not separate FPGA work from full custom chip design.</li>
<li><b>Geospatial {moves("gis")}, but agreement across sectors is {a.at["gis", "spearman_across_sectors"]:.2f}.</b> The scores put its weight on farming, extraction
and utilities; occupations put it on engineering services, consulting and research, and farms are not in OEWS at all.
Neither is complete: farm operators who run GPS guidance do not list GIS products.</li>
</ul>
<h3>Limits of the occupational measure</h3>
<ul>
<li>It measures who uses the software, not whether the sector could run without it. Two engineers running FEA on every
product are a small share of the wage bill and a hard dependency. That is why exposure still comes from the elicited scores.</li>
<li>O*NET records that an occupation uses a product, not how many hours.</li>
<li>The software map and the {min_products}-product rule are judgment calls, though much smaller and easier to check than the score
matrix.</li>
<li>Work bought from engineering firms shows up in those firms, not in the buyer: a utility that contracts out its
hydraulic modeling looks like it does none.</li>
</ul>
"""


def method_page(d: Data) -> str:
    srows = [f'<tr><td class="wrap">{e(k[0].upper() + k[1:])}</td><td class="num">{r.spearman_vs_headline:.2f}</td>'
             f'<td class="num">{int(r.top5_overlap)} of 5</td></tr>' for k, r in d.sens.iterrows()]
    arows = [f'<tr><td>{e(words(k))}</td><td class="num">{r.without_capital * 100:.2f}</td><td class="num">{r.output_per_basket_dollar * 100:.2f}</td>'
             f'<td class="num">{r.capital_multiplier:.1f}&times;</td></tr>'
             for k, r in d.arch.sort_values("capital_multiplier", ascending=False).head(8).iterrows()]
    occ = occupations_section(d)
    body = f"""
<h1>Method</h1>
<p class="lede">Input-output analysis: define a basket of needs, trace everything the economy must
produce to deliver it, then ask which engineering capabilities those producers depend on.</p>

<h2>Steps</h2>
<h3>Tables</h3>
<p>The U.S. Bureau of Economic Analysis 2017 benchmark Make and Use tables: 402 industries by 402 commodities,
after redefinitions, in producer prices.</p>
<h3>Capital as an input</h3>
<p>A standard input-output table treats equipment and buildings as final demand, so a tractor is not an input to
farming. Here, investment is routed back to the industries that use it. Capital goods with an evident user go to that
user (farm machinery to farms, medical equipment to health care, turbines to electric utilities). The rest is spread
in proportion to each industry's gross operating surplus.</p>
{table([th("Kind of sector"), th("Without capital, &cent;", "num"), th("With capital, &cent;", "num"), th("Change", "num")], arows,
       caption="Output required per dollar of basket. Machines only show up once capital counts as an input.")}
<h3>Total requirements</h3>
<p>With <i>U</i> the Use table, <i>K</i> the capital matrix, <i>V</i> the Make table, <i>g</i> industry output and <i>q</i> commodity output:</p>
<pre><code>B = (U + K) diag(g)^-1     D = V diag(q)^-1     A = B D     L = (I - A)^-1</code></pre>
<p><code>L[j, i]</code> is dollars of commodity <i>j</i> needed, directly and indirectly, per dollar of final demand for
commodity <i>i</i>. Imports stay inside <i>U</i>, so <i>L</i> describes the technology required wherever it runs.</p>
<h3>Basket</h3>
<p>Household plus government consumption, with every commodity assigned to one of eleven needs or left out.
Mixed retail, wholesale and freight margins are split across needs in proportion to goods spending.</p>
<h3>Capabilities</h3>
<p>Each commodity gets one of 56 engineering archetypes, and each archetype a score from 0 to 3 on each capability:
3 means the sector cannot design, run or maintain its product or plant without it, 2 means important and routine,
1 means incidental. Scores describe the sector's own activity; dependence on suppliers comes from <i>L</i>.
Scores map to weights of 1.0, 0.3 and 0.1.</p>
{occ}
<h2>How far to trust it</h2>
<p>Checked by tests: the Use table balances, the capital matrix conserves investment, and the model reproduces the
observed output of every sizeable commodity to within 1%, with and without capital.</p>
{table([th("Variant"), th("Rank correlation with headline", "num"), th("Top five shared", "num")], srows,
       caption="How much the capability ranking moves when an assumption changes.")}
<h3>Limits, most important first</h3>
<ul>
<li>The capability scores are one model's opinion. The ranking is arithmetic on those scores. It makes the judgments
explicit and shows their consequences, and it confirms nothing independently. The
<a href="#occupations">occupational check</a> tests the usage half of them against data.</li>
<li>No substitutability. Weight understates a small input with no substitute, and breadth cannot tell a relay from a sign.</li>
<li>US spending defines the basket. A basket in physical units would shift weight toward farming, water and energy.</li>
<li>Capital buyers are allocated by rule, not observed. The rules move the per-need figures; the overall ranking does not depend on them.</li>
<li>Gross investment stands in for capital use, so growing sectors look more capital-hungry than they are in steady state.</li>
<li>Archetypes are coarse. All machinery shares one row of scores, apart from fluid machinery.</li>
<li>Only design software is counted. Tacit process knowledge, metrology, materials data and general mathematics
software are not on the list.</li>
</ul>

<h2>Change it</h2>
<p>Every judgment is a CSV in <a href="{REPO}/tree/main/config"><code>config/</code></a>: what counts as a need,
who buys which capital goods, which archetype each sector is, and the score matrix. Edit one, then:</p>
<pre><code>python scripts/03_run.py     # recompute results/
python -m plenty.site        # rebuild this site
python -m pytest tests</code></pre>
"""
    return page("Method", "method.html", body)


def main():
    d = Data()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    pages = {"index.html": index, "needs.html": needs_page, "capabilities.html": capabilities_page,
             "gaps.html": gaps_page, "work.html": work_page, "sectors.html": sectors_page,
             "method.html": method_page}
    for name, fn in pages.items():
        (SITE / name).write_text(fn(d), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

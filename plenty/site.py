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

from . import analysis as A, occupations as O

ROOT = Path(__file__).resolve().parent.parent
CONFIG, RESULTS, WEB, SITE = ROOT / "config", ROOT / "results", ROOT / "plenty" / "web", ROOT / "site"
TAXONOMY = ROOT / "taxonomy"
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
    ("sectors.html", "Sectors", None), ("activities.html", "Activities", None), ("method.html", "Method", None),
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
        self.sbn = pd.read_csv(RESULTS / "sector_by_need.csv", index_col=0)
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
        self.rationale = pd.read_csv(CONFIG / "score_rationale.csv", dtype=str).fillna("")
        self.calibration = pd.read_csv(RESULTS / "score_weight_calibration.csv", index_col=0)
        self.rdi = pd.read_csv(RESULTS / "rd_intensity.csv", index_col=0)
        self.has_board = self.caps.board.notna()
        # The capability taxonomy (taxonomy/build.py): domains, capabilities and tasks; where each
        # was drawn from; and which taxonomy capabilities each of the 18 weighted functions became.
        self.tax = pd.read_csv(TAXONOMY / "capabilities.csv", dtype=str).fillna("").astype({"level": int})
        self.tax_children = {k: g for k, g in self.tax.groupby("parent")}
        self.tax_name = self.tax.set_index("id").name
        cross = pd.read_csv(TAXONOMY / "crosswalk.csv").fillna("")
        self.tax_cross = cross.assign(capability=cross.node.str.split(".").str[:2].str.join("."),
                                      domain=cross.node.str.split(".").str[0])
        self.tax_func = pd.read_csv(TAXONOMY / "function_map.csv").fillna("")
        # Where today's value flows (plenty/flows.py): need dollar -> sectors -> occupations -> capabilities.
        self.flow = pd.read_csv(RESULTS / "capability_flow.csv", index_col=0)
        self.flow_need = pd.read_csv(RESULTS / "capability_flow_by_need.csv", index_col=0)
        self.flow_need_d = pd.read_csv(RESULTS / "capability_flow_distinctive_by_need.csv", index_col=0)
        self.flow_work = pd.read_csv(RESULTS / "capability_flow_work.csv", index_col=0)
        self.flow_occ = pd.read_csv(RESULTS / "capability_flow_occupations.csv")
        self.flow_acct = pd.read_csv(RESULTS / "capability_flow_accounting.csv", index_col=0)
        # Demand and means side by side, per capability: its flow, and how many of its tasks have a
        # known open tool or could have an open benchmark. Open leaderboards that exist today are in
        # config/boards.csv, placed on the taxonomy capability each one measures.
        tasks = self.tax[self.tax.level == 2]
        self.balance = tasks.groupby("parent").agg(
            tasks=("id", "size"), open=("open_tools", lambda x: (x != "").sum()),
            bench=("benchmarkable", lambda x: (x == "yes").sum())).join(self.flow[["name", "domain", "flow", "rank", "top_need"]])
        self.boards = pd.read_csv(CONFIG / "boards.csv").fillna("")
        # The work that has to get done (plenty/work.py): O*NET work activities at three levels, the
        # flow through each, and the software listed by the people who do each.
        self.act = pd.read_csv(RESULTS / "activity_flow.csv", index_col=0).fillna({"parent": ""})
        self.act_need = pd.read_csv(RESULTS / "activity_flow_by_need.csv", index_col=0)
        self.act_work = pd.read_csv(RESULTS / "activity_flow_work.csv", index_col=0)
        self.act_occ = pd.read_csv(RESULTS / "activity_flow_occupations.csv")
        self.act_tasks = pd.read_csv(RESULTS / "activity_flow_tasks.csv")
        self.act_cap = pd.read_csv(RESULTS / "activity_capability_flow.csv")
        self.act_acct = pd.read_csv(RESULTS / "activity_flow_accounting.csv", index_col=0).value
        self.act_children = {k: g.sort_values("flow", ascending=False) for k, g in self.act[self.act.parent != ""].groupby("parent")}
        self.act_software = {k: g for k, g in self.act_cap.sort_values("flow", ascending=False).groupby("iwa")}
        # AI as a means (plenty/ai.py): each vendor's share of conversations by activity, beside the work's share
        self.ai = pd.read_csv(RESULTS / "activity_ai.csv", index_col=0)
        self.ai_src = pd.read_csv(RESULTS / "activity_ai_sources.csv", index_col=0)

    def cap_name(self, k):
        return self.caps.at[k, "name"]

    def boards_html(self, capabilities, none: str = "") -> str:
        """Links to the open leaderboards that measure any of these taxonomy capabilities."""
        b = self.boards[self.boards.capability.isin(list(capabilities))]
        return "; ".join(f'<a href="{e(x.url)}">{e(x.board)}</a>' if x.url else e(x.board) for x in b.itertuples()) or none

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

SCORE_MEANING = {3: "cannot design, run or maintain its product or plant without it", 2: "important and routine",
                 1: "incidental", 0: "not used"}
SHOW_SECTORS = 15   # sectors listed before the "show all" fold on a capability page


def score_tip(score: int, extra: str = "", focusable: bool = True) -> str:
    """Attributes for the hover tip (site.js) saying what a 0-3 score means and how it counts.
    focusable adds a tab stop so keyboard users get the tip too (links have one already)."""
    tip = f"Score {score}: {SCORE_MEANING[score]}."
    if score:
        tip += f" Counts \u00d7 {A.SCORE_WEIGHT[score]:g} toward the weight"
        tip += ", and the sector counts toward exposure." if score >= 3 else "."
    if extra:
        tip += " " + extra
    return f'data-tip="{e(tip)}"' + (' tabindex="0"' if focusable else "")


def cap_href(k: str, anchor: str = "") -> str:
    return f"capability-{k}.html" + (f"#{anchor}" if anchor else "")


def sector_scores(d: Data, k: str) -> pd.Series:
    """Elicited 0-3 score on capability k for every sector (scores are set per kind of sector)."""
    return d.scores[k].reindex(d.sectors.archetype).set_axis(d.sectors.index).astype(int)


def weight_terms(d: Data, k: str) -> pd.DataFrame:
    """Per-sector terms that sum to capability k's weight (analysis.run, weight_equal_need)."""
    score = sector_scores(d, k)
    t = pd.DataFrame({"archetype": d.sectors.archetype, "score": score, "score_weight": score.map(A.SCORE_WEIGHT),
                      "share": d.sectors.value_added_share_equal})
    t["term"] = t.score_weight * t.share
    return t[t.term > 0].sort_values("term", ascending=False)


def exposure_terms(d: Data, k: str) -> pd.DataFrame:
    """Per-sector terms that sum to capability k's exposure (analysis.run, exposure_mean)."""
    crit = sector_scores(d, k) >= 3
    t = pd.DataFrame({"archetype": d.sectors.archetype, "term": d.sectors.output_per_need_dollar_equal})[crit]
    return t.sort_values("term", ascending=False)


def f4(x: float) -> str:
    return f"{x:.4f}"


def rationale(d: Data, arch: str, k: str) -> str:
    r = d.rationale
    hit = r[(r.archetype == arch) & (r.capability == k)]
    if len(hit):
        row = hit.iloc[0]
        src = f' <span class="dim">Sources: {e(row.sources)}</span>' if row.sources else ""
        return f"<p>{e(row.rationale)}{src}</p>"
    score = int(d.scores.at[arch, k])
    title = f"Justify score: {words(arch)} x {d.cap_name(k)} = {score}"
    return (f'<p class="dim">No justification recorded yet. <a href="{issue_link(title)}">Propose one</a> '
            f'(it goes in <code>config/score_rationale.csv</code>).</p>')


def occupational_evidence(d: Data, arch: str, k: str) -> str:
    sh, name = d.occ_shares, d.cap_name(k)
    if d.agree.at[k, "thin"]:
        return f'<p class="dim">Occupations: too few occupations list {e(name)} software to measure.</p>'
    mine = sh[(d.sectors.archetype.reindex(sh.index) == arch)]
    measured = mine[mine.source == "oews"][k]
    if measured.empty:
        why = {"fallback:farm": "OEWS does not survey farms",
               "fallback:government_or_special": "these sectors have no OEWS industry"}.get(mine.source.iloc[0], "no OEWS data")
        return f'<p class="dim">Occupations: not measured ({why}).</p>'
    all_meas = sh.source == "oews"
    by_score = sh.loc[all_meas, k].groupby(sector_scores(d, k)[all_meas]).mean()
    score = int(d.scores.at[arch, k])
    rng = (f"{measured.min():.1%} to {measured.max():.1%}, median {measured.median():.1%}" if len(measured) > 1
           else f"{measured.iloc[0]:.1%}")
    compare = ", ".join(f"{s}: {v:.1%}" for s, v in by_score.sort_index(ascending=False).items())
    return (f'<p>Occupations: {rng} of the wage bill in these sectors goes to occupations that use {e(name)} software. '
            f'<span class="dim">Average over all measured sectors, by their score for {e(name)}: {compare}.</span> '
            f'<a href="method.html#occupations">How this is measured</a>.</p>')


def rd_evidence(d: Data, arch: str, k: str) -> str:
    """Business R&D per dollar of output for a kind's sectors, against sectors at each score."""
    if not d.caps.at[k, "rd_proxy"]:
        return ""
    rd = d.rdi.rd_per_output
    mine = rd[d.sectors.archetype.reindex(rd.index) == arch].dropna()
    if mine.empty:
        return '<p class="dim">R&amp;D: not covered (the NSF survey leaves out farms and government).</p>'
    covered = rd.dropna()
    by_score = covered.groupby(sector_scores(d, k)[covered.index]).median()
    rng = (f"{mine.min():.1%} to {mine.max():.1%} of their output on R&amp;D (median {mine.median():.1%})" if len(mine) > 1
           else f"{mine.iloc[0]:.1%} of their output on R&amp;D")
    compare = ", ".join(f"{s}: {v:.1%}" for s, v in by_score.sort_index(ascending=False).items())
    return (f'<p>R&amp;D: the industries these sectors belong to spend {rng}. <span class="dim">Median over all covered '
            f'sectors, by their score for {e(d.cap_name(k))}: {compare}.</span> <a href="method.html#rd">How this is measured</a>.</p>')


def tipped(text: str, tip: str) -> str:
    """A value that explains itself on hover or focus (site.js)."""
    return f'<span data-tip="{e(tip)}" tabindex="0">{text}</span>'


def weight_term_tip(w: float, share: float, term: float, n: int | None = None) -> str:
    tip = f"Score weight {w:g} \u00d7 share of value added {share:.3%} = {term:.4f}."
    if n is not None:
        tip = (f"Score weight {w:g} \u00d7 its {n} sector{'s' if n != 1 else ''}' combined share of value added "
               f"{share:.3%} = {term:.4f}. The same as the sum of their terms.")
    return tip


EXPOSURE_TERM_TIP = ("Dollars of this sector's output needed, directly and through its customers, per dollar of "
                     "basket (each need counted equally). Scored 3, so it counts in full: {term:.4f}.")


def total_tip(n: int, what: str, total: float) -> str:
    return f"Sum of the {n} sector terms: {what} = {total:.4f}."


def kind_rows(d: Data, k: str, t: pd.DataFrame, with_score: bool, prefix: str) -> list[str]:
    """One row per kind of sector, each followed by its sectors as hidden child rows that the
    kind's name toggles open (site.js). Each group shares one band so it reads as a block."""
    g = t.groupby("archetype").agg(n=("term", "size"), term=("term", "sum"))
    if with_score:
        g = g.join(t.groupby("archetype").agg(share=("share", "sum")))
    g = g.sort_values("term", ascending=False)
    rows = []
    for i, (a, r) in enumerate(g.iterrows()):
        band = ' band' if i % 2 == 0 else ''
        group = f"{prefix}-{a}"
        score = int(d.scores.at[a, k])
        cells = [f'<td><button type="button" class="expander" aria-expanded="false" data-group="{group}">'
                 f'{e(words(a))}</button></td>']
        if with_score:
            cells += [f'<td class="num"><a href="#score-{a}" {score_tip(score, "Click for the evidence.", focusable=False)}>{score}</a></td>',
                      f'<td class="num">&times; {A.SCORE_WEIGHT[score]:g}</td>',
                      f'<td class="num">{int(r.n)}</td>', f'<td class="num">{r.share:.2%}</td>']
        else:
            cells += [f'<td class="num">{int(r.n)}</td>']
        w = A.SCORE_WEIGHT[score]
        tip = (weight_term_tip(w, r.share, r.term, int(r.n)) if with_score else
               f"Sum of the output per basket dollar of its {int(r.n)} sector{'s' if r.n != 1 else ''}, each scored 3: {r.term:.4f}.")
        cells += [f'<td class="num">{tipped(f4(r.term), tip)}</td>']
        rows.append(f'<tr class="kind{band}">{"".join(cells)}</tr>')
        for j, c in t[t.archetype == a].iterrows():
            cells = [f'<td class="child"><a href="sectors.html#{j}">{e(d.sectors.at[j, "name"])}</a></td>']
            if with_score:
                cells += [f'<td class="num dim"><span {score_tip(score)}>{score}</span></td>', f'<td class="num dim">&times; {A.SCORE_WEIGHT[score]:g}</td>',
                          '<td></td>', f'<td class="num">{c.share:.2%}</td>']
            else:
                cells += ['<td></td>']
            tip = weight_term_tip(w, c.share, c.term) if with_score else EXPOSURE_TERM_TIP.format(term=c.term)
            cells += [f'<td class="num">{tipped(f4(c.term), tip)}</td>']
            rows.append(f'<tr class="sub{band}" data-group="{group}" hidden>{"".join(cells)}</tr>')
    return rows


def sector_rows(d: Data, t: pd.DataFrame, with_score: bool) -> list[str]:
    rows = []
    for j, r in t.iterrows():
        cells = [f'<td class="name"><a href="sectors.html#{j}">{e(d.sectors.at[j, "name"])}</a></td>',
                 f'<td class="dim"><a href="#score-{r.archetype}">{e(words(r.archetype))}</a></td>']
        if with_score:
            cells += [f'<td class="num" data-v="{r.score}"><span {score_tip(int(r.score))}>{int(r.score)}</span></td>', f'<td class="num" data-v="{r.share}">{r.share:.3%}</td>']
        tip = (weight_term_tip(A.SCORE_WEIGHT[int(r.score)], r.share, r.term) if with_score
               else EXPOSURE_TERM_TIP.format(term=r.term))
        cells += [f'<td class="num" data-v="{r.term}">{tipped(f4(r.term), tip)}</td>']
        rows.append(f'<tr>{"".join(cells)}</tr>')
    return rows


def folded_table(head: list[str], rows: list[str], foot: str, what: str) -> str:
    """The first SHOW_SECTORS rows, then the full sortable table behind a fold."""
    if len(rows) <= SHOW_SECTORS:
        return table(head, rows, foot=foot)
    return (table(head, rows[:SHOW_SECTORS], foot=foot) +
            f'<details class="fold"><summary>Show all {len(rows)} {what}</summary>'
            f'{table(head, rows, attrs=" data-full", foot=foot)}</details>')


def by_need_list(values: pd.Series, fmt=f3) -> str:
    top = values.idxmax()
    items = "".join(f'<li{" class=max" if n == top else ""}><span>{e(NEED_NAME.get(n, n))}</span><span>{fmt(v)}</span></li>'
                    for n, v in values.items())
    return f'<ul class="byneed">{items}</ul>'


def capability_detail_page(d: Data, k: str) -> str:
    name, r = d.cap_name(k), d.ct.loc[k]
    n = len(d.ct)
    cw = d.calibration.weight_calibrated
    wt, xt = weight_terms(d, k), exposure_terms(d, k)
    weight, expo = wt.term.sum(), xt.term.sum()
    w_total = tipped(f4(weight), total_tip(len(wt), "weight", weight))

    w_kind = table([th("Kind of sector"), th("Score", "num"), th("Weight", "num"), th("Sectors", "num"),
                    th("Share of value added", "num"), th("Term", "num")],
                   kind_rows(d, k, wt, True, "w"), attrs=" data-tree",
                   foot=f'<tr><td>Weight</td><td></td><td></td><td class="num">{len(wt)}</td>'
                        f'<td class="num">{wt.share.sum():.2%}</td><td class="num">{w_total}</td></tr>')
    w_sec = folded_table([th("Sector", sort="text"), th("Kind", sort="text"), th("Score", "num", "num"),
                          th("Share of value added", "num", "num"), th("Term", "num", "num")],
                         sector_rows(d, wt, True),
                         f'<tr><td>Weight</td><td></td><td></td><td class="num">{wt.share.sum():.3%}</td><td class="num">{w_total}</td></tr>',
                         "sectors")
    if len(xt):
        x_total = tipped(f4(expo), total_tip(len(xt), "exposure", expo))
        x_kind = table([th("Kind of sector"), th("Sectors", "num"), th("Output per basket $", "num")],
                       kind_rows(d, k, xt, False, "x"), attrs=" data-tree",
                       foot=f'<tr><td>Exposure</td><td class="num">{len(xt)}</td><td class="num">{x_total}</td></tr>')
        x_sec = folded_table([th("Sector", sort="text"), th("Kind", sort="text"), th("Output per basket $", "num", "num")],
                             sector_rows(d, xt, False),
                             f'<tr><td>Exposure</td><td></td><td class="num">{x_total}</td></tr>', "sectors")
        x_need = by_need_list(d.sbn.loc[xt.index].sum())
        exposure_html = f"""<p>Exposure counts only sectors scored 3: those that cannot design, run or maintain their product or
plant without {e(name)}. For each, it takes the dollars of output that sector must produce, directly or through its
customers, per dollar of basket, with every need counted equally. The sum is {expo * 100:.1f} cents per basket dollar.</p>
<h3>By kind of sector</h3>
<p class="note">Click a kind to list its sectors.</p>
{x_kind}
<h3>Sector by sector</h3>
{x_sec}
<h3>By need</h3>
<p class="note">The same sum per dollar of each need. Exposure is their average; the largest is in bold.</p>
{x_need}"""
    else:
        exposure_html = f"<p>No kind of sector is scored 3 for {e(name)}, so its exposure is zero.</p>"

    kinds = wt.groupby("archetype").term.sum().sort_values(ascending=False).index
    entries = []
    for a in kinds:
        score = int(d.scores.at[a, k])
        entries.append(f"""<article class="score" id="score-{a}">
<h3>{e(words(a)).capitalize()} <span class="pill s{score}" {score_tip(score)}>{score}</span> <span class="dim">{SCORE_MEANING[score]}</span></h3>
{rationale(d, a, k)}
{occupational_evidence(d, a, k)}
{rd_evidence(d, a, k)}
</article>""")
    zero = [words(a) for a in d.scores.index[d.scores[k] == 0]]

    body = f"""
<p class="crumbs"><a href="index.html">Balance</a> / <a href="capabilities.html#{k}">Capabilities</a></p>
<h1>{e(name)}</h1>
<p class="lede">{e(d.caps.at[k, "description"].replace("; ", ", "))}.</p>
<dl class="figures">
<div><dt><a href="#weight">Weight</a></dt><dd>{f3(r["volume weight"])}</dd><dd class="dim">rank {int(r.volume_rank)} of {n}</dd></div>
<div><dt><a href="#exposure">Exposure</a></dt><dd>{f3(r["exposure"])}</dd><dd class="dim">rank {int(r.exposure_rank)} of {n}</dd></div>
<div><dt><a href="method.html#occupations">Occupational weight</a></dt><dd>{f3(r["occupational weight"])}</dd><dd class="dim">rank {int(r.occupational_rank)} of {n}</dd></div>
<div><dt>Open leaderboard</dt><dd class="small">{d.board_html(k)}</dd></div>
</dl>

<h2 id="weight">Weight, worked out</h2>
<p>Weight is a sum over sectors. Each sector's share of the value added embodied in the basket of needs (every need
counted equally) is multiplied by the weight of its score for {e(name)}: 1 for a 3 ({SCORE_MEANING[3]}), 0.3 for a 2
({SCORE_MEANING[2]}), 0.1 for a 1 ({SCORE_MEANING[1]}). {len(wt)} of {len(d.sectors)} sectors have a nonzero score.
Scores are set per kind of sector, so the sum is shown first by kind; each kind links to
<a href="#scores">its score and the evidence for it</a>.</p>
<p class="note">The weights 1, 0.3 and 0.1 are assumed. <a href="method.html#score-weights">Occupation data</a> put a 2 at
{cw[2]:.2f} and a 1 at {cw[1]:.2f}; with those, {e(name)} would weigh {f3(r["calibrated weight"])} (rank
{int(r.calibrated_rank)} of {n}).</p>
<h3>By kind of sector</h3>
<p class="note">Click a kind to list its sectors.</p>
{w_kind}
<h3>Sector by sector</h3>
{w_sec}
<h3>By need</h3>
<p class="note">The same sum within each need. The weight is their average; the largest is in bold.</p>
{by_need_list(d.cbn.loc[k])}

<h2 id="exposure">Exposure, worked out</h2>
{exposure_html}

<h2 id="scores">The scores behind it</h2>
<p>One score per kind of sector, from <a href="{REPO}/blob/main/config/archetype_capabilities.csv"><code>config/archetype_capabilities.csv</code></a>,
in the order of the table above. Each shows its justification and what occupation data, and for design tools R&amp;D,
say about it.</p>
<div class="scores">{"".join(entries)}</div>
<p class="note">Scored 0 (not used): {e(", ".join(zero)) or "none"}.</p>
"""
    return page(name, f"capability-{k}.html", body, long_title=True)


def balance_tree(d: Data) -> list[str]:
    """Demand against means: one row per domain, each followed by its capabilities as hidden
    child rows that the domain's name toggles open (site.js)."""
    B = d.balance
    dom = B.groupby("domain").agg(flow=("flow", "sum"), tasks=("tasks", "sum"), open=("open", "sum"),
                                  bench=("bench", "sum"), n=("flow", "size")).sort_values("flow", ascending=False)
    rows = []
    for i, (k, r) in enumerate(dom.iterrows()):
        band, name = (" band" if i % 2 == 0 else ""), d.tax_name[k]
        caps = B[B.domain == k].sort_values("flow", ascending=False)
        rows.append(
            f'<tr class="kind{band}"><td><button type="button" class="expander" aria-expanded="false" data-group="b-{k}">'
            f'{e(name)}</button><div class="dim capdef">{int(r.n)} capabilities</div></td>'
            f'<td>{bar(r.flow, dom.flow.max(), cents(r.flow, 1), f"{name}: {r.flow * 100:.1f} cents of each need dollar flow through its capabilities")}</td>'
            f'<td>{bar(r.open / r.tasks, 1, f"{r.open / r.tasks:.0%}", f"{name}: {int(r.open)} of {int(r.tasks)} tasks have a known open-source tool")}</td>'
            f'<td>{bar(r.bench / r.tasks, 1, f"{r.bench / r.tasks:.0%}", f"{name}: an open benchmark is possible today for {int(r.bench)} of {int(r.tasks)} tasks")}</td>'
            f'<td>{d.boards_html(caps.index)}</td></tr>')
        rows += [
            f'<tr class="sub{band}" data-group="b-{k}" hidden><td class="child"><a href="capabilities.html#{c.Index}">{e(c.name)}</a></td>'
            f'<td class="num"><a href="{flow_href(c.Index)}" data-tip="Rank {int(c.rank)} of {len(B)}. Click for the derivation.">{cents(c.flow)}</a></td>'
            f'<td>{int(c.open)} of {int(c.tasks)} tasks</td><td>{int(c.bench)} of {int(c.tasks)} tasks</td>'
            f'<td>{d.boards_html([c.Index])}</td></tr>' for c in caps.itertuples()]
    return rows


def index(d: Data) -> str:
    total = d.needs.final_demand_musd.sum() / 1e6
    B, A = d.balance, d.act
    acct = d.act_acct
    half = B[B.open * 2 < B.tasks].sort_values("flow", ascending=False)
    lead = ", ".join(f'<a href="{flow_href(k)}">{e(r["name"].lower())}</a>' for k, r in half.head(3).iterrows())
    I = A[A.level == "intermediate"].sort_values("flow", ascending=False)
    biggest = ", ".join(f'<a href="{act_href(k)}">{e(r["name"].rstrip(".").lower())}</a>' for k, r in I.head(3).iterrows())
    U = d.ai[d.ai.level == "intermediate"].sort_values("pooled", ascending=False)
    n_half = int(((U.pooled.cumsum() / U.pooled.sum()) < 0.5).sum()) + 1
    half_flow, absent = U.flow_share.iloc[:n_half].sum(), U.flow_share[U.intensity < 0.1].sum()
    body = f"""
<h1>A material balance for the machines behind human needs</h1>
<p class="lede">Plenty keeps an account of what people need, the work that meeting those needs takes, and which of
the means of doing that work exist in the open. Where the two sides do not balance, there is work to do.</p>
<p class="caveat">This is a first pass. The work and its flows come from public data. AI models wrote the list of software
capabilities and what is said about open tools, and nobody who works in these fields has reviewed either.
<a href="method.html#trust">How far to trust it</a>.</p>

<h2>The balance today</h2>
<h3 id="demand">Demand: the work that has to get done</h3>
{table([th(x) for x in ACTIVITY_HEAD], activity_tree(d), attrs=" data-tree", caption=ACTIVITY_CAPTION)}
<p class="note">{acct["flowed"] * 100:.0f} cents of each need dollar are traced to a kind of work; the rest sits in sectors or
occupations with no data. The largest activities are {biggest}. <a href="activities.html">All {len(I)} activities</a>.</p>

<h3 id="means">Means: the software that exists to do it</h3>
{table(
    [th("Domain, then its capabilities"), th("Flow, &cent; per need dollar"), th("Tasks with an open tool"),
     th("Open benchmark possible"), th("Open leaderboard today")],
    balance_tree(d), attrs=" data-tree",
    caption="Software is one means of doing the work. Flow here is the part of each need dollar earned by the people who list a "
            "domain's software. The next columns are the share of its tasks that have a known open-source tool, and the share for "
            "which public reference problems exist to score tools on. Click a domain to list its capabilities.")}
<p class="note">{(B.tasks.sum() - B.open.sum()):,} of {B.tasks.sum():,} software tasks have no known open tool, and {len(half)} of {len(B)}
capabilities have one for fewer than half their tasks; the largest of those by flow are {lead}.
{len(d.boards)} open leaderboards exist. <a href="gaps.html">See the gaps</a>.</p>
<h3 id="ai">Means: AI</h3>
<p>AI systems are a way of doing much of this work, and three vendors publish what theirs are used for. Half of that use
falls in {n_half} of the {len(I)} activities, which together carry {half_flow:.0%} of the need dollar: gathering information,
editing and writing, and work on computers. Activities that carry {absent:.0%} of the dollar, most of them physical work
and directing people, get less than a tenth of the AI use their size would suggest. The last column of the first table
shows it for every kind of work. <a href="activities.html#ai">Where AI is used</a>.</p>
<p class="note">Use is not capability. How well AI systems do each kind of work is what open benchmarks would measure, and
that is not collected yet. <a href="method.html#ai">What the sources are and what they leave out</a>.</p>

<h2>How the account is kept</h2>
<ol class="loop">
<li><a href="needs.html">Collect needs</a><p>{len(d.needs)} needs, each counted equally, met the way US households
and governments met them in 2017 with ${total:.1f} trillion of spending. Each need dollar is traced through
<a href="sectors.html">sectors</a> to the <a href="activities.html">work</a> it pays for.</p></li>
<li><a href="capabilities.html">Collect capabilities</a><p>The means of doing the work. So far {len(B)} kinds of software in
{(d.tax.level == 0).sum()} domains and {B.tasks.sum():,} tasks, drafted from published taxonomies, with what is known to exist
in the open for each.</p></li>
<li><a href="gaps.html">Identify gaps</a><p>Means that work depends on and that have no open tool, or that nobody is
measuring in the open.</p></li>
<li><a href="work.html">Dispatch work</a><p>{len(d.work)} proposed leaderboards, measurements and reviews. Each one
can be claimed by opening an issue.</p></li>
</ol>
<p class="note">An earlier account of <a href="capabilities.html#functions">eighteen engineering functions</a> also measures
exposure: what cannot run without a function.</p>
"""
    return page("Plenty", "index.html", body)


def needs_page(d: Data) -> str:
    T = d.needs
    n_needs = len(T)
    rows = []
    for n, r in T.iterrows():
        rows.append(
            f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="wrap dim">{e(d.needs_cfg.at[n, "description"].replace("; ", ", "))}</td>'
            f'<td class="num">{1 / n_needs:.1%}</td>'
            f'<td class="num">{r.final_demand_musd / 1e3:,.0f}</td>'
            f'<td>{bar(r.share, T.share.max(), f"{r.share:.0%}", f"{NEED_NAME[n]}: ${r.final_demand_musd / 1e3:,.0f} billion, {r.share:.1%} of spending on the {n_needs} needs. Not its weight: every need weighs {1 / n_needs:.1%}.")}</td></tr>')
    foot = f'<tr><td>All needs</td><td></td><td class="num">100%</td><td class="num">{T.final_demand_musd.sum() / 1e3:,.0f}</td><td></td></tr>'
    water = T.share["water_sanitation"]

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

    def largest(frame, n):
        return "; ".join(f'<a href="{flow_href(k)}">{e(d.tax_name[k].lower())}</a> ({v * 100:.1f})'
                         for k, v in frame[n].nlargest(5).items())
    det = d.act[d.act.level == "detailed"]
    def work_of(n):
        return "; ".join(f'<a href="{act_href(det.at[k, "parent"])}">{e(det.at[k, "name"].rstrip(".").lower())}</a> ({v * 100:.1f})'
                         for k, v in d.act_need[n].nlargest(5).items())
    runs_on = [f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="wrap">{work_of(n)}</td>'
               f'<td class="wrap">{largest(d.flow_need_d, n)}</td></tr>' for n in need_cols]

    ups = []
    for n in need_cols:
        u = d.upstream[d.upstream.need == n].head(5)
        items = "; ".join(f"{e(x['name'].split(',')[0].lower())} ({x.output_per_need_dollar * 100:.1f}&cent;)" for _, x in u.iterrows())
        ups.append(f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="wrap">{items}</td></tr>')

    body = f"""
<h1>Needs</h1>
<p class="lede">Each of these {n_needs} needs counts equally: {1 / n_needs:.1%} of every capability measure on this site.
Within a need, what US households and governments spent on it in 2017 decides which sectors that share passes through.</p>
<p>Needs are complements, not substitutes. More health care does not make up for no water, so losing any one need
costs the whole bundle and no need can weigh more than another. Spending cannot measure this: it prices the last
unit, and water is cheap because it is a solved problem. By spending, water and sanitation would be {water:.1%}
of the basket; here it is {1 / n_needs:.1%}. Within a need the options do substitute (groceries or restaurants,
bus or car), so there spending is the right measure of how the need is met.</p>
{table([th("Need"), th("What it covers"), th("Weight", "num"), th("Spending, $ billion", "num"), th("Share of spending")], rows, foot=foot)}
<p class="note">Left out by default: federal government, finance and legal services, and a discretionary group (alcohol,
tobacco, gambling, lodging, jewelry, pets, personal services). They still count wherever the needs above buy from them.
Edit <code>config/basket.csv</code> and <code>config/needs.csv</code> to change what counts.</p>
<p class="caveat">Equal weights move the judgment into the list itself: splitting food into groceries and restaurants
would double food's weight. The list is ours and is not yet anchored to a published one such as Doyal and Gough's
intermediate needs or FEMA's community lifelines. Within a need, spending still overstates some things: restaurants
are over a third of food. A basket in physical units (calories, square meters, kilowatt-hours) is
<a href="work.html#sufficiency-basket">proposed work</a>.</p>

<h2 id="runs-on">What each need runs on today</h2>
<p>The work the largest parts of each need's dollar pay for (<a href="activities.html">activities</a>), and the software
most particular to the people who do it (<a href="capabilities.html">capabilities</a>). Figures are cents of the need's
dollar.</p>
{table([th("Need"), th("The work: detailed activities"), th("The means: software listed, by distinctive work")], runs_on,
       caption="The five largest flows of each kind per need. Flow shows where today's work goes, not what a need could not do without.")}

<h2>What each need draws on: engineering functions</h2>
{table(head, hrows, attrs=' id="heat"', caption="Percent of each need's embodied value added that arises in sectors depending on the capability, score-weighted. Stronger color is more.")}

<h2>Physical inputs behind each need</h2>
{table([th("Need"), th("Largest upstream physical sectors, in cents per dollar of the need")], ups,
       caption="Excludes what the need buys directly. Includes the equipment and buildings used up along the way.")}
"""
    return page("Needs", "needs.html", body)


BENCH_PILL = {"yes": "s3", "partly": "s2", "no": "s1"}
SHOW_FLOWS = 20     # capabilities in the largest-flows table
FLOW_SECTOR_CUT = 0.002   # a flow page names the sectors sending at least this share of the flow; the rest are summed
SHOW_SOURCES = 4    # schemes named per capability before "and n more"


def taxonomy_sources(cross: pd.DataFrame) -> str:
    """The published schemes a capability and its tasks cite, most cited first. A check mark
    means at least one of its entries here was checked against the source."""
    if cross.empty:
        return "no published counterpart found"
    g = cross.groupby("scheme").basis.agg(n="size", checked=lambda b: (b == "fetched").any())
    g = g.sort_values(["checked", "n"], ascending=False)
    names = [e(k) + (" &#10003;" if r.checked else "") for k, r in g.head(SHOW_SOURCES).iterrows()]
    more = f" and {len(g) - SHOW_SOURCES} more" if len(g) > SHOW_SOURCES else ""
    return "; ".join(names) + more


def flow_href(k: str, anchor: str = "") -> str:
    return "flow-" + k.replace(".", "-").replace("_", "-") + ".html" + (f"#{anchor}" if anchor else "")


def cents(x: float, digits: int = 2) -> str:
    """A share of the need dollar, in cents."""
    return f"{x * 100:.{digits}f}&cent;"


def flow_terms(d: Data, k: str, work: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-sector terms that sum to k's flow (flows.flow): the sector's share of the basket's
    value added times the share of its work in k. work is commodity x k: the capability table
    by default, the activity table for a work activity."""
    s = d.sectors
    work = d.flow_work if work is None else work
    t = pd.DataFrame({"name": s.name, "archetype": s.archetype, "share": s.value_added_share_equal,
                      "work": work[k].reindex(s.index).fillna(0.0)})
    t["term"] = t.share * t.work
    # != 0, not > 0: a few sectors (scrap, used goods) have negative value added and belong in the sum
    return t[t.term != 0].sort_values("term", ascending=False)


def flow_term_tip(name: str, share: float, work: float, term: float, n: int | None = None) -> str:
    who = f"Its {n} sector{'s' if n != 1 else ''} hold" if n is not None else "This sector holds"
    return (f"{who} {share:.3%} of the value added behind a need dollar; {work:.2%} of that work goes to "
            f"{name[:1].lower() + name[1:]}: {term * 100:.4f} cents." + (" The sum of their terms." if n is not None else ""))


def flow_kind_rows(name: str, t: pd.DataFrame) -> list[str]:
    """Kinds of sector, each followed by its sectors as hidden child rows (site.js), as kind_rows."""
    cut = FLOW_SECTOR_CUT * t.term.sum()
    rows = []
    for i, (a, g) in enumerate(sorted(t.groupby("archetype"), key=lambda x: -x[1].term.sum())):
        band, group = (" band" if i % 2 == 0 else ""), f"f-{a}"
        share, term = g.share.sum(), g.term.sum()
        rows.append(
            f'<tr class="kind{band}"><td><button type="button" class="expander" aria-expanded="false" data-group="{group}">'
            f'{e(words(a))}</button></td><td class="num">{len(g)}</td><td class="num">{share:.2%}</td>'
            f'<td class="num">{term / share:.2%}</td>'
            f'<td class="num">{tipped(f"{term * 100:.4f}", flow_term_tip(name, share, term / share, term, len(g)))}</td></tr>')
        shown, rest = g[g.term.abs() >= cut], g[g.term.abs() < cut]
        rows += [f'<tr class="sub{band}" data-group="{group}" hidden><td class="child"><a href="sectors.html#{x.Index}">{e(x.name)}</a></td>'
                 f'<td></td><td class="num">{x.share:.3%}</td><td class="num">{x.work:.2%}</td>'
                 f'<td class="num">{tipped(f"{x.term * 100:.4f}", flow_term_tip(name, x.share, x.work, x.term))}</td></tr>'
                 for x in shown.itertuples()]
        if len(rest):   # the many sectors that each send next to nothing, as one line so the sum stays exact
            rows.append(f'<tr class="sub{band}" data-group="{group}" hidden><td class="child dim">{len(rest)} smaller sector{"s" if len(rest) != 1 else ""}</td>'
                        f'<td></td><td class="num">{rest.share.sum():.3%}</td><td class="num">{rest.term.sum() / rest.share.sum():.2%}</td>'
                        f'<td class="num">{rest.term.sum() * 100:.4f}</td></tr>')
    return rows


def act_href(a: str, anchor: str = "") -> str:
    return "activity-" + a.replace(".", "-") + ".html" + (f"#{anchor}" if anchor else "")


def act_name(d: Data, a: str) -> str:
    """O*NET's names end in a full stop at the lower levels; drop it for headings and links."""
    return d.act.at[a, "name"].rstrip(".")


def software_links(d: Data, a: str, n: int = 3) -> str:
    """The software capabilities listed most by the people who do intermediate activity a."""
    g = d.act_software.get(a)
    if g is None:
        return '<span class="dim">none listed</span>'
    return ", ".join(f'<a href="{flow_href(k)}">{e(d.tax_name[k].lower())}</a>' for k in g.capability.head(n))


def open_bar(r, name: str) -> str:
    if pd.isna(r.software_open_share):
        return '<span class="dim">no software listed</span>'
    return bar(r.software_open_share, 1, f"{r.software_open_share:.0%}",
               f"{name}: of the software listed by the people who do this work, {r.software_open_share:.0%} of its tasks have a known open-source tool")


AI_NAME = {"claude": "Claude", "chatgpt": "ChatGPT", "copilot": "Copilot", "claude_api": "Anthropic API",
           "copilot_action": "Copilot, by what the AI did"}
AI_MIN_SHARE = 0.001    # below this share of AI use, a source's descriptions of the use are too thin to show


def share(x: float) -> str:
    """A share of conversations or of the dollar, as a percentage that does not round small to nothing."""
    return "0%" if x == 0 else "&lt;0.1%" if x < 0.0005 else f"{x * 100:.1f}%"


def ai_tip(d: Data, a: str) -> str:
    r = d.ai.loc[a]
    by = ", ".join(f"{AI_NAME[k]} {r[k] * 100:.1f}%" for k in ("claude", "chatgpt", "copilot"))
    return (f"{r['name'].rstrip('.')}: {r.pooled * 100:.1f}% of AI conversations on average ({by}), against "
            f"{r.flow_share * 100:.1f}% of the need dollar's work.")


def activity_tree(d: Data) -> list[str]:
    """Demand against means: one row per general work activity, each followed by its intermediate
    activities as hidden child rows that its name toggles open (site.js)."""
    G = d.act[d.act.level == "general"].sort_values("flow", ascending=False)
    gmax = d.ai.pooled[d.ai.level == "general"].max()
    rows = []
    for i, (g, r) in enumerate(G.iterrows()):
        band, kids = (" band" if i % 2 == 0 else ""), d.act_children[g]
        rows.append(
            f'<tr class="kind{band}" id="{g}" data-cap><td><button type="button" class="expander" aria-expanded="false" data-group="{g}">'
            f'{e(r["name"])}</button><div class="dim capdef">{len(kids)} activities</div></td>'
            f'<td>{bar(r.flow, G.flow.max(), cents(r.flow, 1), f"{r["name"]}: {r.flow * 100:.2f} cents of each need dollar pay for this kind of work")}</td>'
            f'<td></td><td>{open_bar(r, r["name"])}</td>'
            f'<td>{bar(d.ai.at[g, "pooled"], gmax, share(d.ai.at[g, "pooled"]), ai_tip(d, g))}</td></tr>')
        rows += [
            f'<tr class="sub{band}" data-group="{g}" hidden><td class="child"><a href="{act_href(k)}">{e(c["name"].rstrip("."))}</a></td>'
            f'<td class="num"><a href="{act_href(k, "flow")}" data-tip="Rank {int(c["rank"])} of {len(d.act[d.act.level == "intermediate"])}. Click for the derivation.">{cents(c.flow)}</a></td>'
            f'<td class="wrap">{software_links(d, k)}</td>'
            f'<td class="num">{"" if pd.isna(c.software_open_share) else f"{c.software_open_share:.0%}"}</td>'
            f'<td class="num"><span data-tip="{e(ai_tip(d, k))}" tabindex="0">{share(d.ai.at[k, "pooled"])}</span></td></tr>' for k, c in kids.iterrows()]
    return rows


ACTIVITY_HEAD = ["Kind of work, then its activities", "Demand: flow, &cent;", "Means: software listed with it",
                 "Means: open tools", "Means: share of AI use"]
ACTIVITY_CAPTION = ("Demand is the part of each need dollar that pays for a kind of work today. It shows where the work goes, not how "
                    "much it matters. Means are the kinds of software most particular to the people who do the work, the share of "
                    "that software's tasks with a known open-source tool, and the share of AI conversations that are about this kind "
                    "of work (the average of Claude, ChatGPT and Copilot). Flow is in cents of a dollar, so it compares directly with "
                    "the AI share in percent. Click a kind of work to list its activities, and an activity to see where its flow comes from.")


def activities_page(d: Data) -> str:
    A, acct = d.act, d.act_acct
    I = A[A.level == "intermediate"].sort_values("flow", ascending=False)
    top = [f'<tr><th scope="row"><a href="{act_href(k)}">{e(r["name"].rstrip("."))}</a></th><td class="dim">{e(A.at[r.parent, "name"])}</td>'
           f'<td data-v="{r.flow}"><a class="barlink" href="{act_href(k, "flow")}">{bar(r.flow, I.flow.max(), cents(r.flow), f"{r["name"]} {r.flow * 100:.2f} cents of each need dollar. Click for the derivation.")}</a></td>'
           f'<td>{e(NEED_NAME[r.top_need])}</td><td class="wrap">{software_links(d, k)}</td></tr>' for k, r in I.head(SHOW_FLOWS).iterrows()]
    U = d.ai[d.ai.level == "intermediate"].sort_values("pooled", ascending=False)
    cum = U.pooled.cumsum() / U.pooled.sum()
    n_half = int((cum < 0.5).sum()) + 1
    half_flow, absent = U.flow_share.iloc[:n_half].sum(), U.flow_share[U.intensity < 0.1].sum()
    ai_top = [f'<tr><th scope="row"><a href="{act_href(k, "ai")}">{e(r["name"].rstrip("."))}</a></th><td class="num" data-v="{r.flow_share}">{share(r.flow_share)}</td>'
              + "".join(f'<td class="num" data-v="{r[c]}">{share(r[c])}</td>' for c in ("claude", "chatgpt", "copilot"))
              + f'<td class="num" data-v="{r.intensity}">{r.intensity:.1f}</td></tr>' for k, r in U.head(SHOW_FLOWS).iterrows()]
    least = U.sort_values("flow_share", ascending=False).head(60).sort_values("intensity").head(12)
    ai_least = [f'<tr><th scope="row"><a href="{act_href(k, "ai")}">{e(r["name"].rstrip("."))}</a></th><td class="dim">{e(A.at[A.at[k, "parent"], "name"])}</td>'
                f'<td class="num" data-v="{r.flow_share}">{share(r.flow_share)}</td><td class="num" data-v="{r.pooled}">{share(r.pooled)}</td></tr>'
                for k, r in least.iterrows()]
    body = f"""
<h1>Activities</h1>
<p class="lede">The work that has to get done to meet the needs: {(A.level == "general").sum()} kinds of work, {len(I)} activities and
{(A.level == "detailed").sum():,} detailed activities, as the U.S. Department of Labor's O*NET describes them. Software, AI
or a person with a pencil are ways of doing this work. This is the work itself.</p>
<p>Each need dollar is traced to the work it pays for. The dollar is split among the sectors whose value added it embodies,
each sector's part among its occupations by pay, and each occupation's part among its tasks by how important they are and
how many of its workers do them. {acct["flowed"] * 100:.0f} cents of the dollar reach an activity this way.
{acct["sectors_without_occupation_data"] * 100:.0f} cents sit in sectors with no occupation data and
{acct["work_not_placed"] * 100:.0f} in occupations O*NET has no task list for.</p>
<p class="caveat">Flow measures where today's paid work goes. It does not measure how much an activity matters, and it
follows pay: directing and supervising rank high partly because managers are paid well.
<a href="method.html#activities">How the flow is computed and what it leaves out</a>.</p>

<h2 id="largest">The largest activities</h2>
{table([th("Activity"), th("Kind of work"), th("Flow, &cent; per need dollar"), th("Need that sends it most"), th("Software listed with it")], top,
       caption=f"The {SHOW_FLOWS} largest of {len(I)} activities. Software listed with it is the software most particular to the people who "
               "do the work; O*NET says which software an occupation uses, not which of its tasks it is used for.")}

<h2 id="ai">Where AI is used</h2>
<p>Three AI vendors publish what their systems are used for, classified into these same activities. Half of that use
falls in {n_half} activities that carry {half_flow:.0%} of the need dollar. Activities that carry {absent:.0%} of the dollar
get less than a tenth of the AI use their size would suggest.</p>
<p class="caveat">This is where AI is used, not how well it does the work. A conversation asking how to weld counts
toward welding. The figures are each vendor's own classification of its chat logs, mostly from consumer plans.
<a href="method.html#ai">What the three sources are and what they leave out</a>.</p>
{table([th("Activity"), th("Share of the need dollar", "num", "num"), th("Claude", "num", "num"), th("ChatGPT", "num", "num"),
        th("Copilot", "num", "num"), th("AI use against its share of work", "num", "num")], ai_top,
       caption=f"The {SHOW_FLOWS} activities with the most AI use, by the average of the three sources. The last column divides that average by "
               "the activity's share of the dollar: 10 means ten times as much AI use as its share of the work.")}
<h3>The largest work with the least AI use</h3>
{table([th("Activity"), th("Kind of work"), th("Share of the need dollar", "num", "num"), th("Share of AI use", "num", "num")], ai_least,
       caption="Of the 60 largest activities, the twelve with the least AI use relative to their size.")}

<h2 id="all">All the work</h2>
<div class="controls"><label for="tq">Find an activity</label>
<input type="search" id="tq" placeholder="for example: diagnose, weld, schedule, teach" autocomplete="off">
<span id="tcount" class="note" role="status"></span></div>
{table([th(x) for x in ACTIVITY_HEAD], activity_tree(d), attrs=" data-tree", caption=ACTIVITY_CAPTION)}
"""
    return page("Activities", "activities.html", body)


def activity_page(d: Data, a: str) -> str:
    r, name = d.act.loc[a], act_name(d, a)
    n = (d.act.level == "intermediate").sum()
    t = flow_terms(d, a, d.act_work)
    total = t.term.sum()
    tot = tipped(f"{total * 100:.4f}", f"Sum of the {len(t)} sector terms: {total * 100:.4f} cents of each need dollar.")
    kids = d.act_children.get(a)
    by_need = d.act_need.loc[kids.index].sum()
    occ, tasks = d.act_occ[d.act_occ.iwa == a], d.act_tasks[d.act_tasks.iwa == a]
    sw = d.act_software.get(a)
    if sw is not None:
        srows = [f'<tr><td><a href="{flow_href(x.capability)}">{e(d.tax_name[x.capability])}</a></td>'
                 f'<td class="dim">{e(d.tax_name[x.capability.split(".")[0]])}</td><td class="num">{x.flow * 100:.4f}</td>'
                 f'<td class="num">{int(d.balance.at[x.capability, "open"])} of {int(d.balance.at[x.capability, "tasks"])}</td></tr>'
                 for x in sw.itertuples()]
        software = f"""<p>The kinds of software most particular to the people who do this work, by the part of this activity's flow that
their listing carries. O*NET records which software an occupation uses, not which of its tasks it is used for, so this
is the software around the work, not proof that it does the work. AI systems are barely in O*NET's lists yet.</p>
{table([th("Software capability"), th("Domain"), th("Flow shared with this work, &cent;", "num"), th("Its tasks with a known open tool", "num")], srows)}"""
    else:
        software = "<p>The occupations that do this work list no software that the capability list places.</p>"
    u = d.ai.loc[a]
    arows = [f'<tr><td>{e(d.ai_src.at[k, "what"])}</td><td class="dim">{e(d.ai_src.at[k, "where"])}, {e(d.ai_src.at[k, "when"])}</td>'
             f'<td class="num">{share(u[k])}</td></tr>' for k in d.ai_src.index]
    facts = []
    if u.claude >= AI_MIN_SHARE or u.claude_api >= AI_MIN_SHARE:
        if pd.notna(u.automation):
            facts.append(f"In Claude chat, {u.automation:.0%} of this use hands the task over to the AI and the rest works alongside it.")
        if pd.notna(u.hours_without_ai) and pd.notna(u.minutes_with_ai):
            facts.append(f"Anthropic estimates the tasks would take a person {u.hours_without_ai:.1f} hours without AI and "
                         f"{u.minutes_with_ai:.0f} minutes with it.")
    if u.copilot_action >= AI_MIN_SHARE and pd.notna(u.copilot_completion):
        facts.append(f"When Copilot itself did this activity, Microsoft judged the task completed in {u.copilot_completion:.0%} of conversations.")
    ai_html = f"""<p>What three AI vendors report their systems being used for. This activity is {share(u.flow_share)} of the work
the need dollar pays for, and {share(u.pooled)} of AI conversations on average across Claude, ChatGPT and Copilot
({"about " + f"{u.intensity:.1f}" + " times" if u.intensity >= 0.1 else "under a tenth of"} its share of the work).</p>
{table([th("Source"), th("Where and when"), th("Share of its conversations", "num")], arows,
       caption="Each figure is the share of that source's classified conversations about this activity. A source that does not publish an activity, because too few conversations fall in it, is shown as zero.")}
{"<p>" + " ".join(facts) + "</p>" if facts else ""}
<p class="note">This is where AI is used, not how well it does the work: a conversation asking how to do something counts toward
doing it. <a href="method.html#ai">What the sources are and what they leave out</a>.</p>"""
    body = f"""
<p class="crumbs"><a href="activities.html">Activities</a> / <a href="activities.html#{r.parent}">{e(d.act.at[r.parent, "name"])}</a></p>
<h1>{e(name)}</h1>
<dl class="figures">
<div><dt><a href="#flow">Flow</a></dt><dd>{cents(r.flow)}</dd><dd class="dim">of each need dollar; rank {int(r["rank"])} of {n}</dd></div>
<div><dt><a href="method.html#activities">Weighting tasks by frequency</a></dt><dd>{cents(r.flow_frequency)}</dd><dd class="dim">instead of importance</dd></div>
<div><dt>Need that sends it most</dt><dd class="small">{e(NEED_NAME[r.top_need])}</dd></div>
<div><dt><a href="#means">Software around it with an open tool</a></dt><dd>{"n/a" if pd.isna(r.software_open_share) else f"{r.software_open_share:.0%}"}</dd></div>
</dl>
<p class="caveat">Flow is where today's paid work goes, not how much an activity matters.
<a href="method.html#activities">How the flow is computed</a>.</p>

<h2 id="detailed">What it consists of</h2>
{table([th("Detailed activity"), th("Flow, &cent;", "num"), th("Need that sends it most")],
       [f'<tr><td class="name">{e(c["name"].rstrip("."))}</td><td class="num">{c.flow * 100:.4f}</td><td>{e(NEED_NAME[c.top_need])}</td></tr>' for _, c in kids.iterrows()],
       foot=f'<tr><td>{e(name)}</td><td class="num">{kids.flow.sum() * 100:.4f}</td><td></td></tr>')}

<h2 id="tasks">The tasks behind it</h2>
<p>The tasks, in O*NET's words, that carry the most of this flow, and the occupation each belongs to.</p>
{table([th("Task"), th("Occupation"), th("Flow, &cent;", "num")],
       [f'<tr><td class="wrap">{e(x.task)}</td><td class="dim">{e(x.occupation)}</td><td class="num">{x.flow * 100:.4f}</td></tr>' for x in tasks.itertuples()],
       caption=f"The largest {len(tasks)}.")}

<h2 id="flow">The flow, worked out</h2>
<p>A need dollar is first split among the sectors whose value added it embodies (every need counted equally). Each
sector's part is split among its occupations by pay, and each occupation's part among its tasks. What reaches this activity
from each sector is that sector's share of the dollar times the share of its work that is this activity.</p>
<h3>By kind of sector</h3>
<p class="note">Click a kind to list its sectors. Hover over a term to see its arithmetic. Terms are in cents per need dollar.</p>
{table([th("Kind of sector"), th("Sectors", "num"), th("Share of value added", "num"), th("Share of its work", "num"),
        th("Term, &cent;", "num")], flow_kind_rows(name, t), attrs=" data-tree",
       foot=f'<tr><td>Flow</td><td class="num">{len(t)}</td><td class="num">{t.share.sum():.2%}</td>'
            f'<td class="num">{(total / t.share.sum() if len(t) else 0):.2%}</td><td class="num">{tot}</td></tr>')}
<h3>By need</h3>
<p class="note">Cents of each need's dollar that pay for this activity. The flow is their average; the largest is in bold.</p>
{by_need_list(by_need, cents)}

<h2 id="occupations">Who does it</h2>
{table([th("Occupation"), th("Share of its work", "num"), th("Its share of the need dollar", "num"), th("Flow, &cent;", "num")],
       [f'<tr><td class="name">{e(o.title)}</td><td class="num">{o.share_of_work:.1%}</td><td class="num">{o.share_of_basket:.2%}</td>'
        f'<td class="num">{o.flow * 100:.4f}</td></tr>' for o in occ.itertuples()],
       caption=f"The largest {len(occ)}. An occupation's share of the need dollar is the value added of the sectors that employ it, by pay.")}

<h2 id="means">The means: software listed with it</h2>
{software}

<h2 id="ai">The means: AI</h2>
{ai_html}
"""
    return page(name, act_href(a), body, long_title=True)


def flow_page(d: Data, k: str) -> str:
    r, node = d.flow.loc[k], d.tax.set_index("id").loc[k]
    name, n, dom = node["name"], len(d.flow), k.split(".")[0]
    t = flow_terms(d, k)
    total = t.term.sum()
    occ = d.flow_occ[d.flow_occ.capability == k]
    tasks = d.tax_children[k]
    if len(t):
        tot = tipped(f"{total * 100:.4f}", f"Sum of the {len(t)} sector terms: {total * 100:.4f} cents of each need dollar.")
        derivation = f"""<p>A need dollar is first split among the sectors whose value added it embodies (every need counted
equally). Each sector's part is split among its occupations by pay, and each occupation's part among the capabilities
whose software it lists. What reaches {e(name.lower())} from each sector is that sector's share of the dollar times the
share of its work done with it.</p>
<h3>By kind of sector</h3>
<p class="note">Click a kind to list its sectors. Hover over a term to see its arithmetic. Terms are in cents per need dollar.</p>
{table([th("Kind of sector"), th("Sectors", "num"), th("Share of value added", "num"), th("Share of work with it", "num"),
        th("Term, &cent;", "num")], flow_kind_rows(name, t), attrs=" data-tree",
       foot=f'<tr><td>Flow</td><td class="num">{len(t)}</td><td class="num">{t.share.sum():.2%}</td>'
            f'<td class="num">{total / t.share.sum():.2%}</td><td class="num">{tot}</td></tr>')}
<h3>By need</h3>
<p class="note">Cents of each need's dollar that reach this capability. The flow is their average; the largest is in bold.</p>
{by_need_list(d.flow_need.loc[k], cents)}
<h2 id="occupations">Whose work it passes through</h2>
<p>The occupations that carry the most of this flow. Each lists some of this capability's software in O*NET; the
share of its work is those products as a share of all the software it lists, every product counted equally.</p>
{table([th("Occupation"), th("Products here, of listed", "num"), th("Share of its work", "num"),
        th("Its share of the need dollar", "num"), th("Flow, &cent;", "num")],
       [f'<tr><td class="name">{e(o.title)}</td><td class="num">{o.products_in_capability} of {o.products_listed}</td>'
        f'<td class="num">{o.share_of_work:.1%}</td><td class="num">{o.share_of_basket:.2%}</td>'
        f'<td class="num">{o.flow * 100:.4f}</td></tr>' for o in occ.itertuples()],
       caption=f"The largest {len(occ)}. An occupation's share of the need dollar is the value added of the sectors that employ it, by pay.")}"""
    else:
        derivation = f"""<p>No value reaches {e(name.lower())}: no occupation in the wage data lists software that the
taxonomy places here. That says the chain cannot see it, not that nobody does it.</p>"""
    w = d.act_cap[d.act_cap.capability == k].sort_values("flow", ascending=False).head(8)
    listed_with = (f"""<p>The work most often done by the people who list this software, by the part of its flow they share. This is
the work the software sits beside, not proof of what it is used for.</p>
{table([th("Activity"), th("Kind of work"), th("Flow shared, &cent;", "num")],
       [f'<tr><td><a href="{act_href(x.iwa)}">{e(act_name(d, x.iwa))}</a></td><td class="dim">{e(d.act.at[d.act.at[x.iwa, "parent"], "name"])}</td>'
        f'<td class="num">{x.flow * 100:.4f}</td></tr>' for x in w.itertuples()])}""" if len(w) else
                   "<p>No occupation with a task list also lists this software.</p>")
    body = f"""
<p class="crumbs"><a href="capabilities.html">Capabilities</a> / <a href="capabilities.html#{dom}">{e(d.tax_name[dom])}</a></p>
<h1>{e(name)}</h1>
<p class="lede">{e(node.definition)}</p>
<dl class="figures">
<div><dt><a href="#flow">Flow</a></dt><dd>{cents(r.flow)}</dd><dd class="dim">of each need dollar; rank {int(r["rank"])} of {n}</dd></div>
<div><dt><a href="method.html#flows">By distinctive work</a></dt><dd>{cents(r.flow_distinctive)}</dd><dd class="dim">rank {int(r.rank_distinctive)} of {n}</dd></div>
<div><dt>{'<a href="#occupations">Occupations that list it</a>' if len(t) else "Occupations that list it"}</dt><dd>{int(r.occupations)}</dd><dd class="dim">{int(r.products)} products placed here</dd></div>
<div><dt>Need that sends it most</dt><dd class="small">{e(NEED_NAME[r.top_need])}</dd></div>
</dl>
<p class="caveat">Flow is where today's work goes, not how much a capability matters. A tool that few people use can
still be one that nothing gets made without. <a href="method.html#flows">How the flow is computed</a>.</p>

<h2 id="flow">The flow, worked out</h2>
{derivation}

<h2 id="work">The work it is listed with</h2>
{listed_with}

<h2 id="tasks">Its tasks</h2>
<ul class="tasklist">{"".join(f'<li>{e(x.name)} <span class="pill {BENCH_PILL[x.benchmarkable]}" data-tip="Open benchmark possible: {e(x.benchmark_note)}" tabindex="0">{x.benchmarkable}</span></li>' for x in tasks.itertuples())}</ul>
<p class="note">Definitions, open tools and sources are on the <a href="capabilities.html#{k}">capabilities page</a>.</p>
"""
    return page(name, flow_href(k), body, long_title=True)


def taxonomy_rows(d: Data, dom: str) -> list[str]:
    """One row per capability of a domain, each followed by its tasks as hidden child rows that
    the capability's name toggles open (site.js)."""
    empty = d.tax_cross.iloc[0:0]
    by_cap = {k: g for k, g in d.tax_cross[d.tax_cross.domain == dom].groupby("capability")}
    rows = []
    for i, c in enumerate(d.tax_children[dom].itertuples()):
        band = " band" if i % 2 == 0 else ""
        tasks = d.tax_children[c.id]
        n, yes, partly = len(tasks), (tasks.benchmarkable == "yes").sum(), (tasks.benchmarkable == "partly").sum()
        rows.append(
            f'<tr class="kind{band}" id="{c.id}" data-cap><td><button type="button" class="expander" aria-expanded="false" '
            f'data-group="{c.id}">{e(c.name)}</button><div class="dim capdef">{e(c.definition)}</div>'
            f'<div class="dim capsrc">Drawn from: {taxonomy_sources(by_cap.get(c.id, empty))}</div></td>'
            f'<td class="num nowrap" data-tip="{e(c.name)}: {d.flow.at[c.id, "flow"] * 100:.3f} cents of each need dollar reach it, rank '
            f'{int(d.flow.at[c.id, "rank"])} of {len(d.flow)}. Click for the derivation."><a href="{flow_href(c.id)}">{cents(d.flow.at[c.id, "flow"])}</a></td>'
            f'<td class="num">{n}</td><td class="nowrap">{yes} yes, {partly} partly</td>'
            f'<td class="nowrap">{(tasks.open_tools != "").sum()} of {n} tasks</td><td></td></tr>')
        for t in tasks.itertuples():
            note = t.benchmark_note[:1].upper() + t.benchmark_note[1:]
            rows.append(
                f'<tr class="sub{band}" data-group="{c.id}" hidden><td class="child"><span class="tname">{e(t.name)}</span>'
                f'<div class="dim">{e(t.definition)}</div></td><td></td><td></td>'
                f'<td><span class="pill {BENCH_PILL[t.benchmarkable]}" data-tip="{e(note)}" tabindex="0">{t.benchmarkable}</span></td>'
                f'<td class="wrap">{e(t.open_tools.replace("; ", ", ")) or "<span class=dim>none known</span>"}</td>'
                f'<td class="wrap dim">{e(t.state_of_art.replace("; ", ", "))}</td></tr>')
    return rows


def taxonomy_section(d: Data) -> str:
    T, X = d.tax, d.tax_cross
    tasks = T[T.level == 2].assign(domain=lambda t: t.id.str.split(".").str[0])
    domains = T[T.level == 0]
    summary, sections = [], []
    dom_flow = d.flow.groupby("domain").flow.sum()
    fmax = d.flow.flow.max()
    top = [f'<tr><th scope="row"><a href="{flow_href(k)}">{e(r["name"])}</a></th><td class="dim">{e(d.tax_name[r.domain])}</td>'
           f'<td data-v="{r.flow}"><a class="barlink" href="{flow_href(k, "flow")}">{bar(r.flow, fmax, cents(r.flow), f"{r["name"]}: {r.flow * 100:.2f} cents of each need dollar. Click for the derivation.")}</a></td>'
           f'<td data-v="{r.flow_distinctive}">{bar(r.flow_distinctive, fmax, cents(r.flow_distinctive), f"{r["name"]}: {r.flow_distinctive * 100:.2f} cents when each occupation is credited for what is distinctive of it; rank {int(r.rank_distinctive)}")}</td>'
           f'<td>{e(NEED_NAME[r.top_need])}</td></tr>' for k, r in d.flow.head(SHOW_FLOWS).iterrows()]
    acct = d.flow_acct.flow
    head = [th("Capability, then its tasks"), th("Flow", "num"), th("Tasks", "num"), th("Open benchmark possible"), th("Open tools"),
            th("Proprietary state of the art")]
    for dm in domains.itertuples():
        t, x = tasks[tasks.domain == dm.id], X[X.domain == dm.id]
        n, yes, has_open = len(t), int((t.benchmarkable == "yes").sum()), int((t.open_tools != "").sum())
        checked = int((x.basis == "fetched").sum())
        f_dom = dom_flow[dm.id]
        summary.append(
            f'<tr><th scope="row"><a href="#{dm.id}">{e(dm.name)}</a></th><td class="num">{len(d.tax_children[dm.id])}</td>'
            f'<td class="num">{n}</td>'
            f'<td data-v="{f_dom}">{bar(f_dom, dom_flow.max(), cents(f_dom, 1), f"{dm.name}: {f_dom * 100:.1f} cents of each need dollar reach its capabilities")}</td>'
            f'<td data-v="{yes / n}">{bar(yes / n, 1, f"{yes / n:.0%}", f"{dm.name}: an open benchmark is possible today for {yes} of {n} tasks")}</td>'
            f'<td data-v="{has_open / n}">{bar(has_open / n, 1, f"{has_open / n:.0%}", f"{dm.name}: {has_open} of {n} tasks have a known open-source tool")}</td>'
            f'<td class="num" data-v="{checked / len(x)}">{checked} of {len(x)}</td></tr>')
        sections.append(
            f'<section data-domain id="{dm.id}"><h2>{e(dm.name)}</h2><p class="note">{e(dm.definition)}</p>'
            f'{table(head, taxonomy_rows(d, dm.id), attrs=" data-tree")}</section>')
    n_checked, n_cross = int((X.basis == "fetched").sum()), len(X)
    return f"""
<h1>Capabilities</h1>
<p class="lede">The means of doing the <a href="activities.html">work</a>: {(T.level == 1).sum()} kinds of software in
{len(domains)} domains, broken into {len(tasks):,} tasks. A capability here is something software does for the people
doing the work. A task is a problem with defined inputs and outputs, small enough that an open benchmark could be
built for it.</p>
<p>Software is one means among several. AI systems are another: <a href="activities.html#ai">where AI is used</a>
is shown against the work itself, not in this list.</p>
<p class="caveat">This list is a new draft. AI models wrote it from published taxonomies, and nobody who works in these
fields has reviewed it. {n_checked:,} of its {n_cross:,} source citations were checked against the source itself; the rest
are from memory. <a href="method.html#taxonomy">How the list was made</a>.</p>
{table([th("Domain"), th("Capabilities", "num", "num"), th("Tasks", "num", "num"), th("Flow, &cent; per need dollar", sort="num"),
        th("Open benchmark possible", sort="num"), th("Has an open tool", sort="num"), th("Sources checked", "num", "num")], summary,
       caption="Flow is the part of each need dollar that reaches the domain's capabilities (below). "
               "Open benchmark possible counts tasks marked yes: public reference problems exist to score tools on. "
               "Sources checked counts citations of published taxonomies and standards that were read at the source.")}

<h2 id="flows">Where today's value flows</h2>
<p>Each need dollar is traced to the capabilities it passes through. The dollar is split among the sectors whose value
added it embodies, each sector's part among its occupations by pay, and each occupation's part among the capabilities
whose software it lists. {acct["flowed"] * 100:.0f} cents of the dollar reach a capability this way.
{acct["sectors_without_occupation_data"] * 100:.0f} cents sit in sectors with no occupation data and
{acct["work_not_placed"] * 100:.0f} cents are work the chain cannot place.</p>
<p class="caveat">Flow measures where today's work goes. It does not measure how much a capability matters: general
office tools lead because everyone uses them, and a capability that few people use, such as genome analysis, can still be
one that a need cannot be met without. <a href="method.html#flows">How the flow is computed and what it leaves out</a>.</p>
{table([th("Capability"), th("Domain"), th("Flow, by share of work"), th("By distinctive work"), th("Need that sends it most")], top,
       caption=f"The {SHOW_FLOWS} largest of {len(d.flow)}, in cents of each need dollar; every capability's flow is in the lists below. "
               "By distinctive work splits each occupation's part toward the capabilities few other occupations list, so tools everyone "
               "uses take less. Both columns share one scale. Click a bar for the derivation.")}
<div class="controls"><label for="tq">Find a capability or task</label>
<input type="search" id="tq" placeholder="for example: modal analysis, payroll, routing" autocomplete="off">
<span id="tcount" class="note" role="status"></span></div>
<p class="note">Click a capability to list its tasks, or its flow to see where it comes from. &#10003; marks a source that was checked against the published document;
unmarked sources are cited from memory. Hover over yes, partly or no to see why. Open tools and state of the art are what
the authors knew of and have not been checked: "none known" does not mean none exists.
The full list is in <a href="{REPO}/tree/main/taxonomy"><code>taxonomy/</code></a> as JSON and CSV.</p>
{"".join(sections)}
"""


def capabilities_page(d: Data) -> str:
    order = d.ct.sort_values("volume weight", ascending=False).index
    became = d.tax_func.groupby("function").node.agg(list)
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
            f'<tr id="{k}"><th scope="row" class="cap"><a href="{cap_href(k)}">{e(d.cap_name(k))}</a><div class="dim" style="font-weight:400">{e(d.caps.at[k, "description"].replace("; ", ", "))}</div>'
            f'<div class="dim capsrc" style="font-weight:400">In the new list: {", ".join(f"""<a href="#{n}">{e(d.tax_name[n].lower())}</a>""" for n in became.get(k, []))}</div></th>'
            f'<td data-v="{r["volume weight"]}">{bar(r["volume weight"], vmax, f3(r["volume weight"]), f"Volume rank {int(r.volume_rank)} of {len(d.ct)}")}</td>'
            f'<td data-v="{r["occupational weight"]}">{bar(r["occupational weight"], omax, f3(r["occupational weight"]), otip)}</td>'
            f'<td data-v="{r["exposure"]}">{bar(r["exposure"], emax, f3(r["exposure"]), f"Exposure rank {int(r.exposure_rank)} of {len(d.ct)}")}</td>'
            f'<td class="num" data-v="{r["reach 1c"]}">{r["reach 1c"]:.0%}</td>'
            f'<td class="wrap dim">{e(crit)}</td>'
            f'<td>{d.board_html(k)}</td></tr>')
    body = f"""{taxonomy_section(d)}
<h2 id="functions">Engineering functions with weights</h2>
<p>Eighteen kinds of engineering computation, weighted by how much of the basket of needs passes through sectors that
depend on them. This is the older list. Its weights come from scores an AI model wrote for each kind of sector, and
they include exposure, which the flow above cannot give: how much of the basket passes through sectors that cannot run
without the function. Each function has turned out to be several capabilities in the new list, linked under its name.</p>
<p class="caveat">These numbers show demand for each function. They do not yet show supply: how far today's open
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
<h3>Reading the two measures together</h3>
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

    head = [th("Function"), th("Rank by weight", "num", "num"), th("Rank by exposure", "num", "num"),
            th("Most exposed need"), th("Open leaderboard"), th("Proposed work")]
    open_gaps = ct[~ct.has_board].sort_values(["worst_rank", "volume_rank"])
    covered = ct[ct.has_board].sort_values(["worst_rank", "volume_rank"])
    thin_rows = [
        f'<tr><td class="name">{e(r["name"])}</td><td class="num">{r.output_per_basket_dollar * 100:.2f}&cent;</td>'
        f'<td class="num">{r.need_breadth_observed:.1f}</td></tr>' for _, r in d.thin.head(15).iterrows()]
    B = d.balance
    fmax = B.flow.max()

    def gap_rows(frame):
        return [
            f'<tr><th scope="row"><a href="capabilities.html#{k}">{e(r["name"])}</a></th><td class="dim">{e(d.tax_name[r.domain])}</td>'
            f'<td data-v="{r.flow}"><a class="barlink" href="{flow_href(k)}">{bar(r.flow, fmax, cents(r.flow), f"{r["name"]}: rank {int(r["rank"])} of {len(B)} by flow. Click for the derivation.")}</a></td>'
            f'<td class="num" data-v="{(r.tasks - r.open) / r.tasks}">{int(r.tasks - r.open)} of {int(r.tasks)}</td>'
            f'<td class="num" data-v="{r.bench / r.tasks}">{int(r.bench)} of {int(r.tasks)}</td>'
            f'<td>{d.boards_html([k], none="<span class=dim>none</span>")}</td></tr>' for k, r in frame.iterrows()]
    ghead = [th("Capability", sort="text"), th("Domain", sort="text"), th("Flow, &cent; per need dollar", sort="num"),
             th("Tasks with no known open tool", "num", "num"), th("Open benchmark possible", "num", "num"), th("Open leaderboard")]
    none_open = B[B.open == 0].sort_values("flow", ascending=False)
    half = B[(B.open > 0) & (B.open * 2 < B.tasks)].sort_values("flow", ascending=False)
    measured = B[B.index.isin(d.boards.capability)]
    body = f"""
<h1>Gaps</h1>
<p class="lede">A gap is a capability that value flows through and that has no open tool, or that nobody is measuring
in the open. Of {len(B)} capabilities, {len(none_open)} have no known open tool for any task, {len(half)} more have one for
fewer than half their tasks, and {len(B) - len(measured)} have no open leaderboard.</p>
<p class="caveat">Read this page as a list of places to look, not a ranking of what matters. Flow shows where today's work
goes. Open tools are what the authors of the capability list knew of and have not been checked: "no known open tool"
does not mean none exists, and a tool existing does not mean it is good enough. How far open tools are from the best
available is <a href="work.html#inventory">not collected yet</a>.</p>
<h2>No known open tool for any task</h2>
{table(ghead, gap_rows(none_open), caption="Ordered by flow. Click a column heading to sort.")}
<h2>An open tool for fewer than half the tasks</h2>
{table(ghead, gap_rows(half), caption="Ordered by flow.")}
<h2>Measured in the open today</h2>
{table(ghead, gap_rows(measured.sort_values("flow", ascending=False)),
       caption="The capabilities with an open leaderboard. A board existing does not mean the gap is closed. It means the distance to the state of the art is being measured.")}

<h2 id="functions">Engineering functions</h2>
<p>The earlier account ranks eighteen engineering functions by weight and by exposure: how much of the basket passes
through sectors that cannot run without the function. Flow cannot give exposure, so this ranking is kept.</p>
<h3>No open leaderboard</h3>
{table(head, rows_for(open_gaps), caption=f"Ordered by the worse of the two ranks, so a function has to matter on both measures to rise. Ranks are out of {len(ct)}.")}
<h3>Covered by a leaderboard</h3>
{table(head, rows_for(covered))}
<p class="caveat">This part ranks gaps by demand alone. A real gap is demand times the distance between open tools and the
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
            f'<tr id="{code}" data-phys="{phys}" data-text="{e(text)}"><td class="name">{e(r["name"])}</td><td class="dim">{e(words(r.archetype))}</td>'
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
    c = d.calibration
    cal_rows = [f'<tr><td>{s}</td><td class="num">{int(r.cells):,}</td><td class="num">{r.mean_share:.1%}</td>'
                f'<td class="num">{r.weight_assumed:g}</td><td class="num">{r.weight_calibrated:.2f}</td></tr>'
                for s, r in c.iterrows()]
    cal_rho = d.ct["volume weight"].corr(d.ct["calibrated weight"], method="spearman")
    gain = (d.ct["calibrated weight"] / d.ct["volume weight"]).nlargest(3).index
    gainers = ", ".join(d.cap_name(k) for k in gain)
    same_top5 = set(d.ct["volume weight"].nlargest(5).index) == set(d.ct["calibrated weight"].nlargest(5).index)
    rows = [f'<tr><td>{e(d.cap_name(k))}</td><td class="num">{int(a.at[k, "elicited_rank"])}</td>'
            f'<td class="num">{int(a.at[k, "occupational_rank"])}</td>'
            f'<td class="num">{"&ndash;" if a.at[k, "thin"] else f"{a.at[k, "spearman_across_sectors"]:.2f}"}</td>'
            f'<td class="num">{"" if pd.isna(a.at[k, "spearman_rd"]) else f"{a.at[k, "spearman_rd"]:.2f}"}</td></tr>'
            for k in order]
    rdi = d.rdi
    rd_n = int(rdi.rd_per_output.notna().sum())
    rd_mapped = rdi.dropna().groupby("berd_industry").rd_musd.first().sum() / 1e3
    proxies = ", ".join(d.cap_name(k) for k in d.caps.index[d.caps.rd_proxy.astype(bool)])
    rd_rho = a.spearman_rd.dropna()
    weak = [d.cap_name(k) for k in rd_rho.index[rd_rho < 0.3]]
    rd_range = f"{rd_rho[rd_rho >= 0.3].min():.2f} to {rd_rho.max():.2f}"

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
{table([th("Capability"), th("Elicited rank", "num"), th("Occupational rank", "num"), th("Agreement across sectors", "num"),
        th("R&amp;D agreement", "num")], rows,
       caption=f"Rank correlation between the two capability rankings: {rho:.2f}. Agreement across sectors: rank correlation, over the "
               f"{n_meas} measured sectors, between the elicited weight and the occupational share. Sorted by how far the "
               "occupational measure moves the capability up. A dash marks a capability too thin to measure: its occupational rank comes "
               "from its elicited scores, rescaled with the pooled average of the other capabilities, and says nothing new. "
               "R&amp;D agreement: the same correlation against business R&amp;D per dollar of output, for design tools only (below).")}
<h3 id="score-weights">What a score is worth</h3>
<p>The model turns scores into weights of 0.1, 0.3 and 1, a judgment of its own. Occupations give a check on it: across
every measured sector and capability, the average occupational share rises with the elicited score. Taking each score's
average above the score-0 baseline, scaled so a 3 counts 1, gives the weights the data imply.</p>
{table([th("Score"), th("Sector-capability cells", "num"), th("Mean occupational share", "num"),
        th("Assumed weight", "num"), th("Implied weight", "num")], cal_rows,
       caption=f"With the implied weights every capability weighs more, and the ranking correlates {cal_rho:.2f} with the headline "
               f"({'same top five' if same_top5 else 'a different top five'}). Capabilities spread thinly over many sectors gain most: {e(gainers)}. "
               "Occupations measure use, while a 3 also claims the sector cannot run without the capability, so these weights "
               "speak to the usage half of the scores only.")}
<h3 id="rd">A second check: business R&amp;D</h3>
<p>For product-design tools ({e(proxies)}), research spending is a second measure of use: a sector that designs
new products needs them, one that runs a plant or a store mostly does not. The NSF Business Enterprise R&amp;D Survey
reports R&amp;D performed in the United States by industry in 2017, the same year as the input-output tables. Each sector
gets its industry's R&amp;D divided by the BEA output of the sectors in that industry. {rd_n} sectors are covered,
${rd_mapped:.0f} billion of the survey's $400 billion; it leaves out farms and government. Companies are classified by
their main business, so a computer maker that designs at home and builds abroad shows R&amp;D close to its US output.</p>
<p>Agreement with the scores is {rd_range} for the design tools{" except " + " and ".join(e(w).lower() for w in weak) + (" (" + ", ".join(f"{rd_rho[k]:.2f}" for k in rd_rho.index[rd_rho < 0.3]) + ")") if weak else ""}
in the table above. R&amp;D also reaches {" and ".join(e(d.cap_name(k)).lower() for k in a.index[a.thin & a.spearman_rd.notna()]) or "no capability"},
which too few occupations list to measure. Which design tools are judged by R&amp;D is
set in <a href="{REPO}/blob/main/config/capabilities.csv"><code>config/capabilities.csv</code></a> (<code>rd_proxy</code>).</p>
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


def flow_method(d: Data) -> str:
    a, f = d.flow_acct.flow, d.flow
    dom = f.groupby("domain")[["flow", "flow_distinctive"]].sum().sort_values("flow", ascending=False)
    rows = [f'<tr><td>{e(d.tax_name[k])}</td><td class="num">{r.flow * 100:.1f}</td><td class="num">{r.flow_distinctive * 100:.1f}</td></tr>'
            for k, r in dom.iterrows()]
    proxied = int((d.flow_work.source == "oews_proxy").sum())
    spearman = f.flow.corr(f.flow_distinctive, method="spearman")
    return f"""<h2 id="flows">Flowing value through software capabilities</h2>
<p>The same need dollar can be traced to the software the work is done with. The first two steps are the same as for
<a href="#activities">the work</a>; the third splits each occupation's part among the capabilities whose software it lists,
where the activity flow splits it among its tasks. Each step only splits what it receives, so the parts add up to the dollar.</p>
<pre><code>share[j]    = sector j's share of the value added embodied in a need dollar   (the model above; needs counted equally)
theta[o, k] = products occupation o lists in capability k / all products o lists     (O*NET; a product in several capabilities is divided among them)
work[j, k]  = sum_o wagebill[j, o] theta[o, k] / sum_o wagebill[j, o]               (OEWS May 2021)
flow[k]     = sum_j share[j] * work[j, k]</code></pre>
<p>Of each dollar, {a["flowed"] * 100:.0f} cents reach a capability. {a["sectors_without_occupation_data"] * 100:.0f} cents sit in
sectors with no occupation data (mostly housing services, which are imputed rents). {a["work_not_placed"] * 100:.0f} cents are work
the chain cannot place: occupations with no software list, and listed products the taxonomy has no example of. Government
and farms ({proxied} sectors) are measured through stand-ins: schools, hospitals and the government industries in OEWS, and
support activities for farming.</p>
<p><b>By distinctive work.</b> The second version changes only how an occupation's part is divided among its capabilities:
in proportion to products times <code>log(occupations / occupations that list anything in the capability)</code>. A
capability every occupation lists gets almost nothing from each; one that few list gets most of theirs. The weighting is a
judgment, shown beside the plain split so the two can be compared. Their rankings correlate at {spearman:.2f}.</p>
{table([th("Domain"), th("Flow, &cent;", "num"), th("By distinctive work, &cent;", "num")], rows,
       caption="Cents of each need dollar reaching each domain's capabilities.")}
<h3>What the flow is not</h3>
<ul>
<li>It is not importance. It measures where today's work goes. A capability few people use can be one a need cannot be
met without, and a flow of present value cannot see what a capability makes possible, such as a new drug.</li>
<li>Every product an occupation lists counts equally. O*NET says which software an occupation uses, not for how long.</li>
<li>A sector's whole value added, capital's share included, is split the way its payroll is.</li>
<li>Software that runs inside machines without anyone at a desk does not appear.</li>
<li>Flow stops at capabilities. A capability's tasks have example products, but too few to split its flow among them.</li>
</ul>
"""


def activity_method(d: Data) -> str:
    a, A = d.act_acct, d.act
    G = A[A.level == "general"].sort_values("flow", ascending=False)
    rows = [f'<tr><td>{e(r["name"])}</td><td class="num">{r.flow * 100:.1f}</td><td class="num">{r.flow_frequency * 100:.1f}</td></tr>'
            for _, r in G.head(10).iterrows()]
    ml = d.flow.loc[["science.machine_learning", "computing.ml_platforms"]]
    src_rows = [f'<tr><td>{e(r.what)}</td><td>{e(r["where"])}</td><td>{e(r.when)}</td><td class="num">{int(r.activities)}</td>'
                f'<td class="num">{r.spearman_with_flow:.2f}</td></tr>' for _, r in d.ai_src.iterrows()]
    return f"""<h2 id="activities">Flowing value through the work</h2>
<p>Needs are met by work, and software, AI or a person with a pencil are means of doing it. The account is therefore kept
at the level of the work: O*NET's work activities ({(A.level == "general").sum()} general, {(A.level == "intermediate").sum()}
intermediate, {(A.level == "detailed").sum():,} detailed), which group the tasks O*NET records for each occupation. Each need
dollar is traced to them in three steps, and each step only splits what it receives, so the parts add up to the dollar.</p>
<pre><code>share[j]    = sector j's share of the value added embodied in a need dollar   (the model above; needs counted equally)
weight[t]   = importance of task t to its occupation * share of its workers who do it   (O*NET task ratings)
theta[o, d] = sum of weight[t] over o's tasks in activity d / sum of weight[t] over all o's tasks
work[j, d]  = sum_o wagebill[j, o] theta[o, d] / sum_o wagebill[j, o]               (OEWS May 2021)
flow[d]     = sum_j share[j] * work[j, d]</code></pre>
<p>Of each dollar, {a["flowed"] * 100:.0f} cents reach an activity. {a["sectors_without_occupation_data"] * 100:.0f} cents sit in
sectors with no occupation data (mostly housing services, which are imputed rents) and {a["work_not_placed"] * 100:.0f} in
occupations O*NET has no task list for. A task that belongs to several detailed activities is divided among them.</p>
{table([th("Kind of work"), th("Flow, &cent;", "num"), th("Weighting tasks by frequency, &cent;", "num")], rows,
       caption=f"The ten largest general work activities. Weighting tasks by how often they are done, in place of importance, "
               f"gives a rank correlation of {a["spearman_frequency_intermediate"]:.2f} across the intermediate activities.")}
<h3>What this flow is not</h3>
<ul>
<li>It is not importance. It measures where today's paid work goes, and it follows pay: directing and supervising rank high
partly because managers are paid well.</li>
<li>It is not time. O*NET rates how important a task is and how often it is done, not how many hours it takes.</li>
<li>A sector's whole value added, capital's share included, is split the way its payroll is.</li>
<li>Work done by machines without anyone doing it does not appear, and neither does unpaid work.</li>
</ul>
<h3>From the work to its means</h3>
<p>Each activity is shown with the software listed by the people who do it. O*NET says which software an occupation uses,
not which of its tasks it is used for, so the link assumes an occupation's software is spread evenly over its activities,
and credits each occupation for the software particular to it (the distinctive split described below). It shows the
software around the work. It does not show that the software does the work.</p>
<h3 id="ai">AI as a means</h3>
<p>AI systems are another means of doing the work, and three vendors publish what theirs are used for, each classifying its
own conversations into O*NET's work activities:</p>
{table([th("Source"), th("Where"), th("When"), th("Activities reported", "num"), th("Rank correlation with the work's flow", "num")], src_rows,
       caption="Each source gives the share of its conversations in each of the 332 intermediate activities. The last column compares "
               "that with each activity's share of the need dollar.")}
<p>The sources agree with each other more than any agrees with where the work is. The site shows their average
(Claude chat, ChatGPT and Copilot, counted equally) beside each activity's share of the need dollar.</p>
<ul>
<li>Use is not capability. These figures say what people bring to an AI system, not whether it does the work well. A
conversation asking how to weld counts toward welding.</li>
<li>They are each vendor's own classification of its chat logs, made by a language model, and nobody outside can check them.</li>
<li>Coverage is narrow: mostly consumer plans in the United States. ChatGPT's figures leave out enterprise accounts and
coding tools. Claude's chat figures are restricted here to work use by weighting each activity by the share of its
conversations that are work; coding through Claude Code is in neither Anthropic series.</li>
<li>The periods differ. Copilot's data are from 2024 and the others from 2026.</li>
<li>Activities with too few conversations are not published, and count as zero here.</li>
<li>None of this is in the flows above. The flow follows paid people through 2021 wages, so work AI already does leaves no
trace in it. Machine learning as a kind of software receives {ml.flow.iloc[0] * 100:.2f} cents of a need dollar.</li>
</ul>
<p>How well AI systems do each kind of work is what an open benchmark measures. That is the part of the means side this
account does not have yet.</p>
"""


def taxonomy_method(d: Data) -> str:
    T, X = d.tax, d.tax_cross
    tasks = T[T.level == 2]
    n_x, n_ok = len(X), int((X.basis == "fetched").sum())
    by = X.groupby("domain").basis.agg(n="size", ok=lambda b: (b == "fetched").sum())
    by["share"] = by.ok / by.n
    name = d.tax_name
    weak = ", ".join(f"{e(name[k].lower())} ({int(r.ok)} of {int(r.n)})" for k, r in by.sort_values("share").head(3).iterrows())
    strong = ", ".join(e(name[k].lower()) for k in by.sort_values("share", ascending=False).head(3).index)
    bench = tasks.benchmarkable.value_counts()
    return f"""<h2 id="taxonomy">The means: a taxonomy of software capabilities</h2>
<p>The <a href="capabilities.html">list of capabilities</a> is a hand-written taxonomy of what software does for the people
who do the work: {(T.level == 0).sum()} domains, {(T.level == 1).sum()} capabilities and {len(tasks):,} tasks. It classifies by
function (what is computed or done), not by who uses a product or how popular it is, and it is assembled from
{X.scheme.nunique()} published taxonomies and standards, among them the NAFEMS simulation competency areas, NIST's
classification of mathematical software, the EDAM bioinformatics ontology, the WHO classification of digital health
interventions, the APQC process framework and the ACM computing classification.</p>
<h3>How it was made</h3>
<ol>
<li>An editor (an AI model) wrote the domains, the boundaries between them, a first list of capabilities, and the published
taxonomies each domain had to integrate.</li>
<li>One author per domain (also AI models) wrote the capabilities and tasks from that brief, the sources, and
O*NET's list of the software each occupation uses, from which every example product is taken.</li>
<li>The editor read the whole tree, gave each task that two domains had modeled a single owner, and fixed the references
between domains.</li>
<li>A separate checker per domain tried to read each cited source and compared every citation with what it found.</li>
</ol>
<h3>How far to trust it</h3>
<ul>
<li>{n_ok:,} of {n_x:,} citations ({n_ok / n_x:.0%}) were checked against the source itself. Checking corrected 192 and removed 11
that cited something that does not exist. The rest could not be read: ISO, IEC, SAE and ASTM documents are paywalled or
refuse automated reading. Sourcing is weakest for {weak} and strongest for {strong}.</li>
<li>Each task says whether an open benchmark is possible ({int(bench.get("yes", 0))} yes, {int(bench.get("partly", 0))} partly,
{int(bench.get("no", 0))} no) and names open-source and proprietary tools. Those three fields are the authors' knowledge and
were not checked.</li>
<li>No one who works in these fields has reviewed it. It carries a flow (next section) but nothing yet that says how
much each capability matters.</li>
</ul>
<p class="note">Everything is in <a href="{REPO}/tree/main/taxonomy"><code>taxonomy/</code></a>: the tree as JSON and CSV, the brief the
authors followed, each checker's verdicts with the page read, and a log of every edit.</p>
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
produce to deliver it, then follow each need dollar to the work it pays for and the means that work is done with.</p>

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
Mixed retail, wholesale and freight margins are split across needs in proportion to goods spending.
Each need is then scaled to one dollar and the needs are averaged, so every need counts equally. Needs are
complements (no amount of one makes up for another), so price, which measures the last unit, cannot rank them;
spending is used only within a need, where the options do substitute. Weighting needs by spending instead is
<a href="#trust">a variant</a>.</p>
<h3>Capabilities</h3>
<p>Each commodity gets one of 56 engineering archetypes, and each archetype a score from 0 to 3 on each capability:
3 means the sector cannot design, run or maintain its product or plant without it, 2 means important and routine,
1 means incidental. Scores describe the sector's own activity; dependence on suppliers comes from <i>L</i>.
Scores map to weights of 1.0, 0.3 and 0.1, an assumption that
<a href="#score-weights">occupation data</a> suggest is too steep.</p>
{occ}
{activity_method(d)}
{taxonomy_method(d)}
{flow_method(d)}
<h2 id="trust">How far to trust it</h2>
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
<li>The list of needs carries weight. Every need counts equally, so splitting one need in two doubles its share.
The list is ours, not a published one.</li>
<li>Within each need, US spending decides which sectors serve it. A basket in physical units would shift weight
toward farming, water and energy.</li>
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
    for k in d.ct.index:
        pages[cap_href(k)] = lambda d, k=k: capability_detail_page(d, k)
    for k in d.flow.index:
        pages[flow_href(k)] = lambda d, k=k: flow_page(d, k)
    pages["activities.html"] = activities_page
    for a in d.act.index[d.act.level == "intermediate"]:
        pages[act_href(a)] = lambda d, a=a: activity_page(d, a)
    for name, fn in pages.items():
        (SITE / name).write_text(fn(d), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

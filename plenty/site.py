"""Render the static site (site/) from config/ and results/.

    python scripts/03_run.py     # refresh results/ first if config/ changed
    python -m plenty.site

Pages follow the planning loop: needs, capabilities, gaps, work; plus the sector table and the
method. Assets in plenty/web/ are copied as they are. Everything is plain HTML with relative links,
so the site works from any path (GitHub Pages serves it under /plenty/).
"""
from __future__ import annotations
import functools
from dataclasses import dataclass
import html
import json
import math
import shutil
import urllib.parse
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis as A, matrix as MX, model as M, occupations as O

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

    @functools.cached_property
    def io(self) -> M.Model:
        """The input-output model itself, for the pages that show its matrices."""
        return M.build()

    @functools.cached_property
    def need_dollars(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(d, x): what a dollar of each need buys, and the output it takes."""
        return A.need_dollars(self.io)

    @functools.cached_property
    def need_value_added(self) -> pd.DataFrame:
        """v: each sector's share of the value added behind a dollar of each need (columns sum to one)."""
        va = self.need_dollars[1].mul(A.value_added_share(self.io), axis=0)
        return va / va.sum()

    @functools.cached_property
    def wage_bill(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """(P, info, occupations, survey): what the surveyed industries covering each sector paid each
        occupation in a year, $M (sector x occupation); how each sector was measured; each
        occupation's title and major group; and each surveyed industry's title and whole wage bill, $M."""
        bill, info = O.wage_mix(self.io.t.commodities, use_proxies=True)
        o = O.oews()
        titles = o.drop_duplicates("OCC_CODE").set_index("OCC_CODE").OCC_TITLE
        occ = pd.DataFrame({"title": titles.reindex(bill.columns),
                            "major": [titles[c[:2] + "-0000"].removesuffix(" Occupations") for c in bill.columns]})
        all_jobs = o[o.OCC_CODE == "00-0000"].set_index("NAICS")
        survey = pd.DataFrame({"title": all_jobs.NAICS_TITLE, "wagebill_musd": all_jobs.wagebill / 1e6})
        return bill / 1e6, info, occ, survey

    @functools.cached_property
    def wages(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """(W, info, occupations): each sector's wage bill as shares over occupations. A row sums to
        one, or to nothing where the sector is not measured."""
        bill, info, occ, _ = self.wage_bill
        return bill.div(bill.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0), info, occ

    @functools.cached_property
    def capital(self) -> M.Capital:
        """How investment is placed on industries: what the capital matrix is made from."""
        return M.capital_allocation(self.io.t)

    @functools.cached_property
    def sheets(self) -> dict:
        """The model's matrices that have a page, by letter."""
        return sheets(self)

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

def page(title: str, active: str, body: str, long_title: bool = False, scripts: tuple[str, ...] = ()) -> str:
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
<script src="site.js"></script>{"".join(f'<script src="{x}"></script>' for x in scripts)}
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


def _m(body: str, block: bool = False) -> str:
    """MathML, which browsers render natively: the site loads nothing from elsewhere."""
    return f'<div class="eq"><math display="block">{body}</math></div>' if block else f"<math>{body}</math>"


def _sub(a: str, b: str) -> str:
    """a with subscript b; each letter of b is its own identifier, so that it is set in italic."""
    return f"<msub><mi>{a}</mi><mrow>{''.join(f'<mi>{c}</mi>' for c in b)}</mrow></msub>"


def _sum(i: str) -> str:
    return f"<munder><mo>&sum;</mo><mi>{i}</mi></munder>"


# bold letters are Unicode's mathematical bold: browsers do not all honour mathvariant
_I, _A = "&#x1D408;", "&#x1D400;"
# a symbol that has a page of its own is a link to it; HTML is allowed inside a MathML identifier
_A_LINK = f'<mi><a href="matrix-A.html">{_A}</a></mi>'
_ONE_LESS_C = f'<mrow><mo>(</mo><mn>1</mn><mo>&minus;</mo>{_sub("c", "a")}<mo>)</mo></mrow>'


MATRIX_A = "matrix-A.html"
MATRIX_PAGES = "ABDUKVSWP" # the matrices with a picture page of their own: matrix-A.html, matrix-B.html and so on
# every symbol with a page: those matrices, investment by investor (a table, being five columns wide)
# and the vector of weights
# and the two vectors there is one of for each need. A file is not named by a letter's case alone:
# some file systems cannot tell matrix-D from matrix-d.
SYMBOL_PAGES = {**{k: f"matrix-{k}.html" for k in MATRIX_PAGES}, "F": "matrix-F.html", "z": "vector-z.html",
                "d": "vector-d.html", "x": "vector-x.html", "v": "vector-v.html"}
# short labels for the major groups of occupations, by the first two digits of the code
SOC_SHORT = {"11": "Management", "13": "Business, finance", "15": "Computing, math", "17": "Engineering", "19": "Science",
             "21": "Social service", "23": "Legal", "25": "Education", "27": "Arts, media", "29": "Health practitioners",
             "31": "Health support", "33": "Protective", "35": "Food service", "37": "Cleaning, grounds",
             "39": "Personal care", "41": "Sales", "43": "Office support", "45": "Farming", "47": "Construction, extraction",
             "49": "Repair", "51": "Production", "53": "Transport, moving"}
HEAT_FLOOR = 5e-4          # a need's table shades entries from a twentieth of a cent up, and leaves smaller ones blank
LEFT_OUT_NAME = {"defense": "Federal defense", "federal_civil": "Federal nondefense government",
                 "finance_legal": "Finance and legal services", "discretionary": "Discretionary",
                 "accounting": "Accounting entries"}
INVESTOR_NAME = {"private": "Private business", "residential": "Housing", "fed_defense": "Federal defense",
                 "fed_nondefense": "Federal nondefense", "state_local": "State and local government"}
MATRIX_SHOWN = "221100"    # the sector A's lookup opens on: electric power
MATRIX_PARTS = "matrix-A-parts.js"   # B and D, fetched when a cell of A is first marked
MATRIX_PART_CUT = 1e-5     # entries of B under a thousandth of a cent are left out of that file
MATRIX_TOP = 15            # entries in a table of the largest
# How each kind of matrix is filed and shown: the unit of its data file, the smallest entry kept in
# it (smaller ones are blank in the picture), the two ends of the colour scale and their legend,
# what a blank cell is said to hold, and how a cell's printed value is described.
MATRIX_KINDS = {
    "per_dollar": {"unit": 1e-5, "cut": 1e-4, "scale": (1e-4, 1.0), "ticks": ("0.01&cent;", "0.1&cent;", "1&cent;", "10&cent;", "$1"),
                   "blank": "under 0.01¢ per dollar", "small": "under a hundredth of a cent", "in_cell": "in cents"},
    "share": {"unit": 1e-5, "cut": 1e-4, "scale": (1e-4, 1.0), "ticks": ("0.01%", "0.1%", "1%", "10%", "100%"),
              "blank": "under 0.01%", "small": "under a hundredth of a percent", "in_cell": "in percent"},
    "dollars": {"unit": 1.0, "cut": 0.5, "scale": (1.0, 1e6), "ticks": ("$1M", "$10M", "$100M", "$1B", "$10B", "$100B", "$1T"),
                "blank": "under $0.5 million", "small": "under half a million dollars",
                "in_cell": "in millions of dollars, with k for thousands"},
}
MATRIX_CUT, MATRIX_UNIT = MATRIX_KINDS["per_dollar"]["cut"], MATRIX_KINDS["per_dollar"]["unit"]


def _bold(letter: str) -> str:
    """A capital or small Latin letter as Unicode's mathematical bold."""
    return f"&#x{0x1D400 + ord(letter) - ord('A') if letter.isupper() else 0x1D41A + ord(letter) - ord('a'):X};"


def _sym(letter: str, here: str = "") -> str:
    """A matrix or vector by its letter. One with a page of its own links to it, except from that page."""
    if letter in SYMBOL_PAGES and letter != here:
        return f'<mi><a href="{SYMBOL_PAGES[letter]}">{_bold(letter)}</a></mi>'
    return f"<mi>{_bold(letter)}</mi>"


def _vec(letter: str, here: str = "", sub: str = "n") -> str:
    """A vector there is one of for each need (or whatever sub counts). One with a page links to it,
    letter and subscript together: browsers misplace a MathML subscript on a base that is a link, so
    the subscript of a linked vector is set as HTML inside the link."""
    if letter in SYMBOL_PAGES and letter != here:
        return f'<mi><a href="{SYMBOL_PAGES[letter]}">{_bold(letter)}<sub><i>{sub}</i></sub></a></mi>'
    return f"<msub><mi>{_bold(letter)}</mi><mrow>{''.join(f'<mi>{c}</mi>' for c in sub)}</mrow></msub>"


def _elt(shown: str, sub: str, page: str = "") -> str:
    """One entry of a matrix or vector: an italic letter with subscripts, linked to the page of the
    symbol it is an entry of (page, a key of SYMBOL_PAGES) when there is one."""
    if not page:
        return _sub(shown, sub)
    italic = f"&#x{0x1D44E + ord(shown) - ord('a'):X};"
    return f'<mi><a href="{SYMBOL_PAGES[page]}">{italic}<sub><i>{sub}</i></sub></a></mi>'


_ONES = "<mn>&#x1D7CF;</mn>"     # a column of ones: a matrix times it is the matrix's row totals


def _diag(letter: str = "", body: str = "") -> str:
    """A vector written as a diagonal matrix: the vector of that letter, or the one body spells out."""
    return f"<mrow><mspace width=\"0.17em\"/><mi>diag</mi><mo>&#x2061;</mo><mo>(</mo>{body or f'<mi>{_bold(letter)}</mi>'}<mo>)</mo></mrow>"


def _inv(base: str) -> str:
    return f"<msup>{base}<mrow><mo>&minus;</mo><mn>1</mn></mrow></msup>"


def _eqs(rows: list[tuple[str, str]]) -> str:
    """Equations set one to a line and aligned at the equals sign."""
    return _m('<mtable displaystyle="true" columnalign="right center left" columnspacing="0.3em" rowspacing="1.1em">'
              + "".join(f'<mtr><mtd class="l">{a}</mtd><mtd><mo>=</mo></mtd><mtd class="r">{b}</mtd></mtr>' for a, b in rows)
              + "</mtable>", block=True)


def _b_from(here: str) -> str:
    return f'<mrow><mo>(</mo>{_sym("U", here)}<mo>+</mo>{_sym("K", here)}<mo>)</mo></mrow><mo>&#x2062;</mo>{_inv(_diag("g"))}'


def _d_from(here: str) -> str:
    return f'{_sym("V", here)}<mo>&#x2062;</mo>{_inv(_diag("q"))}'


@dataclass
class Sheet:
    """One of the model's matrices, arranged for a page of its own: sectors in the page's order,
    and the words its picture uses for a row, a column and a cell."""
    key: str                       # its letter
    name: str                      # after the letter in the page's title
    kind: str                      # a key of MATRIX_KINDS
    values: pd.DataFrame
    row_names: pd.Series
    col_names: pd.Series
    row_tip: str                   # before a row's name, and a column's, in a cell's hover tip
    col_tip: str
    row_is: str                    # the same under the picture, for what is marked
    col_is: str
    axis: str                      # over the picture: what the columns are
    caption: str                   # the start of the picture's caption
    second: pd.DataFrame | None = None     # the part of each entry that is equipment and buildings
    exact: bool = False            # entries are whole units, so a blank cell holds nothing at all
    col_groups: pd.Series | None = None    # column -> group, where the columns are not sectors
    short: dict | None = None      # short labels for those groups
    order: str = "Sectors are in the Bureau's order within fifteen groups."

    @property
    def href(self) -> str: return f"matrix-{self.key}.html"
    @property
    def data_file(self) -> str: return f"matrix-{self.key}-data.js"
    @property
    def csv_file(self) -> str: return f"matrix-{self.key}.csv"
    @property
    def title(self) -> str: return f"{self.key}, {self.name}"
    @property
    def shown(self) -> np.ndarray:
        """Which entries the picture and the data file hold."""
        return np.abs(self.values.values) >= MATRIX_KINDS[self.kind]["cut"]


def matrix_a(d: Data):
    """(A, the part of it that is capital), both with sectors in the order the page shows them."""
    m = d.io
    order = MX.ordered(m.t.commodities)
    return m.A.loc[order, order], MX.direct_parts(m)[1].loc[order, order]


def sheets(d: Data) -> dict[str, Sheet]:
    """The matrices that have a page, by letter. Commodities and industries are each put in groups."""
    m, t = d.io, d.io.t
    com, ind = MX.ordered(t.commodities), MX.ordered(t.industries)
    purchases, capital, D = MX.factors(m)
    A, A_capital = matrix_a(d)
    occ = d.wage_bill[2]
    by_occupation = dict(col_groups=occ.major, short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
                         order="Sectors are in the Bureau's order within fifteen groups, and occupations in the order of the "
                               "Standard Occupational Classification within its 22 major groups.")
    goods = dict(row_names=t.names, col_names=t.ind_names)       # commodities down, industries across
    makers = dict(row_names=t.ind_names, col_names=t.names)      # industries down, commodities across
    out = [
        Sheet("A", "the direct requirements", "per_dollar", A, t.names, t.names,
              row_tip="Input", col_tip="To make", row_is="Row, the input:", col_is="Column, the thing made:",
              axis="Made: one dollar of each commodity",
              caption="Each column is a commodity being made and each row an input to it. Colour is cents of the input per "
                      "dollar made, on a log scale. The diagonal blocks are groups buying from themselves.",
              second=A_capital),
        Sheet("B", "what industries use per dollar", "per_dollar", (purchases + capital).loc[com, ind], **goods,
              row_tip="Input", col_tip="Used by", row_is="Row, the input:", col_is="Column, the industry using it:",
              axis="Industries: per dollar of their output",
              caption="Each column is an industry and each row a commodity it uses. Colour is cents of the commodity per "
                      "dollar of the industry's output, on a log scale.",
              second=capital.loc[com, ind]),
        Sheet("D", "who makes each commodity", "share", D.loc[ind, com], **makers,
              row_tip="Industry", col_tip="Its share of", row_is="Row, the industry:", col_is="Column, the commodity made:",
              axis="Commodities: who makes each",
              caption="Each column is a commodity and each row an industry that might make it. Colour is the industry's "
                      "share of the commodity, on a log scale. The bright diagonal is industries making what they are named for."),
        Sheet("U", "the Use table", "dollars", t.U.loc[com, ind], **goods,
              row_tip="Bought", col_tip="By", row_is="Row, the commodity bought:", col_is="Column, the industry buying:",
              axis="Industries buying",
              caption="Each column is an industry and each row a commodity it bought. Colour is millions of dollars in 2017, "
                      "on a log scale.", exact=True),
        Sheet("K", "the capital matrix", "dollars", m.K.loc[com, ind], **goods,
              row_tip="Capital good", col_tip="Placed on", row_is="Row, the capital good:",
              col_is="Column, the industry it is placed on:", axis="Industries using the capital",
              caption="Each column is an industry and each row a kind of equipment, building or software placed on it. Colour "
                      "is millions of dollars in 2017, on a log scale. Most rows are empty: few commodities are capital goods."),
        Sheet("S", "where each capital good is placed", "share", d.capital.shares.loc[com, ind], **goods,
              row_tip="Capital good", col_tip="Share placed on", row_is="Row, the capital good:",
              col_is="Column, the industry it is placed on:", axis="Industries: their share of each capital good",
              caption="Each column is an industry and each row a capital good. Colour is the share of an investor's purchases of "
                      "the good that is placed on the industry, on a log scale. A short bright run is a good with few users; "
                      "a long faint one is a good spread over every industry of its kind."),
        Sheet("W", "who does each sector's work", "share", d.wages[0].loc[com], t.names, occ.title,
              row_tip="Sector", col_tip="Share of its wage bill paid to", row_is="Row, the sector:", col_is="Column, the occupation:",
              axis="Occupations: their share of each sector's wage bill",
              caption="Each row is a sector and each column an occupation. Colour is the occupation's share of the sector's "
                      "wage bill, on a log scale. A bright column is an occupation every sector pays, such as managers; a "
                      "bright patch is one that belongs to a few sectors.", **by_occupation),
        Sheet("P", "what each sector's industries paid each occupation", "dollars", d.wage_bill[0].loc[com], t.names, occ.title,
              row_tip="Sector", col_tip="Paid to", row_is="Row, the sector:", col_is="Column, the occupation:",
              axis="Occupations: what each sector's industries paid them",
              caption="Each row is a sector and each column an occupation. Colour is millions of dollars paid in a year, on a "
                      "log scale. Rows are as bright as the surveyed industries behind them are large, which is what "
                      "dividing by the row's total takes away.", **by_occupation),
        Sheet("V", "the Make table", "dollars", t.V.loc[ind, com], **makers,
              row_tip="Industry", col_tip="Made", row_is="Row, the industry:", col_is="Column, the commodity made:",
              axis="Commodities made",
              caption="Each column is a commodity and each row an industry that might make it. Colour is millions of dollars "
                      "made in 2017, on a log scale. The bright diagonal is industries making what they are named for.", exact=True),
    ]
    return {s.key: s for s in out}


def sheet_data(s: Sheet, **extra) -> str:
    """A matrix page's data file: what the picture needs to name rows, columns and cells, and
    every entry of at least the kind's cut, by column, as (row, value) in the kind's unit, or
    (row, value, capital part) for a matrix that has one."""
    kind = MATRIX_KINDS[s.kind]
    v, w, keep = s.values.values, s.second.values if s.second is not None else None, s.shown
    def units(x):
        return int(round(x / kind["unit"]))
    cells = [[x for i in np.flatnonzero(keep[:, j]) for x in ((i, units(v[i, j])) if w is None else (i, units(v[i, j]), units(w[i, j])))]
             for j in range(v.shape[1])]
    def side(codes, names, groups=None):
        g = MX.groups(codes) if groups is None else groups
        return {"codes": list(codes), "names": [names[c] for c in codes], "groups": [g[c] for c in codes]}
    payload = {"key": s.key, "kind": s.kind, "unit": kind["unit"], "cut": kind["cut"], "scale": kind["scale"],
               "blank": "nothing" if s.exact else kind["blank"], "short": {**MX.SHORT, **(s.short or {})},
               "rows": side(s.values.index, s.row_names), "cols": side(s.values.columns, s.col_names, s.col_groups),
               "rowTip": s.row_tip, "colTip": s.col_tip, "rowIs": s.row_is, "colIs": s.col_is,
               "second": w is not None, "cells": [[int(x) for x in col] for col in cells], **extra}
    return "window.PLENTY_MATRIX = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def matrix_data(d: Data, key: str) -> str:
    """The data file of one matrix page. A's also carries what its sector lookup and its cells' derivation need."""
    s = d.sheets[key]
    if key != "A":
        return sheet_data(s)
    unit = MATRIX_UNIT
    return sheet_data(s, shown=MATRIX_SHOWN, parts=MATRIX_PARTS,
                      total=[round(x / unit) for x in s.values.values.sum(axis=0)],
                      capital=[round(x / unit) for x in s.second.values.sum(axis=0)])


def matrix_a_parts(d: Data) -> str:
    """What a cell of A is made of, for the page to show when a cell is marked: B by industry as
    (commodity, value, capital part), each entry of at least MATRIX_PART_CUT, and D by commodity as
    (industry, share). Commodities are numbered in the page's order and industries in the model's."""
    m = d.io
    order = list(matrix_a(d)[0].index)
    purchases, capital, D = MX.factors(m)
    b, k, shares = (purchases + capital).loc[order].values, capital.loc[order].values, D[order].values
    def units(x):
        return round(x / MATRIX_UNIT)
    B = [[int(x) for i in np.flatnonzero(np.abs(b[:, c]) >= MATRIX_PART_CUT) for x in (i, units(b[i, c]), units(k[i, c]))]
         for c in range(b.shape[1])]
    made_by = [[int(x) for i in np.flatnonzero(shares[:, j]) if units(shares[i, j]) for x in (i, units(shares[i, j]))]
               for j in range(shares.shape[1])]
    payload = {"unit": MATRIX_UNIT, "cut": MATRIX_PART_CUT, "industries": [m.t.ind_names[c] for c in m.t.industries],
               "B": B, "D": made_by}
    return "window.PLENTY_MATRIX_PARTS = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def sheet_csv(s: Sheet) -> str:
    return s.values.to_csv(float_format="%.6g")


def sheet_picture(s: Sheet, also: str = "", extra: str = "") -> str:
    """The picture of a matrix with its margins, buttons and legend, drawn by web/matrix.js.
    also: a sentence for the caption about this picture alone; extra: markup the script uses."""
    kind, (nr, nc) = MATRIX_KINDS[s.kind], s.values.shape
    blank = "zero" if s.exact else f"zero or {kind['small']}"
    return f"""<figure class="mx">
<div class="mx-frame">
<div class="mx-axis mx-axis-top"><span>{e(s.axis)} &rarr;</span>
<span class="mx-zoom"><button type="button" id="mx-zoom-out" aria-label="Zoom out" disabled>&minus;</button><button
 type="button" id="mx-zoom-in" aria-label="Zoom in">+</button><button type="button" id="mx-zoom-all" disabled>Whole matrix</button><button
 type="button" id="mx-unsort" disabled>Default order</button></span></div>
<div class="mx-strip mx-top" id="mx-top"></div>
<div class="mx-strip mx-left" id="mx-left"></div>
<div class="mx-plot" style="aspect-ratio: {nc} / {nr}">
<canvas id="mx-canvas" width="{nc}" height="{nr}" role="img" tabindex="0"
 aria-label="Heat map of the {nr} by {nc} matrix {s.key}, {e(s.name)}. The tables on this page and the CSV file give the same figures."></canvas>
<i id="mx-h" aria-hidden="true"></i><i id="mx-v" aria-hidden="true"></i>
</div>
</div>
<div class="mx-note" id="mx-note" aria-live="polite"></div>
{extra}<div class="mx-legend" aria-hidden="true"><div class="mx-ramp"></div>
<div class="mx-ticks">{"".join(f"<span>{x}</span>" for x in kind["ticks"])}</div></div>
<figcaption>{s.caption} The {(~s.shown).mean():.0%} of entries that are {blank} are blank. {s.order}</figcaption>
</figure>
<p class="note mx-how">Hover over a cell for its row, its column and its value. Click a cell to mark it with its row and
column, or click in a margin to mark one row or one column.{" " + also if also else ""} To zoom, scroll or pinch over the picture or its
margins, or use the buttons. To move, drag with the mouse wheel pressed or with Ctrl held, or with a finger on a touch
screen. Close in, the margins name each sector, and closer still each cell shows its value, {kind["in_cell"]}. The
arrows beside a sector's name, and the buttons under the picture for whatever is marked, sort the whole matrix by that
row or column: largest first, then smallest first, then back to the Bureau's order. Sorting by a row or column marks
it, and unmarking it lets go of the sort.</p>"""


def _figures(items) -> str:
    return '<dl class="figures">' + "".join(
        f'<div><dt>{a}</dt><dd>{b}</dd><dd class="dim">{c}</dd></div>' for a, b, c in items) + "</dl>"


def _trillion(x: float) -> str:
    return f"${x / 1e6:.1f} trillion"


def matrix_page(d: Data, key: str) -> str:
    """The page of U, K, B, D or V: what it is, where it comes from, the picture, and its largest entries."""
    m, t, s = d.io, d.io.t, d.sheets[key]
    v, (n, n_cols) = s.values.values, s.values.shape
    sym = lambda x: _m(_sym(x, key))
    nonzero = ("Entries that are not zero", f"{(v != 0).mean():.0%}", f"{int((v != 0).sum()):,} of {v.size:,}")
    diagonal = sum(t.V.at[c, c] for c in t.commodities if c in t.V.index) / t.V.values.sum()
    code = f'<a href="{REPO}/blob/main/plenty/model.py"><code>plenty/model.py</code></a>'
    top, off_diagonal, via, trail = s.values.stack().sort_values(ascending=False), "", "", None
    by_rows, by_cols = "commodities", "industries"

    if key == "U":
        lede = ("What each industry bought to use up. The entry in row <i>i</i> and column <i>k</i> is the millions of dollars of "
                "commodity <i>i</i> that industry <i>k</i> bought in 2017 as an input to what it made.")
        figures = [nonzero, ("Total", _trillion(v.sum()), "bought by industries in 2017"),
                   ("Largest entry", f"${v.max() / 1e3:.0f} billion", e(f"{t.names[top.index[0][0]]}, bought by {t.ind_names[top.index[0][1]]}".lower()))]
        about = f"""<p>This is the Bureau of Economic Analysis's Use table for 2017 at its finest level, as published, less the
columns for final demand and the rows for wages, taxes and profits. What households, governments and foreigners buy for
their own use, and what is bought to keep as equipment or buildings, is final demand; equipment and buildings come back
into the account through {sym("K")}.</p>
<p>Imports are included: a purchase counts whether the commodity was made here or abroad. {int((v < 0).sum())} entries
are negative, where an industry sold more of a commodity, as scrap or used goods, than it bought.</p>
<p>It goes into {sym("B")}, and from there into {sym("A")}:</p>
{_eqs([(_sym("B", key), _b_from(key))])}"""
        heads, caption = ("Commodity bought", "By industry", "$ million"), "Oil going to refineries is the largest. Most of the rest are finance, insurance and real estate."
    elif key == "K":
        cap = d.capital
        goods, members = int((v != 0).any(axis=1).sum()), cap.group.value_counts()
        kinds = ", ".join(f"{INVESTOR_NAME[h].lower()} ({members[h]})" for h in cap.investment.columns)
        lede = ("What each industry used of equipment, buildings and software, estimated. The entry in row <i>i</i> and column "
                "<i>k</i> is the millions of dollars of capital good <i>i</i> bought in 2017 and placed on industry <i>k</i>.")
        figures = [nonzero, ("Total", _trillion(v.sum()), "of investment in 2017"),
                   ("Capital goods", f"{goods}", f"of {n} commodities are bought as investment")]
        about = f"""<p>The Bureau of Economic Analysis publishes what was bought as investment, commodity by commodity and by five
kinds of investor, but not which industry bought it at this level of detail. So this matrix is built here. Each investor's
purchases of a capital good are split among that investor's industries:</p>
{_m(f'{_sub("k", "ik")}<mo>=</mo>{_sub("f", "ih")}<mo>&#x2062;</mo>{_sub("s", "ik")}', block=True)}
<dl class="where">
<dt>{sym("F")}</dt><dd>what was bought as investment: the millions of dollars of capital good <i>i</i> bought in 2017 by
investor <i>h</i>, {_trillion(cap.investment.values.sum())} in all. It is read from the Bureau's Use table.</dd>
<dt>{_m("<mi>h</mi>")}</dt><dd>the kind of investor that industry <i>k</i> is. Industries of each kind: {kinds}.</dd>
<dt>{sym("S")}</dt><dd>the share of that purchase placed on industry <i>k</i>. This is where the judgment is:
{sum(1 for x in cap.steps if x["note"])} pairings of a capital good with its evident users, and a weight for sharing within a
set of users.</dd>
</dl>
<p>Each row of {sym("K")} adds up to what was invested in that capital good, so nothing is made or lost. {int((v < 0).sum())}
entries are negative: sales of used equipment and scrap, shared out the same way so that the accounts balance. The
<a href="method.html#capital">method page</a> says why capital is counted as an input at all, and the code is {code}.</p>
<p>It is added to {sym("U")} to make {sym("B")}:</p>
{_eqs([(_sym("B", key), _b_from(key))])}"""
        heads, caption = ("Capital good", "Placed on industry", "$ million"), "Mostly structures: houses, roads and schools. Research and development is counted as investment too."
    elif key == "S":
        cap = d.capital
        goods = int((v != 0).any(axis=1).sum())
        rules = [x for x in cap.steps if x["note"]]
        lede = ("How each capital good is shared out. The entry in row <i>i</i> and column <i>k</i> is the share of an investor's "
                "purchases of capital good <i>i</i> that is placed on industry <i>k</i>, the investor being the kind that <i>k</i> is.")
        figures = [nonzero, ("Capital goods", f"{goods}", f"of {n} commodities are bought as investment"),
                   ("Pairings", f"{len(rules)}", "of a capital good with its evident users")]
        among = (f'<munder><mo>&sum;</mo><mrow><mi>m</mi><mo>&isin;</mo>{_sub("&Omega;", "ik")}</mrow></munder>')
        def step_row(x):
            placed = cap.investment.loc[x["commodities"], x["group"]].sum()
            what = ("; ".join(e(t.names[c]) for c in x["commodities"]) if x["note"]
                    else f'<span class="dim">Everything else it invests in ({len(x["commodities"])} commodities)</span>')
            where = e(x["note"].split("->")[-1].strip()) if x["note"] else '<span class="dim">all its industries</span>'
            return (f'<tr><td class="name">{e(INVESTOR_NAME[x["group"]])}</td><td class="name">{what}</td><td class="name">{where}</td>'
                    f'<td class="num">{len(x["users"])}</td><td class="num">{placed:,.0f}</td></tr>'.replace(">-", ">&minus;"))
        about = f"""<p>An investor's purchase of a capital good is shared among the industries that could have bought it, in proportion to a weight:</p>
{_m(f'{_sub("s", "ik")}<mo>=</mo><mfrac>{_sub("z", "k")}<mrow>{among}{_sub("z", "m")}</mrow></mfrac>', block=True)}
<dl class="where">
<dt>{sym("z")}</dt><dd>each industry's weight: its gross operating surplus if it is a private business or housing, and its
output if it is government.</dd>
<dt>{_m(_sub("&Omega;", "ik"))}</dt><dd>the industries that could have bought capital good <i>i</i>, among those of the same kind of
investor as <i>k</i>: the ones a pairing below names for it, or all of that kind if none does. If <i>k</i> is not one of
them, or its kind of investor bought none of <i>i</i>, the share is zero.</dd>
</dl>
<p>So within one kind of investor a row adds up to one: the whole purchase is placed. Every industry in a set gets the
same mix of what the set shares, which is the crude part: with no pairing, a law office and a steel mill get the same
equipment per dollar of operating surplus.</p>
<p>It multiplies {sym("F")} to make {sym("K")}:</p>
{_m(f'{_sub("k", "ik")}<mo>=</mo>{_sub("f", "ih")}<mo>&#x2062;</mo>{_sub("s", "ik")}', block=True)}

<h2 id="rules">Who could have bought it</h2>
{table([th("Investor"), th("Capital goods"), th("Placed on"), th("Industries", "num"), th("$ million", "num")],
       [step_row(x) for x in cap.steps],
       caption=f'Each line is one set: the investor&rsquo;s purchases of the capital goods on the left are shared among the industries '
               f'on the right. A capital good takes the first pairing that names it. The pairings are judgment, kept in '
               f'<a href="{REPO}/blob/main/config/capital_allocation.csv"><code>config/capital_allocation.csv</code></a>; '
               f'the one for multifamily housing is in the code, {code}.')}"""
        heads, caption = None, ""
        via = f' / <a href="matrix-K.html#about">{_m(_sym("K", "K"))}, the capital matrix</a>'
    elif key == "B":
        totals = s.values.sum()
        lede = ("Each industry's recipe. The entry in row <i>i</i> and column <i>k</i> is the dollars of commodity <i>i</i> that "
                "industry <i>k</i> uses per dollar of what it makes, with equipment and buildings counted as inputs.")
        figures = [("Entries that are not zero", f"{(v != 0).mean():.0%}", f"{s.shown.mean():.0%} are a hundredth of a cent or more"),
                   ("Inputs per dollar of output", f"{totals.median() * 100:.0f}&cent;", "the median column total"),
                   ("Equipment and buildings", f"{s.second.values.sum() / v.sum():.0%}", "of the total of all entries")]
        about = f"""<p>What industries bought, plus the equipment and buildings placed on them, divided by what each industry made:</p>
{_eqs([(_sym("B", key), _b_from(key)),
       (_sub("b", "ik"), f'<mfrac><mrow>{_sub("u", "ik")}<mo>+</mo>{_sub("k", "ik")}</mrow>{_sub("g", "k")}</mfrac>')])}
<p>{_m(f"<mi>{_bold('g')}</mi>")} is each industry's output, {_trillion(t.g.sum())} in all, which is the sum of its row of {sym("V")}.
A column of {sym("B")} adds up to what the industry spends per dollar of output on inputs, equipment and buildings; the
rest of the dollar is wages, taxes, and whatever owners keep after investing.</p>
<p>{sym("B")} is by industry, but needs are for commodities. Multiplying by {sym("D")} gives {sym("A")}, which is by commodity
on both sides. The code is {code}.</p>"""
        heads, caption = ("Input", "Industry using it", "&cent; per dollar of its output"), "Many are a raw material going into the plant that processes it."
    elif key == "V":
        lede = ("What each industry made. The entry in row <i>k</i> and column <i>j</i> is the millions of dollars of commodity "
                "<i>j</i> that industry <i>k</i> made in 2017.")
        figures = [nonzero, ("Total", _trillion(v.sum()), "made in 2017"),
                   ("On the diagonal", f"{diagonal:.0%}", "made by the industry named for the commodity")]
        about = f"""<p>This is the Bureau of Economic Analysis's Make table for 2017 at its finest level, as published. An industry
mostly makes the commodity it is named for, but not only that: a refinery also makes petrochemicals, and a broadcaster also sells
advertising. The entries off the diagonal are those secondary products.</p>
<p>Summing a row gives the industry's output, {_m(f"<mi>{_bold('g')}</mi>")}, which {sym("B")} divides by. Summing a column gives
the commodity's output, {_m(f"<mi>{_bold('q')}</mi>")}, which turns this table into shares:</p>
{_eqs([(_sym("D", key), _d_from(key))])}"""
        heads, caption = ("Industry", "Commodity made", "$ million"), "Commodities made by an industry other than the one named for them."
        by_rows, by_cols, off_diagonal = "industries", "commodities", "The largest entries off the diagonal"
    elif key == "W":
        _, info, occ = d.wages
        direct, proxy = info.index[info.source == "oews"], info.index[info.source == "oews_proxy"]
        none = [c for c in s.values.index if not info.source[c].startswith("oews")]
        lede = ("Who does each sector's work, by pay. The entry in row <i>j</i> and column <i>o</i> is the share of sector "
                "<i>j</i>'s wage bill that is paid to occupation <i>o</i>.")
        figures = [nonzero, ("Sectors measured", f"{len(direct) + len(proxy)}", f"{len(direct)} directly and {len(proxy)} by a stand-in"),
                   ("Largest share", f"{v.max():.0%}", e(f"{occ.title[top.index[0][1]]}, in {t.names[top.index[0][0]]}".lower()))]
        P_ = _sym("P", key)
        row_totals = _inv(_diag(body=P_ + "<mo>&#x2062;</mo>" + _ONES))
        about = f"""<p>Each row of {sym("P")}, what a sector paid each occupation in a year, divided by the row's total:</p>
{_eqs([(_sym("W", key), row_totals + "<mo>&#x2062;</mo>" + P_),
       (_sub("w", "jo"), f'<mfrac>{_sub("p", "jo")}<mrow>{_sum("r")}{_sub("p", "jr")}</mrow></mfrac>')])}
<dl class="where">
<dt>{sym("P")}</dt><dd>what the surveyed industries that cover sector <i>j</i> paid occupation <i>o</i>, from the Bureau of
Labor Statistics's survey of employment and wages.</dd>
<dt>{_m(_ONES)}</dt><dd>a column of ones, so that {_m(P_ + "<mo>&#x2062;</mo>" + _ONES)} is each row's total: the sector's
whole wage bill. Dividing by it turns a row of dollars into shares.</dd>
</dl>
<p class="note">The two lines say the same thing, for the whole matrix and for one entry. With arrays:
<code>W = P / P.sum(axis=1, keepdims=True)</code>.</p>
<p>So a row adds up to one, and it says nothing about how large the sector is: that comes from
{_m(_vec("v", key))}. In the <a href="method.html#account">account</a>, a sector's whole share of the need dollar is split
the way its wage bill is, including the part that is not wages at all.</p>
<p>{len(none)} sectors have no row and pass nothing on, and {len(proxy)} are measured by a stand-in. Which they are, and
what else to know about the survey, is on the page for {sym("P")}. The code is
<a href="{REPO}/blob/main/plenty/occupations.py"><code>plenty/occupations.py</code></a>.</p>"""
        heads, caption = ("Sector", "Occupation", "Share of the sector's wage bill"), "Sectors that are mostly one occupation."
        by_rows, by_cols = "sectors", "occupations"
        trail = ""
    elif key == "P":
        _, info, occ, survey = d.wage_bill
        direct, proxy = info.index[info.source == "oews"], info.index[info.source == "oews_proxy"]
        none = [c for c in s.values.index if not info.source[c].startswith("oews")]
        used = pd.Series([i for x in info.oews_industries[info.oews_industries != ""] for i in x.split(";")]).value_counts()
        dropped = info.wagebill_dropped_frac.median()
        lede = ("What each sector paid each occupation, as far as the survey can say. The entry in row <i>j</i> and column "
                "<i>o</i> is the millions of dollars paid in a year to occupation <i>o</i> by the surveyed industries that cover sector <i>j</i>.")
        figures = [nonzero, ("Sectors with a row", f"{len(direct) + len(proxy)}", f"{len(direct)} directly and {len(proxy)} by a stand-in"),
                   ("Largest entry", f"${v.max() / 1e3:.0f} billion", e(f"{occ.title[top.index[0][1]]}, in {t.names[top.index[0][0]]}".lower()))]
        E_, M_, T_ = (f"<mi>{_bold(x)}</mi>" for x in "EMT")
        def named(codes):
            return "; ".join(e(t.names[c].lower()) for c in codes)
        about = f"""<p>From the Bureau of Labor Statistics's Occupational Employment and Wage Statistics for May 2021, which gives
employment and the mean annual wage for each occupation in each of {len(survey)} industries. Their product is what an
industry paid an occupation in a year, and a sector's row adds up the industries that cover it:</p>
{_eqs([(_sym("P", key), f'{T_}<mo>&#x2062;</mo><mrow><mo>(</mo>{E_}<mo>&#x2218;</mo>{M_}<mo>)</mo></mrow>'),
       (_sub("p", "jo"), f'{_sum("i")}{_sub("t", "ji")}<mo>&#x2062;</mo>{_sub("e", "io")}<mo>&#x2062;</mo>{_sub("m", "io")}')])}
<dl class="where">
<dt>{_m(E_)}</dt><dd>employment: the number of people in occupation <i>o</i> in surveyed industry <i>i</i>.</dd>
<dt>{_m(M_)}</dt><dd>their mean annual wage, in dollars.</dd>
<dt>{_m("<mo>&#x2218;</mo>")}</dt><dd>the product entry by entry, not the matrix product.</dd>
<dt>{_m(T_)}</dt><dd>which surveyed industries cover which sector: {_m(_sub("t", "ji"))} is one if industry <i>i</i> covers sector
<i>j</i>, and zero if not. It comes from the crosswalk between the Bureau of Economic Analysis's sectors and industry codes.</dd>
</dl>
<p class="note">With arrays: <code>P = T @ (E * M)</code>.</p>
<p>The survey has {len(survey)} industries and there are {n} sectors, so sectors share. {int((used > 1).sum())} surveyed
industries each cover more than one sector, and one covers {int(used.max())}
({e(survey.title[used.idxmax()].split(" (")[0].lower())}). Such an industry is counted in full in every sector it covers. So
the rows overlap: this matrix adds up to {_trillion(v.sum())}, while the surveyed industries paid {_trillion(survey.wagebill_musd.sum())}
in all. That does no harm to {sym("W")}, which uses only the proportions within a row, but a row here is not the sector's
own wage bill, and rows must not be added together.</p>
<ul>
<li>The survey is four years later than the 2017 tables.</li>
<li>Where the survey withholds an occupation's employment or wage, that occupation is left out of the row. For the
median sector this is {dropped:.1%} of the wage bill. Wages above the survey's ceiling of ${O.OEWS_TOP_CODE:,.0f} are counted at the ceiling.</li>
<li>{len(proxy)} sectors are measured by a stand-in: public schools and hospitals by education and hospitals of every
ownership, other government by the survey's government industries, and farms by support activities for farming.</li>
<li>{len(none)} sectors have no row at all: {named(none)}.</li>
</ul>
<p>The code is <a href="{REPO}/blob/main/plenty/occupations.py"><code>plenty/occupations.py</code></a>.</p>"""
        heads, caption = ("Sector", "Occupation", "$ million"), "Large occupations in large industries. The same figure appears wherever sectors share a surveyed industry."
        by_rows, by_cols = "sectors", "occupations"
        trail = f' /\n<a href="matrix-W.html#about">{_m(_sym("W", "W"))}, who does each sector&rsquo;s work</a>'
    else:
        assert key == "D", key
        makers = (v > 0).sum(axis=0)
        lede = ("Which industries make each commodity. The entry in row <i>k</i> and column <i>j</i> is the share of commodity "
                "<i>j</i> that industry <i>k</i> made in 2017.")
        figures = [nonzero, ("On the diagonal", f"{diagonal:.0%}", "of output is made by the industry named for the commodity"),
                   ("Commodities with one maker", f"{int((makers == 1).sum())}", f"of {n}; the most any has is {int(makers.max())}")]
        nobody = [t.names[c].lower() for c in s.values.columns[makers == 0]]
        about = f"""<p>The Make table with each column divided by its total, so that a column says who makes the commodity:</p>
{_eqs([(_sym("D", key), _d_from(key)),
       (_sub("d", "kj"), f'<mfrac>{_sub("v", "kj")}{_sub("q", "j")}</mfrac>')])}
<p>{_m(f"<mi>{_bold('q')}</mi>")} is the output of each commodity, the sum of its column of {sym("V")}. Each column here adds up to
one{f", except for {e(' and '.join(nobody))}, which no industry makes and whose columns are empty" if nobody else ""}.</p>
<p>It is what turns {sym("B")}, which is by industry, into {sym("A")}, which is by commodity: each commodity gets the recipe of the
industries that make it, in proportion to how much of it each makes. This is the industry-technology assumption. The code is {code}.</p>"""
        heads, caption = ("Industry", "Commodity", "Share of the commodity"), "Commodities made in part by an industry other than the one named for them."
        by_rows, by_cols, off_diagonal = "industries", "commodities", "The largest entries off the diagonal"

    # W is in the account itself and P is reached through it; the others are reached through A
    behind_a = trail if trail is not None else f' /\n<a href="{MATRIX_A}#derivation">{_m(_sym("A", "A"))}, the direct requirements</a>{via}'
    largest = ""
    if heads:
        if off_diagonal:
            top = top[[i != j for i, j in top.index]]
        top = top.head(MATRIX_TOP)
        def show(x):
            return {"per_dollar": f"{x * 100:.1f}", "share": f"{x:.1%}", "dollars": f"{x:,.0f}"}[s.kind]
        head = [th(heads[0]), th(heads[1]), th(heads[2], "num")] + ([th("Of which equipment and buildings, &cent;", "num")] if s.second is not None else [])
        trows = [f'<tr><td class="name">{e(s.row_names[i])}</td><td class="name">{e(s.col_names[j])}</td><td class="num">{show(x)}</td>'
                 + (f'<td class="num">{show(s.second.at[i, j])}</td>' if s.second is not None else "") + "</tr>" for (i, j), x in top.items()]
        largest = f'<h2 id="largest">{off_diagonal or "The largest entries"}</h2>\n{table(head, trows, caption=caption)}'
    body = f"""
<p class="crumbs"><a href="method.html">Method</a> / <a href="method.html#account">The account in three lines</a>{behind_a}</p>
<h1 class="long">{_m(_sym(key, key))}, {e(s.name)}</h1>
<p class="lede">{lede}</p>
{_figures([("Size", f"{n} &times; {n_cols}", f"{by_rows} by {by_cols}")] + figures)}

<h2 id="about">What it is</h2>
{about}

<h2 id="picture">The whole matrix</h2>
{sheet_picture(s)}

{largest}
<p><a href="{s.csv_file}">Download the matrix as CSV</a> ({n} rows and {n_cols} columns, codes as headings).</p>
"""
    return page(s.title, "method.html", body, long_title=True, scripts=(s.data_file, "matrix.js"))


def _capital_crumbs() -> str:
    return (f'<p class="crumbs"><a href="method.html">Method</a> / <a href="method.html#account">The account in three lines</a> /\n'
            f'<a href="{MATRIX_A}#derivation">{_m(_sym("A", "A"))}, the direct requirements</a> / '
            f'<a href="matrix-K.html#about">{_m(_sym("K", "K"))}, the capital matrix</a></p>')


def _millions(x: float) -> str:
    """A whole number of millions for a table cell, blank for none."""
    return f"{x:,.0f}".replace("-", "&minus;") if round(x) else ""


def investment(d: Data) -> pd.DataFrame:
    """F: what each kind of investor bought of each capital good, $M, for the commodities bought at all."""
    inv = d.capital.investment
    return inv[(inv != 0).any(axis=1)]


def investment_page(d: Data) -> str:
    """The page of F. It is five columns wide, so it is a table to sort and not a picture."""
    t, inv = d.io.t, investment(d)
    kinds, total = list(inv.columns), inv.values.sum()
    columns = ", ".join(f"<code>{c}</code>" for h in kinds for c in M.CAPITAL_COLUMNS[h])
    rows = [f'<tr><th scope="row">{e(t.names[c])}</th>'
            + "".join(f'<td class="num" data-v="{r[h]:.0f}">{_millions(r[h])}</td>' for h in kinds)
            + f'<td class="num" data-v="{r.sum():.0f}">{_millions(r.sum())}</td></tr>' for c, r in inv.iterrows()]
    foot = ("<tr><td>All capital goods</td>" + "".join(f'<td class="num">{_millions(inv[h].sum())}</td>' for h in kinds)
            + f'<td class="num">{_millions(total)}</td></tr>')
    body = f"""
{_capital_crumbs()}
<h1 class="long">{_m(_sym("F", "F"))}, what was bought as investment</h1>
<p class="lede">The equipment, buildings and software bought to keep. The entry in row <i>i</i> and column <i>h</i> is the
millions of dollars of commodity <i>i</i> that investor <i>h</i> bought in 2017 as investment.</p>
{_figures([("Size", f"{len(d.capital.investment)} &times; {len(kinds)}", "commodities by kinds of investor"),
           ("Capital goods", f"{len(inv)}", f"of {len(d.capital.investment)} commodities were bought as investment"),
           ("Total", _trillion(total), "of investment in 2017"),
           ("By private business", f"{inv['private'].sum() / total:.0%}", "of the total")])}

<h2 id="about">What it is</h2>
<p>This is the Bureau of Economic Analysis's own figure, from the final-demand side of its 2017 Use table. The Bureau
records investment in separate columns for each kind of investor ({columns}), covering equipment, structures and
intellectual property. The columns for one kind of investor are added together here, and nothing else is done to them.</p>
<p>What it does not say is which industry each purchase was for. That is the job of {_m(_sym("S", "F"))}, which shares each
entry out among the industries of its kind of investor to make {_m(_sym("K", "F"))}:</p>
{_m(f'{_sub("k", "ik")}<mo>=</mo>{_sub("f", "ih")}<mo>&#x2062;</mo>{_sub("s", "ik")}', block=True)}
<p>{int((inv.values < 0).sum())} entries are negative: an investor sold more used equipment or scrap than it bought of
that commodity.</p>

<h2 id="table">The whole matrix</h2>
{table([th("Capital good", sort="text")] + [th(e(INVESTOR_NAME[h]), "num", sort="num") for h in kinds] + [th("All investors", "num", sort="num")],
       rows, foot=foot, caption="Millions of dollars in 2017. Click a heading to sort. Commodities nobody bought as investment are left out.")}
<p><a href="matrix-F.csv">Download the matrix as CSV</a> ({len(d.capital.investment)} rows, sector codes as headings).</p>
"""
    return page("F, what was bought as investment", "method.html", body, long_title=True)


def weights_page(d: Data) -> str:
    """The page of z, the weight industries of a set share a capital good by."""
    t, cap = d.io.t, d.capital
    by_surplus = cap.group.isin(["private", "residential"])
    def kind(c):
        return "Gross operating surplus" if by_surplus[c] else "Output"
    order = MX.ordered(t.industries)
    rows = [f'<tr><th scope="row">{e(t.ind_names[c])}</th><td class="name">{e(INVESTOR_NAME[cap.group[c]])}</td>'
            f'<td class="name">{kind(c)}</td><td class="num" data-v="{cap.weight[c]:.0f}">{cap.weight[c]:,.0f}</td></tr>' for c in order]
    none = int((cap.weight[by_surplus] <= 0).sum())
    body = f"""
{_capital_crumbs()}
<h1 class="long">{_m(_sym("z", "z"))}, the weight of each industry</h1>
<p class="lede">What industries share a capital good by. When a purchase is shared among a set of industries, each gets a
part in proportion to its weight.</p>
{_figures([("Size", f"{len(order)}", "industries"),
           ("By gross operating surplus", f"{int(by_surplus.sum())}", "private business and housing"),
           ("By output", f"{int((~by_surplus).sum())}", "government industries")])}

<h2 id="about">What it is</h2>
<p>For a private business or housing industry, the weight is its gross operating surplus in 2017: what it had left of
its value added after wages and taxes on production. It stands in for how much capital the industry holds, since that is
what capital earns. It is a row of the Bureau of Economic Analysis's Use table, with a loss counted as
zero{f"; {none} industr{'y' if none == 1 else 'ies'} had none and so get nothing that is shared by weight" if none else ""}.</p>
<p>For a government industry, the weight is its output, the sum of its row of {_m(_sym("V", "z"))}.</p>
<p>Weights are only ever compared within a set of industries of one kind of investor, so the two measures never meet.
They go into {_m(_sym("S", "z"))}:</p>
{_m(f'{_sub("s", "ik")}<mo>=</mo><mfrac>{_sub("z", "k")}<mrow><munder><mo>&sum;</mo><mrow><mi>m</mi><mo>&isin;</mo>{_sub("&Omega;", "ik")}</mrow></munder>{_sub("z", "m")}</mrow></mfrac>', block=True)}

<h2 id="table">The whole vector</h2>
{table([th("Industry", sort="text"), th("Kind of investor", sort="text"), th("Weight is", sort="text"), th("$ million", "num", sort="num")],
       rows, caption="Millions of dollars in 2017. Click a heading to sort.")}
<p><a href="vector-z.csv">Download the vector as CSV</a> (sector codes in the first column).</p>
"""
    return page("z, the weight of each industry", "method.html", body, long_title=True)


def _need_heads() -> list[str]:
    return [th(f"<span>{e(v)}</span>", "grp", sort="num") for v in NEED_NAME.values()]


def _heat_cells(row, digits: int = 1) -> str:
    """One table cell for each need: cents of the need's dollar, shaded on a log scale from HEAT_FLOOR to a dollar."""
    out = []
    for x in row:
        if abs(x) < HEAT_FLOOR:
            out.append('<td class="h" data-v="0"></td>')
            continue
        shade = 0 if x < 0 else round(60 * min(1.0, math.log10(x / HEAT_FLOOR) / -math.log10(HEAT_FLOOR)))
        text = f"{x * 100:.{digits}f}".replace("-", "&minus;")
        out.append(f'<td class="h" style="--h:{shade}" data-v="{x * 100:.4g}">{text}</td>')
    return "".join(out)


def _account_crumbs() -> str:
    return '<p class="crumbs"><a href="method.html">Method</a> / <a href="method.html#account">The account in three lines</a></p>'


def basket_page(d: Data) -> str:
    """The page of d: what a dollar of each need buys."""
    t, (dn, _) = d.io.t, d.need_dollars
    needs = list(dn.columns)
    assert needs == list(NEED_NAME), needs
    basket = pd.read_csv(CONFIG / "basket.csv", dtype={"commodity": str}).set_index("commodity").need
    spent = A.need_demand(t)                       # $M by commodity and by every need in the config
    bought = t.F["F01000"] + t.F[A.GOV_CONSUMPTION].sum(axis=1)
    total = spent[needs].sum()
    margins = [c for c in dn.index if basket[c] == "margin"]
    def under(c):
        return "Margin, split" if basket[c] == "margin" else NEED_NAME.get(basket[c], LEFT_OUT_NAME.get(basket[c], basket[c]))
    # rows: the commodities bought for one of the needs, need by need and largest first, the margins last
    shown = dn[(dn != 0).any(axis=1)]
    place = {n: i for i, n in enumerate(needs)}
    order = sorted(shown.index, key=lambda c: (place.get(basket[c], len(needs)), -shown.loc[c].max()))
    rows = [f'<tr><th scope="row">{e(t.names[c])}</th><td class="name">{e(under(c))}</td>'
            f'<td class="num" data-v="{spent.loc[c, needs].sum():.0f}">{spent.loc[c, needs].sum():,.0f}</td>{_heat_cells(dn.loc[c])}</tr>'
            for c in order]
    foot = ('<tr><td>All commodities</td><td></td>' + f'<td class="num">{total.sum():,.0f}</td>'
            + "".join('<td class="num">100.0</td>' for _ in needs) + "</tr>")
    def biggest(n):
        return "; ".join(f"{e(t.names[c].lower())} ({v * 100:.0f}&cent;)" for c, v in dn[n].nlargest(3).items())
    nrows = [f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="num">{int((dn[n] != 0).sum())}</td>'
             f'<td class="num">{total[n] / 1e3:,.0f}</td><td class="wrap">{biggest(n)}</td></tr>' for n in needs]
    out = [n for n in spent.columns if n not in needs]
    orows = [f'<tr><th scope="row">{e(LEFT_OUT_NAME[n])}</th><td class="wrap dim">{e(d.needs_cfg.at[n, "description"].replace("; ", ", "))}</td>'
             f'<td class="num">{spent[n].sum() / 1e3:,.0f}</td></tr>'.replace(">-", ">&minus;") for n in out]
    y = f'<msub><mi>y</mi><mrow><mi>i</mi><mi>n</mi></mrow></msub>'
    body = f"""
{_account_crumbs()}
<h1 class="long">{_m(_vec("d", "d"))}, what a dollar of each need buys</h1>
<p class="lede">The basket. There is one {_m(_vec("d", "d"))} for each of the {len(needs)} needs: a dollar of that need, split
over the commodities households and governments bought for it in 2017.</p>
{_figures([("Size", f"{len(dn)} &times; {len(needs)}", "commodities by needs"),
           ("In a basket", f"{len(shown)}", f"of {len(dn)} commodities are bought for one of the needs"),
           ("Spending counted", _trillion(total.sum()), f"of {_trillion(bought.sum())} bought by households and governments"),
           ("Left out", f"{1 - total.sum() / bought.sum():.0%}", "of that spending is for none of the needs")])}

<h2 id="about">How it is derived</h2>
<p>It starts from what households and governments bought to use in 2017, on the final-demand side of the Bureau of
Economic Analysis's Use table: personal consumption (<code>F01000</code>) and government consumption
({", ".join(f"<code>{c}</code>" for c in A.GOV_CONSUMPTION)}). Investment is not in it, because equipment and buildings
are counted as inputs, through {_m(_sym("K"))}. Nor are exports.</p>
<p>Each commodity is counted under one need, or under none, by a list made by hand
(<a href="{REPO}/blob/main/config/basket.csv"><code>config/basket.csv</code></a>). Each need's column is then divided
by its total, so that it adds up to one dollar:</p>
{_m(f'{_sub("d", "in")}<mo>=</mo><mfrac>{y}<mrow>{_sum("m")}<msub><mi>y</mi><mrow><mi>m</mi><mi>n</mi></mrow></msub></mrow></mfrac>', block=True)}
<dl class="where">
<dt>{_m(y)}</dt><dd>what was spent on commodity <i>i</i> and counted under need <i>n</i>, in millions of dollars. For most
commodities that is all of the spending on it, under one need.</dd>
</dl>
<p>{len(margins)} commodities are trade and freight margins: what was paid to wholesalers, general stores and truckers
for getting goods to the buyer. They belong to no one need, so each is split over the needs in proportion to what
each need spent on goods (farm, mine and factory products).</p>
<p>Dividing by the total is what makes <a href="needs.html">every need count equally</a>: spending decides what is in a
need's dollar, not how much the need weighs.</p>
{table([th("Need"), th("Commodities", "num"), th("Spending, $ billion", "num"), th("The largest parts of its dollar")], nrows,
       caption="Each need's column: how many commodities are in it, the total it is divided by, and where most of the dollar goes.")}

<h2 id="left-out">What is left out</h2>
{table([th("Spending on"), th("What it covers"), th("$ billion", "num")], orows,
       caption="Household and government spending counted under none of the needs. It still counts wherever the needs buy from it.")}

<h2 id="table">The whole matrix</h2>
{table([th("Commodity", sort="text"), th("Counted under", sort="text"), th("Spending, $ million", "num", sort="num")] + _need_heads(),
       rows, attrs=" data-heatgrid", foot=foot,
       caption=f"Cents of each need's dollar. Each column adds up to 100. Click a heading to sort; sorting by a need shows its basket. "
               f"Entries under {HEAT_FLOOR * 100:.2f}&cent; are blank, and so are the {len(dn) - len(shown)} commodities in no basket, which are left out.")}
<p><a href="vector-d.csv">Download the matrix as CSV</a> ({len(dn)} rows, sector codes in the first column, dollars per dollar).</p>
<p>It is what {_m(_sym("A"))} is applied to, to get {_m(_vec("x", "d"))}, the output behind each need:</p>
{_m(_vec("x", "d") + "<mo>=</mo>" + _inv(f'<mrow><mo>(</mo>{_sym("I")}<mo>&minus;</mo>{_sym("A")}<mo>)</mo></mrow>') + "<mo>&#x2062;</mo>" + _vec("d", "d"), block=True)}
"""
    return page("d, what a dollar of each need buys", "method.html", body, long_title=True)


def requirements_page(d: Data) -> str:
    """The page of x: the output it takes to deliver a dollar of each need."""
    t, (dn, x) = d.io.t, d.need_dollars
    needs = list(x.columns)
    direct = pd.Series((d.io.A.values @ dn.values).sum(axis=0), index=needs)
    total = x.sum()
    shown = x[(x.abs() >= HEAT_FLOOR).any(axis=1)]
    mean = shown.mean(axis=1).sort_values(ascending=False)
    rows = [f'<tr><th scope="row">{e(t.names[c])}</th><td class="num" data-v="{mean[c] * 100:.4g}">{mean[c] * 100:.1f}</td>'
            f'{_heat_cells(shown.loc[c])}</tr>' for c in mean.index]
    foot = ('<tr><td>All commodities</td>' + f'<td class="num">{total.mean() * 100:.0f}</td>'
            + "".join(f'<td class="num">{v * 100:.0f}</td>' for v in total) + "</tr>")
    def dollars(v):
        return f"${v:.2f}"
    rrows = [f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="num">{dollars(dn[n].sum())}</td><td class="num">{dollars(direct[n])}</td>'
             f'<td class="num">{dollars(total[n] - dn[n].sum() - direct[n])}</td><td class="num" data-v="{total[n]:.4f}">{dollars(total[n])}</td></tr>'
             for n in needs]
    A_, I_ = _sym("A"), _sym("I")
    inverse = _inv(f"<mrow><mo>(</mo>{I_}<mo>&minus;</mo>{A_}<mo>)</mo></mrow>")
    least, most = total.idxmin(), total.idxmax()
    (top_c, top_n), top_v = shown.stack().idxmax(), shown.values.max()
    body = f"""
{_account_crumbs()}
<h1 class="long">{_m(_vec("x", "x"))}, the output behind each need</h1>
<p class="lede">Everything the economy must produce to deliver a dollar of a need: the dollar itself, the inputs to it,
the inputs to those, and the equipment and buildings used up along the way. There is one {_m(_vec("x", "x"))} for each need.</p>
{_figures([("Size", f"{len(x)} &times; {len(needs)}", "commodities by needs"),
           ("Output behind a dollar", f"${total.min():.2f} to ${total.max():.2f}", e(f"from {NEED_NAME[least].lower()} to {NEED_NAME[most].lower()}")),
           ("Commodities drawn on", f"{len(shown)}", f"of {len(x)} supply {HEAT_FLOOR * 100:.2f}&cent; or more to some need"),
           ("Largest entry", f"{top_v * 100:.0f}&cent;", e(f"{t.names[top_c]}, for {NEED_NAME[top_n]}".lower()))])}

<h2 id="about">How it is derived</h2>
<p>From {_m(_vec("d", "x"))}, what the need's dollar buys, and {_m(A_)}, what it takes to make a dollar of each thing:</p>
{_eqs([(_vec("x", "x"), f'{inverse}<mo>&#x2062;</mo>{_vec("d", "x")}'),
       ("", f'{_vec("d", "x")}<mo>+</mo>{A_}<mo>&#x2062;</mo>{_vec("d", "x")}<mo>+</mo><msup>{A_}<mn>2</mn></msup><mo>&#x2062;</mo>{_vec("d", "x")}<mo>+</mo><mo>&hellip;</mo>')])}
<p>The second line is the first written out round by round. The first term is the basket itself. The second is what
is used up in making it, {_m(A_)} applied once. The third is what is used up in making that, and so on. The inverse adds up
every round.</p>
{table([th("Need"), th("The dollar itself", "num"), th("Its direct inputs", "num"), th("Everything further back", "num"), th("All output", "num")], rrows,
       caption="Dollars of output, of all commodities together, behind one dollar of each need, by round.")}
<p>A column adds up to more than a dollar because output is counted every time something is sold on: the wheat, the flour
and the bread are each somebody's output. Counting equipment and buildings as inputs adds to it again.
<a href="method.html#requirements">Total requirements</a> on the method page has the formulas, and
<a href="sectors.html">the sector table</a> has more about each commodity.</p>

<h2 id="table">The whole matrix</h2>
{table([th("Commodity", sort="text"), th("Mean of the needs", "num", sort="num")] + _need_heads(), rows, attrs=" data-heatgrid", foot=foot,
       caption=f"Cents of each commodity's output behind a dollar of each need. Click a heading to sort; sorting by a need shows what it "
               f"draws on most. Entries under {HEAT_FLOOR * 100:.2f}&cent; are blank, and the {len(x) - len(shown)} commodities with no larger entry are left out.")}
<p><a href="vector-x.csv">Download the matrix as CSV</a> ({len(x)} rows, sector codes in the first column, dollars per dollar).</p>
<p class="note">{int((x.values < 0).sum())} entries are negative, all small: scrap and used goods, which a sector can sell more of than it buys.</p>
"""
    return page("x, the output behind each need", "method.html", body, long_title=True)


def value_added_page(d: Data) -> str:
    """The page of v: each sector's share of the value added behind a dollar of each need."""
    t, (_, x), v = d.io.t, d.need_dollars, d.need_value_added
    needs = list(v.columns)
    lam = A.value_added_share(d.io)
    behind = x.mul(lam, axis=0).sum()
    shown = v[(v.abs() >= HEAT_FLOOR).any(axis=1)]
    mean = shown.mean(axis=1).sort_values(ascending=False)
    rows = [f'<tr><th scope="row">{e(t.names[c])}</th><td class="num" data-v="{mean[c] * 100:.4g}">{mean[c] * 100:.1f}</td>'
            f'{_heat_cells(shown.loc[c])}</tr>' for c in mean.index]
    foot = ('<tr><td>All sectors</td><td class="num">100.0</td>' + "".join('<td class="num">100.0</td>' for _ in needs) + "</tr>")
    def biggest(n):
        return "; ".join(f"{e(t.names[c].lower())} ({s:.0%})" for c, s in v[n].nlargest(3).items())
    nrows = [f'<tr><th scope="row">{e(NEED_NAME[n])}</th><td class="num" data-v="{behind[n]:.4f}">${behind[n]:.2f}</td>'
             f'<td class="wrap">{biggest(n)}</td></tr>' for n in needs]
    lam_j, lam_m = '<msub><mi>&lambda;</mi><mi>j</mi></msub>', '<msub><mi>&lambda;</mi><mi>m</mi></msub>'
    (top_c, top_n), top_v = shown.stack().idxmax(), shown.values.max()
    body = f"""
{_account_crumbs()}
<h1 class="long">{_m(_vec("v", "v"))}, whose income a need dollar becomes</h1>
<p class="lede">The value added behind a dollar of a need, split over the sectors where it arises. There is one
{_m(_vec("v", "v"))} for each need, and it is how the need's dollar is handed to sectors.</p>
{_figures([("Size", f"{len(v)} &times; {len(needs)}", "sectors by needs"),
           ("Value added behind a dollar", f"${behind.min():.2f} to ${behind.max():.2f}", e(f"from {NEED_NAME[behind.idxmin()].lower()} to {NEED_NAME[behind.idxmax()].lower()}")),
           ("Sectors with a share", f"{len(shown)}", f"of {len(v)} have {HEAT_FLOOR:.2%} or more of some need"),
           ("Largest entry", f"{top_v:.0%}", e(f"{t.names[top_c]}, for {NEED_NAME[top_n]}".lower()))])}

<h2 id="about">How it is derived</h2>
<p>From {_m(_vec("x", "v"))}, the output behind the need's dollar. Each sector's output is turned into the value added in
it, and each need's column is divided by its total:</p>
{_m(f'{_sub("v", "jn")}<mo>=</mo><mfrac><mrow>{lam_j}<mo>&#x2062;</mo>{_sub("x", "jn")}</mrow><mrow>{_sum("m")}{lam_m}<mo>&#x2062;</mo>{_sub("x", "mn")}</mrow></mfrac>', block=True)}
<dl class="where">
<dt>{_m(lam_j)}</dt><dd>the value added in a dollar of commodity <i>j</i>'s output: the wages, taxes and operating surplus of
the industries that make it, per dollar they produce. Each industry's figure is the three value-added rows of the
Bureau of Economic Analysis's Use table over its output, and industries are mixed by {_m(_sym("D"))}, their shares of the
commodity.</dd>
</dl>
<p>Output counts a thing every time it is sold on; value added counts each sector's own contribution once. So this
is the step from what must be produced to who is paid for producing it.</p>
{table([th("Need"), th("Value added behind a dollar", "num"), th("The largest shares of it")], nrows,
       caption="The total each need's column is divided by, and the sectors that hold most of it.")}
<p>The total is more than a dollar because equipment and buildings are counted as inputs here, while the surplus that
pays for them is still part of each sector's value added. With capital left out of the inputs it comes to between
98 cents and a dollar. Dividing by the total sets this aside: {_m(_vec("v", "v"))} is each sector's share, and a column adds
up to one.</p>
<p>In the second line of the <a href="method.html#account">account</a>, {_m(_sub("v", "jn"))} is what sector <i>j</i> gets
of need <i>n</i>'s dollar, to be split among its occupations by {_m(_sym("W"))}.</p>

<h2 id="table">The whole matrix</h2>
{table([th("Sector", sort="text"), th("Mean of the needs", "num", sort="num")] + _need_heads(), rows, attrs=" data-heatgrid", foot=foot,
       caption=f"Percent of the value added behind a dollar of each need. Each column adds up to 100. Click a heading to sort. "
               f"Entries under {HEAT_FLOOR:.2%} are blank, and the {len(v) - len(shown)} sectors with no larger entry are left out.")}
<p><a href="vector-v.csv">Download the matrix as CSV</a> ({len(v)} rows, sector codes in the first column, shares of one).</p>
<p class="note">{int((v.values < 0).sum())} entries are negative, all small.</p>
"""
    return page("v, whose income a need dollar becomes", "method.html", body, long_title=True)


def matrix_a_page(d: Data) -> str:
    m, t, s = d.io, d.io.t, d.sheets["A"]
    A, K = s.values, s.second
    a, n, names = A.values, len(A), t.names
    shown = s.shown
    col_total = A.sum()
    over = col_total[col_total > 1]
    own = sum(t.V.at[c, c] for c in t.commodities if c in t.V.index) / t.V.values.sum()

    # A summed to groups
    G = MX.by_group(m.A, t.q) * 100
    gmax = G.values.max()
    def heat(v):
        mix = 60 * max(v, 0) / gmax
        text = f"{abs(v):.1f}" if round(v, 1) >= 0 else f"&minus;{-v:.1f}"
        return f'<td class="heat" style="background:color-mix(in srgb, var(--series) {mix:.0f}%, transparent)">{text}</td>'
    grows = [f'<tr><th scope="row">{e(g)}</th>{"".join(heat(v) for v in G.loc[g])}</tr>' for g in G.index]
    gfoot = '<tr><td>All inputs</td>' + "".join(f'<td class="num">{v:.1f}</td>' for v in G.sum()) + "</tr>"
    ghead = [th("Input, by group")] + [th(f"<span>{e(MX.SHORT[g])}</span>", "grp") for g in G.columns]

    # the largest entries
    top = A.stack().sort_values(ascending=False).head(MATRIX_TOP)
    def pick(c):
        return f'<a href="#sector" data-sector="{c}">{e(names[c])}</a>'
    trows = [f'<tr><td class="name">{pick(i)}</td><td class="name">{pick(j)}</td><td class="num">{v * 100:.1f}</td>'
             f'<td class="num">{K.at[i, j] * 100:.1f}</td></tr>' for (i, j), v in top.items()]
    (qi, qj), qv = next(iter(top.items()))

    A_, B_, D_, U_, K_, V_, I_ = (_sym(x, "A") for x in "ABDUKVI")
    series = (f'{_inv(f"<mrow><mo>(</mo>{I_}<mo>&minus;</mo>{A_}<mo>)</mo></mrow>")}<mo>=</mo>{I_}<mo>+</mo>{A_}<mo>+</mo>'
              f'<msup>{A_}<mn>2</mn></msup><mo>+</mo><msup>{A_}<mn>3</mn></msup><mo>+</mo><mo>&hellip;</mo>')
    derivation = _eqs([(B_, _b_from("A")), (D_, _d_from("A")), (A_, f'{B_}<mo>&#x2062;</mo>{D_}')])
    where = [
        (U_, f"the Use table: what each of {len(t.industries)} industries bought of each of {n} commodities in 2017, "
             f"{_trillion(t.U.values.sum())} in all. Imports are included."),
        (K_, f'the capital matrix: {_trillion(m.K.values.sum())} of equipment, buildings and software bought that year, placed on the '
             f'industries that use them. The Bureau of Economic Analysis does not publish who bought what at this level, so '
             f'<a href="method.html#capital">this is estimated</a>.'),
        (V_, "the Make table: how much of each commodity each industry made."),
        (f"<mi>{_bold('g')}</mi>", f"each industry's output, {_trillion(t.g.sum())} in all. Dividing by it turns purchases into purchases per dollar."),
        (f"<mi>{_bold('q')}</mi>", "the output of each commodity."),
        (B_, "what each industry buys per dollar of what it makes."),
        (D_, f"which industries make each commodity. An industry mostly makes the commodity it is named for "
             f"({own:.0%} of output), so {_m(D_)} is close to the identity."),
    ]
    why = f"""<template id="mx-why"><h3>How the cell is made up</h3>
<p>{_m(A_)} is {_m(B_)} times {_m(D_)}, so a cell is one row of {_m(B_)} against one column of {_m(D_)}. Each industry
that makes the column's commodity brings what it uses of the row's, in proportion to its share:</p>
{_m(f'{_sub("a", "ij")}<mo>=</mo>{_sum("k")}{_sub("b", "ik")}<mo>&#x2062;</mo>{_sub("d", "kj")}', block=True)}</template>
"""
    body = f"""
<p class="crumbs"><a href="method.html">Method</a> / <a href="method.html#account">The account in three lines</a></p>
<h1 class="long">{_m(A_)}, the direct requirements</h1>
<p class="lede">What it takes to make a dollar of each thing. The entry in row <i>i</i> and column <i>j</i> is the dollars of
commodity <i>i</i> used up in making one dollar of commodity <i>j</i>, with equipment and buildings counted as inputs.</p>
{_figures([("Size", f"{n} &times; {n}", "commodities by commodities"),
           ("Entries that are not zero", f"{(a != 0).mean():.0%}", f"{shown.mean():.0%} are a hundredth of a cent or more"),
           ("Inputs per dollar of output", f"{col_total.median() * 100:.0f}&cent;", "the median column total"),
           ("Equipment and buildings", f"{K.values.sum() / a.sum():.0%}", "of the total of all entries")])}

<h2 id="use">What it is for</h2>
<p>To deliver a dollar of something, the economy must make that dollar, then the inputs to it, then the inputs to
those, and so on. Each round is another multiplication by {_m(A_)}, and the rounds add up to the inverse in the
<a href="method.html#account">first line of the account</a>:</p>
{_m(series, block=True)}

<h2 id="derivation">How it is derived</h2>
<p>From the Bureau of Economic Analysis's 2017 benchmark tables and one matrix built here. Each matrix has a page of its
own: follow its letter.</p>
{derivation}
<dl class="where">{"".join(f"<dt>{_m(k)}</dt><dd>{v}</dd>" for k, v in where)}</dl>
<p>The Use table says what industries buy, but people need commodities, and some industries make more than one.
Multiplying by {_m(D_)} gives each commodity the recipe of the industries that make it, in proportion to how much of
it each makes.</p>
<p>Imports stay in {_m(U_)}, so a column is the recipe for the commodity wherever its inputs are made. The code is
<a href="{REPO}/blob/main/plenty/model.py"><code>plenty/model.py</code></a>.</p>

<h2 id="picture">The whole matrix</h2>
{sheet_picture(s, also="A marked cell is taken apart under the picture, into the industries that make the column's commodity.", extra=why)}

<h2 id="sector">One sector's column and row</h2>
<div class="controls"><label for="mx-pick">Sector</label><select id="mx-pick"></select></div>
<noscript><p class="note">This lookup needs JavaScript. The whole matrix is in <a href="{s.csv_file}">the CSV file</a>.</p></noscript>
<div class="mx-lookup">
<section><h3 id="mx-in-title">What a dollar of it uses</h3><div id="mx-in"></div></section>
<section><h3 id="mx-out-title">Who uses it</h3><div id="mx-out"></div></section>
</div>
<p class="note">A column's total is what a dollar of output spends on inputs, equipment and buildings. What is left is
wages, taxes, and whatever owners keep after investing.{f" {len(over)} column{'s' if len(over) > 1 else ''} totals more than a dollar: {e(names[over.index[0]].lower())}, which spent more than it sold." if len(over) else ""}</p>

<h2 id="groups">Summed to groups</h2>
{table(ghead, grows, attrs=' id="heat"', foot=gfoot,
       caption="Cents of each group's products used per dollar of each group's output. Read down a column for a group's recipe. "
               "The last group is bookkeeping rows in the Bureau's tables, not industries.")}

<h2 id="largest">The largest entries</h2>
{table([th("Input"), th("To make a dollar of"), th("&cent; per dollar", "num"), th("Of which equipment and buildings, &cent;", "num")], trows,
       caption="Most are a raw material going into the plant that processes it.")}
<p class="note">These are the Bureau's figures as published. The largest, {qv * 100:.0f} cents of {e(names[qi].lower())} per dollar
of {e(names[qj].lower())}, is in the Use table itself and looks like a quirk of how that industry's leases are recorded.</p>
<p class="note">{int((a < 0).sum())} entries are negative, nearly all in the rows for used goods and scrap, where an industry
sold more than it bought. They are small (the largest is {-a.min() * 100:.1f} cents) and blank in the picture.</p>
<p><a href="{s.csv_file}">Download the matrix as CSV</a> ({n} rows and columns, sector codes as headings).</p>
"""
    return page(s.title, "method.html", body, long_title=True, scripts=(s.data_file, "matrix.js"))


def account_section(d: Data) -> str:
    """The whole account as three equations, and which of their terms are known."""
    def row(lhs, rhs):
        return f'<mtr><mtd class="l">{lhs}</mtd><mtd><mo>=</mo></mtd><mtd class="r">{rhs}</mtd></mtr>'
    eq = _m('<mtable displaystyle="true" columnalign="right center left" columnspacing="0.3em" rowspacing="1.1em">'
            + row(_vec("x"),
                  f'<msup><mrow><mo>(</mo><mi>{_I}</mi><mo>&minus;</mo>{_A_LINK}<mo>)</mo></mrow><mrow><mo>&minus;</mo><mn>1</mn></mrow></msup>'
                  f'<mo>&#x2062;</mo>{_vec("d")}')
            + row(_sub("f", "a"),
                  f'<mfrac><mn>1</mn><mi>N</mi></mfrac><mo>&#x2062;</mo>{_sum("n")}{_sum("j")}{_elt("v", "jn", "v")}'
                  f'{_sum("o")}{_elt("w", "jo", "W")}<mo>&#x2062;</mo>{_sub("&theta;", "oa")}')
            + row("<mi>gap</mi>", f'{_sum("a")}{_sub("f", "a")}<mo>&#x2062;</mo>{_ONE_LESS_C}')
            + "</mtable>", block=True)
    where = [
        (_vec("d"), f"final demand for need {_m('<mi>n</mi>')}, scaled to one dollar: "
                     f'<a href="{SYMBOL_PAGES["d"]}">what each need\'s dollar buys</a>'),
        (_A_LINK, f'the input-output table, with capital counted as an input: <a href="{MATRIX_A}">the matrix and how it is derived</a>'),
        (_vec("x"), f'everything the economy must produce, directly and indirectly, to deliver that dollar: '
                     f'<a href="{SYMBOL_PAGES["x"]}">the output behind each need</a> '
                        '(<a href="#requirements">total requirements</a>)'),
        (_elt("v", "jn", "v"), f"sector {_m('<mi>j</mi>')}'s share of the value added in {_m(_vec('x'))}: "
                               f'<a href="{SYMBOL_PAGES["v"]}">whose income a need dollar becomes</a>'),
        (_elt("w", "jo", "W"), f"occupation {_m('<mi>o</mi>')}'s share of sector {_m('<mi>j</mi>')}'s wage bill: "
                               f'<a href="{SYMBOL_PAGES["W"]}">who does each sector\'s work</a>'),
        (_sub("&theta;", "oa"), f"the share of occupation {_m('<mi>o</mi>')}'s work that is activity {_m('<mi>a</mi>')}"),
        ("<mi>N</mi>", f"the number of needs, {len(NEED_NAME)}, each counted equally"),
        (_sub("f", "a"), f'the part of a need dollar that pays for activity {_m("<mi>a</mi>")} (<a href="#activities">how it is computed</a>)'),
        (_sub("c", "a"), f"the fraction of activity {_m('<mi>a</mi>')} that machines can do, ideally with open tools"),
    ]
    n_act = int((d.act.level == "intermediate").sum())
    return f"""<h2 id="account">The account in three lines</h2>
{eq}
<dl class="where">{"".join(f"<dt>{_m(k)}</dt><dd>{v}</dd>" for k, v in where)}</dl>
<p>The first two lines are computed. Together they place {d.act_acct.flowed * 100:.1f} cents of a need dollar on
{n_act} <a href="activities.html">activities</a>. The third line is the goal, and {_m(_sub("c", "a"))} is the unknown.</p>
<p>So far there are only proxies for {_m(_sub("c", "a"))}: the share of an activity's software tasks with a known open-source
tool, and the share of <a href="#ai">AI use</a> that falls on it. Neither is capability. Measuring {_m(_sub("c", "a"))} is what
open benchmarks are for, and {_m(_sub("f", "a") + "<mo>&#x2062;</mo>" + _ONE_LESS_C)} ranks where to build them first.</p>
<p class="note">{_m(_sub("f", "a"))} is where today's money goes, not how much an activity matters, so the gap is measured
in today's prices.</p>
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

{account_section(d)}
<h2>Steps</h2>
<h3>Tables</h3>
<p>The U.S. Bureau of Economic Analysis 2017 benchmark Make and Use tables: 402 industries by 402 commodities,
after redefinitions, in producer prices.</p>
<h3 id="capital">Capital as an input</h3>
<p>A standard input-output table treats equipment and buildings as final demand, so a tractor is not an input to
farming. Here, investment is routed back to the industries that use it. Capital goods with an evident user go to that
user (farm machinery to farms, medical equipment to health care, turbines to electric utilities). The rest is spread
in proportion to each industry's gross operating surplus.</p>
{table([th("Kind of sector"), th("Without capital, &cent;", "num"), th("With capital, &cent;", "num"), th("Change", "num")], arows,
       caption="Output required per dollar of basket. Machines only show up once capital counts as an input.")}
<h3 id="requirements">Total requirements</h3>
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
    pages[MATRIX_A] = matrix_a_page
    for key in MATRIX_PAGES.replace("A", ""):
        pages[f"matrix-{key}.html"] = lambda d, key=key: matrix_page(d, key)
    pages[SYMBOL_PAGES["F"]], pages[SYMBOL_PAGES["z"]] = investment_page, weights_page
    pages[SYMBOL_PAGES["v"]] = value_added_page
    pages[SYMBOL_PAGES["d"]], pages[SYMBOL_PAGES["x"]] = basket_page, requirements_page
    for name, fn in pages.items():
        (SITE / name).write_text(fn(d), encoding="utf-8")
    for key, sheet in d.sheets.items():
        (SITE / sheet.data_file).write_text(matrix_data(d, key), encoding="utf-8")
        (SITE / sheet.csv_file).write_text(sheet_csv(sheet), encoding="utf-8")
    (SITE / MATRIX_PARTS).write_text(matrix_a_parts(d), encoding="utf-8")
    (SITE / "matrix-F.csv").write_text(d.capital.investment.to_csv(float_format="%.6g"), encoding="utf-8")
    (SITE / "vector-z.csv").write_text(d.capital.weight.rename("weight").to_csv(float_format="%.6g"), encoding="utf-8")
    for letter, frame in zip("dxv", (*d.need_dollars, d.need_value_added)):
        (SITE / f"vector-{letter}.csv").write_text(frame.to_csv(float_format="%.6g"), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

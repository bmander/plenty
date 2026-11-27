"""Render the static site (site/) from the model, config/ and results/.

    python scripts/03_run.py     # refresh results/ first if config/ changed
    python -m plenty.site

The site is the account: five equations on the home page, and a page for every matrix and
vector they are made from, down to the published tables. Assets in plenty/web/ are copied as
they are. Everything is plain HTML with relative links, so the site works from any path (GitHub
Pages serves it under /plenty/).
"""
from __future__ import annotations
import functools
from dataclasses import dataclass
import html
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis as A, flows as FL, matrix as MX, model as M, occupations as O, work as WK

ROOT = Path(__file__).resolve().parent.parent
RESULTS, WEB, SITE = ROOT / "results", ROOT / "plenty" / "web", ROOT / "site"
REPO = "https://github.com/bmander/plenty"

NEED_NAME = {
    "food": "Food", "clothing": "Clothing", "shelter": "Shelter", "energy": "Energy",
    "water_sanitation": "Water and sanitation", "health": "Health", "education": "Education",
    "mobility": "Mobility", "communication": "Communication", "safety": "Safety",
    "meaning": "Meaning and recreation",
}

e = html.escape


# ---------------------------------------------------------------- data

class Data:
    def __init__(self):
        # The work that has to get done (plenty/work.py): O*NET work activities at three levels, the
        # flow through each, and how much of the software listed by the people who do each is open.
        self.act = pd.read_csv(RESULTS / "activity_flow.csv", index_col=0).fillna({"parent": ""})
        self.act_acct = pd.read_csv(RESULTS / "activity_flow_accounting.csv", index_col=0).value
        # The taxonomy of software capabilities (taxonomy/build.py): domains, capabilities and their tasks
        self.tax = pd.read_csv(FL.TAXONOMY / "capabilities.csv", dtype=str).fillna("").astype({"level": int})
        self.cap_acct = pd.read_csv(RESULTS / "capability_flow_accounting.csv", index_col=0).flow
        # Which work software could do at all: each activity is information work, or needs a body, or
        # is work in which the person is the point. Judgment, made by hand.
        self.kinds = pd.read_csv(M.CONFIG / "activity_kinds.csv", index_col=0).kind
        # Households (data/households): how people spend their time, and what households at each level of income spend
        households = M.ROOT / "data" / "households"
        self.time_use = pd.read_csv(households / "time_use_2017.csv").drop_duplicates("activity", keep=False).set_index("activity").hours_per_day
        self.spending = pd.read_csv(households / "spending_quintiles_2017.csv").set_index("item")

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
    def survey(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """(E, M, T, industries), with P = T (E o M) / 1e6. E and M are the survey's employment and
        mean annual wage (dollars), surveyed industry x occupation, NaN where nothing is published.
        T is sector x surveyed industry: one where the industry covers the sector. industries has
        each surveyed industry's title and group, in the order the pages show them."""
        P, info, _, survey = self.wage_bill
        o = O.oews()
        det = o[o.O_GROUP.str.lower() == "detailed"]
        def group(code):                                # the survey files government under 999
            return "Government" if code.startswith("99") else MX.groups([code])[code]
        ind = pd.DataFrame({"title": survey.title, "group": [group(c) for c in survey.index]})
        ind = ind.loc[sorted(ind.index, key=lambda c: (MX.ORDER.index(ind.group[c]), c))]
        E, wage = (det.pivot(index="NAICS", columns="OCC_CODE", values=x).reindex(index=ind.index, columns=P.columns)
                   for x in ("emp", "wage"))
        T = pd.DataFrame(0.0, index=P.index, columns=ind.index)
        for c, covered_by in info.oews_industries.items():
            if covered_by:
                T.loc[c, covered_by.split(";")] = 1.0
        return E, wage, T, ind

    @functools.cached_property
    def wages(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """(W, info, occupations): each sector's wage bill as shares over occupations. A row sums to
        one, or to nothing where the sector is not measured."""
        bill, info, occ, _ = self.wage_bill
        return bill.div(bill.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0), info, occ

    @functools.cached_property
    def theta(self) -> pd.DataFrame:
        """Theta: occupation x intermediate work activity, the share of the occupation's work that is
        the activity, for the occupations the wage survey publishes. A row sums to one, or to
        nothing where no task of the occupation is rated. With it the flow to activities is one
        product: the needs' mean v, times W, times Theta."""
        tasks = WK.occupation_activity_shares(WK.task_activity_shares(WK.tasks()))
        by_detailed = O._occupation_uses(self.wages[0].columns, tasks, "mean").fillna(0.0)
        iwa = WK.hierarchy().iwa.reindex(by_detailed.columns)
        return by_detailed.T.groupby(iwa.values).sum().T.sort_index(axis=1)

    @functools.cached_property
    def phi(self) -> pd.DataFrame:
        """Phi: occupation x software capability, the share of the occupation's work done with the
        capability, for the occupations the wage survey publishes: the share of the software
        products it lists that are of the capability, split by how specific each capability is to
        the occupation (flows.occupation_shares, distinctive). A row sums to the share of the
        occupation's products the taxonomy places, at most one. With it the flow to capabilities
        is one product: the needs' mean v, times W, times Phi."""
        caps = FL.capabilities()
        shares = FL.occupation_shares(FL.listings(), FL.product_capabilities(), caps, distinctive=True)
        return O._occupation_uses(self.wages[0].columns, shares, "mean").fillna(0.0)[caps]

    @functools.cached_property
    def weights(self) -> pd.DataFrame:
        """omega: need x way of weighing the needs, each column summing to one: every need the same;
        by what households and governments spent on each; and by what the poorest fifth of households
        spent on each themselves (config/spending_needs.csv says which item of spending is which need)."""
        needs = list(self.need_dollars[0].columns)
        spent = A.need_demand(self.io.t)[needs].sum()
        placed = pd.read_csv(M.CONFIG / "spending_needs.csv")
        poorest = self.spending.lowest.astype(float)[placed["item"]].groupby(placed.need.values).sum().reindex(needs).fillna(0.0)
        return pd.DataFrame({"equal": 1 / len(needs), "spending": spent / spent.sum(), "poorest": poorest / poorest.sum()}, index=needs)

    @functools.cached_property
    def unpaid(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(G, detail). G is the unpaid work done at home for every dollar spent on the needs, occupation
        x work activity: each kind of household work is filed under the work activity it is and the
        occupation that does it for pay (config/unpaid_work.csv), and is worth its hours a day for each
        adult, times the adults there are, times that occupation's mean wage. detail has each kind's
        hours and its value in dollars a year."""
        E, wage, _, _ = self.survey
        jobs = E.fillna(0.0).where(wage.notna(), 0.0)
        hourly = (jobs * wage.fillna(0.0)).sum() / jobs.sum() / HOURS_A_YEAR      # an occupation's mean wage, wherever it is published
        s = self.spending["all"].astype(float)
        adults = s["Number of consumer units (in thousands)"] * 1e3 * (s["People"] - s["Children under 18"])
        work = pd.read_csv(M.CONFIG / "unpaid_work.csv")
        hours = self.time_use[work.activity].values
        detail = work.assign(hours_per_day=hours, usd=hours * 365 * adults * hourly[work.occupation].values)
        needs = list(self.need_dollars[0].columns)
        spent = A.need_demand(self.io.t)[needs].values.sum() * 1e6
        G = detail.groupby(["occupation", "work_activity"]).usd.sum().unstack(fill_value=0.0) / spent
        return G.reindex(index=self.wages[0].columns, columns=self.theta.columns, fill_value=0.0), detail

    @functools.cached_property
    def defined_share(self) -> pd.Series:
        """a: of each capability's tasks with no known open tool, the share that is well defined: the
        taxonomy says whether a task's result could be scored by a benchmark (yes counts whole,
        partly half). Nothing where every task has a tool."""
        tasks = self.tax[self.tax.level == 2]
        closed = tasks[tasks.open_tools == ""]
        score = closed.benchmarkable.map(DEFINED)
        return score.groupby(closed.parent).mean().reindex(self.phi.columns).fillna(0.0)

    @functools.cached_property
    def open_share(self) -> pd.Series:
        """c: the share of each capability's tasks for which the taxonomy names an open-source tool."""
        tasks = self.tax[self.tax.level == 2]
        return (tasks.open_tools != "").groupby(tasks.parent).mean().reindex(self.phi.columns)

    @functools.cached_property
    def capital(self) -> M.Capital:
        """How investment is placed on industries: what the capital matrix is made from."""
        return M.capital_allocation(self.io.t)

    @functools.cached_property
    def sheets(self) -> dict:
        """The model's matrices that have a page, by letter."""
        return sheets(self)

    @functools.cached_property
    def units(self) -> dict:
        """What the terms count and measure in, each with a page, by the name it is filed under."""
        return units(self)


# ---------------------------------------------------------------- pieces

def page(title: str, body: str, home: bool = False, scripts: tuple[str, ...] = ()) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e("Plenty" if home else f"{title} | Plenty")}</title>
<meta name="description" content="A material balance for the machines behind human needs: a dollar of each need, traced through the economy to the work it pays for.">
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="sheet">
<header class="masthead">
<a class="wordmark" href="index.html">Plenty</a>
<nav aria-label="Sections"><a href="index.html"{' aria-current="page"' if home else ""}>The account</a><a href="index.html#terms">Every term</a><a href="index.html#units">Every unit</a></nav>
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



# ---------------------------------------------------------------- the account and its terms
# The account is five equations. Every matrix and vector in them, and every one those are made
# from, down to the published tables, is a term with a page of its own: what its rows, columns and
# entries are, where it comes from, what it is made from and what it goes into, and a picture of
# the whole of it (web/matrix.js).

def _m(body: str, block: bool = False) -> str:
    """MathML, which browsers render natively: the site loads nothing from elsewhere."""
    return f'<div class="eq"><math display="block">{body}</math></div>' if block else f"<math>{body}</math>"


def _sub(a: str, b: str) -> str:
    """a with subscript b; each letter of b is its own identifier, so that it is set in italic."""
    return f"<msub><mi>{a}</mi><mrow>{''.join(f'<mi>{c}</mi>' for c in b)}</mrow></msub>"


def _sum(i: str) -> str:
    return f"<munder><mo>&sum;</mo><mi>{i}</mi></munder>"


HOME = "index.html"                   # the account, which every term's page leads back to
THETA, PHI, OMEGA = "Θ", "Φ", "ω"
GREEK = {THETA: ("Theta", "&#x1D6AF;"), PHI: ("Phi", "&#x1D6BD;"), OMEGA: ("omega", "&#x1D6DA;")}   # a Greek letter's name in a file, and its bold
HOURS_A_YEAR = 2080                   # a year of full-time work, which turns a yearly wage into an hourly one
# the terms, in the order the account's table lists them
GROUPS = [
    ("The account", ["x", "p", "k", "o"]),
    ("Needs", ["d", "Y", OMEGA]),
    ("The input-output model", ["L", "A", "B", "D", "U", "V", "g", "q"]),
    ("Capital", ["K", "F", "H", "S", "z"]),
    ("Value added", ["v", "r", "y"]),
    ("Work", ["W", "P", "T", "E", "M"]),
    ("Software capabilities", [PHI, "a", "c"]),
    ("Work activities", ["f", THETA, "G", "s", "b"]),
]
TERMS = [k for _, keys in GROUPS for k in keys]
DEFINED = {"yes": 1.0, "partly": 0.5, "no": 0.0}     # how far a task the taxonomy calls benchmarkable counts as well defined
PER_NEED = "dxv"                      # the vectors there is one of for each need, written with a subscript n
# what each computed term is made from; a term that is not here is data
USES = {"x": ["L", "d"], "p": [OMEGA, "v", "W"], "k": ["p", THETA, "G", "s", PHI], "o": ["k", "a", "c"], "b": ["f", "s"],
        "f": ["p", THETA, "G"], "G": ["E", "M", "Y"], "d": ["Y"], "L": ["A"], "A": ["B", "D"], "B": ["U", "K", "g"],
        "D": ["V", "q"], "g": ["V"], "q": ["V"], "K": ["F", "H", "S"], "S": ["z", "H"], "z": ["g", "H"],
        "v": ["r", "x"], "r": ["y", "g", "D"], "W": ["P"], "P": ["T", "E", "M"]}


def stem(key: str) -> str:
    """The name a term's files go by. A matrix is filed as a matrix and a vector as a vector, so
    that no two differ by a letter's case alone: some file systems cannot tell D from d."""
    return f"matrix-{GREEK[key][0]}" if key in GREEK else f"matrix-{key}" if key.isupper() else f"vector-{key}"


SYMBOL_PAGES = {k: stem(k) + ".html" for k in TERMS}
# short labels for the major groups of occupations, by the first two digits of the code
SOC_SHORT = {"11": "Management", "13": "Business, finance", "15": "Computing, math", "17": "Engineering", "19": "Science",
             "21": "Social service", "23": "Legal", "25": "Education", "27": "Arts, media", "29": "Health practitioners",
             "31": "Health support", "33": "Protective", "35": "Food service", "37": "Cleaning, grounds",
             "39": "Personal care", "41": "Sales", "43": "Office support", "45": "Farming", "47": "Construction, extraction",
             "49": "Repair", "51": "Production", "53": "Transport, moving"}
INVESTOR_NAME = {"private": "Private business", "residential": "Housing", "fed_defense": "Federal defense",
                 "fed_nondefense": "Federal nondefense", "state_local": "State and local government"}
MATRIX_PARTS = "matrix-A-parts.js"   # B and D, fetched when a cell of A is first marked
MATRIX_PART_CUT = 1e-5     # entries of B under a thousandth of a cent are left out of that file
MATRIX_WIDTH, MATRIX_HEIGHT = 802, 780   # the most a picture takes of the page, in CSS pixels
# A matrix at least this many times as tall as it is wide is drawn with its columns locked in view,
# each this wide at most (a lone column wider), in a picture of a fixed height.
THIN, THIN_COLUMN, THIN_VECTOR, THIN_HEIGHT = 8, 110, 170, 620
# How each kind of matrix is filed and shown: the unit of its data file, the smallest entry kept in
# it (smaller ones are blank in the picture), the two ends of the colour scale and their legend,
# what a blank cell is said to hold, what colour stands for, and how a cell's printed value is described.
MATRIX_KINDS = {
    "per_dollar": {"unit": 1e-5, "cut": 1e-4, "scale": (1e-4, 1.0), "ticks": ("0.01&cent;", "0.1&cent;", "1&cent;", "10&cent;", "$1"),
                   "blank": "under 0.01¢ per dollar", "small": "under a hundredth of a cent", "colour": "cents per dollar",
                   "in_cell": "in cents"},
    "share": {"unit": 1e-5, "cut": 1e-4, "scale": (1e-4, 1.0), "ticks": ("0.01%", "0.1%", "1%", "10%", "100%"),
              "blank": "under 0.01%", "small": "under a hundredth of a percent", "colour": "the share", "in_cell": "in percent"},
    "dollars": {"unit": 1.0, "cut": 0.5, "scale": (1.0, 1e6), "ticks": ("$1M", "$10M", "$100M", "$1B", "$10B", "$100B", "$1T"),
                "blank": "under $0.5 million", "small": "under half a million dollars", "colour": "millions of dollars",
                "in_cell": "in millions of dollars, with k for thousands"},
    "people": {"unit": 1.0, "cut": 0.5, "scale": (10.0, 1e7), "ticks": ("10", "100", "1k", "10k", "100k", "1M", "10M"),
               "blank": "none published", "small": "not published", "colour": "the number of jobs",
               "in_cell": "in jobs, with k for thousands"},
    # a wage's scale is narrow, so its ticks are doublings; wages beyond either end take the end's colour
    "wage": {"unit": 1.0, "cut": 0.5, "scale": (25e3, 2e5), "ticks": ("$25k", "$50k", "$100k", "$200k"),
             "blank": "none published", "small": "not published", "colour": "the mean annual wage, from $25,000 to $200,000",
             "in_cell": "in thousands of dollars a year"},
    # ones and zeros: no scale to show
    "mark": {"unit": 1.0, "cut": 0.5, "scale": (0.1, 1.0), "ticks": (), "blank": "no", "small": "", "colour": "", "in_cell": "as a 1"},
}
MATRIX_UNIT = MATRIX_KINDS["per_dollar"]["unit"]


# --- writing the terms. Bold letters are Unicode's mathematical bold: browsers do not all honour
# mathvariant. A term is a link to its page, except on that page; HTML is allowed inside a MathML
# identifier, and a subscript or a transpose on a linked letter is set as HTML inside the link,
# because browsers misplace a MathML script on a base that is a link.

def _bold(letter: str) -> str:
    """A capital or small Latin letter, or a capital Greek one, as Unicode's mathematical bold."""
    if letter in GREEK:
        return GREEK[letter][1]
    return f"&#x{0x1D400 + ord(letter) - ord('A') if letter.isupper() else 0x1D41A + ord(letter) - ord('a'):X};"


_TR = '<mi mathvariant="normal">T</mi>'      # the mark of a transpose
_ONES = "<mn>&#x1D7CF;</mn>"                  # a column of ones: a matrix times it is the matrix's row totals
_TIMES = "<mo>&#x2062;</mo>"                  # a product, written as nothing
_HADAMARD = "<mo>&#x2218;</mo>"               # entry by entry


def _sym(letter: str, here: str = "", T: bool = False) -> str:
    """A matrix or vector by its letter, transposed if T."""
    if letter in SYMBOL_PAGES and letter != here:
        return f'<mi><a href="{SYMBOL_PAGES[letter]}">{_bold(letter)}{"<sup>T</sup>" if T else ""}</a></mi>'
    return f"<msup><mi>{_bold(letter)}</mi>{_TR}</msup>" if T else f"<mi>{_bold(letter)}</mi>"


def _vec(letter: str, here: str = "", sub: str = "n", T: bool = False) -> str:
    """A vector there is one of for each need (or whatever sub counts), transposed if T."""
    if letter in SYMBOL_PAGES and letter != here:
        script = sub if sub.isdigit() else f"<i>{sub}</i>"
        return (f'<mi><a href="{SYMBOL_PAGES[letter]}">{_bold(letter)}<sub>{script}</sub>{"<sup>T</sup>" if T else ""}</a></mi>')
    script = "".join(f"<mn>{c}</mn>" if c.isdigit() else f"<mi>{c}</mi>" for c in sub)
    base = f"<mi>{_bold(letter)}</mi><mrow>{script}</mrow>"
    return f"<msubsup>{base}{_TR}</msubsup>" if T else f"<msub>{base}</msub>"


def _term(key: str, here: str = "") -> str:
    """A term as the account writes it: with a subscript n if there is one of it for each need."""
    return _vec(key, here) if key in PER_NEED else _sym(key, here)


def _elt(shown: str, sub: str, page: str = "", here: str = "") -> str:
    """One entry of a matrix or vector: an italic letter with subscripts, linked to the page of the
    term it is an entry of (page, a key of SYMBOL_PAGES) except on that page."""
    if not page or page == here:
        return _sub(shown, sub)
    italic = f"&#x{0x1D44E + ord(shown) - ord('a'):X};"
    return f'<mi><a href="{SYMBOL_PAGES[page]}">{italic}<sub><i>{sub}</i></sub></a></mi>'


def _paren(body: str) -> str:
    return f"<mrow><mo>(</mo>{body}<mo>)</mo></mrow>"


def _diag(body: str) -> str:
    """A vector written as a diagonal matrix."""
    return f'<mrow><mspace width="0.17em"/><mi>diag</mi><mo>&#x2061;</mo><mo>(</mo>{body}<mo>)</mo></mrow>'


def _inv(base: str) -> str:
    return f"<msup>{base}<mrow><mo>&minus;</mo><mn>1</mn></mrow></msup>"


def _inverse(here: str = "") -> str:
    """(I - A)^-1, the total requirements, which have a page of their own under the letter L. A is
    a link to A's page, and a link cannot hold another, so the rest of the expression, its brackets,
    its I and its exponent, are each a link to L's page. They are set as text because an operator
    with a link inside it loses its spacing."""
    A_ = _sym("A", here)
    if here == "L":
        return _inv(_paren(f'{_sym("I")}<mo>&minus;</mo>{A_}'))
    def to(text, cls="inv"):
        return f'<a href="{SYMBOL_PAGES["L"]}" class="{cls}">{text}</a>'
    return (f'<msup><mrow><mtext>{to("(", "inv br")}</mtext><mi>{to(_bold("I"))}</mi><mo>&minus;</mo>{A_}<mtext>{to(")", "inv br")}</mtext></mrow>'
            f'<mtext>{to("&minus;1")}</mtext></msup>')


def _eqs(rows: list[tuple[str, str]]) -> str:
    """Equations set one to a line and aligned at the equals sign."""
    return _m('<mtable displaystyle="true" columnalign="right center left" columnspacing="0.3em" rowspacing="1.1em">'
              + "".join(f'<mtr><mtd class="l">{a}</mtd><mtd><mo>=</mo></mtd><mtd class="r">{b}</mtd></mtr>' for a, b in rows)
              + "</mtable>", block=True)


def equation(key: str, here: str = "") -> tuple[str, str]:
    """The two sides of the equation that defines a computed term (or the gap), as MathML. Every
    term in it is a link to its page, except the one whose page this is."""
    def S(k, T=False):
        return _sym(k, here, T)
    def V(k, T=False):
        return _vec(k, here, T=T)
    if key == "x":
        return V("x"), _inverse(here) + _TIMES + V("d")
    if key == "p":        # a need dollar by occupation, however the needs are weighed
        weight = (_sub("&omega;", "n") if here == OMEGA else
                  f'<mi><a href="{SYMBOL_PAGES[OMEGA]}">&#x1D714;<sub><i>n</i></sub></a></mi>')
        return S("p", T=True), f'{_sum("n")}{weight}{_TIMES}{V("v", T=True)}{_TIMES}{S("W")}'
    if key == "f":        # the same dollar by what the work is, with the unpaid work done at home
        return S("f", T=True), f'{S("p", T=True)}{_TIMES}{S(THETA)}<mo>+</mo><msup>{_ONES}{_TR}</msup>{_TIMES}{S("G")}'
    if key == "k":        # and the information work in it, paid and unpaid, by the software it is done with
        work = f'{S("p")}{_HADAMARD}{S(THETA)}{_TIMES}{S("s")}<mo>+</mo>{S("G")}{_TIMES}{S("s")}'
        return S("k", T=True), f'<msup>{_paren(work)}{_TR}</msup>{_TIMES}{S(PHI)}'
    if key == "o":        # entry by entry: what is paid for work with a capability, that is well defined, and is not open
        return S("o"), f'{S("k")}{_HADAMARD}{S("a")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("c")}")}'
    if key == "b":        # what software could not do: the work that needs a body or a person
        return S("b"), f'{S("f")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("s")}")}'
    if key == "gap":      # and the whole of it
        return "<mi>gap</mi>", f'<msup>{_ONES}{_TR}</msup>{_TIMES}{S("o")}'
    if key == "d":        # the matrix whose columns are the d of each need
        first, last = _vec("d", here, sub="1"), _vec("d", here, sub="N")
        return (f"<mrow><mo>[</mo>{first}<mspace width=\"0.3em\"/><mo>&#x22EF;</mo><mspace width=\"0.3em\"/>{last}<mo>]</mo></mrow>",
                f'{S("Y")}{_TIMES}{_inv(_diag(S("Y", T=True) + _TIMES + _ONES))}')
    if key == "L":
        return S("L"), _inv(_paren(f'{_sym("I")}<mo>&minus;</mo>{S("A")}'))
    if key == "A":
        return S("A"), f'{S("B")}{_TIMES}{S("D")}'
    if key == "B":
        return S("B"), f'{_paren(S("U") + "<mo>+</mo>" + S("K"))}{_TIMES}{_inv(_diag(S("g")))}'
    if key == "D":
        return S("D"), f'{S("V")}{_TIMES}{_inv(_diag(S("q")))}'
    if key == "g":
        return S("g"), f'{S("V")}{_TIMES}{_ONES}'
    if key == "q":
        return S("q"), f'{S("V", T=True)}{_TIMES}{_ONES}'
    if key == "K":
        return S("K"), f'{_paren(S("F") + _TIMES + S("H", T=True))}{_HADAMARD}{S("S")}'
    if key == "S":
        among = f'<munder><mo>&sum;</mo><mrow><mi>m</mi><mo>&isin;</mo>{_sub("&Omega;", "ik")}</mrow></munder>'
        return _elt("s", "ik", "S", here), f'<mfrac>{_elt("z", "k", "z", here)}<mrow>{among}{_elt("z", "m", "z", here)}</mrow></mfrac>'
    if key == "v":
        return V("v"), (f'<mfrac><mrow>{_diag(S("r"))}{_TIMES}{V("x")}</mrow>'
                        f'<mrow>{S("r", T=True)}{_TIMES}{V("x")}</mrow></mfrac>')
    if key == "r":
        return S("r", T=True), f'{S("y", T=True)}{_TIMES}{_inv(_diag(S("g")))}{_TIMES}{S("D")}'
    if key == "W":
        return S("W"), f'{_inv(_diag(S("P") + _TIMES + _ONES))}{_TIMES}{S("P")}'
    if key == "P":
        return S("P"), f'{S("T")}{_TIMES}{_paren(S("E") + _HADAMARD + S("M"))}'
    raise KeyError(key)


EQUATIONS = ["x", "p", "k", "o", "f", "b", "d", "L", "A", "B", "D", "g", "q", "K", "S", "v", "r", "W", "P"]   # the terms equation() defines

# What one entry of each term is measured in, in a few words. A unit that has a page is written
# [as it reads here|the name its page is filed under], and is a link wherever this is set as HTML.
_WORK = "[work dollars|work-dollar] per [need dollar|need-dollar]"
_MILLIONS, _MARK = "[millions of dollars|million-dollars], in 2017", "[one or zero|one-or-zero]"
MEASURED_IN = {
    "x": "[commodity dollars|commodity-dollar] produced per [need dollar|need-dollar]",
    "p": _WORK, "k": _WORK, "o": _WORK, "f": _WORK, "b": _WORK, "G": _WORK,
    "d": "[commodity dollars|commodity-dollar] bought per [need dollar|need-dollar]",
    "Y": _MILLIONS, "U": _MILLIONS, "V": _MILLIONS, "g": _MILLIONS, "q": _MILLIONS, "K": _MILLIONS, "F": _MILLIONS,
    "z": _MILLIONS, "y": _MILLIONS,
    OMEGA: "the need's weight, a [share|share] of one",
    "L": "[commodity dollars|commodity-dollar] produced per commodity dollar delivered",
    "A": "[commodity dollars|commodity-dollar] of the input per commodity dollar of the output",
    "B": "[commodity dollars|commodity-dollar] of the input per dollar of the industry's output",
    "D": "the industry's [share|share] of the commodity's output",
    "H": _MARK, "T": _MARK, "s": _MARK,
    "S": "[share|share] of the purchases of the capital good by investors of one kind",
    "v": "the sector's [share|share] of the [value-added dollars|value-added-dollar] behind the need",
    "r": "[value-added dollars|value-added-dollar] per [commodity dollar|commodity-dollar] produced",
    "W": "the occupation's [share|share] of the sector's wage bill",
    "P": "[millions of dollars|million-dollars] a year, at the wages of May 2021",
    "E": "[jobs|job], in May 2021",
    "M": "[dollars a year|dollar-a-year], in May 2021",
    PHI: "[share|share] of the occupation's work",
    THETA: "[share|share] of the occupation's work",
    "a": "[share|share] of the capability's tasks that have no open tool",
    "c": "[share|share] of the capability's tasks",
}
_UNIT_LINK = re.compile(r"\[([^|\]]+)\|([a-z-]+)\]")


def _file(path: str) -> str:
    """A link to a file of the repository, by its path."""
    kind = "tree" if path.endswith("/") else "blob"
    return f'<a href="{REPO}/{kind}/main/{path}"><code>{path}</code></a>'


@dataclass
class Sheet:
    """One term of the account, arranged for a page of its own: its matrix with rows and columns in
    the page's order, what they and its entries are, where it comes from, and the words its picture
    uses for a row, a column and a cell."""
    key: str                       # its letter
    name: str                      # after the letter in the page's title
    kind: str                      # a key of MATRIX_KINDS
    values: pd.DataFrame
    row_names: pd.Series
    col_names: pd.Series
    rows: str                      # what the rows are, after their number: "input commodities", or "needs: a dollar of each"
    cols: str                      # and the columns; for a single column, what it holds
    entries: str                   # what an entry is, with its unit
    row_tip: str                   # before a row's name, and a column's, in a cell's hover tip
    col_tip: str
    axis: str                      # over the picture: what the columns are
    source: str = ""               # for a term that is data: where it comes from
    note: str = ""                 # what a reader must know to read it right
    code: str = ""                 # the file that reads or computes it
    row_is: str = ""               # under the picture, for what is marked; made from the tips if left empty
    col_is: str = ""
    second: pd.DataFrame | None = None     # the part of each entry that is equipment and buildings
    exact: bool = False            # entries are whole units, so a blank cell holds nothing at all
    col_groups: pd.Series | None = None    # column -> group, where the columns are not sectors
    row_groups: pd.Series | None = None    # and the same for rows
    blanks: tuple[str, str] | None = None  # what a blank cell holds, as a hover tip says it and as the caption does
    marked: str = ""               # for a matrix of ones and zeros: what a one says
    sums: str = ""                 # which totals mean something and are shown beside the picture: "both", "cols" or ""
    short: dict | None = None      # short labels for those groups
    order: str = "Sectors are in the Bureau's order within fifteen groups."

    @property
    def href(self) -> str: return f"{stem(self.key)}.html"
    @property
    def data_file(self) -> str: return f"{stem(self.key)}-data.js"
    @property
    def csv_file(self) -> str: return f"{stem(self.key)}.csv"
    @property
    def title(self) -> str: return f"{self.key}, {self.name}"
    @property
    def thin(self) -> bool:
        """Tall and narrow: drawn with its columns locked in view."""
        return self.values.shape[0] >= THIN * self.values.shape[1]
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
    """Every term, by letter. Commodities and industries are each put in groups."""
    m, t, cap = d.io, d.io.t, d.capital
    com, ind = MX.ordered(t.commodities), MX.ordered(t.industries)
    purchases, capital, D = MX.factors(m)
    A_, A_capital = matrix_a(d)
    P, _, occ, _ = d.wage_bill
    E, wage, T, surveyed = d.survey
    dn, xn = d.need_dollars
    needs = list(dn.columns)
    act = d.act[d.act.level == "intermediate"].loc[d.theta.columns]

    bea = ("U.S. Bureau of Economic Analysis, 2017 benchmark input-output accounts, at the detail level, after "
           f"redefinitions, in producer prices: {_file('data/bea/')}.")
    oews = ("U.S. Bureau of Labor Statistics, Occupational Employment and Wage Statistics, May 2021, national estimates "
            f"by four-digit industry: {_file('data/occupations/')}.")
    model, occupations = "plenty/model.py", "plenty/occupations.py"
    occupation_order = "occupations in the order of the Standard Occupational Classification within its 22 major groups"
    by_occupation = dict(col_groups=occ.major, short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
                         order=f"Sectors are in the Bureau's order within fifteen groups, and {occupation_order}.")
    by_occupation_only = dict(by_occupation, order=f"Surveyed industries are in code order within fifteen groups, and {occupation_order}.")
    not_published = ("none published", "not published, because nobody was counted there or the figure is withheld,")
    by_need = dict(col_names=pd.Series(NEED_NAME)[needs], col_groups=pd.Series("Needs", index=needs), col_is="Column, the need:")
    by_investor = dict(col_names=pd.Series(INVESTOR_NAME)[list(cap.investment.columns)],
                       col_groups=pd.Series("Kinds of investor", index=cap.investment.columns),
                       col_is="Column, the kind of investor:")
    by_activity = dict(row_names=act.name, row_groups=act.parent.map(d.act.name))
    activity_order = "Activities are in O*NET's order within its 41 general work activities."
    def lone(s: pd.Series, key: str, label: str, unit: str = "$ million") -> dict:
        """A vector as a matrix of one column, with its unit over it."""
        return dict(values=s.to_frame(key), col_names=pd.Series({key: label}), col_groups=pd.Series({key: unit}),
                    cols=label[0].lower() + label[1:], col_tip="Entry", col_is="Column:", axis=label)
    investors = pd.DataFrame({h: (cap.group == h).astype(float) for h in cap.investment.columns})
    # software capabilities, in the taxonomy's order within its domains
    caps = list(d.phi.columns)
    tax = d.tax.set_index("id")
    domain = tax.name[tax.parent[caps]].set_axis(caps)
    by_capability = dict(row_names=tax.name[caps], row_groups=domain, short={tax.name[k]: k.capitalize() for k in tax.index[tax.level == 0]})
    capability_order = f"Capabilities are in the taxonomy's order within its {domain.nunique()} domains."
    info = (d.kinds.reindex(act.index) == "information").astype(float)        # s
    # the three ways of weighing the needs, which every term from p on has a column for
    weights, (unpaid, unpaid_detail) = d.weights, d.unpaid
    ways = pd.Series({"equal": "Needs counted equally", "spending": "By spending on each", "poorest": "By the poorest fifth's budget"})
    by_weighing = dict(col_names=ways, col_groups=pd.Series("Ways of weighing the needs", index=ways.index), col_tip="Needs weighed",
                       col_is="Column, the way the needs are weighed:", cols="ways of weighing the needs", axis="Ways of weighing the needs")
    by_occupation_row = dict(row_names=occ.title, row_groups=occ.major, short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
                             order=f"Occupations are in {occupation_order[len('occupations in '):]}.")
    def frame(values, index) -> pd.DataFrame:
        return pd.DataFrame(values, index=index, columns=weights.columns)
    paid = d.wages[0].loc[com].values.T @ (d.need_value_added.loc[com].values @ weights.values)
    by_occ = frame(paid, occ.index)                                                         # p
    to_activity = frame(d.theta.values.T @ by_occ.values, act.index).add(unpaid.sum(), axis=0)      # f
    information = by_occ.mul(d.theta.values @ info.values, axis=0).add(unpaid.values @ info.values, axis=0)
    flow = frame(d.phi.values.T @ information.values, caps)                                 # k
    overhang = flow.mul(d.defined_share * (1 - d.open_share), axis=0)                       # o
    out = [
        # --- the account
        Sheet("x", "the output behind a dollar of each need", "per_dollar", xn.loc[com], t.names,
              rows="produced commodities", cols="needs: a dollar of each", **by_need,
              entries="Dollars of the commodity produced, at every stage of supply, to deliver a dollar of the need.",
              row_tip="Produced", col_tip="For a dollar of", row_is="Row, the commodity produced:", axis="Needs: one dollar of each",
              code="plenty/analysis.py", sums="cols"),
        Sheet("p", "the occupations a need dollar pays", "per_dollar", by_occ, **by_occupation_row, **by_weighing,
              rows="occupations",
              entries="Dollars per need dollar that the sectors behind the needs pay the occupation.",
              note="What a sector pays is its whole value added, shared out the way its payroll is.",
              row_tip="Occupation", code="plenty/site.py", sums="cols"),
        Sheet("k", "the part of a need dollar that pays for work done with each capability", "per_dollar", flow,
              **by_capability, **by_weighing, rows="software capabilities: the taxonomy's",
              entries="Dollars per need dollar that pay for the information work of the people who work with the capability, "
                      "with the unpaid information work done at home. It is the work the software serves, not what the software "
                      "earns.",
              note="Only information work is placed here. Work that needs a body or a person is not, and nor is the work of "
                   "occupations that list no software, or software the taxonomy does not place.",
              row_tip="Capability", code="plenty/flows.py", sums="cols", order=capability_order),
        Sheet("o", "the overhang of each capability", "per_dollar", overhang,
              **by_capability, **by_weighing, rows="software capabilities: the taxonomy's",
              entries="Dollars per need dollar: what is paid for information work done with the capability, times the share of "
                      "its tasks that have no known open tool, times the share of those that is well defined.",
              note="A column adds up to the gap. Sorted, it is the order to work in, as far as the terms it is made from can be "
                   "trusted.",
              row_tip="Capability", code="plenty/site.py", sums="cols", order=capability_order),
        # --- needs
        Sheet("d", "the commodities a dollar of each need buys", "per_dollar", dn.loc[com], t.names,
              rows="purchased commodities", cols="needs: a dollar of each", **by_need,
              entries="The part of a dollar of the need that is spent on the commodity. A column adds up to one dollar.",
              row_tip="Bought", col_tip="With a dollar of", row_is="Row, the commodity bought:", axis="Needs: one dollar of each",
              code="plenty/analysis.py"),
        Sheet("Y", "spending on each need", "dollars", A.need_demand(t)[needs].loc[com], t.names,
              rows="purchased commodities", cols="needs: the purpose of the purchase", **by_need,
              entries="Millions of dollars bought by households and governments in 2017 and counted under the need.",
              source=f"{bea} It is the Use table's columns for personal consumption (<code>F01000</code>) and government "
                     f"consumption ({', '.join(f'<code>{c}</code>' for c in A.GOV_CONSUMPTION)}). Each commodity is counted under "
                     f"one need, or under none, by a list made by hand, {_file('config/basket.csv')}. Trade and freight margins "
                     "are split over the needs in proportion to what each spent on goods.",
              note="Investment and exports are not in it. Equipment and buildings are counted as inputs instead, through "
                   f"{_m(_sym('K'))}.",
              row_tip="Bought", col_tip="For", row_is="Row, the commodity bought:", axis="Needs: spending on each",
              code="plenty/analysis.py", sums="both"),
        Sheet(OMEGA, "the weights of the needs", "share", weights, pd.Series(NEED_NAME)[needs], **by_weighing,
              rows="needs", row_groups=pd.Series("Needs", index=needs),
              entries="The weight of the need. A column adds up to one.",
              source=f"Counted equally, each of the {len(needs)} needs weighs the same. By what is spent, a need weighs its share "
                     f"of {_m(_sym('Y'))}. The poorest fifth's budget is what the fifth of households with the lowest incomes "
                     f"spent on each need themselves, from the Consumer Expenditure Survey of the U.S. Bureau of Labor Statistics, "
                     f"2017: {_file('data/households/')}. Which item of spending belongs to which need is judgment: "
                     f"{_file('config/spending_needs.csv')}.",
              note="The survey counts what households pay themselves. Safety, which governments pay for, has no weight in that "
                   "column, and public schooling and public health insurance are missing from it.",
              row_tip="Need", code="plenty/site.py", order="Needs are in the order the list of them has."),
        # --- the input-output model
        Sheet("L", "the total requirements", "per_dollar", m.L.loc[com, com], t.names, t.names,
              rows="produced commodities", cols="delivered commodities",
              entries="Dollars of the row's commodity produced, at every stage of supply, to deliver a dollar of the column's.",
              note="Imports are counted as if made the way the United States makes them.",
              row_tip="Produced", col_tip="To deliver", row_is="Row, the commodity produced:", col_is="Column, the commodity delivered:",
              axis="Delivered: one dollar of each commodity", code=model, sums="cols"),
        Sheet("A", "the direct requirements", "per_dollar", A_, t.names, t.names,
              rows="input commodities", cols="output commodities",
              entries="Dollars of the input used, directly, per dollar of the thing made, equipment and buildings included.",
              row_tip="Input", col_tip="To make", col_is="Column, the thing made:",
              axis="Made: one dollar of each commodity", code=model, second=A_capital, sums="cols"),
        Sheet("B", "the inputs of each industry per dollar of its output", "per_dollar", (purchases + capital).loc[com, ind], t.names, t.ind_names,
              rows="input commodities", cols="using industries",
              entries="Dollars of the commodity used per dollar of the industry's output, equipment and buildings included.",
              row_tip="Input", col_tip="Used by", col_is="Column, the industry using it:",
              axis="Industries: per dollar of their output", code=model, second=capital.loc[com, ind], sums="cols"),
        Sheet("D", "the industries that make each commodity", "share", D.loc[ind, com], t.ind_names, t.names,
              rows="producing industries", cols="produced commodities",
              entries="The industry's share of the commodity's output. A column adds up to one.",
              row_tip="Industry", col_tip="Its share of", col_is="Column, the commodity made:",
              axis="Commodities: the makers of each", code=model),
        Sheet("U", "the Use table", "dollars", t.U.loc[com, ind], t.names, t.ind_names,
              rows="purchased commodities", cols="purchasing industries",
              entries="Millions of dollars of the commodity bought by the industry as an input in 2017.",
              source=f"{bea} It is the Use table without its columns of final demand and its rows of value added.",
              row_tip="Bought", col_tip="By", row_is="Row, the commodity bought:", col_is="Column, the industry buying:",
              axis="Industries buying", code=model, exact=True, sums="both"),
        Sheet("V", "the Make table", "dollars", t.V.loc[ind, com], t.ind_names, t.names,
              rows="producing industries", cols="produced commodities",
              entries="Millions of dollars of the commodity made by the industry in 2017.",
              source=f"{bea} It is the Make table.",
              row_tip="Industry", col_tip="Made", col_is="Column, the commodity made:",
              axis="Commodities made", code=model, exact=True, sums="both"),
        Sheet("g", "each industry's output", "dollars", **lone(t.g.loc[ind], "g", "Output in 2017"), row_names=t.ind_names,
              rows="industries", entries="Millions of dollars of everything the industry made in 2017: its row of the Make table, added up.",
              row_tip="Industry", code=model, exact=True, sums="both"),
        Sheet("q", "each commodity's output", "dollars", **lone(t.q.loc[com], "q", "Output in 2017"), row_names=t.names,
              rows="commodities", entries="Millions of dollars of the commodity made in 2017 by every industry: its column of the Make "
                                          "table, added up.",
              row_tip="Commodity", code=model, exact=True, sums="both"),
        # --- capital
        Sheet("K", "the capital matrix", "dollars", m.K.loc[com, ind], t.names, t.ind_names,
              rows="commodities: the capital good", cols="industries: the users of the capital good",
              entries="Millions of dollars of the capital good bought as investment in 2017 and placed on the industry.",
              note="It is an estimate. The Bureau publishes investment by commodity and by kind of investor, not by the industry "
                   "that bought it.",
              row_tip="Capital good", col_tip="Placed on", col_is="Column, the industry it is placed on:",
              axis="Industries using the capital", code=model, sums="both"),
        Sheet("F", "investment purchases", "dollars", cap.investment.loc[com], t.names,
              rows="commodities: the capital good", cols="kinds of investor", **by_investor,
              entries="Millions of dollars of the commodity bought as investment in 2017 by investors of the kind. A negative "
                      "entry is a sale of used equipment or scrap.",
              source=f"{bea} It is the Use table's columns for investment, added up by kind of investor: "
                     + "; ".join(f"{INVESTOR_NAME[h].lower()} ({', '.join(f'<code>{c}</code>' for c in cols)})"
                                 for h, cols in M.CAPITAL_COLUMNS.items()) + ".",
              row_tip="Capital good", col_tip="Bought by", axis="Kinds of investor", code=model, sums="both"),
        Sheet("H", "the kind of investor each industry is", "mark", investors.loc[ind], t.ind_names,
              rows="industries", cols="kinds of investor", **by_investor,
              entries="One where the industry is of the kind, and zero elsewhere. Every industry is of one kind.",
              source=f"Lists in {_file(model)}: housing, federal defense, federal nondefense, and state and local government "
                     "are named there, and every other industry is private business.",
              row_tip="Industry", col_tip="Kind of investor", axis="Kinds of investor", code=model,
              blanks=("is not of this kind", "zero"), marked="is of this kind", sums="cols"),
        Sheet("S", "the placement of each capital good", "share", cap.shares.loc[com, ind], t.names, t.ind_names,
              rows="commodities: the capital good", cols="industries: the users of the capital good",
              entries="The share of the purchases of the capital good, by investors of the industry's kind, that is placed on the "
                      "industry. Within one kind of investor a row adds up to one.",
              source=f"{_m(_sub('&Omega;', 'ik'))} is the set of industries that could have bought capital good <i>i</i>, among "
                     f"those of the same kind of investor as <i>k</i>: the ones a pairing names for it, or all of that kind if none "
                     f"does. The {sum(1 for x in cap.steps if x['note'])} pairings of a capital good with its evident users are "
                     f"judgment, kept in {_file('config/capital_allocation.csv')}.",
              row_tip="Capital good", col_tip="Share placed on", col_is="Column, the industry it is placed on:",
              axis="Industries: their share of each capital good", code=model),
        Sheet("z", "the weights that share investment among industries", "dollars", **lone(cap.weight.loc[ind], "z", "Weight"), row_names=t.ind_names,
              rows="industries",
              entries="Millions of dollars: the industry's gross operating surplus if it is private business or housing, and its "
                      "output if it is government.",
              source=f"{bea} Gross operating surplus is the Use table's row <code>V00300</code>, with a negative surplus counted "
                     "as none.",
              row_tip="Industry", code=model),
        # --- value added
        Sheet("v", "the value added behind a dollar of each need", "share", d.need_value_added.loc[com], t.names,
              rows="commodities: the sector that earns the income", cols="needs: a dollar of each", **by_need,
              entries="The sector's share of the value added behind a dollar of the need. A column adds up to one.",
              row_tip="Sector", col_tip="Share of a dollar of", axis="Needs: one dollar of each", code="plenty/analysis.py"),
        Sheet("r", "value added per dollar of each commodity", "per_dollar",
              **lone(A.value_added_share(m).loc[com], "r", "Value added per dollar", "per dollar"), row_names=t.names,
              rows="commodities", entries="Dollars of value added per dollar of the commodity's output: its makers' value added per "
                                          "dollar, mixed by their shares of it.",
              row_tip="Commodity", code="plenty/analysis.py"),
        Sheet("y", "each industry's value added", "dollars", **lone(t.VA.sum(axis=0).loc[ind], "y", "Value added in 2017"),
              row_names=t.ind_names, rows="industries",
              entries="Millions of dollars of value added in 2017: what the industry paid its employees, taxes on production "
                      "less subsidies, and its gross operating surplus.",
              source=f"{bea} It is the Use table's three rows of value added "
                     f"({', '.join(f'<code>{c}</code>' for c in M.VA_ROWS)}), added up.",
              row_tip="Industry", code=model, sums="both"),
        # --- work
        Sheet("W", "the occupations that do each sector's work", "share", d.wages[0].loc[com], t.names, occ.title,
              rows="commodities: the sector", cols="occupations",
              entries="The occupation's share of the sector's wage bill. A row adds up to one, or is empty where the sector is "
                      "not measured.",
              row_tip="Sector", col_tip="Share of its wage bill paid to", col_is="Column, the occupation:",
              axis="Occupations: their share of each sector's wage bill", code=occupations, **by_occupation),
        Sheet("P", "the pay of each occupation in each sector", "dollars", P.loc[com], t.names, occ.title,
              rows="commodities: the sector", cols="occupations",
              entries="Millions of dollars paid to the occupation in a year by the surveyed industries that cover the sector.",
              note="Jobs times the mean wage, in the cells where the survey publishes both.",
              row_tip="Sector", col_tip="Paid to", col_is="Column, the occupation:",
              axis="Occupations: their pay in each sector", code=occupations, **by_occupation, sums="both"),
        Sheet("T", "the surveyed industries that cover each sector", "mark", T.loc[com], t.names, surveyed.title,
              rows="commodities: the sector", cols="surveyed industries",
              entries="One where the surveyed industry covers the sector, and zero elsewhere.",
              source=f"The Bureau of Economic Analysis's concordance of its sectors with the industry classification the survey "
                     f"uses, in {_file('data/occupations/')}, and in {_file(occupations)} the stand-ins for what the survey "
                     "files elsewhere or leaves out: public schools and hospitals, other government, and farms. Housing and the "
                     "accounting sectors are covered by nothing.",
              row_tip="Sector", col_tip="Surveyed industry", axis="Surveyed industries", code=occupations,
              col_groups=surveyed.group, blanks=("does not cover it", "zero"), marked="covers it",
              order="Sectors and surveyed industries are each in code order within the same fifteen groups.", sums="both"),
        Sheet("E", "jobs in each occupation", "people", E.fillna(0.0), surveyed.title, occ.title,
              rows="surveyed industries", cols="occupations", entries="Jobs in the occupation in the industry, in May 2021.",
              source=oews,
              note="It counts wage and salary jobs at nonfarm employers, not people: someone with two jobs is in it twice, and the "
                   "self-employed are not in it.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: the jobs of each industry in them",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only, sums="both"),
        Sheet("M", "the wage of each occupation", "wage", wage.fillna(0.0), surveyed.title, occ.title,
              rows="surveyed industries", cols="occupations",
              entries="The mean annual wage of the occupation in the industry, in dollars, in May 2021.",
              source=oews, note="A wage of $208,000 or more is recorded as $208,000.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: their mean annual wage in each industry",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only),
        # --- software capabilities
        Sheet(PHI, "the software each occupation works with", "share", d.phi, occ.title, tax.name[caps],
              rows="occupations", cols="software capabilities: the taxonomy's",
              entries="The share of the occupation's work that is done with the capability. A row adds up to the share of the "
                      "occupation's software the taxonomy places, at most one.",
              source=f"O*NET 31.0, the U.S. Department of Labor's database of occupations, lists the software products each "
                     f"occupation uses: {_file('data/occupations/')}. The taxonomy places each product in the capabilities it is an "
                     f"example of: {_file('taxonomy/')}. An occupation's work is split among its capabilities in proportion to the "
                     "products it lists in each, times how few other occupations list anything there, so that tools everyone "
                     "uses take less. An occupation the survey publishes only as a group takes the mean of the occupations in "
                     "the group.",
              note="A list of products is not time: O*NET says which software an occupation uses, not for how long.",
              row_tip="Occupation", col_tip="Capability", axis="Software capabilities: their share of each occupation's work",
              code="plenty/flows.py", row_groups=occ.major, col_groups=domain,
              short={**{g: SOC_SHORT[c[:2]] for c, g in occ.major.items()}, **by_capability["short"]},
              order=f"Occupations are in the order of the Standard Occupational Classification within its 22 major groups. {capability_order}"),
        Sheet("a", "the well-defined share of the tasks with no open tool", "share",
              **lone(d.defined_share, "a", "Well defined", "share"), **by_capability,
              rows="software capabilities: the taxonomy's",
              entries="Of the capability's tasks with no known open tool, the share whose result could be scored by a benchmark. "
                      "A task that could partly be scored counts half. Zero where every task has a tool.",
              source=f"The taxonomy says of each task whether it is benchmarkable: {_file('taxonomy/capabilities.csv')}.",
              note="This is the taxonomy's own judgment of each task, made when it was compiled.",
              row_tip="Capability", code="taxonomy/build.py", order=capability_order),
        Sheet("c", "the open share of each capability", "share",
              **lone(d.open_share, "c", "Tasks with an open tool", "share"), **by_capability,
              rows="software capabilities: the taxonomy's",
              entries="The share of the capability's tasks for which an open-source tool is known.",
              source=f"The taxonomy names the open tools known for each of its {int((d.tax.level == 2).sum()):,} tasks: "
                     f"{_file('taxonomy/capabilities.csv')}.",
              note="The tools were named from memory when the taxonomy was compiled. An entry says a tool exists, not that it is "
                   "good enough to do the work.",
              row_tip="Capability", code="taxonomy/build.py", order=capability_order),
        # --- work activities: the same dollar, placed on what the work is
        Sheet("f", "the part of a need dollar that pays for each activity", "per_dollar", to_activity, **by_activity, **by_weighing,
              rows="work activities: O*NET's intermediate work activities",
              entries="Dollars per need dollar, paid and unpaid, that go to the activity. It is where today's work goes, not how "
                      "much an activity matters.",
              note="The rest of the dollar is in sectors the survey of occupations does not reach, and in occupations whose tasks "
                   "are not rated.",
              row_tip="Activity", code="plenty/flows.py", sums="cols", order=activity_order),
        Sheet(THETA, "the activities that make up each occupation's work", "share", d.theta, occ.title, act.name,
              rows="occupations", cols="work activities: O*NET's intermediate work activities",
              entries="The share of the occupation's work that is the activity. A row adds up to one, or is empty where no task of "
                      "the occupation is rated.",
              source=f"O*NET 31.0, the U.S. Department of Labor's database of occupations: {_file('data/occupations/')}. Each task of "
                     "an occupation counts by its rated importance times the share of people in the occupation who do it, and is "
                     "divided among the activities O*NET files it under. An occupation the survey publishes only as a group "
                     "takes the mean of the occupations in the group.",
              note="Importance is not time: O*NET does not record the hours a task takes.",
              row_tip="Occupation", col_tip="Activity", axis="Work activities: their share of each occupation's work",
              code="plenty/work.py", row_groups=occ.major, col_groups=act.parent.map(d.act.name),
              short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
              order=f"Occupations are in the order of the Standard Occupational Classification within its 22 major groups. {activity_order}"),
        Sheet("G", "the unpaid work done at home", "per_dollar", unpaid, occ.title, act.name,
              rows="occupations: the one that does such work for pay", cols="work activities: the kind of work",
              entries="Dollars of unpaid work at home for every dollar spent on the needs, valued at the mean wage of the "
                      "occupation that does such work for pay.",
              source=f"The hours are from the American Time Use Survey of the U.S. Bureau of Labor Statistics, 2017, and the number "
                     f"of adults from its Consumer Expenditure Survey: {_file('data/households/')}. An occupation's wage is its "
                     f"mean over the industries that publish it. Which activities at home are work, which work activity each is, "
                     f"and which occupation does it for pay, is judgment: {_file('config/unpaid_work.csv')}.",
              note=f"It comes to {unpaid.values.sum() * 100:.0f} cents for every dollar spent on the needs: "
                   f"{unpaid_detail.hours_per_day.sum():.1f} hours a day for each adult, ${unpaid_detail.usd.sum() / 1e12:.1f} trillion "
                   "a year. Housework, cooking, shopping, care and the travel they take are counted. Commuting, other travel, "
                   "study and volunteering are not. It is the same however the needs are weighed.",
              row_tip="Occupation", col_tip="Activity", axis="Work activities", code="plenty/site.py",
              row_groups=occ.major, col_groups=act.parent.map(d.act.name), short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
              sums="both", order=f"Occupations are in {occupation_order[len('occupations in '):]}. {activity_order}"),
        Sheet("s", "the activities that are information work", "mark", **lone(info, "s", "Information work", "one or zero"), **by_activity,
              rows="work activities: O*NET's intermediate work activities",
              entries="One where the activity is information work, which software could do, and zero where it needs a body or is "
                      "work in which the person is the point.",
              source=f"Judgment, made by hand, one activity at a time: {_file('config/activity_kinds.csv')}.",
              row_tip="Activity", code="plenty/site.py", blanks=("needs a body or a person", "zero"), marked="is information work",
              order=activity_order),
        Sheet("b", "the part of a need dollar that pays for work that needs a body", "per_dollar",
              to_activity.mul(1 - info, axis=0), **by_activity, **by_weighing,
              rows="work activities: O*NET's intermediate work activities",
              entries="Dollars per need dollar, paid and unpaid, that go to the activity, where it needs a body or a person. No "
                      "software capability reaches it without a machine to act through.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
    ]
    assert [s.key for s in out] == TERMS, "the terms and their pages have fallen out of step"
    return {s.key: s for s in out}


def sheet_data(s: Sheet, **extra) -> str:
    """A term page's data file: what the picture needs to name rows, columns and cells, and
    every entry of at least the kind's cut, by column, as (row, value) in the kind's unit, or
    (row, value, capital part) for a matrix that has one."""
    kind = MATRIX_KINDS[s.kind]
    v, w, keep = s.values.values, s.second.values if s.second is not None else None, s.shown
    def units(x):
        return int(round(x / kind["unit"]))
    cells = [[x for i in np.flatnonzero(keep[:, j]) for x in ((i, units(v[i, j])) if w is None else (i, units(v[i, j]), units(w[i, j])))]
             for j in range(v.shape[1])]
    def side(codes, names, things, groups=None):
        g = MX.groups(codes) if groups is None else groups
        return {"codes": list(codes), "names": [names[c] for c in codes], "groups": [g[c] for c in codes],
                "things": things.split(":")[0].split(",")[0]}
    payload = {"key": s.key, "kind": s.kind, "unit": kind["unit"], "cut": kind["cut"], "scale": kind["scale"],
               "blank": s.blanks[0] if s.blanks else "nothing" if s.exact else kind["blank"], "marked": s.marked,
               "short": {**MX.SHORT, **(s.short or {})}, "lock": s.thin,
               "rows": side(s.values.index, s.row_names, s.rows, s.row_groups),
               "cols": side(s.values.columns, s.col_names, s.cols if s.values.shape[1] > 1 else "column", s.col_groups),
               "rowTip": s.row_tip, "colTip": s.col_tip, "rowIs": s.row_is or f"Row, the {s.row_tip.lower()}:",
               "colIs": s.col_is or f"Column, the {s.col_tip.lower()}:",
               "second": w is not None, "cells": [[int(x) for x in col] for col in cells], **sheet_sums(s), **extra}
    return "window.PLENTY_MATRIX = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def sheet_sums(s: Sheet) -> dict:
    """The totals a picture shows in its margins, of the whole matrix and not only of what is filed:
    each column's, and for a matrix whose rows add up to something each row's and the whole."""
    def six(x):
        return float(f"{x:.6g}")
    out = {}
    if s.sums:
        out["colSums"] = [six(x) for x in s.values.values.sum(axis=0)]
    if s.sums == "both":
        out["rowSums"] = [six(x) for x in s.values.values.sum(axis=1)]
        out["grand"] = six(s.values.values.sum())
    return out


def matrix_data(d: Data, key: str) -> str:
    """The data file of one term's page. A's also says where to find what its cells' derivation needs."""
    s = d.sheets[key]
    return sheet_data(s, parts=MATRIX_PARTS) if key == "A" else sheet_data(s)


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
    """The picture of a term with its margins, buttons and legend, drawn by web/matrix.js.
    also: a sentence about this picture alone; extra: markup the script uses."""
    kind, (nr, nc) = MATRIX_KINDS[s.kind], s.values.shape
    blank = s.blanks[1] if s.blanks else "zero" if s.exact else f"zero or {kind['small']}"
    if s.thin:          # its columns always all in view, in a picture of a fixed shape
        width = min(MATRIX_WIDTH, nc * (THIN_VECTOR if nc == 1 else THIN_COLUMN))
        shape = f"{width} / {THIN_HEIGHT}"
    else:               # square cells, in a picture of the matrix's shape; a tall matrix is drawn narrower, to stay on the screen
        width = min(MATRIX_WIDTH, round(MATRIX_HEIGHT * nc / nr))
        shape = f"{nc} / {nr}"
    # totals in the margins: rows down the right, columns along the bottom, the whole matrix in the corner
    both = s.sums == "both"
    row_head = '\n<div class="mx-sumhead" aria-hidden="true">Row totals</div>' if both else ""
    row_sums = '\n<div class="mx-sums mx-rowsums"><canvas id="mx-row-sums" aria-hidden="true"></canvas></div>' if both else ""
    col_sums = ('\n<div class="mx-sumfoot" aria-hidden="true">Column totals</div>'
                '\n<div class="mx-sums mx-colsums"><canvas id="mx-col-sums" aria-hidden="true"></canvas></div>'
                + ('\n<div class="mx-corner" id="mx-total"></div>' if both else "")) if s.sums else ""
    summed = {"both": " The bars along the right and the bottom are the totals of each row and column, and the figure in the "
                      "corner is the total of the whole matrix. The longest bar is the largest total in view.",
              "cols": " The bars along the bottom are the totals of each column. The longest bar is the largest total in view.",
              "": ""}[s.sums]
    moving = ("Zooming changes how many rows are in view; the columns are always all there. To move, drag with the mouse "
              "wheel pressed or with Ctrl held, or with a finger on a touch screen." if s.thin else
              "To move, drag with the mouse wheel pressed or with Ctrl held, or with a finger on a touch screen. The picture "
              "can be moved past the matrix's edge, far enough to bring a cell at the edge to the middle.")
    legend = (f'<div class="mx-legend" aria-hidden="true"><div class="mx-ramp"></div>\n<div class="mx-ticks">'
              + "".join(f"<span>{x}</span>" for x in kind["ticks"]) + "</div></div>") if kind["ticks"] else ""
    colour = f"Colour is {kind['colour']}, on a log scale." if kind["colour"] else f"A filled cell is a one: the row {s.marked}."
    return f"""<figure class="mx">
<div class="mx-frame{" mx-lock" if s.thin else ""}" style="grid-template-columns: auto minmax(0, {width + 2}px) auto">
<div class="mx-axis mx-axis-top"><span>{e(s.axis)} &rarr;</span>
<span class="mx-zoom"><button type="button" id="mx-zoom-out" aria-label="Zoom out" disabled>&minus;</button><button
 type="button" id="mx-zoom-in" aria-label="Zoom in">+</button><button type="button" id="mx-zoom-all" disabled>Whole matrix</button><button
 type="button" id="mx-unsort" disabled>Default order</button></span></div>
<div class="mx-strip mx-top" id="mx-top"></div>{row_head}
<div class="mx-strip mx-left" id="mx-left"></div>
<div class="mx-plot" style="aspect-ratio: {shape}">
<canvas id="mx-canvas" width="{nc}" height="{nr}" role="img" tabindex="0"
 aria-label="Heat map of the {nr} by {nc} matrix {s.key}, {e(s.name)}. The CSV file gives the same figures."></canvas>
<i id="mx-h" aria-hidden="true"></i><i id="mx-v" aria-hidden="true"></i>
</div>{row_sums}{col_sums}
</div>
<div class="mx-note" id="mx-note" aria-live="polite"></div>
{extra}{legend}
<figcaption>{colour} The {(~s.shown).mean():.0%} of entries that are {blank} are blank. {s.order}</figcaption>
</figure>
<details class="note mx-how"><summary>Using the picture</summary>
<p>Hover over a cell for its row, its column and its value. Click a cell to mark it with its row and column, or click
in a margin to mark one row or one column.{" " + also if also else ""}{summed} To zoom, scroll or pinch over the picture
or its margins, or use the buttons. {moving} Close in, the margins name each row and column, and closer still each cell
shows its value, {kind["in_cell"]}. The arrows beside a name, and the buttons under the picture for whatever is marked,
sort the whole matrix by that row or column: largest first, then smallest first, then back to the order it came in.
Sorting by a row or column marks it, and unmarking it lets go of the sort.</p></details>"""


@dataclass
class Unit:
    """Something the terms count or measure in, with a page that explains it."""
    key: str            # the name its page is filed under
    name: str           # one of it: "commodity", "need dollar"
    plural: str         # as a term's rows and columns write it: "commodities"
    counts: bool        # what a row or a column is one of; or else what an entry is measured in
    short: str          # in one sentence, for the tip a link to it shows and the table of units
    text: str           # the explanation, as paragraphs of HTML

    @property
    def href(self) -> str: return f"unit-{self.key}.html"
    @property
    def title(self) -> str: return self.name[0].upper() + self.name[1:]


def units(d: Data) -> dict[str, Unit]:
    """Every unit, by the name it is filed under: first what rows and columns are, then what entries
    are measured in."""
    t = d.io.t
    T = lambda key: _m(_term(key))
    trillion = lambda musd: f"${musd / 1e6:.1f} trillion"
    spent = d.sheets["Y"].values.values.sum()
    consumed = (t.F["F01000"] + t.F[A.GOV_CONSUMPTION].sum(axis=1)).sum()
    value_added, pay = t.VA.values.sum(), t.VA.loc["V00100"].sum()
    work, unpaid = d.sheets["f"].values.sum().equal, d.sheets["G"].values.values.sum()
    tax, E = d.tax, d.survey[0]
    occ, surveyed = d.wage_bill[2], d.survey[3]
    needs = [NEED_NAME[n].lower() for n in d.sheets["Y"].values.columns]
    ways = d.sheets[OMEGA].values
    out = [
        Unit("commodity", "commodity", "commodities", True,
             "One of the goods and services the Bureau of Economic Analysis divides the economy's output into.",
             f"""<p>One of the {len(t.commodities)} goods and services that the U.S. Bureau of Economic Analysis divides everything the
economy makes into, in its 2017 benchmark input-output accounts at the detail level: {_file('data/bea/')}. Grain is one, hospitals
another, wholesale trade another.</p>
<p>A commodity is a product, not a maker. It is made by one or more {_unit("industry", "industries")}, in the shares
{T("D")} holds. Where a term's rows are called sectors, each row is still a commodity, standing for the industries that
make it, mixed in those shares.</p>"""),
        Unit("industry", "industry", "industries", True,
             "One of the groups of producers the Bureau of Economic Analysis divides the economy into.",
             f"""<p>One of the {len(t.industries)} groups of producers in the same accounts. An industry is named for its main
product, a {_unit("commodity")}, but it can make others too: {T("V")} says how much of each.</p>
<p>The Bureau's tables say what industries bought and what they paid. The model turns those into what it takes to make a
commodity, through {T("D")}.</p>"""),
        Unit("need", "need", "needs", True,
             "One of the purposes that household and government spending is counted under.",
             f"""<p>One of {len(needs)} purposes that what households and governments buy is counted under: {", ".join(needs)}.
The list is the project's own. Each {_unit("commodity")} is counted under one need, or under none, by a list made by hand:
{_file('config/basket.csv')}.</p>
<p>What is under no need is left out of the account: financial and legal services, national defense and the rest of federal
government among them.</p>"""),
        Unit("weighting", "way of weighing the needs", "ways of weighing the needs", True,
             "One of three ways of dividing a need dollar among the needs.",
             f"""<p>One of {ways.shape[1]} ways of dividing one {_unit("need-dollar", "need dollar")} among the
{_unit("need", "needs")}, each a column of {T(OMEGA)}. Counted equally, every need has the same weight. By spending, a need
weighs what households and governments spent on it. By the poorest fifth's budget, it weighs what the fifth of households with
the lowest incomes spent on it themselves.</p>
<p>Every term from {T("p")} on has a column for each, so the order the account ends in can be read all three ways.</p>"""),
        Unit("investor-kind", "kind of investor", "kinds of investor", True,
             "One of the five kinds of buyer the Bureau of Economic Analysis reports investment for.",
             f"""<p>One of the five kinds of buyer that the Bureau of Economic Analysis reports investment in equipment and buildings
for: {", ".join(n.lower() for n in INVESTOR_NAME.values())}. The Bureau says what each kind bought, not which
{_unit("industry")} bought it, so {T("S")} places each kind's purchases on the industries of that kind.</p>"""),
        Unit("occupation", "occupation", "occupations", True,
             "One of the kinds of job in the Standard Occupational Classification, as the survey of occupations publishes them.",
             f"""<p>One of the {len(occ):,} kinds of job, in {occ.major.nunique()} major groups, that the U.S. Bureau of Labor
Statistics publishes in its Occupational Employment and Wage Statistics for May 2021: {_file('data/occupations/')}. They are
the occupations of the Standard Occupational Classification, except that the survey publishes a few only as a group.</p>
<p>The same occupations are described by O*NET, the Department of Labor's database, which says what tasks each does and what
software it uses. That is how a dollar placed on an occupation goes on to {_unit("activity", "work activities")} and
{_unit("capability", "software capabilities")}.</p>"""),
        Unit("surveyed-industry", "surveyed industry", "surveyed industries", True,
             "One of the industries the survey of occupations reports jobs and wages for.",
             f"""<p>One of the {len(surveyed)} industries that the survey of occupations reports {_unit("job", "jobs")} and wages
for. They are industries of the North American Industry Classification System at about its four-digit level, a few of
them published as groups, with three more for federal, state and local government. They are not the Bureau of Economic Analysis's {_unit("industry", "industries")}, so {T("T")} says which
surveyed industries cover each sector.</p>
<p>The survey leaves out farms and files public schools and hospitals with private ones. Stand-ins are used for those, and
housing is covered by nothing, because nobody is employed in owning a home.</p>"""),
        Unit("capability", "software capability", "software capabilities", True,
             "One of the things software does for the people who work, in the project's own taxonomy.",
             f"""<p>One of the {int((tax.level == 1).sum())} things software does for people at work, in a taxonomy compiled for this
project: {_file('taxonomy/')}. Medical coding, billing and claims is one; structural finite element analysis another. They are in
{int((tax.level == 0).sum())} domains, and each is divided into tasks, {int((tax.level == 2).sum()):,} in all.</p>
<p>The taxonomy says of each task whether its result could be scored by a benchmark, and names the open-source tools known for
it. {T("a")} and {T("c")} are counts of those. It also places the software products O*NET lists, which is how an
{_unit("occupation")}'s work reaches a capability, in {T(PHI)}.</p>"""),
        Unit("activity", "work activity", "work activities", True,
             "One of O*NET's intermediate work activities: a kind of work, whoever does it.",
             f"""<p>One of the {len(d.sheets["f"].values)} intermediate work activities of O*NET 31.0, the U.S. Department of
Labor's database of occupations: {_file('data/occupations/')}. An activity is a kind of work whoever does it, such as
preparing foods or beverages, or maintaining sales or financial records. O*NET files every task of every
{_unit("occupation")} under one or more of them.</p>
<p>Each is marked as information work, which software could do, or as work that needs a body or a person: {T("s")}.</p>"""),
        Unit("need-dollar", "need dollar", "need dollars", False,
             "One dollar of what households and governments spent on the needs in 2017.",
             f"""<p>One dollar of what households and governments spent on the {_unit("need", "needs")} in 2017. The spending is the
Bureau of Economic Analysis's personal consumption and government consumption, {T("Y")}. It came to {trillion(spent)}, of
{trillion(consumed)} of consumption in all.</p>
<p>A dollar of one need, as in {T("x")}, {T("d")} and {T("v")}, is spent the way that need's spending was: on each
{_unit("commodity")} in proportion to its part of the need's column of {T("Y")}.</p>
<p>From {T("p")} on, a need dollar is one dollar divided among all the needs, by one of the
{_unit("weighting", "ways of weighing them")}. A term measured per need dollar says: of each dollar spent on the needs,
this much.</p>
<p>Investment and exports are not in it. Equipment and buildings are counted as inputs instead, through {T("K")}.</p>"""),
        Unit("commodity-dollar", "commodity dollar", "commodity dollars", False,
             "One dollar's worth of a commodity, at the price its producer received in 2017.",
             f"""<p>One dollar's worth of a {_unit("commodity")}, at the producer prices of 2017: what its maker received, before
shops and carriers add their margins. Trade and transport are commodities of their own, and the margins are dollars of
those.</p>
<p>Each term says what the dollar's worth is doing. Produced, it is output, which counts everything made, including what is
used up in making something else: {trillion(t.q.sum())} in 2017. Delivered, it is sold to its last buyer. Used, it is an
input. So the dollars produced behind one dollar delivered come to more than a dollar, and {T("L")} says how much of each.</p>
<p>An {_unit("industry")}'s output is counted in the same dollars.</p>"""),
        Unit("value-added-dollar", "value-added dollar", "value-added dollars", False,
             "One dollar of what an industry's output is worth beyond the inputs it bought.",
             f"""<p>One dollar of what an {_unit("industry")}'s output is worth beyond the inputs it bought. It is what the industry
paid its employees, taxes on production less subsidies, and gross operating surplus: what is left for owners and lenders and
to replace equipment and buildings as they wear out.</p>
<p>Added up over every industry it is gross domestic product: {trillion(value_added)} in 2017, of which
{trillion(pay)} was pay.</p>
<p>It is the income that spending becomes. {T("v")} divides a dollar of each need among the sectors by the value added
each earns behind it.</p>"""),
        Unit("work-dollar", "work dollar", "work dollars", False,
             "One dollar placed on the work it pays for, or one dollar's worth of unpaid work at home.",
             f"""<p>One dollar placed on work. For paid work it is a
{_unit("value-added-dollar", "value-added dollar")} of a sector, divided among the sector's
{_unit("occupation", "occupations")} in proportion to what it pays each, {T("W")}. The whole of the value added is divided
that way, not the payroll alone, so a work dollar is more than the worker was paid: pay was
{pay / value_added * 100:.0f} cents of each dollar of value added in 2017.</p>
<p>For unpaid work at home it is an hour valued at the mean wage of the occupation that does such work for pay, {T("G")}. It
is added to the need dollar, not taken out of it. With the needs counted equally, the work behind a need dollar comes to
{work * 100:.0f} cents: {(work - unpaid) * 100:.0f} paid and {unpaid * 100:.0f} unpaid. The rest of the paid dollar is in
sectors and occupations the surveys do not reach.</p>
<p>The wages are those of May 2021 and the spending is that of 2017, so the unpaid work is valued somewhat high against the
need dollar.</p>"""),
        Unit("million-dollars", "million dollars", "millions of dollars", False,
             "A million dollars at the prices of 2017, as the Bureau of Economic Analysis's tables count.",
             f"""<p>The Bureau of Economic Analysis publishes its 2017 input-output tables in millions of dollars, at the prices of
2017 and at producer prices. The terms that are those tables, or are added up from them, are kept in that unit. One million
of it is a million {_unit("commodity-dollar", "commodity dollars")} where it counts a commodity, and a million
{_unit("value-added-dollar", "value-added dollars")} where it counts value added.</p>
<p>{T("P")} is in millions of dollars too, but of pay in a year at the wages of May 2021, the month of the survey of
occupations. It is used only for its shares, {T("W")}.</p>"""),
        Unit("share", "share", "shares", False,
             "A part of a whole, from zero to one.",
             f"""<p>A part of a whole, from zero to one. Pictures show it in percent. Each term says what the whole is, and so
which way it adds up to one: a column of {T("D")} is one commodity's output, divided among its makers, and a row of
{T("W")} is one sector's wage bill, divided among occupations.</p>
<p>Multiplying by a share divides something up without adding to it or losing any. Where rows or columns add up to less than
one, the term's page says what is missing.</p>"""),
        Unit("one-or-zero", "one or zero", "ones and zeros", False,
             "One where something is so, and zero where it is not.",
             f"""<p>One where something is so, and zero where it is not. Multiplying by such a term keeps the entries it marks and
drops the rest: {T("s")} keeps the work that is information work, and {T("H")} keeps the industries of one kind of
investor.</p>"""),
        Unit("job", "job", "jobs", False,
             "One wage or salary job, as the survey of occupations counted them in May 2021.",
             f"""<p>One wage or salary job at a nonfarm employer, as the Occupational Employment and Wage Statistics of the U.S.
Bureau of Labor Statistics counted them in May 2021: {E.sum().sum() / 1e6:.0f} million in the industries and occupations it
publishes. It is a job and not a person: someone with two jobs is counted twice, and the self-employed are not counted.</p>"""),
        Unit("dollar-a-year", "dollar a year", "dollars a year", False,
             "A dollar of an occupation's mean annual wage, in May 2021.",
             f"""<p>A dollar of the mean annual wage of an {_unit("occupation")} in a
{_unit("surveyed-industry", "surveyed industry")}, from the same survey, in May 2021. The survey records a wage of
${O.OEWS_TOP_CODE:,.0f} or more as ${O.OEWS_TOP_CODE:,.0f}. Where an hourly wage is needed, a year is taken as
{HOURS_A_YEAR:,} hours.</p>"""),
    ]
    return {u.key: u for u in out}


def _unit(key: str, text: str = "") -> str:
    """A link to a unit's page, reading as the key does unless text is given."""
    return f'<a href="unit-{key}.html">{text or key}</a>'


def dimension(d: Data, phrase: str) -> Unit:
    """The unit a term's rows or columns are counted in: the one its phrase names, at greatest length."""
    named = [u for u in d.units.values() if u.counts and u.plural in phrase]
    return max(named, key=lambda u: len(u.plural))


def dimension_html(d: Data, phrase: str) -> str:
    """The phrase for a term's rows or columns, with its unit a link to the unit's page."""
    u = dimension(d, phrase)
    return e(phrase).replace(e(u.plural), _unit(u.key, e(u.plural)), 1)


def measure_text(key: str) -> str:
    """What a term's entries are measured in, as plain words."""
    return _UNIT_LINK.sub(r"\1", MEASURED_IN[key])


def measure_html(key: str) -> str:
    """And as a line of a page: with a capital, and each unit a link to its page."""
    words = MEASURED_IN[key]
    first = 1 if words.startswith("[") else 0
    words = words[:first] + words[first].upper() + words[first + 1:]
    return _UNIT_LINK.sub(lambda m: _unit(m.group(2), m.group(1)), e(words))


def measures(key: str) -> list[str]:
    """The units a term's entries are measured in, by the names they are filed under."""
    return [m.group(2) for m in _UNIT_LINK.finditer(MEASURED_IN[key])]


def term_tip(s: Sheet) -> str:
    """What a link to a term shows under the pointer: its name, what its rows and columns are, and
    what an entry is measured in. A vector has rows alone."""
    nr, nc = s.values.shape
    lines = [s.title, f"Rows: {nr:,} {s.rows.replace(': ', ', ', 1)}"]
    if nc > 1:
        lines.append(f"Columns: {nc:,} {s.cols.replace(': ', ', ', 1)}")
    return "\n".join(lines + [f"Unit: {measure_text(s.key)}"])


def unit_tip(u: Unit) -> str:
    """And a link to a unit: its name, and what it is in a sentence."""
    return f"{u.title}\n{u.short}"


def with_tips(d: Data, page: str) -> str:
    """A page with those tips on every link in it to a term's page or a unit's."""
    for x, tip in [(s, term_tip(s)) for s in d.sheets.values()] + [(u, unit_tip(u)) for u in d.units.values()]:
        page = page.replace(f'<a href="{x.href}"', f'<a href="{x.href}" data-tip="{e(tip)}"')
    return page


def unit_users(d: Data, u: Unit) -> dict[str, list[str]]:
    """The terms that use a unit, by how: as what their rows are, their columns, or their entries."""
    wide = [k for k, s in d.sheets.items() if s.values.shape[1] > 1]
    return {"Rows of": [k for k, s in d.sheets.items() if dimension(d, s.rows) is u],
            "Columns of": [k for k in wide if dimension(d, d.sheets[k].cols) is u],
            "Entries of": [k for k in d.sheets if u.key in measures(k)]}


def unit_page(d: Data, key: str) -> str:
    """The page of one unit: what it is, and the terms that count or measure in it."""
    u = d.units[key]
    spec = [(how, term_links(d, keys)) for how, keys in unit_users(d, u).items() if keys]
    body = f"""
<p class="crumbs"><a href="{HOME}">The account</a> &rsaquo; <a href="{HOME}#units">Every unit</a></p>
<h1 class="long">{e(u.title)}</h1>
{u.text}
<dl class="spec">{"".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in spec)}</dl>
"""
    return page(u.title, body)


def unit_table(d: Data) -> str:
    """Every unit in one table: what it is, and the terms that use it."""
    rows = []
    for counts, band in ((True, "Units of rows and columns"), (False, "Units of entries")):
        rows.append(f'<tr class="band"><th colspan="3" scope="colgroup">{band}</th></tr>')
        for u in d.units.values():
            if u.counts == counts:
                used = [k for keys in unit_users(d, u).values() for k in keys]
                letters = " ".join(_m(_term(k)) for k in TERMS if k in used)
                rows.append(f'<tr><th scope="row"><a href="{u.href}">{e(u.title)}</a></th><td class="wrap">{e(u.short)}</td>'
                            f'<td class="wrap">{letters}</td></tr>')
    return table([th("Unit"), th("Definition"), th("Terms")], rows, attrs=' class="terms units"',
                 caption="Every unit of the account. Each is a link to its page.")


def term_links(d: Data, keys, here: str = "") -> str:
    """Terms by letter and name, each letter a link to its page."""
    return "; ".join(f'{_m(_term(k, here))}, {e(d.sheets[k].name)}' for k in keys)


def term_page(d: Data, key: str) -> str:
    """The page of one term: what its rows, columns and entries are, where it comes from, what it
    is made from and what it goes into, and the picture of the whole of it."""
    s = d.sheets[key]
    nr, nc = s.values.shape
    spec = [("Rows", f"{nr:,} {dimension_html(d, s.rows)}")]
    if nc > 1:
        spec.append(("Columns", f"{nc:,} {dimension_html(d, s.cols)}"))
    spec.append(("Entries", s.entries))
    spec.append(("Unit", measure_html(key)))
    if key in EQUATIONS:
        spec.append(("Computed", _eqs([equation(key, key)])))
    if s.source:
        spec.append(("Source" if key not in EQUATIONS else "Where", s.source))
    if key in USES:
        spec.append(("Made from", term_links(d, USES[key], key)))
    users = [k for k in TERMS if key in USES.get(k, ())]
    into = [equation(k, key) for k in users if k in EQUATIONS] + ([equation("gap", key)] if key == "o" else [])
    plain = [k for k in users if k not in EQUATIONS]
    if into or plain:
        spec.append(("Used in", (_eqs(into) if into else "") + (f"<p>{term_links(d, plain, key)}</p>" if plain else "")))
    if s.note:
        spec.append(("Note", s.note))
    spec.append(("Data", f'<a href="{s.csv_file}">The whole of it as CSV</a>, with codes for rows and columns. The code is {_file(s.code)}.'))
    why = also = ""
    if key == "A":      # a marked cell is taken apart into the industries that make the column's commodity
        also = "A marked cell is taken apart under the picture, into the industries that make the column's commodity."
        why = f"""<template id="mx-why"><h3>The parts of the cell</h3>
<p>{_m(_sym("A", key))} is {_m(_sym("B"))} times {_m(_sym("D"))}, so a cell is one row of {_m(_sym("B"))} against one column of
{_m(_sym("D"))}. Each industry that makes the column's commodity brings what it uses of the row's, in proportion to its share:</p>
{_m(f'{_sub("a", "ij")}<mo>=</mo>{_sum("k")}{_sub("b", "ik")}{_TIMES}{_sub("d", "kj")}', block=True)}</template>
"""
    body = f"""
<p class="crumbs"><a href="{HOME}">The account</a></p>
<h1 class="long">{_m(_term(key, key))}, {e(s.name)}</h1>
<dl class="spec">{"".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in spec)}</dl>
{sheet_picture(s, also=also, extra=why)}
"""
    return page(s.title, body, scripts=(s.data_file, "matrix.js"))


def account_table(d: Data) -> str:
    """Every term of the account in one table: what it is, its size, and what it is made from."""
    rows = []
    for group, keys in GROUPS:
        rows.append(f'<tr class="band"><th colspan="4" scope="colgroup">{e(group)}</th></tr>')
        for k in keys:
            s = d.sheets[k]
            nr, nc = s.values.shape
            size = f"{nr:,} {dimension_html(d, s.rows.split(':')[0])}" + (f" &times; {nc:,} {dimension_html(d, s.cols.split(':')[0])}" if nc > 1 else "")
            a, b = equation(k) if k in EQUATIONS else ("", "")
            made = _m(f"{a}<mo>=</mo>{b}") if a else '<span class="dim">Data</span>'
            rows.append(f'<tr><th scope="row">{_m(_term(k))}</th><td class="wrap"><a href="{s.href}">{e(s.name[0].upper() + s.name[1:])}</a></td>'
                        f'<td class="wrap">{size}</td><td>{made}</td></tr>')
    return table([th("Term"), th("Name"), th("Size"), th("Made from")], rows, attrs=' class="terms"',
                 caption="Every matrix and vector of the account. Each is a link to its page: its rows, columns and entries, where "
                         "it comes from, what it goes into, and a picture of the whole of it.")


def gap(d: Data) -> pd.Series:
    """The last line of the account, for each way of weighing the needs: the part of a need dollar that
    pays for information work that is well defined and done with software that has no known open tool."""
    return d.sheets["o"].values.sum()


def account_section(d: Data) -> str:
    """The whole account as five equations, what they come to, and every term in them."""
    k, b = (d.sheets[key].values.sum() for key in "kb")
    unpaid = d.sheets["G"].values.values.sum()
    g = gap(d) * 100
    return f"""{_eqs([equation(key) for key in ("x", "p", "k", "o", "gap")])}
<p>{_m(_sym(OMEGA))} weighs the needs, in three ways, and every term from {_m(_sym("p"))} on has a column for each.
{_m(_sym("G"))} is the unpaid work done at home, {unpaid * 100:.0f} cents for every dollar spent on the needs, and
{_m(_sym("s"))} marks the work that is information work. {_m(_ONES)} is a column of ones.</p>
<p>With the needs counted equally, the third line places {k.equal * 100:.1f} cents of a need dollar on {len(d.sheets["k"].values)}
software capabilities: the information work of each occupation, by the software it is done with. Another
{b.equal * 100:.1f} cents is work that needs a body or a person, {_m(_sym("b"))}. The fourth line keeps the part of each
capability's work that is well defined and has no known open tool, and the fifth adds it up: {g.equal:.1f} cents. Weighing
the needs by what is spent on each it is {g.spending:.1f} cents, and by the poorest fifth's budget {g.poorest:.1f}. Sorted,
a column of {_m(_sym("o"))} is the order to work in.</p>
<h2 id="terms">Every term</h2>
{account_table(d)}
<h2 id="units">Every unit</h2>
{unit_table(d)}
"""


def index(d: Data) -> str:
    """The home page: the account, and every term in it."""
    body = f"""
<h1>The account</h1>
<p class="lede">A dollar of each need is traced to the commodities it buys, to everything the economy produces to
deliver them, to the sectors whose income it becomes, to the occupations they pay, and to the software those
occupations work with. Every term is a link to its matrix.</p>
{account_section(d)}"""
    return page("The account", body, home=True)


def main():
    d = Data()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    pages = {"index.html": index, **{SYMBOL_PAGES[key]: (lambda d, key=key: term_page(d, key)) for key in TERMS},
             **{u.href: (lambda d, key=key: unit_page(d, key)) for key, u in d.units.items()}}
    for name, fn in pages.items():
        (SITE / name).write_text(with_tips(d, fn(d)), encoding="utf-8")
    for key, sheet in d.sheets.items():
        (SITE / sheet.data_file).write_text(matrix_data(d, key), encoding="utf-8")
        (SITE / sheet.csv_file).write_text(sheet_csv(sheet), encoding="utf-8")
    (SITE / MATRIX_PARTS).write_text(matrix_a_parts(d), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

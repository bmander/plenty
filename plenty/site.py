"""Render the static site (site/) from the model, config/ and results/.

    python scripts/03_run.py     # refresh results/ first if config/ changed
    python -m plenty.site

The site is the account: four equations on the home page, and a page for every matrix and
vector they are made from, down to the published tables. Assets in plenty/web/ are copied as
they are. Everything is plain HTML with relative links, so the site works from any path (GitHub
Pages serves it under /plenty/).
"""
from __future__ import annotations
import functools
from dataclasses import dataclass
import html
import json
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
<nav aria-label="Sections"><a href="index.html"{' aria-current="page"' if home else ""}>The account</a><a href="index.html#terms">Every term</a></nav>
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
# The account is four equations. Every matrix and vector in them, and every one those are made
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
THETA, PHI = "Θ", "Φ"
GREEK = {THETA: ("Theta", "&#x1D6AF;"), PHI: ("Phi", "&#x1D6BD;")}     # a Greek letter's name in a file, and its bold
# the terms, in the order the account's table lists them
GROUPS = [
    ("The account", ["x", "k", "o"]),
    ("Needs", ["d", "Y"]),
    ("The input-output model", ["L", "A", "B", "D", "U", "V", "g", "q"]),
    ("Capital", ["K", "F", "H", "S", "z"]),
    ("Value added", ["v", "r", "y"]),
    ("Work", ["W", "P", "T", "E", "M"]),
    ("Software capabilities", [PHI, "c"]),
    ("Work activities", ["f", THETA]),
]
TERMS = [k for _, keys in GROUPS for k in keys]
PER_NEED = "dxv"                      # the vectors there is one of for each need, written with a subscript n
# what each computed term is made from; a term that is not here is data
USES = {"x": ["L", "d"], "k": ["v", "W", PHI], "o": ["k", "c"], "f": ["v", "W", THETA], "d": ["Y"], "L": ["A"], "A": ["B", "D"], "B": ["U", "K", "g"],
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
    if key in "kf":       # the same dollar, placed on the software the work is done with, or on what the work is
        last = S(PHI if key == "k" else THETA)
        return S(key, T=True), (f'<mfrac><mn>1</mn><mi>N</mi></mfrac>{_TIMES}{_sum("n")}{V("v", T=True)}{_TIMES}{S("W")}{_TIMES}{last}')
    if key == "o":        # entry by entry: what is paid for work with a capability, times the part of it that is not open
        return S("o"), f'{S("k")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("c")}")}'
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


EQUATIONS = ["x", "k", "o", "f", "d", "L", "A", "B", "D", "g", "q", "K", "S", "v", "r", "W", "P"]   # the terms equation() defines


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
    rows: str                      # what the rows are, after their number: "commodities: the input"
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
    flow = pd.Series(d.need_value_added.loc[com].mean(axis=1).values @ d.wages[0].loc[com].values @ d.phi.values, index=caps)
    out = [
        # --- the account
        Sheet("x", "the output behind a dollar of each need", "per_dollar", xn.loc[com], t.names,
              rows="commodities: what is produced", cols="needs: a dollar of each", **by_need,
              entries="Dollars of the commodity produced, at every stage of supply, to deliver a dollar of the need.",
              row_tip="Produced", col_tip="For a dollar of", row_is="Row, the commodity produced:", axis="Needs: one dollar of each",
              code="plenty/analysis.py", sums="cols"),
        Sheet("k", "the part of a need dollar that pays for work done with each capability", "per_dollar",
              **lone(flow, "k", "Share of a need dollar", "per dollar"), **by_capability,
              rows="software capabilities: the taxonomy's",
              entries="Dollars per need dollar, the needs counted equally, that pay the people who work with the capability. It is "
                      "the work the software serves, not what the software earns.",
              note=f"The entries add up to {d.cap_acct.flowed * 100:.1f} cents. Of the rest, "
                   f"{d.cap_acct.sectors_without_occupation_data * 100:.1f} cents are in sectors the survey of occupations does not "
                   f"reach, and {d.cap_acct.work_not_placed * 100:.1f} in occupations that list no software or software the taxonomy "
                   "does not place.",
              row_tip="Capability", code="plenty/flows.py", sums="both", order=capability_order),
        Sheet("o", "the overhang of each capability", "per_dollar",
              **lone(flow * (1 - d.open_share), "o", "Share of a need dollar", "per dollar"), **by_capability,
              rows="software capabilities: the taxonomy's",
              entries="Dollars per need dollar: what is paid for work done with the capability, times the share of its tasks "
                      "that have no known open tool.",
              note="The entries add up to the gap. Sorted, the column is the order to work in, as far as the two terms it is "
                   "made from can be trusted.",
              row_tip="Capability", code="plenty/site.py", sums="both", order=capability_order),
        # --- needs
        Sheet("d", "what a dollar of each need buys", "per_dollar", dn.loc[com], t.names,
              rows="commodities: what is bought", cols="needs: a dollar of each", **by_need,
              entries="The part of a dollar of the need that is spent on the commodity. A column adds up to one dollar.",
              row_tip="Bought", col_tip="With a dollar of", row_is="Row, the commodity bought:", axis="Needs: one dollar of each",
              code="plenty/analysis.py"),
        Sheet("Y", "what was spent on each need", "dollars", A.need_demand(t)[needs].loc[com], t.names,
              rows="commodities: what was bought", cols="needs: what it was bought for", **by_need,
              entries="Millions of dollars bought by households and governments in 2017 and counted under the need.",
              source=f"{bea} It is the Use table's columns for personal consumption (<code>F01000</code>) and government "
                     f"consumption ({', '.join(f'<code>{c}</code>' for c in A.GOV_CONSUMPTION)}). Each commodity is counted under "
                     f"one need, or under none, by a list made by hand, {_file('config/basket.csv')}. Trade and freight margins "
                     "are split over the needs in proportion to what each spent on goods.",
              note="Investment and exports are not in it. Equipment and buildings are counted as inputs instead, through "
                   f"{_m(_sym('K'))}.",
              row_tip="Bought", col_tip="For", row_is="Row, the commodity bought:", axis="Needs: what was spent on each",
              code="plenty/analysis.py", sums="both"),
        # --- the input-output model
        Sheet("L", "the total requirements", "per_dollar", m.L.loc[com, com], t.names, t.names,
              rows="commodities: what is produced", cols="commodities: what is delivered",
              entries="Dollars of the row's commodity produced, at every stage of supply, to deliver a dollar of the column's.",
              note="Imports are counted as if made the way the United States makes them.",
              row_tip="Produced", col_tip="To deliver", row_is="Row, the commodity produced:", col_is="Column, the commodity delivered:",
              axis="Delivered: one dollar of each commodity", code=model, sums="cols"),
        Sheet("A", "the direct requirements", "per_dollar", A_, t.names, t.names,
              rows="commodities: the input", cols="commodities: the thing made",
              entries="Dollars of the input used, directly, per dollar of the thing made, equipment and buildings included.",
              row_tip="Input", col_tip="To make", col_is="Column, the thing made:",
              axis="Made: one dollar of each commodity", code=model, second=A_capital, sums="cols"),
        Sheet("B", "what industries use per dollar", "per_dollar", (purchases + capital).loc[com, ind], t.names, t.ind_names,
              rows="commodities: the input", cols="industries: the user",
              entries="Dollars of the commodity used per dollar of the industry's output, equipment and buildings included.",
              row_tip="Input", col_tip="Used by", col_is="Column, the industry using it:",
              axis="Industries: per dollar of their output", code=model, second=capital.loc[com, ind], sums="cols"),
        Sheet("D", "who makes each commodity", "share", D.loc[ind, com], t.ind_names, t.names,
              rows="industries: the maker", cols="commodities: the thing made",
              entries="The industry's share of the commodity's output. A column adds up to one.",
              row_tip="Industry", col_tip="Its share of", col_is="Column, the commodity made:",
              axis="Commodities: who makes each", code=model),
        Sheet("U", "the Use table", "dollars", t.U.loc[com, ind], t.names, t.ind_names,
              rows="commodities: what was bought", cols="industries: the buyer",
              entries="Millions of dollars of the commodity bought by the industry as an input in 2017.",
              source=f"{bea} It is the Use table without its columns of final demand and its rows of value added.",
              row_tip="Bought", col_tip="By", row_is="Row, the commodity bought:", col_is="Column, the industry buying:",
              axis="Industries buying", code=model, exact=True, sums="both"),
        Sheet("V", "the Make table", "dollars", t.V.loc[ind, com], t.ind_names, t.names,
              rows="industries: the maker", cols="commodities: the thing made",
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
              rows="commodities: the capital good", cols="industries: where it is placed",
              entries="Millions of dollars of the capital good bought as investment in 2017 and placed on the industry.",
              note="It is an estimate. The Bureau publishes investment by commodity and by kind of investor, not by the industry "
                   "that bought it.",
              row_tip="Capital good", col_tip="Placed on", col_is="Column, the industry it is placed on:",
              axis="Industries using the capital", code=model, sums="both"),
        Sheet("F", "what was bought as investment", "dollars", cap.investment.loc[com], t.names,
              rows="commodities: the capital good", cols="kinds of investor", **by_investor,
              entries="Millions of dollars of the commodity bought as investment in 2017 by investors of the kind. A negative "
                      "entry is a sale of used equipment or scrap.",
              source=f"{bea} It is the Use table's columns for investment, added up by kind of investor: "
                     + "; ".join(f"{INVESTOR_NAME[h].lower()} ({', '.join(f'<code>{c}</code>' for c in cols)})"
                                 for h, cols in M.CAPITAL_COLUMNS.items()) + ".",
              row_tip="Capital good", col_tip="Bought by", axis="Kinds of investor", code=model, sums="both"),
        Sheet("H", "what kind of investor each industry is", "mark", investors.loc[ind], t.ind_names,
              rows="industries", cols="kinds of investor", **by_investor,
              entries="One where the industry is of the kind, and zero elsewhere. Every industry is of one kind.",
              source=f"Lists in {_file(model)}: housing, federal defense, federal nondefense, and state and local government "
                     "are named there, and every other industry is private business.",
              row_tip="Industry", col_tip="Kind of investor", axis="Kinds of investor", code=model,
              blanks=("is not of this kind", "zero"), marked="is of this kind", sums="cols"),
        Sheet("S", "where each capital good is placed", "share", cap.shares.loc[com, ind], t.names, t.ind_names,
              rows="commodities: the capital good", cols="industries: where it is placed",
              entries="The share of the purchases of the capital good, by investors of the industry's kind, that is placed on the "
                      "industry. Within one kind of investor a row adds up to one.",
              source=f"{_m(_sub('&Omega;', 'ik'))} is the set of industries that could have bought capital good <i>i</i>, among "
                     f"those of the same kind of investor as <i>k</i>: the ones a pairing names for it, or all of that kind if none "
                     f"does. The {sum(1 for x in cap.steps if x['note'])} pairings of a capital good with its evident users are "
                     f"judgment, kept in {_file('config/capital_allocation.csv')}.",
              row_tip="Capital good", col_tip="Share placed on", col_is="Column, the industry it is placed on:",
              axis="Industries: their share of each capital good", code=model),
        Sheet("z", "what industries share investment by", "dollars", **lone(cap.weight.loc[ind], "z", "Weight"), row_names=t.ind_names,
              rows="industries",
              entries="Millions of dollars: the industry's gross operating surplus if it is private business or housing, and its "
                      "output if it is government.",
              source=f"{bea} Gross operating surplus is the Use table's row <code>V00300</code>, with a negative surplus counted "
                     "as none.",
              row_tip="Industry", code=model),
        # --- value added
        Sheet("v", "whose income a need dollar becomes", "share", d.need_value_added.loc[com], t.names,
              rows="commodities: the sector whose income it is", cols="needs: a dollar of each", **by_need,
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
        Sheet("W", "who does each sector's work", "share", d.wages[0].loc[com], t.names, occ.title,
              rows="commodities: the sector", cols="occupations",
              entries="The occupation's share of the sector's wage bill. A row adds up to one, or is empty where the sector is "
                      "not measured.",
              row_tip="Sector", col_tip="Share of its wage bill paid to", col_is="Column, the occupation:",
              axis="Occupations: their share of each sector's wage bill", code=occupations, **by_occupation),
        Sheet("P", "what each sector's industries paid each occupation", "dollars", P.loc[com], t.names, occ.title,
              rows="commodities: the sector", cols="occupations",
              entries="Millions of dollars paid to the occupation in a year by the surveyed industries that cover the sector.",
              note="Jobs times the mean wage, in the cells where the survey publishes both.",
              row_tip="Sector", col_tip="Paid to", col_is="Column, the occupation:",
              axis="Occupations: what each sector's industries paid them", code=occupations, **by_occupation, sums="both"),
        Sheet("T", "which surveyed industries cover each sector", "mark", T.loc[com], t.names, surveyed.title,
              rows="commodities: the sector", cols="surveyed industries",
              entries="One where the surveyed industry covers the sector, and zero elsewhere.",
              source=f"The Bureau of Economic Analysis's concordance of its sectors with the industry classification the survey "
                     f"uses, in {_file('data/occupations/')}, and in {_file(occupations)} the stand-ins for what the survey "
                     "files elsewhere or leaves out: public schools and hospitals, other government, and farms. Housing and the "
                     "accounting sectors are covered by nothing.",
              row_tip="Sector", col_tip="Surveyed industry", axis="Surveyed industries", code=occupations,
              col_groups=surveyed.group, blanks=("does not cover it", "zero"), marked="covers it",
              order="Sectors and surveyed industries are each in code order within the same fifteen groups.", sums="both"),
        Sheet("E", "how many work in each occupation", "people", E.fillna(0.0), surveyed.title, occ.title,
              rows="surveyed industries", cols="occupations", entries="Jobs in the occupation in the industry, in May 2021.",
              source=oews,
              note="It counts wage and salary jobs at nonfarm employers, not people: someone with two jobs is in it twice, and the "
                   "self-employed are not in it.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: how many people each industry employs in them",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only, sums="both"),
        Sheet("M", "what each occupation is paid", "wage", wage.fillna(0.0), surveyed.title, occ.title,
              rows="surveyed industries", cols="occupations",
              entries="The mean annual wage of the occupation in the industry, in dollars, in May 2021.",
              source=oews, note="A wage of $208,000 or more is recorded as $208,000.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: their mean annual wage in each industry",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only),
        # --- software capabilities
        Sheet(PHI, "what software each occupation works with", "share", d.phi, occ.title, tax.name[caps],
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
        Sheet("c", "how much of each capability is open", "share",
              **lone(d.open_share, "c", "Tasks with an open tool", "share"), **by_capability,
              rows="software capabilities: the taxonomy's",
              entries="The share of the capability's tasks for which an open-source tool is known.",
              source=f"The taxonomy names the open tools known for each of its {int((d.tax.level == 2).sum()):,} tasks: "
                     f"{_file('taxonomy/capabilities.csv')}.",
              note="The tools were named from memory when the taxonomy was compiled. An entry says a tool exists, not that it is "
                   "good enough to do the work.",
              row_tip="Capability", code="taxonomy/build.py", order=capability_order),
        # --- work activities: the same dollar, placed on what the work is
        Sheet("f", "the part of a need dollar that pays for each activity", "per_dollar",
              **lone(act.flow, "f", "Share of a need dollar", "per dollar"), **by_activity,
              rows="work activities: O*NET's intermediate work activities",
              entries="Dollars per need dollar, the needs counted equally. It is where today's money goes, not how much an "
                      "activity matters.",
              note=f"The entries add up to {d.act_acct.flowed * 100:.1f} cents. The rest of the dollar is in sectors the survey of "
                   "occupations does not reach, and in occupations whose tasks are not rated.",
              row_tip="Activity", code="plenty/flows.py", sums="both", order=activity_order),
        Sheet(THETA, "what each occupation's work is", "share", d.theta, occ.title, act.name,
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
<details class="note mx-how"><summary>How to use the picture</summary>
<p>Hover over a cell for its row, its column and its value. Click a cell to mark it with its row and column, or click
in a margin to mark one row or one column.{" " + also if also else ""}{summed} To zoom, scroll or pinch over the picture
or its margins, or use the buttons. {moving} Close in, the margins name each row and column, and closer still each cell
shows its value, {kind["in_cell"]}. The arrows beside a name, and the buttons under the picture for whatever is marked,
sort the whole matrix by that row or column: largest first, then smallest first, then back to the order it came in.
Sorting by a row or column marks it, and unmarking it lets go of the sort.</p></details>"""


def term_links(d: Data, keys, here: str = "") -> str:
    """Terms by letter and name, each letter a link to its page."""
    return "; ".join(f'{_m(_term(k, here))}, {e(d.sheets[k].name)}' for k in keys)


def term_page(d: Data, key: str) -> str:
    """The page of one term: what its rows, columns and entries are, where it comes from, what it
    is made from and what it goes into, and the picture of the whole of it."""
    s = d.sheets[key]
    nr, nc = s.values.shape
    spec = [("Rows", f"{nr:,} {s.rows}")]
    if nc > 1:
        spec.append(("Columns", f"{nc:,} {s.cols}"))
    spec.append(("Entries", s.entries))
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
        why = f"""<template id="mx-why"><h3>How the cell is made up</h3>
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
            size = f"{nr:,} {e(s.rows.split(':')[0])}" + (f" &times; {nc:,} {e(s.cols.split(':')[0].split(',')[0])}" if nc > 1 else "")
            a, b = equation(k) if k in EQUATIONS else ("", "")
            made = _m(f"{a}<mo>=</mo>{b}") if a else '<span class="dim">Data</span>'
            rows.append(f'<tr><th scope="row">{_m(_term(k))}</th><td class="wrap"><a href="{s.href}">{e(s.name[0].upper() + s.name[1:])}</a></td>'
                        f'<td class="wrap">{size}</td><td>{made}</td></tr>')
    return table([th("Term"), th("What it is"), th("Size"), th("Made from")], rows, attrs=' class="terms"',
                 caption="Every matrix and vector of the account. Each is a link to its page: its rows, columns and entries, where "
                         "it comes from, what it goes into, and a picture of the whole of it.")


def gap(d: Data) -> float:
    """The last line of the account: the part of a need dollar that pays for work done with software
    capabilities whose tasks have no known open tool."""
    return float(d.sheets["o"].values.values.sum())


def account_section(d: Data) -> str:
    """The whole account as four equations, what they come to, and every term in them."""
    k = d.sheets["k"].values.iloc[:, 0]
    return f"""{_eqs([equation("x"), equation("k"), equation("o"), equation("gap")])}
<p>{_m("<mi>N</mi>")} is the number of needs, {len(NEED_NAME)}, each counted equally, and {_m(_ONES)} is a column of ones.
The second line places {k.sum() * 100:.1f} cents of a need dollar on {len(k)} software capabilities: what is paid to the people
who work with each. The third keeps the part of each that is paid for work with tasks that have no known open tool, and
the fourth adds it up: {gap(d) * 100:.1f} cents. Sorted, {_m(_sym("o"))} is the order to work in.</p>
<h2 id="terms">Every term</h2>
{account_table(d)}
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
    pages = {"index.html": index, **{SYMBOL_PAGES[key]: (lambda d, key=key: term_page(d, key)) for key in TERMS}}
    for name, fn in pages.items():
        (SITE / name).write_text(fn(d), encoding="utf-8")
    for key, sheet in d.sheets.items():
        (SITE / sheet.data_file).write_text(matrix_data(d, key), encoding="utf-8")
        (SITE / sheet.csv_file).write_text(sheet_csv(sheet), encoding="utf-8")
    (SITE / MATRIX_PARTS).write_text(matrix_a_parts(d), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

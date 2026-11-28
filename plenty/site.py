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
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis as A, flows as FL, hours as HR, matrix as MX, model as M, occupations as O, work as WK

ROOT = Path(__file__).resolve().parent.parent
RESULTS, WEB, SITE, PROPOSALS = ROOT / "results", ROOT / "plenty" / "web", ROOT / "site", ROOT / "proposals"
REPO = "https://github.com/bmander/plenty"

NEED_NAME = {
    "food": "Food", "clothing": "Clothing", "shelter": "Shelter", "energy": "Energy",
    "water_sanitation": "Water and sanitation", "health": "Health", "education": "Education",
    "mobility": "Mobility", "communication": "Communication", "safety": "Safety",
    "meaning": "Meaning and recreation",
}

e = html.escape


# ---------------------------------------------------------------- data

@dataclass
class Proposal:
    """Something that could be built, as its file states it: what it is, how it would be checked, the
    part of each work activity it would do, and what it would cost to make."""
    key: str                       # the name its file and its page go by
    name: str
    by: str
    what: str
    check: str
    does: pd.DataFrame             # by work activity: the share of it claimed, and why
    cost: float | None = None      # hours of people's work to make it, as the proposer estimates
    cost_basis: str = ""

    @property
    def href(self) -> str: return f"proposal-{self.key}.html"
    @property
    def file(self) -> str: return f"proposals/{self.key}.toml"


def proposals(activities, folder: Path | None = None) -> dict[str, Proposal]:
    """Read every proposal in the folder, in the order of their files' names, and refuse one that is not
    whole: it must say what it is and how it is checked, and claim a share above zero and at most
    one of activities there are, each once and each with a reason."""
    out = {}
    for path in sorted((folder or PROPOSALS).glob("*.toml")):
        x = tomllib.loads(path.read_text(encoding="utf-8"))
        does = pd.DataFrame(x.get("does", []), columns=["activity", "share", "basis"]).set_index("activity")
        wrong = [f"no {k}" for k in ("name", "what", "check") if not str(x.get(k, "")).strip()]
        wrong += [f"{a} is not a work activity" for a in does.index.difference(activities)]
        wrong += [f"{a} is claimed twice" for a in does.index[does.index.duplicated()]]
        wrong += [f"{a} has a share of {v}" for a, v in does.share.items() if not 0 < v <= 1]
        wrong += [f"{a} has no reason" for a, v in does.basis.items() if not str(v).strip()]
        if does.empty:
            wrong.append("it claims no activity")
        cost = x.get("cost", {})
        if cost and not (cost.get("hours", 0) > 0 and str(cost.get("basis", "")).strip()):
            wrong.append("its cost needs hours above zero and a basis")
        if wrong:
            raise ValueError(f"{path.name}: " + "; ".join(wrong))
        out[path.stem] = Proposal(path.stem, x["name"], x.get("by", ""), x["what"], x["check"], does,
                                  cost.get("hours"), cost.get("basis", ""))
    return out


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
        # and of each: whether doing it has a result that could be checked, and whether an open implementation of it is known
        self.judged = pd.read_csv(M.CONFIG / "activities.csv", index_col=0).fillna({"open_basis": ""})
        self.kinds = self.judged.kind
        # Households (data/households): how people spend their time, and what households at each level of income spend
        households = M.ROOT / "data" / "households"
        self.time_use = pd.read_csv(households / "time_use_2017.csv").drop_duplicates("activity", keep=False).set_index("activity").hours_per_day
        self.spending = pd.read_csv(households / "spending_quintiles_2017.csv").set_index("item")
        # and how people felt during each kind of activity, by the time-use survey's six-digit code
        self.feelings = pd.read_csv(households / "wellbeing_by_activity.csv", dtype={"code": str}).set_index("code")

    def felt(self, codes: str, measure: str, time: str = "share_of_time") -> float:
        """The mean of one measure of how people felt, over the time spent in activities of these codes
        (each a code or the start of several, with semicolons between)."""
        rated = self.feelings[self.feelings.index.str.startswith(tuple(codes.split(";")))]
        return float((rated[measure] * rated[time]).sum() / rated[time].sum())

    def unpleasant(self, codes: str) -> float:
        """The share of that time that was unpleasant: pain, sadness or stress rated above happiness."""
        return self.felt(codes, "unpleasant")

    def below_rest(self, codes: str) -> float:
        """How far below the same person's other time that was not work that time was rated, in points of
        a scale from 0 to 10, over the ratings that could be compared so."""
        return self.felt(codes, "below_rest", "compared_time")

    @functools.cached_property
    def not_work(self) -> str:
        """The codes of the rated time that was not work: neither a job nor a kind of unpaid work at home."""
        work = (WORKING, *(c for codes in self.unpaid[1].time_use_codes for c in codes.split(";")))
        return ";".join(self.feelings.index[~self.feelings.index.str.startswith(work)])

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
    def software(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
        """(J, Q, R, u, titles): what Phi is made from, as matrices. Q is O*NET occupation x software
        product, one where O*NET lists the product for the occupation. R is product x capability: the
        part of the product the taxonomy places in the capability, a row adding up to one, or to
        nothing where the product is not placed. u is the specificity of each capability: the log of
        the occupations there are over those that list anything in it. J is the survey's occupation x
        O*NET occupation: one where they are the same, an equal part of one for each member of a group
        the survey publishes as one, and nothing where O*NET lists no software. titles names the
        O*NET occupations. Products are in the order of the first capability they are placed in, the
        ones not placed last."""
        ls, pc, caps = FL.listings(), FL.product_capabilities(), FL.capabilities()
        at = {c: i for i, c in enumerate(caps)}
        first = pc.capability.map(at).groupby(pc["product"]).min()
        products = sorted(ls["product"].unique(), key=lambda x: (first.get(x, len(caps)), x))
        socs = sorted(ls.soc.unique())
        Q = pd.crosstab(ls.soc, ls["product"]).reindex(index=socs, columns=products, fill_value=0).astype(float)
        R = pc.pivot(index="product", columns="capability", values="weight").reindex(index=products, columns=caps).fillna(0.0)
        listed = (Q.values @ R.values) > 0
        u = pd.Series(np.log(len(socs) / listed.sum(axis=0).clip(min=1)), index=caps)
        J = pd.DataFrame(0.0, index=self.wages[0].columns, columns=socs)
        for code in J.index:
            members = [code] if code in J.columns else [s for s in socs if s.startswith(code.rstrip("0"))]
            if members:
                J.loc[code, members] = 1 / len(members)
        named = pd.read_csv(O.OCC / "onet_occupations.csv")
        titles = named.Title.groupby(O.soc6(named["O*NET-SOC Code"])).first()[socs]
        return J, Q, R, u, titles

    @functools.cached_property
    def abilities(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """(Lambda, Gamma, judged). Lambda is the survey's occupation x O*NET ability: the occupation's
        rating of the ability, its importance (1 to 5) times the level of it needed (0 to 7), the mean
        of them where the survey publishes a group. Gamma is work activity x ability: one where O*NET
        links the ability to the general work activity the activity is filed under. judged has, for
        each ability, its name, its family, and how far machines already match a working person in it
        (config/abilities.csv), with the reason."""
        ab = pd.read_csv(O.OCC / "onet_abilities.csv")
        judged = pd.read_csv(M.CONFIG / "abilities.csv", index_col=0)
        judged["family"] = judged.index.str[:5].map(ABILITY_FAMILY)
        rated = (ab.importance * ab.level).groupby([O.soc6(ab.onet_soc), ab.ability]).mean().unstack()
        ratings = O._occupation_uses(self.wages[0].columns, rated, "mean").fillna(0.0)[judged.index]
        links = pd.read_csv(O.OCC / "onet_ability_activities.csv")
        general = pd.crosstab(links.gwa, links.ability).reindex(columns=judged.index, fill_value=0).astype(float)
        acts = self.theta.columns
        calls = general.loc[self.act.parent[acts]].set_axis(acts)
        return ratings, calls, judged

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
        hours and its value in dollars a year, the share of the time spent on it that people found unpleasant and the
        share when a bad feeling was severe, and the points they rated it below the rest of their day."""
        E, wage, _, _ = self.survey
        jobs = E.fillna(0.0).where(wage.notna(), 0.0)
        hourly = (jobs * wage.fillna(0.0)).sum() / jobs.sum() / HOURS_A_YEAR      # an occupation's mean wage, wherever it is published
        s = self.spending["all"].astype(float)
        adults = s["Number of consumer units (in thousands)"] * 1e3 * (s["People"] - s["Children under 18"])
        work = pd.read_csv(M.CONFIG / "unpaid_work.csv", dtype={"time_use_codes": str})
        hours = self.time_use[work.activity].values
        detail = work.assign(hours_per_day=hours, hours=hours * 365 * adults, usd=hours * 365 * adults * hourly[work.occupation].values,
                             unpleasant=[self.unpleasant(codes) for codes in work.time_use_codes],
                             severe=[self.felt(codes, "severe") for codes in work.time_use_codes],
                             below_rest=[self.below_rest(codes) for codes in work.time_use_codes])
        G = detail.groupby(["occupation", "work_activity"]).usd.sum().unstack(fill_value=0.0) / self.spent
        return G.reindex(index=self.wages[0].columns, columns=self.theta.columns, fill_value=0.0), detail

    @functools.cached_property
    def spent(self) -> float:
        """What households and governments spent on the needs in 2017, in dollars."""
        needs = list(self.need_dollars[0].columns)
        return A.need_demand(self.io.t)[needs].values.sum() * 1e6

    @functools.cached_property
    def unpaid_hours(self) -> pd.DataFrame:
        """X: the hours of that unpaid work for every thousand dollars spent on the needs, occupation x
        work activity. It is G before the hours are valued at a wage."""
        X = self.unpaid[1].groupby(["occupation", "work_activity"]).hours.sum().unstack(fill_value=0.0) / self.spent * 1000
        return X.reindex(index=self.wages[0].columns, columns=self.theta.columns, fill_value=0.0)

    @functools.cached_property
    def proposals(self) -> dict[str, Proposal]:
        """The proposals (proposals/*.toml), by the name each is filed under."""
        return proposals(self.theta.columns)

    @functools.cached_property
    def defined_share(self) -> pd.Series:
        """a: of each capability's tasks with no known open tool, the share that is well defined: the
        taxonomy says whether a task's result could be scored by a benchmark (yes counts whole,
        partly half). Nothing where every task has a tool."""
        closed = self.tasks[self.tasks.tool == 0]
        return closed.defined.groupby(closed.capability).mean().reindex(self.phi.columns).fillna(0.0)

    @functools.cached_property
    def open_share(self) -> pd.Series:
        """c: the share of each capability's tasks for which the taxonomy names an open-source tool."""
        return self.tasks.tool.groupby(self.tasks.capability).mean().reindex(self.phi.columns)

    @functools.cached_property
    def tasks(self) -> pd.DataFrame:
        """The taxonomy's tasks, in its order: each one's name and capability, the open-source tools
        known for it and whether its result could be scored by a benchmark, as the taxonomy has
        them, and those two as numbers: tool (one if any tool is known) and defined (t and w)."""
        x = self.tax[self.tax.level == 2].set_index("id")
        return pd.DataFrame({"name": x.name, "capability": x.parent, "tools": x.open_tools, "benchmarkable": x.benchmarkable,
                             "tool": (x.open_tools != "").astype(float), "defined": x.benchmarkable.map(DEFINED)})

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
LAMBDA, GAMMA, ALPHA, MU, RHO = "Λ", "Γ", "α", "μ", "ρ"
PI, TAU, ETA, CHI, PSI = "π", "τ", "η", "χ", "ψ"       # the account in hours: the Greek of p and of h, and tau for time
KAPPA, SIGMA = "κ", "σ"                                 # and whether those hours have been going anyway
ZETA = "ζ"                                              # and the part of them people find unpleasant
BETA = "β"                                              # the hours each sector works, which pi and kappa are both made from
XI = "ξ"                                                # and what they cost those who work them, in wellbeing
WORKING = "0501"                                        # the time-use survey's code for working at a job
POINT_HOUR = 1e6 / (365.25 * 24)                        # one point of wellbeing for one hour, in microWELLBYs: a WELLBY is a point for a year
# a Greek letter's name in a file, and its bold
GREEK = {THETA: ("Theta", "&#x1D6AF;"), PHI: ("Phi", "&#x1D6BD;"), OMEGA: ("omega", "&#x1D6DA;"), LAMBDA: ("Lambda", "&#x1D6B2;"),
         GAMMA: ("Gamma", "&#x1D6AA;"), ALPHA: ("alpha", "&#x1D6C2;"), MU: ("mu", "&#x1D6CD;"), RHO: ("rho", "&#x1D6D2;"),
         PI: ("pi", "&#x1D6D1;"), TAU: ("tau", "&#x1D6D5;"), ETA: ("eta", "&#x1D6C8;"), CHI: ("chi", "&#x1D6D8;"), PSI: ("psi", "&#x1D6D9;"),
         KAPPA: ("kappa", "&#x1D6CB;"), SIGMA: ("sigma", "&#x1D6D4;"), ZETA: ("zeta", "&#x1D6C7;"), XI: ("xi", "&#x1D6CF;"), BETA: ("beta", "&#x1D6C3;")}
ABILITY_FAMILY = {"1.A.1": "Cognitive", "1.A.2": "Psychomotor", "1.A.3": "Physical", "1.A.4": "Sensory"}   # O*NET's four families of abilities, by the start of the ability's code
HOURS_A_YEAR = 2080                   # a year of full-time work, which turns a yearly wage into an hourly one
# the terms, in the order the account's table lists them
GROUPS = [
    ("The account", ["x", "p", "f", "h"]),
    ("Needs", ["d", "Y", OMEGA]),
    ("The input-output model", ["L", "A", "B", "D", "U", "V", "g", "q"]),
    ("Capital", ["K", "F", "H", "S", "z"]),
    ("Value added", ["v", "r", "y"]),
    ("Work", ["W", "P", "T", "E", "M"]),
    ("Work activities", [THETA, "G", "m", "e", "s", "b"]),
    ("Hours", [ETA, TAU, PI, BETA, CHI, "Z", "l", "X", ZETA, XI, KAPPA, SIGMA]),
    ("Proposals", [PSI, "C"]),
    ("Abilities", [RHO, ALPHA, MU, LAMBDA, GAMMA]),
    ("Software capabilities", ["k", "o", PHI, "J", "Q", "R", "u", "a", "c", "N", "t", "w"]),
]
TERMS = [k for _, keys in GROUPS for k in keys]
DEFINED = {"yes": 1.0, "partly": 0.5, "no": 0.0}     # how far a task the taxonomy calls benchmarkable counts as well defined
PER_NEED = "dxv"                      # the vectors there is one of for each need, written with a subscript n
# what each computed term is made from; a term that is not here is data
USES = {ETA: [TAU, "m", "e"], TAU: [PI, THETA, "X"], PI: [BETA, "Z"], BETA: [CHI, OMEGA, "v"], CHI: ["l", "g", "D", "r"], "Z": ["T", "E"], "X": ["Y"],
        PSI: ["C", TAU, "e"], KAPPA: [SIGMA, BETA, "Z", THETA, PI], SIGMA: ["l", "g", "V"],
        ZETA: [PI, THETA, "X"], XI: [PI, THETA, "X"],
        "x": ["L", "d"], "p": [OMEGA, "v", "W"], "k": ["p", THETA, "G", "s", PHI], "h": ["f", "m", "e"], RHO: [ALPHA, MU], ALPHA: ["p", THETA, "G", "m", "e", GAMMA, LAMBDA], "o": ["k", "a", "c"], PHI: ["J", "Q", "R", "u"], "u": ["Q", "R"], "a": ["N", "t", "w"], "c": ["N", "t"], "b": ["f", "s"],
        "f": ["p", THETA, "G"], "G": ["E", "M", "Y"], "d": ["Y"], "L": ["A"], "A": ["B", "D"], "B": ["U", "K", "g"],
        "D": ["V", "q"], "g": ["V"], "q": ["V"], "K": ["F", "H", "S"], "S": ["z", "H"], "z": ["g", "H"],
        "v": ["r", "x"], "r": ["y", "g", "D"], "W": ["P"], "P": ["T", "E", "M"]}


def stem(key: str) -> str:
    """The name a term's files go by. A matrix is filed as a matrix and a vector as a vector, so
    that no two differ by a letter's case alone: some file systems cannot tell D from d."""
    return f"{'matrix' if key.isupper() else 'vector'}-{GREEK[key][0] if key in GREEK else key}"


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
ORDER_PARTS = "vector-h-parts.js"    # what each activity is made of and what is judged of it, fetched when a row of h is first marked
TASK_PARTS = "vector-o-parts.js"     # k, a, c and the tasks of each capability, fetched when a row of o is first marked
ORDER_ROWS = 25                      # the rows of o in view when its picture opens: the first of the order to work in
MATRIX_PART_CUT = 1e-5     # entries of B under a thousandth of a cent are left out of that file
MATRIX_WIDTH, MATRIX_HEIGHT = 802, 780   # the most a picture takes of the page, in CSS pixels
# A matrix at least this many times as tall as it is wide is drawn in a picture of a fixed height.
# With few columns they are locked in view, each this wide at most (a lone column wider), and
# zooming changes the rows alone. With more than LOCK_COLUMNS the picture is stretched to hold
# the whole matrix, and zooming brings both its rows and its columns closer.
THIN, THIN_COLUMN, THIN_VECTOR, THIN_HEIGHT = 8, 110, 170, 620
LOCK_COLUMNS = 12
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
    # an occupation's rating of an ability: importance, 1 to 5, times level, 0 to 7
    "rating": {"unit": 1e-2, "cut": 1e-2, "scale": (1.0, 40.0), "ticks": ("1", "2.5", "6", "16", "40"),
               "blank": "zero", "small": "not rated", "colour": "the rating", "in_cell": "to the nearest whole"},
    # hours of work for every thousand dollars
    "hours": {"unit": 1e-4, "cut": 1e-3, "scale": (1e-3, 100.0), "ticks": ("0.001", "0.01", "0.1", "1", "10", "100"),
              "blank": "under 0.001 hours per $1,000", "small": "under a thousandth of an hour", "colour": "hours per thousand dollars",
              "in_cell": "in hours"},
    # hours worked in a year, in millions
    "hours_worked": {"unit": 0.1, "cut": 0.05, "scale": (1.0, 1e4), "ticks": ("1M", "10M", "100M", "1B", "10B"),
                     "blank": "under 50,000 hours", "small": "under fifty thousand hours", "colour": "millions of hours",
                     "in_cell": "in millions of hours, with k for thousands"},
    # wellbeing, in microWELLBYs for every thousand dollars; it can be negative
    "wellbeing": {"unit": 1e-2, "cut": 0.1, "scale": (0.1, 1e3), "ticks": ("0.1", "1", "10", "100", "1,000"),
                  "blank": "under 0.1 microWELLBYs per $1,000", "small": "under a tenth of a microWELLBY",
                  "colour": "microWELLBYs per thousand dollars", "in_cell": "in microWELLBYs"},
    # a number with no unit, such as a logarithm
    "number": {"unit": 1e-3, "cut": 1e-3, "scale": (0.1, 10.0), "ticks": ("0.1", "1", "10"),
               "blank": "under 0.001", "small": "under a thousandth", "colour": "the number", "in_cell": "to two places"},
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


_ITALIC = {"h": "&#x210E;", "α": "&#x1D6FC;", "γ": "&#x1D6FE;", "θ": "&#x1D703;", "λ": "&#x1D706;", "μ": "&#x1D707;", "ρ": "&#x1D70C;"}


def _elt(shown: str, sub: str, page: str = "", here: str = "") -> str:
    """One entry of a matrix or vector: an italic letter with subscripts, linked to the page of the
    term it is an entry of (page, a key of SYMBOL_PAGES) except on that page."""
    if not page or page == here:
        return _sub(shown, sub)
    # Unicode's mathematical italic letters, among which h has a place of its own, and the Greek ones
    italic = _ITALIC.get(shown) or f"&#x{0x1D44E + ord(shown) - ord('a'):X};"
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
    weight = (_sub("&omega;", "n") if here == OMEGA else           # the weight of need n
              f'<mi><a href="{SYMBOL_PAGES[OMEGA]}">&#x1D714;<sub><i>n</i></sub></a></mi>')
    less_open = _paren(f"{_ONES}<mo>&minus;</mo>{S('e')}")
    if key == "p":        # a need dollar by occupation, however the needs are weighed
        return S("p", T=True), f'{_sum("n")}{weight}{_TIMES}{V("v", T=True)}{_TIMES}{S("W")}'
    if key == BETA:       # the same dollar in hours, by sector: the value added a sector earns from it, times its hours for each dollar of value added
        return S(BETA), f'{_diag(S(CHI))}{_TIMES}{_sum("n")}{weight}{_TIMES}{V("v")}'
    if key == PI:         # and by occupation: each sector's hours divided among occupations by their jobs
        return S(PI, T=True), f'{S(BETA, T=True)}{_TIMES}{S("Z")}'
    if key == TAU:        # by what the work is, with the unpaid hours at home
        return S(TAU, T=True), f'{S(PI, T=True)}{_TIMES}{S(THETA)}<mo>+</mo><msup>{_ONES}{_TR}</msup>{_TIMES}{S("X")}'
    if key == ETA:        # and the part of it that is well defined and has no open implementation
        return S(ETA), f'{S(TAU)}{_HADAMARD}{S("m")}{_HADAMARD}{less_open}'
    if key == CHI:        # an industry's hours for each dollar it makes, mixed into commodities, over the commodity's value added per dollar
        return S(CHI, T=True), _TIMES.join([S("l", T=True), _inv(_diag(S("g"))), S("D"), _inv(_diag(S("r")))])
    if key == "Z":        # the jobs of the surveyed industries that cover a sector, as shares of a row
        TE = f'{S("T")}{_TIMES}{S("E")}'
        return S("Z"), f'{_inv(_diag(TE + _TIMES + _ONES))}{_TIMES}{TE}'
    if key == KAPPA:      # the mean of sigma over the sectors an activity is done in for pay, weighted by its paid hours in each
        counted = f'<msup>{_paren(S(SIGMA) + _HADAMARD + S(BETA))}{_TR}</msup>'             # each sector's hours, counted at what they still take
        return S(KAPPA, T=True), _TIMES.join([counted, S("Z"), S(THETA), _inv(_diag(S(THETA, T=True) + _TIMES + S(PI)))])
    if key == PSI:        # the hours in the parts of activities a proposal claims, less what is already open
        return S(PSI), f'{S("C", T=True)}{_TIMES}{_paren(f"{S(TAU)}{_HADAMARD}{less_open}")}'
    if key == "f":        # the same dollar by what the work is, with the unpaid work done at home
        return S("f", T=True), f'{S("p", T=True)}{_TIMES}{S(THETA)}<mo>+</mo><msup>{_ONES}{_TR}</msup>{_TIMES}{S("G")}'
    if key == "k":        # and the information work in it, paid and unpaid, by the software it is done with
        work = f'{S("p")}{_HADAMARD}{S(THETA)}{_TIMES}{S("s")}<mo>+</mo>{S("G")}{_TIMES}{S("s")}'
        return S("k", T=True), f'<msup>{_paren(work)}{_TR}</msup>{_TIMES}{S(PHI)}'
    if key == "h":        # entry by entry: what goes to an activity, that is well defined, and has no open implementation
        return S("h"), f'{S("f")}{_HADAMARD}{S("m")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("e")}")}'
    if key == RHO:        # of the gap that falls on an ability, the part machines do not yet match
        return S(RHO), f'{S(ALPHA)}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S(MU)}")}'
    if key == ALPHA:      # the gap of each occupation in each activity, divided among the abilities the activity calls on, by the occupation's ratings
        E = lambda letter, script, page: _elt(letter, script, page, here)
        work = _paren(f'{E("p", "o", "p")}{_TIMES}{E("θ", "oa", THETA)}<mo>+</mo>{E("g", "oa", "G")}')
        gap_ = f'{work}{_TIMES}{E("m", "a", "m")}{_TIMES}{_paren(f"<mn>1</mn><mo>&minus;</mo>{E('e', 'a', 'e')}")}'
        part = (f'<mfrac><mrow>{E("γ", "ak", GAMMA)}{_TIMES}{E("λ", "ok", LAMBDA)}</mrow>'
                f'<mrow>{_sum("l")}{E("γ", "al", GAMMA)}{_TIMES}{E("λ", "ol", LAMBDA)}</mrow></mfrac>')
        return E("α", "k", ALPHA), f'{_sum("o")}{_sum("a")}{gap_}{_TIMES}{part}'
    if key == "o":        # entry by entry: what is paid for work with a capability, that is well defined, and is not open
        return S("o"), f'{S("k")}{_HADAMARD}{S("a")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("c")}")}'
    if key == PHI:        # an occupation's products in each capability, weighted by how specific the capability is, as shares of a row
        QR = f'{S("Q")}{_TIMES}{S("R")}'
        return S(PHI), _TIMES.join([S("J"), _inv(_diag(S("Q") + _TIMES + _ONES)), _diag(QR + _TIMES + _ONES),
                                    _inv(_diag(QR + _TIMES + S("u"))), '<mspace width="0.17em"/>' + QR, _diag(S("u"))])
    if key == "u":        # how few occupations list anything in the capability
        O_k = "<msub><mi>O</mi><mi>k</mi></msub>"
        return _elt("u", "k", "u", here), f'<mrow><mi>ln</mi><mo>&#x2061;</mo><mfrac><mi>O</mi>{O_k}</mfrac></mrow>'
    if key == "a":        # of a capability's tasks that no open tool does, the part that is well defined
        def over(*more):
            entries = _TIMES.join([_elt("n", "ij", "N", here), *more, _paren(f'<mn>1</mn><mo>&minus;</mo>{_elt("t", "j", "t", here)}')])
            return f'<mrow>{_sum("j")}{entries}</mrow>'
        return _elt("a", "i", "a", here), f'<mfrac>{over(_elt("w", "j", "w", here))}{over()}</mfrac>'
    if key == "c":        # and the part of its tasks that an open tool does
        return S("c"), f'{_inv(_diag(S("N") + _TIMES + _ONES))}{_TIMES}{S("N")}{_TIMES}{S("t")}'
    if key == "b":        # what software could not do: the work that needs a body or a person
        return S("b"), f'{S("f")}{_HADAMARD}{_paren(f"{_ONES}<mo>&minus;</mo>{S("s")}")}'
    if key == "gap":      # and the whole of it
        return "<mi>gap</mi>", f'<msup>{_ONES}{_TR}</msup>{_TIMES}{S("h")}'
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


EQUATIONS = [ETA, TAU, PI, BETA, CHI, "Z", KAPPA, PSI, "x", "p", "f", "h", RHO, ALPHA, "k", "o", PHI, "u", "a", "c", "b", "d", "L", "A", "B", "D", "g", "q", "K", "S", "v", "r", "W", "P"]   # the terms equation() defines

# What one entry of each term is measured in, in a few words. A unit that has a page is written
# [as it reads here|the name its page is filed under], and is a link wherever this is set as HTML.
_WORK = "[work dollars|work-dollar] per [need dollar|need-dollar]"
_MILLIONS, _MARK = "[millions of dollars|million-dollars], in 2017", "[one or zero|one-or-zero]"
_HOURS = "[hours|hour] of work per thousand [need dollars|need-dollar]"
_STILL = f"hours in {HR.YEAR} for each hour in {HR.SINCE}, a [number|number] with no unit"
MEASURED_IN = {
    ETA: _HOURS, TAU: _HOURS, PI: _HOURS, BETA: _HOURS, "X": _HOURS, PSI: _HOURS,
    CHI: "[hours|hour] of work per thousand [value-added dollars|value-added-dollar]",
    "Z": "the occupation's [share|share] of the sector's jobs",
    "l": "millions of [hours|hour] a year, in 2016",
    "C": "the part of the activity the proposal would do, a [share|share] of one",
    KAPPA: _STILL, SIGMA: _STILL,
    ZETA: "unpleasant [hours|hour] of work per thousand [need dollars|need-dollar]",
    XI: "[experienced microWELLBYs|microwellby] per thousand [need dollars|need-dollar]",
    "x": "[commodity dollars|commodity-dollar] produced per [need dollar|need-dollar]",
    "p": _WORK, "k": _WORK, "o": _WORK, "f": _WORK, "h": _WORK, "b": _WORK, "G": _WORK,
    ALPHA: _WORK, RHO: _WORK, GAMMA: _MARK,
    LAMBDA: "the occupation's rating of the ability, a [number|number] with no unit",
    MU: "the part of the ability machines already match, a [share|share] of one",
    "m": "the well-defined part of the activity, a [share|share] of one",
    "e": "the part of the activity that has an open implementation, a [share|share] of one",
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
    "J": "the O*NET occupation's [share|share] of the survey's occupation", "Q": _MARK,
    "R": "the part of the product placed in the capability, a [share|share] of one",
    "u": "a logarithm, a [number|number] with no unit",
    "N": _MARK, "t": _MARK, "w": "the well-defined part of the task, a [share|share] of one",
    THETA: "[share|share] of the occupation's work",
    "a": "[share|share] of the capability's tasks that have no open tool",
    "c": "[share|share] of the capability's tasks",
}
# What a row or a column can be one of: the name its page is filed under, then one of it, then several.
COUNTED = {
    "commodity": ("commodity", "commodities"), "industry": ("industry", "industries"), "need": ("need", "needs"),
    "weighting": ("way of weighing the needs", "ways of weighing the needs"),
    "investor-kind": ("kind of investor", "kinds of investor"), "occupation": ("occupation", "occupations"),
    "onet-occupation": ("O*NET occupation", "O*NET occupations"), "product": ("software product", "software products"),
    "surveyed-industry": ("surveyed industry", "surveyed industries"),
    "ability": ("ability", "abilities"),
    "capability": ("software capability", "software capabilities"), "task": ("task", "tasks"),
    "activity": ("work activity", "work activities"),
    "proposal": ("proposal", "proposals"),
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
    rows: str                      # what the rows are, ending in their unit: "input commodities", "a dollar of each need"
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
        """Tall and narrow: drawn in a picture of a fixed shape, not of its own."""
        return self.values.shape[0] >= THIN * self.values.shape[1]
    @property
    def lock(self) -> bool:
        """And with few enough columns to keep them all in view, however close the rows are."""
        return self.thin and self.values.shape[1] <= LOCK_COLUMNS
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
    # what Phi is made from: O*NET's occupations and the software products it lists for them
    J, listing, placing, specificity, onet_titles = d.software
    major_of = {c[:2]: g for c, g in occ.major.items()}
    onet_major = pd.Series({c: major_of[c[:2]] for c in listing.index})
    product_names = pd.Series(listing.columns, index=listing.columns)
    not_placed = "Not placed"
    product_group = pd.Series([domain.iloc[row.argmax()] if row.any() else not_placed for row in (placing.values > 0)], index=placing.index)
    soc_short = {g: SOC_SHORT[c[:2]] for c, g in occ.major.items()}
    product_order = ("Products are in the order of the first capability they are placed in, and by name within it, with those the "
                     "taxonomy does not place last.")
    # and its tasks, in the same order
    tasks = d.tasks
    by_task = dict(row_names=tasks.name, row_groups=domain[tasks.capability].set_axis(tasks.index))
    task_order = f"Tasks are in the taxonomy's order within its {domain.nunique()} domains."
    member = pd.DataFrame((np.array(caps, dtype=object)[:, None] == tasks.capability.to_numpy(dtype=object)[None, :]).astype(float), index=caps, columns=tasks.index)   # N
    info = (d.kinds.reindex(act.index) == "information").astype(float)        # s
    # the three ways of weighing the needs, which every term from p on has a column for
    weights, (unpaid, unpaid_detail) = d.weights, d.unpaid
    ways = pd.Series({"equal": "Needs counted equally", "spending": "By spending on each", "poorest": "By the poorest fifth's budget"})
    by_weighing = dict(col_names=ways, col_groups=pd.Series("Ways of weighing the needs", index=ways.index), col_tip="Needs weighed",
                       col_is="Column, the way the needs are weighed:", cols="a need dollar under each way of weighing the needs", axis="Ways of weighing the needs")
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
    defined, opened = (d.judged[c].map(DEFINED).reindex(act.index) for c in ("well_defined", "open"))      # m, e
    by_activity_overhang = to_activity.mul(defined * (1 - opened), axis=0)                 # h
    # the same in hours: each industry's hours for a dollar of its output, mixed into commodities, over the commodity's value added per dollar
    hours_worked = HR.industry_hours(t)                                                    # l, millions of hours
    made_by = t.V.values / np.where(t.q.values > 0, t.q.values, np.inf)[None, :]
    per_value_added = A.value_added_share(m)
    hours_per = pd.Series(np.divide((hours_worked / t.g).values @ made_by * 1000, per_value_added.values, out=np.zeros(len(per_value_added)),
                                    where=per_value_added.values > 1e-9), index=per_value_added.index)             # chi, hours per thousand dollars
    jobs = T.values @ E.fillna(0.0).values
    covered = jobs.sum(axis=1, keepdims=True)
    job_share = pd.DataFrame(np.divide(jobs, covered, out=np.zeros_like(jobs), where=covered > 0), index=T.index, columns=E.columns)     # Z
    by_sector_hours = (d.need_value_added.loc[com].values * hours_per.loc[com].values[:, None]) @ weights.values
    paid_hours = frame(job_share.loc[com].values.T @ by_sector_hours, occ.index)            # pi
    unpaid_hours = d.unpaid_hours                                                           # X
    hours_to_activity = frame(d.theta.values.T @ paid_hours.values, act.index).add(unpaid_hours.sum(), axis=0)      # tau
    hours_overhang = hours_to_activity.mul(defined * (1 - opened), axis=0)                 # eta
    # the hours of it that people find unpleasant: paid hours at the rate of working at a job, unpaid hours at the rate of each kind of work at home
    unpleasant_at_home = ((unpaid_detail.hours * unpaid_detail.unpleasant).groupby(unpaid_detail.work_activity).sum()
                          .reindex(act.index).fillna(0.0) / d.spent * 1000)
    unpleasant_hours = (frame(d.theta.values.T @ paid_hours.values, act.index) * d.unpleasant(WORKING)).add(unpleasant_at_home, axis=0)   # zeta
    # and what it costs those who do it: each hour at the points people rate such work below the rest of their own day
    lost_at_home = ((unpaid_detail.hours * unpaid_detail.below_rest).groupby(unpaid_detail.work_activity).sum()
                    .reindex(act.index).fillna(0.0) / d.spent * 1000)
    wellbeing_lost = (frame(d.theta.values.T @ paid_hours.values, act.index) * d.below_rest(WORKING)).add(lost_at_home, axis=0) * POINT_HOUR   # xi
    # whether those hours have been going anyway: each sector's hours for a unit of real value added, now against then,
    # and for each activity the mean of that over the sectors it is done in for pay, weighted by its paid hours in each
    still = HR.sector_still_needed(t)                                                       # sigma
    def of_activities(sector_hours: np.ndarray) -> np.ndarray:
        placed = (job_share.loc[com].values * sector_hours[:, None]) @ d.theta.values       # sector x activity: the activity's paid hours in the sector
        total = placed.sum(axis=0)
        return np.divide(still.loc[com].values @ placed, total, out=np.zeros(len(total)), where=total > 0)
    activity_still = frame(np.column_stack([of_activities(by_sector_hours[:, j]) for j in range(weights.shape[1])]), act.index)      # kappa
    span = f"{HR.YEAR} for each hour in {HR.SINCE}"
    # what each proposal claims of each activity, and the hours that comes to
    proposed = pd.Series({k: x.name for k, x in d.proposals.items()})
    claims = pd.DataFrame({k: x.does.share for k, x in d.proposals.items()}).reindex(act.index).fillna(0.0)      # C
    would_do = frame(claims.values.T @ hours_to_activity.mul(1 - opened, axis=0).values, claims.columns)          # psi
    of_proposals = pd.Series("Proposals", index=claims.columns)
    proposal_order = "Proposals are in the order of their files' names."
    production_account = ("The integrated industry-level production account of the U.S. Bureau of Economic Analysis and Bureau of "
                          f"Labor Statistics, 1947 to 2016: {_file('data/bea/hours_2016.csv')}.")
    # the gap by ability: each occupation's gap in each activity, divided among the abilities the activity calls on, by the occupation's ratings
    ratings, calls, of_ability = d.abilities
    called = ratings.values @ calls.values.T              # occupation x activity: the occupation's ratings of what the activity calls on
    def gap_by_ability(paid: np.ndarray) -> np.ndarray:
        gap_ = (d.theta.values * paid[:, None] + unpaid.values) * (defined * (1 - opened)).values[None, :]
        return ((np.divide(gap_, called, out=np.zeros_like(gap_), where=called > 0) @ calls.values) * ratings.values).sum(axis=0)
    by_ability_gap = frame(np.column_stack([gap_by_ability(by_occ[c].values) for c in weights.columns]), ratings.columns)      # alpha
    matched = of_ability.machines.map(DEFINED)                                                                                # mu
    of_abilities = dict(row_names=of_ability.name, row_groups=of_ability.family)
    ability_order = "Abilities are in O*NET's order within its four families."
    out = [
        # --- the account
        Sheet("x", "the output behind a dollar of each need", "per_dollar", xn.loc[com], t.names,
              rows="produced commodities", cols="a dollar of each need", **by_need,
              entries="Dollars of the commodity produced, at every stage of supply, to deliver a dollar of the need.",
              row_tip="Produced", col_tip="For a dollar of", row_is="Row, the commodity produced:", axis="Needs: one dollar of each",
              code="plenty/analysis.py", sums="cols"),
        Sheet("p", "the occupations a need dollar pays", "per_dollar", by_occ, **by_occupation_row, **by_weighing,
              rows="paid occupations",
              entries="Dollars per need dollar that the sectors behind the needs pay the occupation.",
              note="What a sector pays is its whole value added, shared out the way its payroll is.",
              row_tip="Occupation", code="plenty/site.py", sums="cols"),
        Sheet("k", "the part of a need dollar that pays for work done with each capability", "per_dollar", flow,
              **by_capability, **by_weighing, rows="the taxonomy's software capabilities",
              entries="Dollars per need dollar that pay for the information work of the people who work with the capability, "
                      "with the unpaid information work done at home. It is the work the software serves, not what the software "
                      "earns.",
              note="Only information work is placed here. Work that needs a body or a person is not, and nor is the work of "
                   "occupations that list no software, or software the taxonomy does not place.",
              row_tip="Capability", code="plenty/flows.py", sums="cols", order=capability_order),
        Sheet("h", "the overhang of each work activity", "per_dollar", by_activity_overhang, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Dollars per need dollar, paid and unpaid, that go to the activity, times the part of it that is well "
                      "defined, times the part that has no known open implementation.",
              note=f"A column adds up to the gap. Sorted, it is the order to work in, as far as the two judgments it rests on "
                   f"can be trusted. Work that needs a body is in it: {_m(_sym('s'))} says which, and a capability of that "
                   "kind needs a machine to act through as well as the processing.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
        Sheet(RHO, "the part of the gap machines do not yet match, by ability", "per_dollar", by_ability_gap.mul(1 - matched, axis=0),
              **of_abilities, **by_weighing, rows="O*NET's abilities",
              entries="Dollars per need dollar: the part of the gap that falls on the ability, times the part of the ability "
                      "in which machines do not yet match a working person.",
              note=f"It rests on three layers of judgment: what is well defined, what has an open implementation, and what "
                   f"machines can do. And the abilities are what work demands of a person, which is not what it demands of "
                   f"a machine: see {_m(_sym(ALPHA))}.",
              row_tip="Ability", code="plenty/site.py", sums="cols", order=ability_order),
        Sheet(ALPHA, "the gap by the ability it calls on", "per_dollar", by_ability_gap, **of_abilities, **by_weighing,
              rows="O*NET's abilities",
              entries="Dollars per need dollar: the part of the gap that falls on the ability. An occupation's gap in an "
                      "activity is divided among the abilities the activity calls on, in proportion to the occupation's "
                      "ratings of them.",
              source=f"The sums run over occupations {_m('<mi>o</mi>')} and work activities {_m('<mi>a</mi>')}. The first "
                     f"factor is the occupation's part of {_m(_sym('h'))} in the activity, and the fraction is ability "
                     f"{_m('<mi>k</mi>')}'s part of it.",
              note="A column adds up to the gap, less the little of it in occupations O*NET does not rate. The abilities say "
                   "what work demands of a person. Cleaning falls on strength, stamina and reach, because that is what tires "
                   "a cleaner. Seeing what is dirty and handling whatever is there are so easy for a person that they are "
                   "not rated, and they are the hard part for a machine.",
              row_tip="Ability", code="plenty/site.py", sums="cols", order=ability_order),
        Sheet(MU, "the part of each ability machines already match", "share", **lone(matched, MU, "Machines match", "share"), **of_abilities,
              rows="O*NET's abilities",
              entries="One where machines match a working person in the ability across the ordinary run of work, a half where "
                      "they match in some conditions or on part of it, and zero where they fall well short.",
              source=f"Judgment, made by hand, one ability at a time, with the reason: {_file('config/abilities.csv')}.",
              note="It is judged of a machine that has the ability in general, in the varied conditions of ordinary work, "
                   "whether or not it is open, and not of one built for a single job. The judgments are of the state of the "
                   "art as recalled, and have not been checked against measurements.",
              row_tip="Ability", code="plenty/site.py", order=ability_order),
        Sheet(LAMBDA, "each occupation's rating of each ability", "rating", ratings, occ.title, of_ability.name,
              rows="rated occupations", cols="O*NET's abilities",
              entries="The importance of the ability to the occupation, from 1 to 5, times the level of it the occupation "
                      "needs, from 0 to 7. An occupation the survey publishes only as a group takes the mean of the "
                      "occupations in the group.",
              source=f"O*NET 31.0, the U.S. Department of Labor's database of occupations, in its table of abilities: "
                     f"{_file('data/occupations/onet_abilities.csv')}. The ratings are made by occupational analysts.",
              note=f"{int((ratings.sum(axis=1) == 0).sum())} of the survey's {len(ratings)} occupations have no ratings.",
              row_tip="Occupation", col_tip="Ability", axis="Abilities", code="plenty/site.py",
              row_groups=occ.major, col_groups=of_ability.family, short=soc_short,
              order=f"Occupations are in the order of the Standard Occupational Classification within its 22 major groups. {ability_order}"),
        Sheet(GAMMA, "the abilities each work activity calls on", "mark", calls, act.name, of_ability.name,
              rows="O*NET's intermediate work activities", cols="O*NET's abilities",
              entries="One where O*NET links the ability to the general work activity that the activity is filed under, and "
                      "zero elsewhere.",
              source=f"O*NET 31.0, in its table linking abilities to work activities: "
                     f"{_file('data/occupations/onet_ability_activities.csv')}. The links are to its "
                     f"{d.act.parent[act.index].nunique()} general work activities, so the activities under one of those "
                     "have the same row.",
              note=f"{int((calls.sum(axis=0) == 0).sum())} of the {calls.shape[1]} abilities are linked to no activity.",
              row_tip="Activity", col_tip="Ability", axis="Abilities", code="plenty/site.py",
              row_groups=act.parent.map(d.act.name), col_groups=of_ability.family,
              blanks=("does not call on it", "zero"), marked="calls on it", sums="both",
              order=f"{activity_order} {ability_order}"),
        Sheet("o", "the overhang of each software capability", "per_dollar", overhang,
              **by_capability, **by_weighing, rows="the taxonomy's software capabilities",
              entries="Dollars per need dollar: what is paid for information work done with the capability, times the share of "
                      "its tasks that have no known open tool, times the share of those that is well defined.",
              note=f"It is the same question as {_m(_sym('h'))} asks, put to the software that information work is done with "
                   "today and not to the work itself. Work that needs a body is not in it.",
              row_tip="Capability", code="plenty/site.py", sums="cols", order=capability_order),
        # --- hours
        Sheet(ETA, "the overhang of each work activity, in hours", "hours", hours_overhang, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Hours of work for every thousand need dollars, paid and unpaid, that go to the activity, times the part "
                      "of it that is well defined, times the part that has no known open implementation.",
              note=f"It is {_m(_sym('h'))} counted in hours and not in dollars. An hour is the same hour of someone's life "
                   "whatever it is paid, so work that is paid little, or nothing, counts for more here. A column adds up to "
                   "the gap in hours.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
        Sheet(TAU, "the hours of work behind a need dollar, by activity", "hours", hours_to_activity, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Hours of work for every thousand need dollars, paid and unpaid, that go to the activity.",
              note="The paid hours of sectors the survey of occupations does not reach, and of occupations whose tasks are "
                   "not rated, are not placed.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
        Sheet(PI, "the paid hours of each occupation", "hours", paid_hours, **by_occupation_row, **by_weighing,
              rows="working occupations",
              entries="Hours the occupation works for every thousand need dollars, in the sectors behind the needs.",
              note="A sector's hours are divided among its occupations by their jobs, as if every job had the same hours. "
                   f"Sectors the survey does not reach hold {(by_sector_hours.sum(axis=0)[0] - paid_hours.equal.sum()) / by_sector_hours.sum(axis=0)[0] * 100:.0f}% "
                   "of the paid hours, with the needs counted equally, and those are not placed.",
              row_tip="Occupation", code="plenty/site.py", sums="cols"),
        Sheet(BETA, "the hours each sector works behind a need dollar", "hours", frame(by_sector_hours, com), t.names, **by_weighing,
              rows="sectors that do the work, each a commodity",
              entries="Hours worked in the sector for every thousand need dollars: the value added it earns from them, "
                      "times its hours for each dollar of value added.",
              note=f"These are all the paid hours behind the needs. {_m(_sym(PI))} places them in occupations, and can "
                   "place only those of sectors the survey of occupations reaches.",
              row_tip="Sector", code="plenty/site.py", sums="cols"),
        Sheet(CHI, "the hours of work in a value-added dollar of each commodity", "hours",
              **lone(hours_per.loc[com], CHI, "Hours per thousand dollars of value added", "hours"), row_names=t.names,
              rows="produced commodities",
              entries="Hours worked for every thousand dollars of the commodity's value added: its makers' hours per dollar "
                      "of output, mixed by their shares of it, over its value added per dollar.",
              note="The hours are of 2016 and the dollars of 2017.",
              row_tip="Commodity", code="plenty/site.py"),
        Sheet("Z", "the occupations that hold each sector's jobs", "share", job_share.loc[com], t.names, occ.title,
              rows="sectors, each a commodity", cols="employed occupations",
              entries="The occupation's share of the jobs in the surveyed industries that cover the sector. A row adds up to "
                      "one, or is empty where the sector is not measured.",
              note=f"It divides a sector's hours, where {_m(_sym('W'))} divides its pay.",
              row_tip="Sector", col_tip="Share of its jobs held by", col_is="Column, the occupation:",
              axis="Occupations: their share of each sector's jobs", code="plenty/site.py", **by_occupation),
        Sheet("l", "the hours worked in each industry", "hours_worked",
              **lone(hours_worked.loc[ind], "l", "Hours worked in 2016", "million hours"), row_names=t.ind_names,
              rows="employing industries",
              entries="Millions of hours worked in the industry in 2016, by employees and the self-employed.",
              source=f"{production_account} It has {len(HR.published())} industries. The hours of each are divided among the "
                     "benchmark's industries filed under it in proportion to what each paid its employees.",
              note="The Bureaus call the account experimental. Housing, which pays nobody, gets no hours.",
              row_tip="Industry", code="plenty/hours.py", sums="both"),
        Sheet("X", "the unpaid hours of work at home", "hours", unpaid_hours, occ.title, act.name,
              rows="the paid equivalent of the work, an occupation", cols="the kind of work, a work activity",
              entries="Hours of unpaid work at home for every thousand dollars spent on the needs.",
              source=f"The hours are from the American Time Use Survey of the U.S. Bureau of Labor Statistics, 2017, and the number "
                     f"of adults from its Consumer Expenditure Survey: {_file('data/households/')}. Which activities at home are "
                     f"work, and which work activity each is, is judgment: {_file('config/unpaid_work.csv')}.",
              note=f"It comes to {unpaid_hours.values.sum():.0f} hours for every thousand dollars spent on the needs: "
                   f"{unpaid_detail.hours_per_day.sum():.1f} hours a day for each adult, {unpaid_detail.hours.sum() / 1e9:.0f} billion "
                   f"hours a year. It is {_m(_sym('G'))} before the hours are valued at a wage, and is the same however the "
                   "needs are weighed.",
              row_tip="Occupation", col_tip="Activity", axis="Work activities", code="plenty/site.py",
              row_groups=occ.major, col_groups=act.parent.map(d.act.name), short={g: SOC_SHORT[c[:2]] for c, g in occ.major.items()},
              sums="both", order=f"Occupations are in {occupation_order[len('occupations in '):]}. {activity_order}"),
        Sheet(ZETA, "the unpleasant hours of work behind a need dollar, by activity", "hours", unpleasant_hours, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Hours of work for every thousand need dollars, paid and unpaid, that go to the activity and that the "
                      "people doing such work find unpleasant.",
              source=f"The Well-Being Module of the American Time Use Survey, U.S. Bureau of Labor Statistics, 2010, 2012, 2013 "
                     f"and 2021: {_file('data/households/wellbeing_by_activity.csv')}. Each respondent rated three of the day's "
                     "activities from 0 to 6 on six feelings, and the time of an activity is called unpleasant when pain, sadness "
                     f"or stress was rated above happiness. The paid hours of an activity, in {_m(_sym(TAU))}, count at the rate "
                     f"of working at a job, {d.unpleasant(WORKING) * 100:.0f}% of the time. Its unpaid hours, in {_m(_sym('X'))}, "
                     f"count at the rate of each kind of work at home, which {_file('config/unpaid_work.csv')} names by the "
                     "survey's codes.",
              note="All paid work has the one rate, because the survey's files used here do not say what a respondent's job "
                   "was. So among paid work this says nothing of which activity is worse. People also grow used to what "
                   "they cannot change, and report less distress than an observer would expect.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
        Sheet(XI, "what the work behind a need dollar costs those who do it, by activity", "wellbeing", wellbeing_lost, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Experienced microWELLBYs lost by those who do the activity's work, paid and unpaid, for every thousand "
                      "need dollars: its hours, times the points people rate such work below the rest of their own day, "
                      f"times the {POINT_HOUR:.0f} microWELLBYs that one point for one hour comes to.",
              source=f"The same module of the American Time Use Survey as {_m(_sym(ZETA))}: "
                     f"{_file('data/households/wellbeing_by_activity.csv')}. A rated activity is put on one scale from 0 to 10: "
                     "happiness less the mean of pain, sadness and stress, each rated 0 to 6, moved and stretched so that the worst "
                     "that can be reported is 0 and the best is 10. Each rating is then set against the same person's other rated "
                     "time that was not work, which is what an hour of work given back would become. The paid hours of an "
                     f"activity, in {_m(_sym(TAU))}, count at what working at a job is rated below the rest of the day, "
                     f"{d.below_rest(WORKING):.2f} points. Its unpaid hours, in {_m(_sym('X'))}, count at the points of each kind of "
                     f"work at home, which {_file('config/unpaid_work.csv')} names by the survey's codes.",
              note="A WELLBY is one point, on a scale from 0 to 10, of how satisfied someone is with their life, for one year. "
                   "What is measured here is how people felt at the time, which is not the same thing, and taking a point of one "
                   "for a point of the other is a judgment. The scale is also even: six hours one point down count as one hour "
                   "six points down, and those who study severe pain think the worst hours count for far more than that. An entry "
                   "below zero is work people rate above the rest of their day, as they do the care of children. All paid work "
                   "has the one rate.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
        Sheet(KAPPA, "the hours each activity's paid work still takes", "number", activity_still, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries=f"For the same output, the hours taken in {span}, in the sectors where the activity is done for pay: "
                      f"the mean of {_m(_sym(SIGMA))} over those sectors, each weighted by the activity's paid hours in it.",
              source=f"Read from the left. Each sector's hours, {_m(_sym(BETA))}, are counted at what they still take, "
                     f"{_m(_sym(SIGMA))}. {_m(_sym('Z'))} passes them to the occupations that work them and "
                     f"{_m(_sym(THETA))} to the activities those occupations do. The last factor divides each activity's "
                     f"sum by its paid hours, {_m(_sym(THETA, T=True) + _TIMES + _sym(PI))}, which is the same sum without "
                     f"{_m(_sym(SIGMA))}.",
              note="Under a half, paid work of this kind has been going anyway. Near one or over, it is stuck. It is a measure "
                   "of the sectors an activity is done in and not of the activity itself, and it says nothing of work done "
                   "unpaid. Zero means the activity has no paid hours.",
              row_tip="Activity", code="plenty/site.py", order=activity_order),
        Sheet(SIGMA, f"the hours each sector still takes, {HR.YEAR} against {HR.SINCE}", "number",
              **lone(still.loc[com], SIGMA, f"Hours in {span}", "ratio"), row_names=t.names,
              rows="sectors, each a commodity",
              entries=f"The hours it took in {HR.YEAR} to make a unit of the sector's own real value added, for each hour it took "
                      f"in {HR.SINCE}. Under one, hours have been going. At one or over, none have.",
              source=f"{production_account} Its yearly series is in {_file('data/bea/production_account_1987_2016.csv')}. Real "
                     "value added is output less intermediate inputs, each at its own prices, chained year by year. A commodity "
                     "takes the mean of the industries that make it, weighted by the hours each puts into it.",
              note="The output of health care, education and government is measured largely by what goes into them, so their "
                   "figures say less than the others'.",
              row_tip="Sector", code="plenty/hours.py"),
        # --- proposals
        Sheet(PSI, "the hours each proposal would do", "hours", would_do, proposed, **by_weighing,
              rows="scored proposals", row_groups=of_proposals,
              entries="Hours of work for every thousand need dollars, paid and unpaid, in the parts of activities the proposal "
                      "claims, less the part that already has an open implementation.",
              note="It is a ceiling: the work the claims cover, if the proposal did all of it. A claim is the proposer's own. "
                   "Proposals overlap, so the rows do not add up.",
              row_tip="Proposal", code="plenty/site.py", order=proposal_order),
        Sheet("C", "the part of each work activity each proposal would do", "share", claims, act.name, proposed,
              rows="O*NET's intermediate work activities", cols="scored proposals",
              entries="The part of the activity the proposal claims it would do: one for the whole of it, less for a part.",
              source=f"The proposals, one file each, with the reason for every share: {_file('proposals/')}.",
              note="Nothing here is checked by the account. Each proposal's page lists its claims with their reasons.",
              row_tip="Activity", col_tip="Proposal", axis="Proposals", code="plenty/site.py",
              row_groups=act.parent.map(d.act.name), col_groups=of_proposals,
              order=f"{activity_order} {proposal_order}"),
        # --- needs
        Sheet("d", "the commodities a dollar of each need buys", "per_dollar", dn.loc[com], t.names,
              rows="purchased commodities", cols="a dollar of each need", **by_need,
              entries="The part of a dollar of the need that is spent on the commodity. A column adds up to one dollar.",
              row_tip="Bought", col_tip="With a dollar of", row_is="Row, the commodity bought:", axis="Needs: one dollar of each",
              code="plenty/analysis.py"),
        Sheet("Y", "spending on each need", "dollars", A.need_demand(t)[needs].loc[com], t.names,
              rows="purchased commodities", cols="the purpose of each purchase, a need", **by_need,
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
              rows="weighed needs", row_groups=pd.Series("Needs", index=needs),
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
              rows="producing industries", entries="Millions of dollars of everything the industry made in 2017: its row of the Make table, added up.",
              row_tip="Industry", code=model, exact=True, sums="both"),
        Sheet("q", "each commodity's output", "dollars", **lone(t.q.loc[com], "q", "Output in 2017"), row_names=t.names,
              rows="produced commodities", entries="Millions of dollars of the commodity made in 2017 by every industry: its column of the Make "
                                          "table, added up.",
              row_tip="Commodity", code=model, exact=True, sums="both"),
        # --- capital
        Sheet("K", "the capital matrix", "dollars", m.K.loc[com, ind], t.names, t.ind_names,
              rows="capital goods, each a commodity", cols="capital-using industries",
              entries="Millions of dollars of the capital good bought as investment in 2017 and placed on the industry.",
              note="It is an estimate. The Bureau publishes investment by commodity and by kind of investor, not by the industry "
                   "that bought it.",
              row_tip="Capital good", col_tip="Placed on", col_is="Column, the industry it is placed on:",
              axis="Industries using the capital", code=model, sums="both"),
        Sheet("F", "investment purchases", "dollars", cap.investment.loc[com], t.names,
              rows="capital goods, each a commodity", cols="the buyer's kind of investor", **by_investor,
              entries="Millions of dollars of the commodity bought as investment in 2017 by investors of the kind. A negative "
                      "entry is a sale of used equipment or scrap.",
              source=f"{bea} It is the Use table's columns for investment, added up by kind of investor: "
                     + "; ".join(f"{INVESTOR_NAME[h].lower()} ({', '.join(f'<code>{c}</code>' for c in cols)})"
                                 for h, cols in M.CAPITAL_COLUMNS.items()) + ".",
              row_tip="Capital good", col_tip="Bought by", axis="Kinds of investor", code=model, sums="both"),
        Sheet("H", "the kind of investor each industry is", "mark", investors.loc[ind], t.ind_names,
              rows="investing industries", cols="the industry's kind of investor", **by_investor,
              entries="One where the industry is of the kind, and zero elsewhere. Every industry is of one kind.",
              source=f"Lists in {_file(model)}: housing, federal defense, federal nondefense, and state and local government "
                     "are named there, and every other industry is private business.",
              row_tip="Industry", col_tip="Kind of investor", axis="Kinds of investor", code=model,
              blanks=("is not of this kind", "zero"), marked="is of this kind", sums="cols"),
        Sheet("S", "the placement of each capital good", "share", cap.shares.loc[com, ind], t.names, t.ind_names,
              rows="capital goods, each a commodity", cols="capital-using industries",
              entries="The share of the purchases of the capital good, by investors of the industry's kind, that is placed on the "
                      "industry. Within one kind of investor a row adds up to one.",
              source=f"{_m(_sub('&Omega;', 'ik'))} is the set of industries that could have bought capital good <i>i</i>, among "
                     f"those of the same kind of investor as <i>k</i>: the ones a pairing names for it, or all of that kind if none "
                     f"does. The {sum(1 for x in cap.steps if x['note'])} pairings of a capital good with its evident users are "
                     f"judgment, kept in {_file('config/capital_allocation.csv')}.",
              row_tip="Capital good", col_tip="Share placed on", col_is="Column, the industry it is placed on:",
              axis="Industries: their share of each capital good", code=model),
        Sheet("z", "the weights that share investment among industries", "dollars", **lone(cap.weight.loc[ind], "z", "Weight"), row_names=t.ind_names,
              rows="investing industries",
              entries="Millions of dollars: the industry's gross operating surplus if it is private business or housing, and its "
                      "output if it is government.",
              source=f"{bea} Gross operating surplus is the Use table's row <code>V00300</code>, with a negative surplus counted "
                     "as none.",
              row_tip="Industry", code=model),
        # --- value added
        Sheet("v", "the value added behind a dollar of each need", "share", d.need_value_added.loc[com], t.names,
              rows="sectors that earn the income, each a commodity", cols="a dollar of each need", **by_need,
              entries="The sector's share of the value added behind a dollar of the need. A column adds up to one.",
              row_tip="Sector", col_tip="Share of a dollar of", axis="Needs: one dollar of each", code="plenty/analysis.py"),
        Sheet("r", "value added per dollar of each commodity", "per_dollar",
              **lone(A.value_added_share(m).loc[com], "r", "Value added per dollar", "per dollar"), row_names=t.names,
              rows="produced commodities", entries="Dollars of value added per dollar of the commodity's output: its makers' value added per "
                                          "dollar, mixed by their shares of it.",
              row_tip="Commodity", code="plenty/analysis.py"),
        Sheet("y", "each industry's value added", "dollars", **lone(t.VA.sum(axis=0).loc[ind], "y", "Value added in 2017"),
              row_names=t.ind_names, rows="producing industries",
              entries="Millions of dollars of value added in 2017: what the industry paid its employees, taxes on production "
                      "less subsidies, and its gross operating surplus.",
              source=f"{bea} It is the Use table's three rows of value added "
                     f"({', '.join(f'<code>{c}</code>' for c in M.VA_ROWS)}), added up.",
              row_tip="Industry", code=model, sums="both"),
        # --- work
        Sheet("W", "the occupations that do each sector's work", "share", d.wages[0].loc[com], t.names, occ.title,
              rows="sectors, each a commodity", cols="paid occupations",
              entries="The occupation's share of the sector's wage bill. A row adds up to one, or is empty where the sector is "
                      "not measured.",
              row_tip="Sector", col_tip="Share of its wage bill paid to", col_is="Column, the occupation:",
              axis="Occupations: their share of each sector's wage bill", code=occupations, **by_occupation),
        Sheet("P", "the pay of each occupation in each sector", "dollars", P.loc[com], t.names, occ.title,
              rows="sectors, each a commodity", cols="paid occupations",
              entries="Millions of dollars paid to the occupation in a year by the surveyed industries that cover the sector.",
              note="Jobs times the mean wage, in the cells where the survey publishes both.",
              row_tip="Sector", col_tip="Paid to", col_is="Column, the occupation:",
              axis="Occupations: their pay in each sector", code=occupations, **by_occupation, sums="both"),
        Sheet("T", "the surveyed industries that cover each sector", "mark", T.loc[com], t.names, surveyed.title,
              rows="sectors, each a commodity", cols="covering surveyed industries",
              entries="One where the surveyed industry covers the sector, and zero elsewhere.",
              source=f"The Bureau of Economic Analysis's concordance of its sectors with the industry classification the survey "
                     f"uses, in {_file('data/occupations/')}, and in {_file(occupations)} the stand-ins for what the survey "
                     "files elsewhere or leaves out: public schools and hospitals, other government, and farms. Housing and the "
                     "accounting sectors are covered by nothing.",
              row_tip="Sector", col_tip="Surveyed industry", axis="Surveyed industries", code=occupations,
              col_groups=surveyed.group, blanks=("does not cover it", "zero"), marked="covers it",
              order="Sectors and surveyed industries are each in code order within the same fifteen groups.", sums="both"),
        Sheet("E", "jobs in each occupation", "people", E.fillna(0.0), surveyed.title, occ.title,
              rows="employing surveyed industries", cols="employed occupations", entries="Jobs in the occupation in the industry, in May 2021.",
              source=oews,
              note="It counts wage and salary jobs at nonfarm employers, not people: someone with two jobs is in it twice, and the "
                   "self-employed are not in it.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: the jobs of each industry in them",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only, sums="both"),
        Sheet("M", "the wage of each occupation", "wage", wage.fillna(0.0), surveyed.title, occ.title,
              rows="paying surveyed industries", cols="paid occupations",
              entries="The mean annual wage of the occupation in the industry, in dollars, in May 2021.",
              source=oews, note="A wage of $208,000 or more is recorded as $208,000.",
              row_tip="Surveyed industry", col_tip="Occupation", axis="Occupations: their mean annual wage in each industry",
              code=occupations, row_groups=surveyed.group, blanks=not_published, **by_occupation_only),
        # --- software capabilities
        Sheet(PHI, "the software each occupation works with", "share", d.phi, occ.title, tax.name[caps],
              rows="software-using occupations", cols="the taxonomy's software capabilities",
              entries="The share of the occupation's work that is done with the capability. A row adds up to the share of the "
                      "occupation's software the taxonomy places, at most one.",
              source=f"{_m(_sym('Q'))}{_m(_sym('R'))} counts the products an occupation lists in each capability. Each count is "
                     f"weighted by the capability's specificity, {_m(_sym('u'))}, so that tools everyone uses take less, and "
                     "divided by the row's total, so that the row adds up to one. The row is then scaled to the share of the "
                     f"occupation's products that the taxonomy places. Last, {_m(_sym('J'))} gives each of the survey's "
                     "occupations the row of its O*NET occupation, or the mean of the rows of its group. An occupation none of "
                     "whose products is placed has a row of zeros.",
              note="A list of products is not time: O*NET says which software an occupation uses, not for how long.",
              row_tip="Occupation", col_tip="Capability", axis="Software capabilities: their share of each occupation's work",
              code="plenty/flows.py", row_groups=occ.major, col_groups=domain,
              short={**{g: SOC_SHORT[c[:2]] for c, g in occ.major.items()}, **by_capability["short"]},
              order=f"Occupations are in the order of the Standard Occupational Classification within its 22 major groups. {capability_order}"),
        Sheet("J", "the O*NET occupations each of the survey's occupations stands for", "share", J, occ.title, onet_titles,
              rows="the survey's occupations", cols="member O*NET occupations",
              entries="One where the survey's occupation is the O*NET occupation. Where the survey publishes a group of "
                      "occupations as one, each O*NET occupation in the group has an equal part of one, so that the group takes "
                      "their mean. A row is empty where O*NET lists no software for the occupation.",
              source=f"The two lists of occupations, matched by their codes in the Standard Occupational Classification: "
                     f"{_file('data/occupations/')}. A code of the survey's that ends in zeros is a group, and stands for every "
                     "O*NET occupation whose code begins as it does.",
              note=f"{int((J.sum(axis=1) == 0).sum())} of the survey's {len(J)} occupations have an empty row, and "
                   f"{int(((J > 0).sum(axis=1) > 1).sum())} are groups. {int((J.sum(axis=0) == 0).sum())} of the {J.shape[1]} "
                   "O*NET occupations are under none of the survey's.",
              row_tip="Survey's occupation", col_tip="O*NET occupation", axis="O*NET occupations", code="plenty/occupations.py",
              row_groups=occ.major, col_groups=onet_major, short=soc_short,
              order="Both lists are in the order of the Standard Occupational Classification within its 22 major groups."),
        Sheet("Q", "the software each occupation lists", "mark", listing, onet_titles, product_names,
              rows="listing O*NET occupations", cols="listed software products",
              entries="One where O*NET lists the product among the software the occupation uses, and zero elsewhere.",
              source=f"O*NET 31.0, the U.S. Department of Labor's database of occupations, in its table of technology skills: "
                     f"{_file('data/occupations/onet_software_skills.csv')}. The lists of the finer occupations O*NET has under "
                     "one six-digit code are pooled.",
              note="A list of products is not time: O*NET says which software an occupation uses, not for how long.",
              row_tip="Occupation", col_tip="Product", axis="Software products", code="plenty/flows.py",
              row_groups=onet_major, col_groups=product_group, short={**soc_short, **by_capability["short"]},
              blanks=("does not list it", "zero"), marked="lists it", sums="both",
              order=f"Occupations are in the order of the Standard Occupational Classification within its 22 major groups. {product_order}"),
        Sheet("R", "the capabilities each software product is an example of", "share", placing, product_names, tax.name[caps],
              rows="listed software products", cols="the taxonomy's software capabilities",
              entries="The part of the product placed in the capability: one where it is an example of that capability alone, "
                      "and an equal part of one where it is an example of several. A row is empty where the taxonomy does not "
                      "place the product.",
              source=f"The taxonomy names products as examples of its tasks: {_file('taxonomy/products_seed.csv')}. A product "
                     "is placed in the capabilities those tasks are part of.",
              note=f"The placing is judgment, made when the taxonomy was compiled. {int((placing.sum(axis=1) == 0).sum()):,} of "
                   f"the {len(placing):,} products are not placed, and {int(((placing > 0).sum(axis=1) > 1).sum()):,} are placed "
                   "in more than one capability.",
              row_tip="Product", col_tip="Capability", axis="Software capabilities", code="plenty/flows.py",
              row_groups=product_group, col_groups=domain, short=by_capability["short"],
              order=f"{product_order} {capability_order}"),
        Sheet("u", "the specificity of each capability", "number", **lone(specificity, "u", "Specificity", "number"), **by_capability,
              rows="the taxonomy's software capabilities",
              entries="The natural logarithm of the number of O*NET occupations over the number of them that list a product of "
                      "the capability. It is near zero for a capability nearly every occupation lists, and largest for one "
                      "that a single occupation lists.",
              source=f"{_m('<mi>O</mi>')} is the number of O*NET occupations, {listing.shape[0]}, and "
                     f"{_m('<msub><mi>O</mi><mi>k</mi></msub>')} the number of them that list a product placed in capability "
                     f"{_m('<mi>k</mi>')}: the rows of {_m(_sym('Q'))}{_m(_sym('R'))} whose entry in column {_m('<mi>k</mi>')} "
                     "is not zero. A capability no occupation lists is counted as if one did, and nothing is placed on it "
                     "either way.",
              row_tip="Capability", code="plenty/flows.py", order=capability_order),
        Sheet("a", "the well-defined share of the tasks with no open tool", "share",
              **lone(d.defined_share, "a", "Well defined", "share"), **by_capability,
              rows="the taxonomy's software capabilities",
              entries="Of the capability's tasks with no known open tool, the share whose result could be scored by a benchmark. "
                      "A task that could partly be scored counts half. Zero where every task has a tool.",
              row_tip="Capability", code="plenty/site.py", order=capability_order),
        Sheet("c", "the open share of each capability", "share",
              **lone(d.open_share, "c", "Tasks with an open tool", "share"), **by_capability,
              rows="the taxonomy's software capabilities",
              entries="The share of the capability's tasks for which an open-source tool is known.",
              row_tip="Capability", code="plenty/site.py", order=capability_order),
        Sheet("N", "the tasks of each capability", "mark", member, tax.name[caps], tasks.name,
              rows="the taxonomy's software capabilities", cols="the capability's tasks",
              entries="One where the task is part of the capability, and zero elsewhere. Every task is part of one capability.",
              source=f"The taxonomy divides each capability into tasks: {_file('taxonomy/capabilities.csv')}.",
              note="Nothing says how a capability's work divides among its tasks, so they are counted and not weighed: every "
                   "task of a capability counts the same.",
              row_tip="Capability", col_tip="Task", axis="Tasks", code="taxonomy/build.py",
              row_groups=domain, col_groups=by_task["row_groups"], short=by_capability["short"],
              blanks=("is not part of it", "zero"), marked="is part of it", sums="both",
              order=f"{capability_order} Tasks are in the same order."),
        Sheet("t", "the tasks that have an open tool", "mark", **lone(tasks.tool, "t", "Has an open tool", "one or zero"), **by_task,
              rows="the taxonomy's tasks",
              entries="One where an open-source tool is known for the task, and zero where none is.",
              source=f"The taxonomy names the open tools known for each of its {len(tasks):,} tasks: "
                     f"{_file('taxonomy/capabilities.csv')}.",
              note="The tools were named from memory when the taxonomy was compiled. An entry says a tool exists, not that it is "
                   "good enough to do the work.",
              row_tip="Task", code="taxonomy/build.py", blanks=("has no known open tool", "zero"), marked="has an open tool",
              short=by_capability["short"], order=task_order),
        Sheet("w", "the well-defined part of each task", "share", **lone(tasks.defined, "w", "Well defined", "share"), **by_task,
              rows="the taxonomy's tasks",
              entries="One where the task's result could be scored by a benchmark, a half where it could partly be, and zero "
                      "where it could not.",
              source=f"The taxonomy says of each task whether it is benchmarkable: {_file('taxonomy/capabilities.csv')}.",
              note="This is the taxonomy's own judgment of each task, made when it was compiled.",
              row_tip="Task", code="taxonomy/build.py", short=by_capability["short"], order=task_order),
        # --- work activities: the same dollar, placed on what the work is
        Sheet("f", "the part of a need dollar that pays for each activity", "per_dollar", to_activity, **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Dollars per need dollar, paid and unpaid, that go to the activity. It is where today's work goes, not how "
                      "much an activity matters.",
              note="The rest of the dollar is in sectors the survey of occupations does not reach, and in occupations whose tasks "
                   "are not rated.",
              row_tip="Activity", code="plenty/flows.py", sums="cols", order=activity_order),
        Sheet(THETA, "the activities that make up each occupation's work", "share", d.theta, occ.title, act.name,
              rows="working occupations", cols="O*NET's intermediate work activities",
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
              rows="the paid equivalent of the work, an occupation", cols="the kind of work, a work activity",
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
        Sheet("m", "the well-defined part of each activity", "share", **lone(defined, "m", "Well defined", "share"), **by_activity,
              rows="O*NET's intermediate work activities",
              entries="One where doing the activity has a result that could be checked: a record that is right, an amount "
                      "that is correct, a part within its tolerance, a surface that is clean. A half where part of the result "
                      "could be checked and the rest is a judgment of quality. Zero where the result rests on taste, trust, "
                      "authority or a relationship, and no test would settle it.",
              source=f"Judgment, made by hand, one activity at a time: {_file('config/activities.csv')}.",
              note="An activity is broad, and the judgment is of the ordinary run of it. It says the result could be checked, "
                   "not that anyone yet knows how to produce it.",
              row_tip="Activity", code="plenty/site.py", order=activity_order),
        Sheet("e", "the part of each activity that has an open implementation", "share",
              **lone(opened, "e", "Open implementation", "share"), **by_activity,
              rows="O*NET's intermediate work activities",
              entries="One where something open is known that does the ordinary run of the activity by itself, a half where "
                      "it does a recognizable part of it or works only in narrow conditions, and zero where nothing is known. "
                      "The implementation may be software, a published procedure or the design of a mechanism. A tool that a "
                      "person does the work with does not count.",
              source=f"Judgment, made by hand, one activity at a time, with what the implementation is: "
                     f"{_file('config/activities.csv')}.",
              note=f"The implementations were named from memory and have not been checked. {int((opened > 0).sum())} of the "
                   f"{len(opened)} activities have one, all but {int((opened == 1).sum())} of them in part.",
              row_tip="Activity", code="plenty/site.py", order=activity_order),
        Sheet("s", "the activities that are information work", "mark", **lone(info, "s", "Information work", "one or zero"), **by_activity,
              rows="O*NET's intermediate work activities",
              entries="One where the activity is information work, which software could do, and zero where it needs a body or is "
                      "work in which the person is the point.",
              source=f"Judgment, made by hand, one activity at a time: {_file('config/activities.csv')}.",
              row_tip="Activity", code="plenty/site.py", blanks=("needs a body or a person", "zero"), marked="is information work",
              order=activity_order),
        Sheet("b", "the part of a need dollar that pays for work that needs a body", "per_dollar",
              to_activity.mul(1 - info, axis=0), **by_activity, **by_weighing,
              rows="O*NET's intermediate work activities",
              entries="Dollars per need dollar, paid and unpaid, that go to the activity, where it needs a body or a person. No "
                      "software capability reaches it without a machine to act through.",
              row_tip="Activity", code="plenty/site.py", sums="cols", order=activity_order),
    ]
    by_key = {s.key: s for s in out}
    assert len(by_key) == len(out) and set(by_key) == set(TERMS), "the terms and their pages have fallen out of step"
    return {key: by_key[key] for key in TERMS}


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
                "things": things}
    payload = {"key": s.key, "kind": s.kind, "unit": kind["unit"], "cut": kind["cut"], "scale": kind["scale"],
               "blank": s.blanks[0] if s.blanks else "nothing" if s.exact else kind["blank"], "marked": s.marked,
               "short": {**MX.SHORT, **(s.short or {})}, "lock": s.lock, "stretch": s.thin and not s.lock,
               "rows": side(s.values.index, s.row_names, COUNTED[dimension(s.rows)[0]][1], s.row_groups),
               "cols": side(s.values.columns, s.col_names, COUNTED[dimension(s.cols)[0]][1] if s.values.shape[1] > 1 else "column", s.col_groups),
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
    if key == "A":
        return sheet_data(s, parts=MATRIX_PARTS)
    start = {"sort": 0, "rows": ORDER_ROWS}       # a picture that opens in order: sorted by its first column, largest first, the first row marked
    if key == "h":
        return sheet_data(s, parts=ORDER_PARTS, why="activity", start=start)
    if key == "o":
        return sheet_data(s, parts=TASK_PARTS, why="tasks", start=start)
    if key in (RHO, ETA):
        return sheet_data(s, start=start)
    return sheet_data(s)


def order_parts(d: Data) -> str:
    """What a row of h is made of, for the page to show when a row is marked: the activity's row of f
    and how much of it is unpaid work at home, what is judged of it, and the detailed work activities
    O*NET files under it, each with its part of the paid need dollar, needs counted equally."""
    acts = d.sheets["h"].values.index
    j, unpaid = d.judged.loc[acts], d.unpaid[0].sum()[acts]
    fine = d.act[d.act.level == "detailed"]
    under = {a: g.sort_values("flow", ascending=False) for a, g in fine.groupby("parent")}
    payload = {"f": [[round(float(x), 8) for x in row] for row in d.sheets["f"].values.loc[acts].values],
               "unpaid": [round(float(x), 8) for x in unpaid],
               "defined": list(j.well_defined), "open": list(j.open), "basis": list(j.open_basis), "kind": list(j.kind),
               "detailed": [[[n.rstrip("."), round(float(x), 8)] for n, x in zip(under[a].name, under[a].flow)] if a in under else [] for a in acts]}
    return "window.PLENTY_MATRIX_PARTS = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def order_template(here: str = "") -> str:
    """What the script writes over the parts of a marked row of h."""
    i = lambda letter: _elt(letter, "i", letter, here)
    parts = f'{i("h")}<mo>=</mo>{i("f")}{_TIMES}{i("m")}{_TIMES}{_paren(f"<mn>1</mn><mo>&minus;</mo>{i('e')}")}'
    return f"""<template id="mx-why"><h3>The parts of the row</h3>
<p>A row of {_m(_sym("h", here))} is the activity's row of {_m(_sym("f"))}, times the part of the activity that is well
defined, {_m(_sym("m"))}, times the part that has no open implementation:</p>
{_m(parts, block=True)}</template>
"""


def task_parts(d: Data) -> str:
    """What a row of o is made of, for the page to show when a row is marked: the capability's row
    of k, its a and its c, and its tasks, each as (name, the open tools known for it, whether it is
    benchmarkable). Capabilities are in the page's order."""
    caps = d.sheets["o"].values.index
    tasks = d.tasks
    of = {c: g for c, g in tasks.groupby("capability", sort=False)}
    payload = {"k": [[round(float(x), 8) for x in row] for row in d.sheets["k"].values.loc[caps].values],
               "a": [round(float(x), 6) for x in d.defined_share[caps]], "c": [round(float(x), 6) for x in d.open_share[caps]],
               "tasks": [[list(x) for x in zip(of[c].name, of[c].tools, of[c].benchmarkable)] for c in caps]}
    return "window.PLENTY_MATRIX_PARTS = " + json.dumps(payload, separators=(",", ":")) + ";\n"


def task_template(here: str = "") -> str:
    """What the script writes over the parts of a marked row of o."""
    i = lambda letter, page: _elt(letter, "i", page, here)
    parts = f'{i("o", "o")}<mo>=</mo>{i("k", "k")}{_TIMES}{i("a", "a")}{_TIMES}{_paren(f"<mn>1</mn><mo>&minus;</mo>{i('c', 'c')}")}'
    return f"""<template id="mx-why"><h3>The parts of the row</h3>
<p>A row of {_m(_sym("o", here))} is the capability's row of {_m(_sym("k"))}, times the well-defined share of its tasks with
no open tool, {_m(_sym("a"))}, times the share of its tasks that have none:</p>
{_m(parts, block=True)}</template>
"""


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


SPARSE_CSV = 1_000_000     # a matrix of more cells than this is filed as its entries that are not zero, one to a line


def sheet_csv(s: Sheet) -> str:
    """The whole of a term as CSV: a table, or for a large matrix a line for each entry that is not zero."""
    if s.values.size <= SPARSE_CSV:
        return s.values.to_csv(float_format="%.6g")
    i, j = np.nonzero(s.values.values)
    return pd.DataFrame({"row": s.values.index[i], "column": s.values.columns[j], "value": s.values.values[i, j]}).to_csv(index=False, float_format="%.6g")


def sheet_picture(s: Sheet, also: str = "", extra: str = "") -> str:
    """The picture of a term with its margins, buttons and legend, drawn by web/matrix.js.
    also: a sentence about this picture alone; extra: markup the script uses."""
    kind, (nr, nc) = MATRIX_KINDS[s.kind], s.values.shape
    blank = s.blanks[1] if s.blanks else "zero" if s.exact else f"zero or {kind['small']}"
    if s.thin:          # a picture of a fixed shape: the columns always all in view, or the whole matrix stretched to fill it
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
    past = ("To move, drag with the mouse wheel pressed or with Ctrl held, or with a finger on a touch screen. The picture "
            "can be moved past the matrix's edge, far enough to bring a cell at the edge to the middle.")
    moving = ("Zooming changes how many rows are in view; the columns are always all there. To move, drag with the mouse "
              "wheel pressed or with Ctrl held, or with a finger on a touch screen." if s.lock else
              "The whole matrix is stretched to fill the picture, and zooming brings its rows and its columns closer together, "
              f"the rows going on after the columns are as close as they come. {past}" if s.thin else past)
    legend = (f'<div class="mx-legend" aria-hidden="true"><div class="mx-ramp"></div>\n<div class="mx-ticks">'
              + "".join(f"<span>{x}</span>" for x in kind["ticks"]) + "</div></div>") if kind["ticks"] else ""
    colour = f"Colour is {kind['colour']}, on a log scale." if kind["colour"] else f"A filled cell is a one: the row {s.marked}."
    empty = (~s.shown).mean()      # a matrix that is nearly all blank is not said to be all blank
    return f"""<figure class="mx">
<div class="mx-frame{" mx-lock" if s.lock else ""}" style="grid-template-columns: auto minmax(0, {width + 2}px) auto">
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
<figcaption>{colour} The {empty:.{1 if 0.995 <= empty < 1 else 0}%} of entries that are {blank} are blank. {s.order}</figcaption>
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
        Unit("commodity", *COUNTED["commodity"], True,
             "One of the goods and services the Bureau of Economic Analysis divides the economy's output into.",
             f"""<p>One of the {len(t.commodities)} goods and services that the U.S. Bureau of Economic Analysis divides everything the
economy makes into, in its 2017 benchmark input-output accounts at the detail level: {_file('data/bea/')}. Grain is one, hospitals
another, wholesale trade another.</p>
<p>A commodity is a product, not a maker. It is made by one or more {_unit("industry", "industries")}, in the shares
{T("D")} holds.</p>
<p>Some terms need a maker for each row: whose income a dollar becomes, and who works there. Their rows are called sectors.
A sector is still a row for each commodity, with a maker put in the commodity's place. For value added, {T("r")}, the maker
is every industry that makes the commodity, each counted by its share of it. For work, {T("W")}, it is only the
{_unit("surveyed-industry", "surveyed industries")} whose classification matches the commodity's own, {T("T")}: the
industry named for it, and not the others that make some of it.</p>"""),
        Unit("industry", *COUNTED["industry"], True,
             "One of the groups of producers the Bureau of Economic Analysis divides the economy into.",
             f"""<p>One of the {len(t.industries)} groups of producers in the same accounts. An industry is named for its main
product, a {_unit("commodity")}, but it can make others too: {T("V")} says how much of each.</p>
<p>The Bureau's tables say what industries bought and what they paid. The model turns those into what it takes to make a
commodity, through {T("D")}.</p>"""),
        Unit("need", *COUNTED["need"], True,
             "One of the purposes that household and government spending is counted under.",
             f"""<p>One of {len(needs)} purposes that what households and governments buy is counted under: {", ".join(needs)}.
The list is the project's own. Each {_unit("commodity")} is counted under one need, or under none, by a list made by hand:
{_file('config/basket.csv')}.</p>
<p>What is under no need is left out of the account: financial and legal services, national defense and the rest of federal
government among them.</p>"""),
        Unit("weighting", *COUNTED["weighting"], True,
             "One of three ways of dividing a need dollar among the needs.",
             f"""<p>One of {ways.shape[1]} ways of dividing one {_unit("need-dollar", "need dollar")} among the
{_unit("need", "needs")}, each a column of {T(OMEGA)}. Counted equally, every need has the same weight. By spending, a need
weighs what households and governments spent on it. By the poorest fifth's budget, it weighs what the fifth of households with
the lowest incomes spent on it themselves.</p>
<p>Every term from {T("p")} on has a column for each, so the order the account ends in can be read all three ways.</p>"""),
        Unit("investor-kind", *COUNTED["investor-kind"], True,
             "One of the five kinds of buyer the Bureau of Economic Analysis reports investment for.",
             f"""<p>One of the five kinds of buyer that the Bureau of Economic Analysis reports investment in equipment and buildings
for: {", ".join(n.lower() for n in INVESTOR_NAME.values())}. The Bureau says what each kind bought, not which
{_unit("industry")} bought it, so {T("S")} places each kind's purchases on the industries of that kind.</p>"""),
        Unit("occupation", *COUNTED["occupation"], True,
             "One of the kinds of job in the Standard Occupational Classification, as the survey of occupations publishes them.",
             f"""<p>One of the {len(occ):,} kinds of job, in {occ.major.nunique()} major groups, that the U.S. Bureau of Labor
Statistics publishes in its Occupational Employment and Wage Statistics for May 2021: {_file('data/occupations/')}. They are
the occupations of the Standard Occupational Classification, except that the survey publishes a few only as a group.</p>
<p>The same occupations are described by O*NET, the Department of Labor's database, which says what tasks each does and what
software it uses. That is how a dollar placed on an occupation goes on to {_unit("activity", "work activities")} and
{_unit("capability", "software capabilities")}.</p>"""),
        Unit("onet-occupation", *COUNTED["onet-occupation"], True,
             "One of the occupations O*NET lists software for, by its six-digit code in the Standard Occupational Classification.",
             f"""<p>One of the {d.software[1].shape[0]} occupations for which O*NET 31.0, the U.S. Department of Labor's database
of occupations, lists software: {_file('data/occupations/')}. They are counted by six-digit code in the Standard Occupational
Classification, and the finer occupations O*NET has under one code are pooled.</p>
<p>They are nearly the survey's {_unit("occupation", "occupations")}, but not quite: the survey publishes some occupations
only as a group, and O*NET lists no software for others. {T("J")} says which O*NET occupations each of the survey's stands
for.</p>"""),
        Unit("product", *COUNTED["product"], True,
             "One of the software products O*NET names among the technology an occupation uses.",
             f"""<p>One of the {d.software[1].shape[1]:,} software products that O*NET 31.0 names as examples of the technology
occupations use, such as Microsoft Excel or Dassault Systemes SolidWorks:
{_file('data/occupations/onet_software_skills.csv')}. {T("Q")} says which
{_unit("onet-occupation", "O*NET occupations")} list each.</p>
<p>The taxonomy places {int((d.software[2].sum(axis=1) > 0).sum()):,} of them in the
{_unit("capability", "software capabilities")} they are examples of, {T("R")}. The rest are not placed, and the work done
with them reaches no capability.</p>"""),
        Unit("surveyed-industry", *COUNTED["surveyed-industry"], True,
             "One of the industries the survey of occupations reports jobs and wages for.",
             f"""<p>One of the {len(surveyed)} industries that the survey of occupations reports {_unit("job", "jobs")} and wages
for. They are industries of the North American Industry Classification System at about its four-digit level, a few of
them published as groups, with three more for federal, state and local government. They are not the Bureau of Economic Analysis's {_unit("industry", "industries")}, so {T("T")} says which
surveyed industries cover each sector.</p>
<p>The survey leaves out farms and files public schools and hospitals with private ones. Stand-ins are used for those, and
housing is covered by nothing, because nobody is employed in owning a home.</p>"""),
        Unit("capability", *COUNTED["capability"], True,
             "One of the things software does for the people who work, in the project's own taxonomy.",
             f"""<p>One of the {int((tax.level == 1).sum())} things software does for people at work, in a taxonomy compiled for this
project: {_file('taxonomy/')}. Medical coding, billing and claims is one; structural finite element analysis another. They are in
{int((tax.level == 0).sum())} domains, and each is divided into {_unit("task", "tasks")}, {len(d.tasks):,} in all.</p>
<p>The taxonomy also places the software products O*NET lists, which is how an {_unit("occupation")}'s work reaches a
capability, in {T(PHI)}.</p>"""),
        Unit("task", *COUNTED["task"], True,
             "One of the pieces of work a software capability is divided into, in the project's own taxonomy.",
             f"""<p>One of the {len(d.tasks):,} pieces of work that the taxonomy divides its
{_unit("capability", "software capabilities")} into, {T("N")}: {_file('taxonomy/capabilities.csv')}. Diagnosis and procedure
code assignment is a task of medical coding, billing and claims. Each has its inputs and outputs written down, so that it can
be said what doing it would be.</p>
<p>The taxonomy says two things of each task: whether an open-source tool is known for it, {T("t")}, and whether its result
could be scored by a benchmark, {T("w")}. A task with no open tool whose result could be scored is one to build.</p>
<p>Nothing says how a capability's work divides among its tasks. So the account counts tasks and does not weigh them, and it
puts capabilities in order, not tasks.</p>"""),
        Unit("proposal", *COUNTED["proposal"], True,
             "Something that could be built, said plainly enough to be scored.",
             f"""<p>Something that could be built, as one file states it: what it is, how a stranger would check that it works,
the part of each {_unit("activity", "work activity")} it would do, {T("C")}, and what it would cost to make. There are
{len(d.proposals)}, in {_file('proposals/')}, and the page there says how to write one.</p>
<p>The account does not check a proposal. It says how many hours of work the claims come to, {T(PSI)}.</p>"""),
        Unit("ability", *COUNTED["ability"], True,
             "One of the enduring capacities of a person that O*NET rates occupations by.",
             f"""<p>One of the {len(d.abilities[2])} abilities of O*NET 31.0, the U.S. Department of Labor's database of
occupations: {_file('data/occupations/onet_abilities.csv')}. They are capacities of a person that last, in four families:
{", ".join(f"{int((d.abilities[2].family == f).sum())} {f.lower()}" for f in ABILITY_FAMILY.values())}. Deductive reasoning is
one, manual dexterity another, stamina another.</p>
<p>O*NET's analysts rate every {_unit("occupation")} on each, {T(LAMBDA)}, and link each ability to the kinds of
{_unit("activity", "work activity")} that call on it, {T(GAMMA)}.</p>
<p>An ability is what work demands of a person. It is rated where people differ or tire, and not where everyone finds the
work easy. So the list is a fair account of human effort, and a poor account of what a machine would find hard:
{T(MU)} says how far machines match each one.</p>"""),
        Unit("activity", *COUNTED["activity"], True,
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
        Unit("number", "number", "numbers", False,
             "A number with no unit.",
             f"""<p>A number with no unit: a count, a rating, a ratio of two amounts of the same kind, or the logarithm of
one. {T("u")} is a logarithm, {T(LAMBDA)} a rating, and {T(SIGMA)} a ratio of hours to hours.</p>"""),
        Unit("job", "job", "jobs", False,
             "One wage or salary job, as the survey of occupations counted them in May 2021.",
             f"""<p>One wage or salary job at a nonfarm employer, as the Occupational Employment and Wage Statistics of the U.S.
Bureau of Labor Statistics counted them in May 2021: {E.sum().sum() / 1e6:.0f} million in the industries and occupations it
publishes. It is a job and not a person: someone with two jobs is counted twice, and the self-employed are not counted.</p>"""),
        Unit("hour", "hour", "hours", False,
             "An hour of a person's work, paid or not.",
             f"""<p>An hour of a person's work, whoever does it and whatever it is paid. Paid hours are those the production
account of the Bureau of Economic Analysis and the Bureau of Labor Statistics counts for 2016, of employees and the
self-employed, {T("l")}: {d.sheets["l"].values.values.sum() / 1e3:.0f} billion in all. Unpaid hours are those people report
spending on work at home in the American Time Use Survey of 2017, {T("X")}.</p>
<p>With the needs counted equally, a thousand need dollars have {d.sheets[TAU].values.equal.sum():.0f} hours of work behind
them: {d.sheets[TAU].values.equal.sum() - d.sheets["X"].values.values.sum():.0f} paid and
{d.sheets["X"].values.values.sum():.0f} unpaid.</p>
<p>An hour is what work costs the person who does it, and that is the same whatever the hour earns. It is not a measure of
what the hour brings about, which differs from one hour to the next by many orders of magnitude.</p>"""),
        Unit("microwellby", "experienced microWELLBY", "experienced microWELLBYs", False,
             "A millionth of a WELLBY: one point of wellbeing, on a scale from 0 to 10, for about 32 seconds of someone's life.",
             f"""<p>A WELLBY is one point of wellbeing, on a scale from 0 to 10, for one person for one year. It is the unit in
which some governments and charity evaluators weigh what a policy does for people. A microWELLBY is a millionth of one:
one point for about {365.25 * 24 * 3600 / 1e6:.0f} seconds. One point for one hour is {POINT_HOUR:.0f} of them.</p>
<p>A WELLBY proper is counted from what people say of their life as a whole. These are experienced: counted from what
people said they felt during an activity, in the Well-Being Module of the American Time Use Survey. Each rated activity
is put on one scale from 0 to 10, happiness less the mean of pain, sadness and stress, and set against the same person's
other time that was not work. The two kinds of answer do not always agree, so a figure here is not to be set beside a
WELLBY counted the usual way without saying so.</p>
<p>With the needs counted equally, the work behind a thousand need dollars costs those who do it
{d.sheets[XI].values.equal.sum():,.0f} of them, {T(XI)}.</p>
<h2>A guide to sizes</h2>
<p>A WELLBY is an amount and not a rate, as a kilowatt-hour is: a point held for a time. What follows sets amounts of
every size beside things that come to about that much. The benchmarks of life as a whole are in
{_file('config/wellby_benchmarks.csv')}, and the moments, measured and judged, in {_file('config/wellby_moments.csv')}.
The British Treasury, whose guidance several are from, values one WELLBY at £13,000 in the prices of 2019, between a low
of £10,000 and a high of £16,000.</p>
{wellby_guide(d)}
<p>The scale has a floor and a ceiling. People rate an ordinary hour at 7 or 8 of 10, so nothing can add more than 2 or 3
points and nothing can take away more than 7 or 8. That is why three months in a trench come to under two WELLBYs, about
what two and a half years without a job come to. Whoever finds that too little is finding that the scale is too even at
its ends, and that what such months do to the years after them is not counted in them.</p>"""),
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


def dimension(phrase: str) -> tuple[str, str]:
    """(unit, words): the unit a term's rows or columns are counted in, by the name it is filed under,
    and the words that name it. The phrase for the rows or columns ends in them: "input commodities",
    "a dollar of each need"."""
    named = [(key, words) for key, forms in COUNTED.items() for words in forms if phrase.endswith(words)]
    return max(named, key=lambda x: len(x[1]))


def dimension_html(phrase: str) -> str:
    """The phrase for a term's rows or columns as a line of a page: with a capital, and the unit it
    ends in a link to the unit's page."""
    key, words = dimension(phrase)
    phrase = phrase[0].upper() + phrase[1:]
    return e(phrase[:-len(words)]) + _unit(key, e(phrase[-len(words):]))


def size_html(s: Sheet) -> str:
    """How many rows a term has, and columns if more than one, each counted in its unit."""
    sides = [(n, dimension(phrase)[0]) for n, phrase in zip(s.values.shape, (s.rows, s.cols)) if phrase is s.rows or n > 1]
    return " &times; ".join(f"{n:,} {_unit(key, e(COUNTED[key][1]))}" for n, key in sides)


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
    lines = [s.title, f"Rows: {s.rows}"]
    if s.values.shape[1] > 1:
        lines.append(f"Columns: {s.cols}")
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
    return {"Rows of": [k for k, s in d.sheets.items() if dimension(s.rows)[0] == u.key],
            "Columns of": [k for k in wide if dimension(d.sheets[k].cols)[0] == u.key],
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


ORDER_ALSO = "A marked row is taken apart under the picture, into what it is made from and the detailed activities filed under it."
TASK_ALSO = "A marked row is taken apart under the picture, into what it is made from and the capability's tasks."


def term_page(d: Data, key: str) -> str:
    """The page of one term: what its rows, columns and entries are, where it comes from, what it
    is made from and what it goes into, and the picture of the whole of it."""
    s = d.sheets[key]
    spec = [("Rows", dimension_html(s.rows))]
    if s.values.shape[1] > 1:
        spec.append(("Columns", dimension_html(s.cols)))
    spec.append(("Entries", s.entries))
    spec.append(("Unit", measure_html(key)))
    if key in EQUATIONS:
        spec.append(("Computed", _eqs([equation(key, key)])))
    if s.source:
        spec.append(("Source" if key not in EQUATIONS else "Where", s.source))
    if key in USES:
        spec.append(("Made from", term_links(d, USES[key], key)))
    users = [k for k in TERMS if key in USES.get(k, ())]
    into = [equation(k, key) for k in users if k in EQUATIONS] + ([equation("gap", key)] if key == "h" else [])
    plain = [k for k in users if k not in EQUATIONS]
    if into or plain:
        spec.append(("Used in", (_eqs(into) if into else "") + (f"<p>{term_links(d, plain, key)}</p>" if plain else "")))
    if s.note:
        spec.append(("Note", s.note))
    whole = ("The whole of it as CSV</a>, with codes for rows and columns." if s.values.size <= SPARSE_CSV else
             "Every entry that is not zero as CSV</a>, one to a line, by the codes of its row and column.")
    spec.append(("Data", f'<a href="{s.csv_file}">{whole} The code is {_file(s.code)}.'))
    why = also = ""
    if key == "A":      # a marked cell is taken apart into the industries that make the column's commodity
        also = "A marked cell is taken apart under the picture, into the industries that make the column's commodity."
        why = f"""<template id="mx-why"><h3>The parts of the cell</h3>
<p>{_m(_sym("A", key))} is {_m(_sym("B"))} times {_m(_sym("D"))}, so a cell is one row of {_m(_sym("B"))} against one column of
{_m(_sym("D"))}. Each industry that makes the column's commodity brings what it uses of the row's, in proportion to its share:</p>
{_m(f'{_sub("a", "ij")}<mo>=</mo>{_sum("k")}{_sub("b", "ik")}{_TIMES}{_sub("d", "kj")}', block=True)}</template>
"""
    if key == "h":      # a marked row is taken apart into what it is made from and the detailed activities under it
        also, why = ORDER_ALSO, order_template(key)
    if key == "o":      # and one of o into what it is made from and the capability's tasks
        also, why = TASK_ALSO, task_template(key)
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
            a, b = equation(k) if k in EQUATIONS else ("", "")
            made = _m(f"{a}<mo>=</mo>{b}") if a else '<span class="dim">Data</span>'
            rows.append(f'<tr><th scope="row">{_m(_term(k))}</th><td class="wrap"><a href="{s.href}">{e(s.name[0].upper() + s.name[1:])}</a></td>'
                        f'<td class="wrap">{size_html(s)}</td><td>{made}</td></tr>')
    return table([th("Term"), th("Name"), th("Size"), th("Made from")], rows, attrs=' class="terms"',
                 caption="Every matrix and vector of the account. Each is a link to its page: its rows, columns and entries, where "
                         "it comes from, what it goes into, and a picture of the whole of it.")


def gap(d: Data) -> pd.Series:
    """The last line of the account, for each way of weighing the needs: the part of a need dollar that
    pays for information work that is well defined and done with software that has no known open tool."""
    return d.sheets["h"].values.sum()


def abilities_section(d: Data) -> str:
    """What the gap demands of a person, by family of ability, and what is left where machines fall short."""
    alpha, rho = (d.sheets[key].values.equal * 100 for key in (ALPHA, RHO))
    judged = d.abilities[2]
    families = "".join(
        f'<tr><th scope="row">{e(f)}</th><td class="num">{alpha[judged.family == f].sum():.1f}</td>'
        f'<td class="num">{rho[judged.family == f].sum():.1f}</td>'
        f'<td class="wrap">{e(", ".join(judged.name[rho[judged.family == f].sort_values(ascending=False).index[:3]]).lower())}</td></tr>'
        for f in ABILITY_FAMILY.values())
    total = (f'<tr><td>All abilities</td><td class="num">{alpha.sum():.1f}</td><td class="num">{rho.sum():.1f}</td><td></td></tr>')
    by_family = table([th("Family of abilities"), th("The gap that falls on it, ¢", "num"), th("Of it, what machines do not match, ¢", "num"),
                       th("Largest of what is left")], [families], foot=total,
                      caption="With the needs counted equally, in cents per need dollar.")
    return f"""<p>{_m(_sym(ALPHA))} divides the gap among the {len(alpha)} abilities O*NET rates occupations by: what the work
demands of the person doing it. {_m(_sym(MU))} is a judgment of how far machines already match a person in each, and
{_m(_sym(RHO))} is what is left. Sorted, {_m(_sym(RHO))} says where machines fall short of the work there is to do.</p>
{by_family}
<p>The abilities are a person's, and are rated where people differ or tire. What everyone finds easy is not rated, and
that is often what a machine finds hard.</p>
"""


HOURS_ROWS = 10                      # the rows of eta the home page lists
FELT_HOURS = 0.1                     # the kinds of unpaid work the home page says the feel of: those of this many hours a day or more


def _count(x: float) -> str:
    """A large number in words: 1.2 billion, 340 million, 12,000."""
    for size, word in ((1e9, "billion"), (1e6, "million")):
        if x >= size:
            v = x / size
            return f"{v:.0f} {word}" if v >= 99.5 or abs(v - round(v)) < 0.05 else f"{v:.1f} {word}"
    return f"{x:,.0f}"


def _signed(x: float) -> str:
    """A number to two places with its sign, a true minus for one below zero."""
    return ("&minus;" if x < -0.005 else "") + f"{abs(x):.2f}"


def _few(x: float) -> str:
    """A number to two or three figures: 4,300, 45, 4.7, 0.31."""
    return f"{x:,.0f}" if x >= 9.95 else f"{x:.1f}" if x >= 0.995 else f"{x:.2f}"


def _wellbys(x: float) -> str:
    """A count of WELLBYs, to three figures under a million."""
    return _count(x) if x >= 1e6 else f"{float(f'{x:.3g}'):,.0f}"


GUIDE = "guide"                      # where the guide to the sizes of WELLBYs is, on the page of the unit
HEALTHY_YEAR = 7                     # the points between a year in good health and one as bad as death, by the Treasury's guidance
# the time-use survey's codes for the kinds of time the guide gives as examples
FELT = {"cleanup": "020203", "cleaning": "020101", "commute": "1805", "homework": "0603", "play": "030103", "friends": "1201",
        "eating": "1101", "sport": "1301"}


def _size(w: float) -> str:
    """An amount of wellbeing with its sign: in microWELLBYs up to the row of a thousand of them, in WELLBYs from there."""
    a, sign = abs(w), "&minus;" if w < 0 else "+"
    def figures(x):                  # to two figures under a hundred and three from there, a million or more in words
        if x >= 1e6:
            return _count(x)
        v = float(f"{x:.2g}" if x < 100 else f"{x:.3g}")
        return f"{v:,.0f}" if v >= 100 else f"{v:g}"
    micro = a < 10 ** -2.5
    said = figures(a * 1e6 if micro else a)
    return f"{sign}{said} {'microWELLBY' if micro else 'WELLBY'}{'' if said == '1' else 's'}"


def wellby_benchmarks() -> pd.DataFrame:
    """What others have found things to come to in WELLBYs, of life as a whole (config/wellby_benchmarks.csv)."""
    return pd.read_csv(M.CONFIG / "wellby_benchmarks.csv")


def wellby_moments() -> pd.DataFrame:
    """Moments, each so many points of a scale from 0 to 10 for so many hours: as others have measured them, or, with
    nobody named, as judged here (config/wellby_moments.csv)."""
    return pd.read_csv(M.CONFIG / "wellby_moments.csv", keep_default_na=False)


def wellby_examples(d: Data) -> list[tuple[float, str, str]]:
    """Things of every size, each as (WELLBYs, what it is, where the figure is from as HTML). The first are experienced,
    counted from how people rated their time against the rest of their own day. Then moments, each so many points for
    so long, as others have measured them or as judged here (config/wellby_moments.csv). The last are of life as a
    whole, from config/wellby_benchmarks.csv."""
    detail, xi, scores = d.unpaid[1], d.sheets[XI].values, proposal_scores(d)
    hour = {k: -d.below_rest(codes) / (365.25 * 24) for k, codes in {"job": WORKING, **FELT}.items()}      # WELLBYs for an hour of it, in place of other time that is not work
    home = -(detail.hours * detail.below_rest).sum() / detail.hours.sum() / (365.25 * 24)
    people = d.spending["all"].astype(float)
    people = people["Number of consumer units (in thousands)"] * 1e3 * people["People"]
    felt = [
        (hour["job"] / 60, "A minute at a job"),
        (hour["cleanup"] / 6, "Ten minutes of cleaning up the kitchen"), (hour["commute"] / 6, "Ten minutes of travel to or from work"),
        (hour["job"], "An hour at a job"), (hour["cleaning"], "An hour of cleaning the house"), (hour["homework"], "An hour of homework for a class"),
        (hour["job"] * 8, "A working day of eight hours"),
        (home * detail.hours_per_day.sum() * 365, f"A year of the unpaid work at home an adult does, {detail.hours_per_day.sum():.0f} hours a day"),
        (hour["job"] * HOURS_A_YEAR, "A year of full-time work"), (hour["job"] * HOURS_A_YEAR * 45, "Forty-five years of full-time work"),
        (-xi.spending.sum() * d.spent / 1e9, "All the work behind the needs of the United States, for a year"),
        (hour["play"] / 60, "A minute of play with one's child"),
        (hour["play"] / 6, "Ten minutes of play with one's child"), (hour["friends"], "An hour with friends or family"),
        (hour["eating"], "An hour of eating and drinking"), (hour["sport"], "An hour of sport or exercise"),
        (-hour["job"] * 8, "A day off, in place of a working day of eight hours"),
        (hour["friends"] * 365, "An hour a day with friends or family, for a year"),
        *((r.wellbys_a_year, f'<a href="{d.proposals[k].href}">{e(d.proposals[k].name)}</a>, if it did all it claims, for a year')
          for k, r in scores.iterrows()),
    ]
    marks = wellby_benchmarks()
    life = [(r.wellbys, e(r.what), f'<a href="{e(r.url)}">{e(r.by)}</a>') for r in marks.itertuples()]
    treasury = marks[marks.wellbys == HEALTHY_YEAR].iloc[0]
    life.append((HEALTHY_YEAR * people, f"A year in good health for everyone in the United States, {_count(people)} people",
                 f'<a href="{e(treasury.url)}">{e(treasury.by)}</a>'))
    def judged(r) -> str:            # a moment nobody has measured says the points and the time it is taken to be
        return f"{abs(r.points):g} point{'' if abs(r.points) == 1 else 's'} {'up' if r.points > 0 else 'down'} for {e(r.time)}, a judgment"
    moments = [(r.points * r.hours / (365.25 * 24), e(r.what), f'<a href="{e(r.url)}">{e(r.by)}</a>' if r.by else judged(r))
               for r in wellby_moments().itertuples()]
    return [(w, what, "") for w, what in felt] + moments + life


def wellby_guide(d: Data) -> str:
    """A table of sizes, a row for each power of ten from a tenth of a microWELLBY up, with things that take away
    about that much and things that add it. An example is put in the row nearest its size."""
    examples = wellby_examples(d)
    rung = lambda w: int(np.floor(np.log10(abs(w)) + 0.5))
    rungs = range(-7, max(rung(w) for w, _, _ in examples) + 1)
    def one_point_for(k: int) -> str:
        if k >= 0:
            return "one person for a year" if k == 0 else f"{_count(10 ** k)} people for a year"
        seconds = 10.0 ** k * 365.25 * 24 * 3600
        for size, name in ((7 * 86400, "weeks"), (86400, "days"), (3600, "hours"), (60, "minutes"), (1, "seconds")):
            if seconds >= 1.5 * size:
                return f"one person for {seconds / size:.{0 if seconds / size >= 9.5 else 1}f} {name}".replace(".0 ", " ")
    def cell(k: int, sign: int) -> str:
        here = sorted((x for x in examples if rung(x[0]) == k and np.sign(x[0]) == sign), key=lambda x: abs(x[0]))
        return "<br>".join(f"{what}: {_size(w)}" + (f" ({source})" if source else "") for w, what, source in here)
    def amount(k: int) -> str:       # a thousandth of a WELLBY is said as a thousand microWELLBYs
        return "1,000 microWELLBYs" if k == -3 else _size(10.0 ** k)[1:]
    rows = [f'<tr><th scope="row">{amount(k)}</th><td class="wrap">{one_point_for(k)}</td>'
            f'<td class="wrap">{cell(k, -1)}</td><td class="wrap">{cell(k, 1)}</td></tr>' for k in rungs]
    moments = wellby_moments()
    cited = pd.concat([moments[moments.by != ""], wellby_benchmarks()]).drop_duplicates("source")
    sources = " ".join(f'<a href="{e(r.url)}">{e(r.source)}</a>.' for r in cited.itertuples())
    return table([th("Amount"), th("That is one point for"), th("Takes about that much away"), th("Adds about that much")], rows,
                 attrs=f' data-scores id="{GUIDE}"',
                 caption="Each row is ten times the one above, and a thing is put in the row nearest its size. A figure with "
                         "nothing after it is counted here, from how people rated that time against the rest of their own "
                         "day. A figure called a judgment is nobody's measurement: it is the points and the time it says, "
                         "multiplied. A figure with a name after it is that source's, of feelings at the time or of life as "
                         "a whole, each on its own scale from 0 to 10, and the three are not the same measure. "
                         f"The sources: {sources}")


def hours_section(d: Data) -> str:
    """The account again in hours, and what changes when work is counted by the time it takes and not by its pay."""
    f, h, tau, eta = (d.sheets[key].values for key in ("f", "h", TAU, ETA))
    unpaid_dollars, unpaid_hours = d.sheets["G"].values.values.sum(), d.sheets["X"].values.values.sum()
    kept = d.sheets["m"].values.iloc[:, 0] * (1 - d.sheets["e"].values.iloc[:, 0])
    unpaid = d.unpaid_hours.sum() * kept
    place = h.equal.rank(ascending=False).astype(int)
    names = d.sheets[ETA].row_names
    rows = [f'<tr><th scope="row" class="wrap">{e(names[a])}</th><td class="num">{v:.1f}</td><td class="num">{unpaid[a]:.1f}</td>'
            f'<td class="num">{h.equal[a] * 100:.2f}</td><td class="num">{place[a]}</td></tr>'
            for a, v in eta.equal.nlargest(HOURS_ROWS).items()]
    first = table([th("Work activity"), th("Hours per $1,000", "num"), th("Of them unpaid", "num"), th("In dollars, ¢", "num"),
                   th("Place by dollars", "num")], rows, attrs=" data-scores",
                  caption=f"The first {HOURS_ROWS} rows of the gap in hours, with the needs counted equally, beside the same rows "
                          "counted in dollars.")
    a_year = tau.spending.sum() * d.spent / 1000
    zeta, detail, at_work = d.sheets[ZETA].values, d.unpaid[1], d.unpleasant(WORKING)
    at_home = (detail.hours * detail.unpleasant).sum() / detail.hours.sum()
    unpleasant_unpaid = at_home * unpaid_hours
    xi, job_below, job_severe = d.sheets[XI].values, d.below_rest(WORKING), d.felt(WORKING, "severe")
    home_below, home_severe = ((detail.hours * detail[m]).sum() / detail.hours.sum() for m in ("below_rest", "severe"))
    lost_unpaid = home_below * unpaid_hours * POINT_HOUR
    below = detail.set_index("activity").below_rest
    kinds = [("Working at a job", d.time_use["Working"], at_work, job_severe, job_below)] + [
        (r.activity, r.hours_per_day, r.unpleasant, r.severe, r.below_rest) for r in detail.sort_values("hours_per_day", ascending=False).itertuples()
        if r.hours_per_day >= FELT_HOURS]
    felt = table([th("Kind of time"), th("Hours a day for each person", "num"), th("Part of it that is unpleasant", "num"),
                  th("Part with a bad feeling at 5 or 6", "num"), th("Points below the rest of the day", "num")],
                 [f'<tr><th scope="row" class="wrap">{e(name)}</th><td class="num">{hours:.2f}</td><td class="num">{part * 100:.0f}%</td>'
                  f'<td class="num">{severe * 100:.0f}%</td><td class="num">{_signed(points)}</td></tr>'
                  for name, hours, part, severe, points in kinds], attrs=" data-scores",
                 foot=f'<tr><td>Time that is not work</td><td></td><td class="num">{d.unpleasant(d.not_work) * 100:.0f}%</td>'
                      f'<td class="num">{d.felt(d.not_work, "severe") * 100:.0f}%</td><td class="num">{_signed(0)}</td></tr>',
                 caption=f"Paid work, and the kinds of unpaid work at home that take at least {FELT_HOURS} hours a day, as people "
                         "of 15 and over reported them. Points are of a scale from 0 to 10, against the same person's other "
                         "time that was not work.")
    return f"""{_eqs([equation(key) for key in (BETA, PI, TAU, ETA)])}
<p>A dollar counts work by what it is paid. An hour counts it by the time of someone's life it takes, which is the same
whatever it earns. {_m(_sym(CHI))} is the hours worked for each dollar of a sector's value added, so {_m(_sym(BETA))} is
the hours each sector works. {_m(_sym("Z"))} divides a sector's hours among occupations by their jobs, and
{_m(_sym("X"))} is the unpaid work at home, in hours.</p>
<p>With the needs counted equally, a thousand need dollars have {tau.equal.sum():.0f} hours of work behind them:
{tau.equal.sum() - unpaid_hours:.0f} paid and {unpaid_hours:.0f} unpaid. Unpaid work is {unpaid_dollars / f.equal.sum() * 100:.0f}%
of the work counted in dollars and {unpaid_hours / tau.equal.sum() * 100:.0f}% of it counted in hours: a paid work dollar is the
whole of a sector's value added, of which pay is about half, and an hour at home is valued at the wage of a cook or a
cleaner. The gap,
{_m(_sym(ETA))}, is {eta.equal.sum():.0f} of the {tau.equal.sum():.0f} hours. As the needs were in fact paid for, the work
behind them took {_count(a_year)} hours in the year.</p>
{first}
<p>The same survey asked people how they felt during three activities of their day. The time of an activity is called
unpleasant here when pain, sadness or stress was rated above happiness. Working at a job is unpleasant
{at_work * 100:.0f}% of the time, and unpaid work at home {at_home * 100:.0f}%. So of the {tau.equal.sum():.0f} hours behind a
thousand need dollars, {zeta.equal.sum():.1f} are unpleasant, {_m(_sym(ZETA))}: {zeta.equal.sum() - unpleasant_unpaid:.1f} paid
and {unpleasant_unpaid:.1f} unpaid. Unpaid work is {unpaid_hours / tau.equal.sum() * 100:.0f}% of the hours and
{unpleasant_unpaid / zeta.equal.sum() * 100:.0f}% of the unpleasant ones.</p>
{felt}
<p>Unpleasant or not is a coarse count: it gives a mildly irritating hour the weight of an hour of agony. So each rated
activity is also put on one scale from 0 to 10, happiness less the mean of pain, sadness and stress, and set against the
same person's other rated time that was not work, which is what an hour of work given back would become. Working at a job
is rated {job_below:.2f} points below the rest of the day and unpaid work at home {home_below:.2f}: cleaning is
{below["Interior cleaning"]:.2f} below it, preparing food {below["Food and drink preparation"]:.2f}, and caring for the
household's children {-below["Caring for and helping household children"]:.2f} above it.</p>
<p>A WELLBY is one point of wellbeing for one person for one year, so one point for one hour is {POINT_HOUR:.0f}
microWELLBYs. At that rate the work behind a thousand need dollars costs those who do it {xi.equal.sum():,.0f}
experienced microWELLBYs, {_m(_sym(XI))}: {xi.equal.sum() - lost_unpaid:,.0f} paid and {lost_unpaid:,.0f} unpaid. Unpaid
work is {unpaid_hours / tau.equal.sum() * 100:.0f}% of the hours and {lost_unpaid / xi.equal.sum() * 100:.0f}% of this cost.
As the needs were in fact paid for, it comes to {_wellbys(xi.spending.sum() * d.spent / 1e9)} WELLBYs a year. A
<a href="{d.units["microwellby"].href}#{GUIDE}">guide to sizes</a> sets these amounts beside other things.</p>
<p>They are called experienced because a WELLBY proper is counted from what people say of their life as a whole, and
these are counted from what they felt at the time. The scale is also even: six hours one point down count as one hour
six points down, and those who study severe pain think the worst hours count for far more. Counting only the time with
a bad feeling at 5 or 6, a job has {job_severe * 100:.0f}%, unpaid work at home {home_severe * 100:.0f}% and time that is
not work {d.felt(d.not_work, "severe") * 100:.0f}%. All paid work is given the one rate, because the files used here do
not say what a respondent's job was.</p>
"""


def proposal_scores(d: Data) -> pd.DataFrame:
    """What each proposal comes to: the activities it claims, the work in them that is not already open, in cents
    per need dollar and hours per thousand need dollars (needs counted equally), in hours a year (as the needs
    were paid for), the unpaid part of those and the part people find unpleasant, what those hours cost the people who work
    them in experienced WELLBYs a year, its cost in hours, the hours a year for each hour of cost and the WELLBYs a year
    for each thousand hours of it, and the hours the paid work it claims still takes, now against then: the mean of
    kappa over its paid hours."""
    f, tau, C = d.sheets["f"].values, d.sheets[TAU].values, d.sheets["C"].values
    left = 1 - d.sheets["e"].values.iloc[:, 0]
    a_year = d.spent / 1000              # an hour per thousand need dollars, in hours a year
    out = pd.DataFrame({"activities": (C > 0).sum(), "cents": C.T @ (f.equal * left) * 100, "hours": C.T @ (tau.equal * left),
                        "a_year": C.T @ (tau.spending * left) * a_year, "unpaid_a_year": C.T @ (d.unpaid_hours.sum() * left) * a_year,
                        "unpleasant_a_year": C.T @ (d.sheets[ZETA].values.spending * left) * a_year,
                        "wellbys_a_year": C.T @ (d.sheets[XI].values.spending * left) * a_year / 1e6,
                        "cost": pd.Series({k: x.cost for k, x in d.proposals.items()}, dtype=float)})
    paid = C.mul((tau.equal - d.unpaid_hours.sum()) * left, axis=0)                   # the paid hours each claims, by activity
    still = paid.mul(d.sheets[KAPPA].values.equal, axis=0).sum() / paid.sum()
    return out.assign(back=out.a_year / out.cost, wellbys_back=out.wellbys_a_year / out.cost * 1000, still=still)


def proposals_section(d: Data) -> str:
    """The proposals there are, what each would do and cost, and what none of them claims."""
    tau, eta, C = d.sheets[TAU].values, d.sheets[ETA].values, d.sheets["C"].values
    left = 1 - d.sheets["e"].values.iloc[:, 0]
    scores = proposal_scores(d).sort_values("a_year", ascending=False)
    def cell(x, text):
        return f'<td class="num">{text if pd.notna(x) else "none given"}</td>'
    rows = [f'<tr><th scope="row"><a href="{d.proposals[k].href}">{e(d.proposals[k].name)}</a></th>'
            f'<td class="num">{_count(r.a_year)}</td><td class="num">{_count(r.unpaid_a_year)}</td>'
            f'<td class="num">{_wellbys(r.wellbys_a_year)}</td>'
            + cell(r.cost, _count(r.cost)) + cell(r.back, _few(r.back)) + cell(r.wellbys_back, _few(r.wellbys_back))
            + f'<td class="num">{r.still:.2f}</td></tr>'
            for k, r in scores.iterrows()]
    listed = table([th("Proposal"), th("Hours a year", "num"), th("Of them unpaid", "num"), th("Experienced WELLBYs a year", "num"),
                    th("Cost to make, hours", "num"), th("Hours a year for each hour of cost", "num"),
                    th("WELLBYs a year for each thousand hours of cost", "num"),
                    th(f"Its paid work: hours in {HR.YEAR} for each in {HR.SINCE}", "num")], rows, attrs=" data-scores",
                   caption="Hours and WELLBYs a year are as the needs were in fact paid for.")
    together = (tau.equal * left * C.max(axis=1)).sum()
    unclaimed = eta.equal[C.max(axis=1) == 0].nlargest(3)
    names = d.sheets[ETA].row_names
    return f"""<p>The account says where the work is. It cannot say what could be built to do it. A proposal says that: what it
is, how a stranger would check that it works, the part of each work activity it would do, {_m(_sym("C"))}, and what it
would cost to make. The account then says how many hours the claims come to, less what is already open:</p>
{_eqs([equation(PSI)])}
{listed}
<p>A proposal's hours are a ceiling: the work its claims cover, if it did all of it. Hours are not alike to those who
work them, so each is also weighed by the points people rate such work below the rest of their day, {_m(_sym(XI))}, which
gives what the hours cost them in experienced WELLBYs a year. That moves paid work up: a job is rated further below the
rest of the day than most work at home is. The shares and the costs are each
proposer's own, and the costs here are guesses at an order of magnitude, so the hours and the WELLBYs for each hour of
cost are no firmer than that. The last column says whether the paid work a proposal claims has been going anyway: the hours it took
in {HR.YEAR} for each hour it took in {HR.SINCE}, for the same output, in the sectors where it is done,
{_m(_sym(KAPPA))}. Well under one, such work is already being done away with and a proposal adds less. Near one, it is
stuck. It is a measure of the sectors the work is done in, so it says little of an activity that is spread over many,
and health care's output is measured too poorly for its figure to be trusted.
Proposals overlap, and where two claim the same activity the larger claim is counted once: together these claim
{together:.0f} of the {tau.equal.sum():.0f} hours behind a thousand need dollars. The largest rows of {_m(_sym(ETA))}
that none of them claims are {", ".join(e(names[a].rstrip(".")).lower() for a in unclaimed.index[:-1])} and
{e(names[unclaimed.index[-1]].rstrip(".")).lower()}.</p>
<p>A proposal is one file in {_file('proposals/')}, and the page there says how to write one.</p>
"""


def proposal_page(d: Data, key: str) -> str:
    """The page of one proposal: what it states, what it comes to, and each of its claims with the hours in it."""
    x, score, psi = d.proposals[key], proposal_scores(d).loc[key], d.sheets[PSI].values.loc[key]
    tau, opened, names = d.sheets[TAU].values.equal, d.sheets["e"].values.iloc[:, 0], d.sheets[TAU].row_names
    does = x.does.assign(hours=tau[x.does.index] * (1 - opened[x.does.index]) * x.does.share).sort_values("hours", ascending=False)
    rows = [f'<tr><th scope="row" class="wrap">{e(names[a])}</th><td class="num">{r.share:g}</td><td class="wrap">{e(r.basis)}</td>'
            f'<td class="num">{tau[a]:.2f}</td><td class="num">{opened[a]:g}</td><td class="num">{r.hours:.2f}</td></tr>'
            for a, r in does.iterrows()]
    foot = f'<tr><td>All it claims</td><td></td><td></td><td></td><td></td><td class="num">{psi.equal:.2f}</td></tr>'
    claims = table([th("Work activity"), th("Part claimed", "num"), th("Why"), th("Hours in the activity", "num"),
                    th("Part already open", "num"), th("Hours it would do", "num")], rows, foot=foot, attrs=" data-scores",
                   caption="Hours of work for every thousand need dollars, paid and unpaid, with the needs counted equally. "
                           "The hours it would do are the hours in the activity, times the part claimed, times the part not already open.")
    spec = [("What it is", e(x.what)), ("How it is checked", e(x.check))]
    if x.by:
        spec.append(("Proposed by", e(x.by)))
    spec.append(("Would do", f"{psi.equal:.1f} hours of work for every thousand need dollars with the needs counted equally, "
                             f"{psi.spending:.1f} weighing them by what is spent on each, and {psi.poorest:.1f} by the poorest "
                             f"fifth's budget: its row of {_m(_sym(PSI))}. In dollars that is {score.cents:.1f} cents of work "
                             "per need dollar."))
    spec.append(("In a year", f"{_count(score.a_year)} hours, as the needs were in fact paid for. {_count(score.unpaid_a_year)} of them "
                              "are unpaid work at home, which no job goes with."))
    spec.append(("Of them unpleasant", f"{_count(score.unpleasant_a_year)} hours a year, at the rates people report for such work: "
                                       f"its claims' part of {_m(_sym(ZETA))}."))
    spec.append(("In wellbeing", f"{_wellbys(score.wellbys_a_year)} experienced WELLBYs a year: what those hours cost the people who "
                                 f"work them, each hour at the points people rate such work below the rest of their day. It is "
                                 f"its claims' part of {_m(_sym(XI))}, and comes to "
                                 f"{score.wellbys_a_year * 1e6 / POINT_HOUR / score.a_year:.2f} points for each of its hours."))
    if x.cost:
        spec.append(("Cost to make", f"{_count(x.cost)} hours of people's work, by the proposer's estimate. {e(x.cost_basis)}"))
        spec.append(("For each hour of cost", f"{score.back:,.0f} hours a year, if it did all it claims, and for each thousand "
                                              f"hours of cost {_few(score.wellbys_back)} WELLBYs a year."))
    spec.append(("Has it been moving", f"The paid work it claims took {score.still:.2f} hours in {HR.YEAR} for each hour in {HR.SINCE}, "
                                       f"for the same output, in the sectors where it is done: the mean of {_m(_sym(KAPPA))} over "
                                       "its paid hours. Well under one, such work is going anyway. Near one, it is stuck."))
    spec.append(("File", _file(x.file)))
    body = f"""
<p class="crumbs"><a href="{HOME}">The account</a> &rsaquo; <a href="{HOME}#proposals">Proposals</a></p>
<h1 class="long">{e(x.name)}</h1>
<dl class="spec">{"".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in spec)}</dl>
{claims}
"""
    return page(x.name, body)


def account_section(d: Data) -> str:
    """The whole account as five equations, what they come to, and every term in them."""
    f, h = (d.sheets[key].values for key in "fh")
    unpaid = d.sheets["G"].values.values.sum()
    info = d.sheets["s"].values.iloc[:, 0]
    g, thought = gap(d) * 100, h.mul(info, axis=0).sum() * 100
    return f"""{_eqs([equation(key) for key in ("x", "p", "f", "h", "gap")])}
<p>{_m(_sym(OMEGA))} weighs the needs, in three ways, and every term from {_m(_sym("p"))} on has a column for each.
{_m(_sym(THETA))} says what each occupation's work is, as {len(f)} work activities, and {_m(_sym("G"))} is the unpaid work
done at home, {unpaid * 100:.0f} cents for every dollar spent on the needs. {_m(_ONES)} is a column of ones.</p>
<p>With the needs counted equally, the third line places {f.equal.sum() * 100:.0f} cents of work, paid and unpaid, on the
activities it consists of. The fourth keeps the part of each activity that is well defined, {_m(_sym("m"))}, and has no
known open implementation, {_m(_sym("e"))}, and the fifth adds it up: {g.equal:.1f} cents. Weighing the needs by what is
spent on each it is {g.spending:.1f} cents, and by the poorest fifth's budget {g.poorest:.1f}.</p>
<p>An activity is a capability whatever carries it out: software, a written procedure or a mechanism. Of the
{g.equal:.1f} cents, {thought.equal:.1f} are information work, and {g.equal - thought.equal:.1f} are work that needs a
body, where the processing needs a machine to act through as well.</p>
<h2 id="order">The order to work in</h2>
<p>This is {_m(_sym("h"))}, sorted by its first column: the activities with the most well-defined work and no known open
implementation, with the needs counted equally. Its first {ORDER_ROWS} rows are in view, and the other two columns weigh
the needs the other two ways. The first row is marked, and under the picture it is taken apart: into what it is made
from, what is judged of it, and the detailed activities filed under it. Click another row to take that one apart.</p>
{sheet_picture(d.sheets["h"], also=ORDER_ALSO, extra=order_template())}
<h2 id="abilities">The abilities the gap calls on</h2>
{abilities_section(d)}
<p>The same question can be put to the software that information work is done with today:
{_m(_sym("k"))} places that work on {len(d.sheets["k"].values)} software capabilities, and {_m(_sym("o"))} keeps the part
with no open tool, {d.sheets["o"].values.equal.sum() * 100:.1f} cents.</p>
<h2 id="hours">The same account in hours</h2>
{hours_section(d)}
<h2 id="proposals">Proposals</h2>
{proposals_section(d)}
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
deliver them, to the sectors whose income it becomes, to the occupations they pay, and to the activities their
work consists of. Every term is a link to its matrix.</p>
{account_section(d)}"""
    return page("The account", body, home=True, scripts=(d.sheets["h"].data_file, "matrix.js"))


def main():
    d = Data()
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(WEB, SITE)
    pages = {"index.html": index, **{SYMBOL_PAGES[key]: (lambda d, key=key: term_page(d, key)) for key in TERMS},
             **{u.href: (lambda d, key=key: unit_page(d, key)) for key, u in d.units.items()},
             **{x.href: (lambda d, key=key: proposal_page(d, key)) for key, x in d.proposals.items()}}
    for name, fn in pages.items():
        (SITE / name).write_text(with_tips(d, fn(d)), encoding="utf-8")
    for key, sheet in d.sheets.items():
        (SITE / sheet.data_file).write_text(matrix_data(d, key), encoding="utf-8")
        (SITE / sheet.csv_file).write_text(sheet_csv(sheet), encoding="utf-8")
    (SITE / MATRIX_PARTS).write_text(matrix_a_parts(d), encoding="utf-8")
    (SITE / ORDER_PARTS).write_text(order_parts(d), encoding="utf-8")
    (SITE / TASK_PARTS).write_text(task_parts(d), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"wrote {len(pages)} pages to {SITE}")


if __name__ == "__main__":
    main()

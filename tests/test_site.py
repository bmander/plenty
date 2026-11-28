import html as markup
import json
import tomllib
import re
import numpy as np
import pandas as pd
import pytest
from plenty import site


@pytest.fixture(scope="module")
def built():
    site.main()
    return site.Data()


def test_site_builds_and_links_resolve(built):
    pages = sorted(p.name for p in site.SITE.glob("*.html"))
    units = [u.href for u in built.units.values()]
    proposed = [x.href for x in built.proposals.values()]
    assert pages == sorted(["index.html"] + list(site.SYMBOL_PAGES.values()) + units + proposed)      # the account, and a page for each term, unit and proposal
    for name in pages:
        text = (site.SITE / name).read_text()
        assert ">nan<" not in text and "nan%" not in text, name
        for href in re.findall(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', text):
            if href.startswith(("http://", "https://")):
                continue
            assert (site.SITE / href).exists(), f"{name}: broken link {href}"
        # every anchor used, on another page or this one, exists on its target
        for target, anchor in re.findall(r'href="([A-Za-z0-9-]*\.html)?#([^"]+)"', text):
            assert f'id="{anchor}"' in (site.SITE / (target or name)).read_text(), f"{name}: {target}#{anchor}"


def _data(sheet):
    text = (site.SITE / sheet.data_file).read_text()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def _link(x):
    """How a link to a term's page opens, or a unit's: with the tip it shows under the pointer."""
    tip = site.term_tip(x) if isinstance(x, site.Sheet) else site.unit_tip(x)
    return f'<a href="{x.href}" data-tip="{markup.escape(tip)}"'


def test_a_link_to_a_term_says_what_its_rows_columns_and_entries_are(built):
    assert set(site.MEASURED_IN) == set(site.TERMS)
    for key, sheet in built.sheets.items():
        lines = site.term_tip(sheet).split("\n")
        assert lines[0] == sheet.title and lines[1] == f"Rows: {sheet.rows}" and lines[-1] == f"Unit: {site.measure_text(key)}", key
        # a vector has rows alone
        assert (len(lines) == 4 and lines[2] == f"Columns: {sheet.cols}") if sheet.values.shape[1] > 1 else len(lines) == 3, key
    x = site.term_tip(built.sheets["x"]).split("\n")
    assert x[1:] == ["Rows: produced commodities", "Columns: a dollar of each need",
                     "Unit: commodity dollars produced per need dollar"]
    for name in [site.HOME] + list(site.SYMBOL_PAGES.values()):      # and every link to a term carries its own
        text = (site.SITE / name).read_text()
        for href, tip in re.findall(r'<a href="((?:matrix|vector)-[A-Za-z]+\.html)"(?: data-tip="([^"]*)")?', text):
            sheet = next(s for s in built.sheets.values() if s.href == href)
            assert markup.unescape(tip) == site.term_tip(sheet), f"{name}: {href}"


def test_every_unit_has_a_page_and_every_term_links_to_its_units(built):
    units = built.units
    home = (site.SITE / site.HOME).read_text()
    assert len({u.href for u in units.values()}) == len(units) and all(u.key == key for key, u in units.items())
    used = set()
    for key, sheet in built.sheets.items():
        page = (site.SITE / sheet.href).read_text()
        spec = page[page.index('<dl class="spec">'):page.index("</dl>")]
        nr, nc = sheet.values.shape
        # the rows and the columns are each said as what they are, ending in their unit, which is a link; their number is not said
        sides = [("Rows", nr, sheet.rows)] + ([("Columns", nc, sheet.cols)] if nc > 1 else [])
        for label, n, phrase in sides:
            unit, words = site.dimension(phrase)
            u = units[unit]
            assert u.counts and words in (u.name, u.plural) and phrase.endswith(words), (key, phrase)
            said = phrase[0].upper() + phrase[1:]
            line = f'<dt>{label}</dt><dd>{markup.escape(said[:-len(words)])}{_link(u)}>{markup.escape(said[-len(words):])}</a></dd>'
            assert line in spec, (key, label)
            used.add(unit)
        # the table of terms has the numbers, each counted in the unit
        size = " &times; ".join(f"{n:,} {_link(units[site.dimension(phrase)[0]])}>{units[site.dimension(phrase)[0]].plural}</a>" for _, n, phrase in sides)
        assert f'<td class="wrap">{size}</td>' in home, key
        # and the entries are measured in units that have pages, and are not what rows are counted in
        measured = site.measures(key)
        assert measured and all(not units[m].counts for m in measured), key
        line = spec.split("<dt>Unit</dt>")[1].split("</dd>")[0]
        assert all(f'<a href="{units[m].href}"' in line for m in measured) and "[" not in line and "|" not in line, key
        assert "[" not in site.measure_text(key) and "|" not in site.measure_text(key), key
        used.update(measured)
    assert used == set(units)                                  # no unit is left without a term
    table = home[home.index('id="units"'):]
    for key, u in units.items():
        assert f'<th scope="row">{_link(u)}>{markup.escape(u.title)}</a></th>' in table, key
        page = (site.SITE / u.href).read_text()
        assert f"<h1 class=\"long\">{markup.escape(u.title)}</h1>" in page, key
        users = site.unit_users(built, u)
        assert any(users.values()), key
        for how, terms in users.items():                       # its page lists the terms that use it, by how
            assert (f"<dt>{how}</dt>" in page) == bool(terms), (key, how)
            for term in terms:
                assert f'<a href="{built.sheets[term].href}"' in page.split(f"<dt>{how}</dt>")[1].split("</dd>")[0], (key, how, term)
    x = site.unit_users(built, units["need-dollar"])
    in_hours = [site.ETA, site.TAU, site.PI, site.BETA, "X", site.ZETA, site.KEPT, site.LOST, site.BACK, site.JOBS, site.PSI, site.BEHIND, site.ILL]
    assert x["Entries of"] == list("xpfhdGb") + in_hours + [site.RHO, site.ALPHA, "k", "o"] and not x["Rows of"] and not x["Columns of"]
    assert site.unit_users(built, units["hour"])["Entries of"] == [site.ETA, site.TAU, site.PI, site.BETA, site.LABOUR, site.CHI, "l", "X", site.ZETA, site.PSI, site.BEHIND, site.WITH]
    assert site.unit_users(built, units["healthy-hour"]) == {"Rows of": [], "Columns of": [], "Entries of": [site.KEPT, site.LOST, site.BACK]}
    assert site.unit_users(built, units["job-year"]) == {"Rows of": [], "Columns of": [], "Entries of": [site.JOBS]}
    assert site.unit_users(built, units["healthy-year"]) == {"Rows of": [], "Columns of": [], "Entries of": [site.ILL]}
    assert site.unit_users(built, units["cause"]) == {"Rows of": [site.LIFTS, site.ILL], "Columns of": [], "Entries of": []}
    assert site.unit_users(built, units["proposal"]) == {"Rows of": [site.KEPT, site.LOST, site.BACK, site.JOBS, site.PSI, site.BEHIND],
                                                             "Columns of": ["C", site.WITH, site.REPLACED, site.LIFTS], "Entries of": []}
    assert site.unit_users(built, units["need"]) == {"Rows of": [site.OMEGA], "Columns of": ["x", "d", "Y", "v"], "Entries of": []}


def test_the_account_is_five_equations_and_a_table_of_every_term(built):
    html = (site.SITE / site.HOME).read_text()
    account = html[:html.index('id="order"')]
    assert account.count('<math display="block"') == 1 and account.count("<mtr>") == 5
    # what the lines come to is said under them, for each way of weighing the needs
    f, gap, o = (built.sheets[key].values.sum() for key in "fho")
    assert f"{f.equal * 100:.0f} cents of work" in html and f"{len(built.sheets['f'].values)} work activities" in html
    assert all(f"{x * 100:.1f}" in html for x in gap) and (site.gap(built) == gap).all()
    # how much of the gap is information work and how much needs a body, and what the same question comes to for software
    thought = (built.sheets["h"].values.equal * built.sheets["s"].values.iloc[:, 0]).sum()
    assert f"{thought * 100:.1f} are information work" in html and f"{(gap.equal - thought) * 100:.1f} are work that needs a\nbody" in html
    assert f"{o.equal * 100:.1f} cents" in html and f"{len(built.sheets['k'].values)} software capabilities" in html
    assert f"{built.sheets['G'].values.values.sum() * 100:.0f} cents" in html
    table = html[html.index('id="terms"'):]
    for key, sheet in built.sheets.items():
        assert f'<td class="wrap">{_link(sheet)}>' in table, key       # each term is listed, by name
        assert f'<mi>{_link(sheet)}>' in html, key                     # and its letter is a link wherever it is written
    assert list(built.sheets) == site.TERMS and len(set(site.SYMBOL_PAGES.values())) == len(site.TERMS)
    assert len({name.lower() for name in site.SYMBOL_PAGES.values()}) == len(site.TERMS)   # no two files differ by case alone
    # A is a link to its own page, so the rest of the inverse is the link to L's: two brackets, the I and the exponent
    piece = f'{_link(built.sheets["L"])} class="inv'
    for name in (site.HOME, site.SYMBOL_PAGES["x"]):
        text = (site.SITE / name).read_text()
        assert text.count(piece) >= 4 and text.count(piece) % 4 == 0, name
        assert text.count(f'<mtext>{piece}">&minus;1</a></mtext></msup>') == text.count(piece) // 4, name


def test_the_equations_the_pages_print_hold_of_the_matrices_they_show(built):
    v = {k: s.values for k, s in built.sheets.items()}
    def col(key):
        return v[key].iloc[:, 0]
    com, ind = v["A"].index, v["U"].columns
    eye = np.eye(len(com))
    assert np.allclose(v["L"].values @ (eye - v["A"].values), eye, atol=1e-9) and np.diag(v["L"].values).min() >= 1
    assert max(abs(np.linalg.eigvals(v["A"].values))) < 1         # which is why the rounds of supply add up at all
    assert np.allclose(v["x"].values, v["L"].values @ v["d"].loc[com].values)
    assert np.allclose(v["d"].values, (v["Y"] / v["Y"].sum()).values) and np.allclose(v["d"].sum(), 1.0)
    assert np.allclose(v["A"].values, v["B"].values @ v["D"].loc[ind, com].values)
    assert np.allclose(v["B"].values, (v["U"] + v["K"]).values / col("g")[ind].values)
    assert np.allclose(col("g")[v["V"].index], v["V"].sum(axis=1)) and np.allclose(col("q")[v["V"].columns], v["V"].sum(axis=0))
    made = col("q")[com].values > 0
    assert np.allclose(v["D"].loc[ind, com].values[:, made], (v["V"].loc[ind, com] / col("q")[com]).values[:, made])
    # capital: each investor's purchases, placed on its industries
    H = v["H"].loc[ind]
    assert (H.sum(axis=1) == 1).all() and list(H.columns) == list(v["F"].columns) == list(site.INVESTOR_NAME)
    assert np.allclose(v["K"].values, (v["F"].loc[com].values @ H.values.T) * v["S"].values)
    assert np.allclose(v["K"].sum(axis=1), v["F"].loc[com].sum(axis=1))      # nothing is made or lost in the placing
    government = H[["fed_defense", "fed_nondefense", "state_local"]].sum(axis=1) == 1
    assert np.allclose(col("z")[government], col("g")[government]) and (col("z") >= 0).all()
    # value added
    r = col("r")[com]
    assert np.allclose(r, (col("y")[ind] / col("g")[ind]).values @ v["D"].loc[ind, com].values)
    earned = v["x"].loc[com].mul(r, axis=0)
    assert np.allclose(v["v"].loc[com].values, (earned / earned.sum()).values) and np.allclose(v["v"].sum(), 1.0)
    # work
    occ = v["W"].columns
    paid = v["P"].sum(axis=1)
    assert np.allclose(v["W"].values, v["P"].div(paid.replace(0, np.nan), axis=0).fillna(0.0).values)
    assert np.allclose(v["P"].values, v["T"].values @ (v["E"] * v["M"]).values / 1e6)
    theta, phi = v[site.THETA], v[site.PHI]
    assert list(theta.index) == list(phi.index) == list(occ) and set(np.round(theta.sum(axis=1), 9)) == {0.0, 1.0}
    assert phi.values.min() >= 0 and phi.sum(axis=1).max() <= 1 + 1e-9
    # the needs are weighed three ways, and every term from p on has a column for each
    w, needs = v[site.OMEGA], list(v["v"].columns)
    assert list(w.index) == needs and list(w.columns) == ["equal", "spending", "poorest"] and np.allclose(w.sum(), 1.0)
    assert np.allclose(w.equal, 1 / len(needs)) and np.allclose(w.spending, v["Y"].sum() / v["Y"].values.sum())
    assert w.at["safety", "poorest"] == 0 and w.poorest.idxmax() == "shelter"       # households do not pay for police themselves
    p = v["W"].values.T @ (v["v"].loc[com].values @ w.values)                    # the second line of the account
    assert np.allclose(p, v["p"].loc[occ].values, atol=1e-12) and list(v["p"].columns) == list(w.columns)
    # with the needs counted equally, and before any unpaid work, these are the flows the scripts publish
    assert np.allclose(p[:, 0] @ theta.values, built.act.flow[theta.columns], atol=1e-9)
    published = pd.read_csv(site.RESULTS / "capability_flow.csv", index_col=0).flow_distinctive
    assert np.allclose(p[:, 0] @ phi.values, published[phi.columns], atol=1e-9)
    # Phi is made from what O*NET lists and where the taxonomy places it: J, Q, R and u
    J, Q, R, u = v["J"].loc[occ], v["Q"], v["R"], col("u")[phi.columns]
    assert list(J.columns) == list(Q.index) and list(Q.columns) == list(R.index) and list(R.columns) == list(phi.columns)
    assert set(np.unique(Q.values)) == {0.0, 1.0} and Q.values.sum() == len(site.FL.listings())
    placed = R.sum(axis=1)
    assert np.allclose(placed[placed > 0], 1) and (placed == 0).sum() > 0 and R.values.min() >= 0     # a product is placed whole, or not at all
    listed = Q.values @ R.values                              # the products each occupation lists in each capability
    assert np.allclose(u, np.log(len(Q) / np.clip((listed > 0).sum(axis=0), 1, None))) and (u > 0).all()
    weighted, lists = listed @ u.values, Q.values.sum(axis=1)
    assert (lists > 0).all() and ((weighted > 0) == (listed.sum(axis=1) > 0)).all()
    some = weighted > 0
    onet = np.zeros_like(listed)
    onet[some] = (listed[some] * u.values) * (listed[some].sum(axis=1) / lists[some] / weighted[some])[:, None]
    assert np.allclose(J.values @ onet, phi.values, atol=1e-12)
    rows = J.sum(axis=1)
    assert np.allclose(rows[rows > 0], 1) and ((rows == 0) == (phi.sum(axis=1) == 0)).sum() >= len(rows) - 2
    # the unpaid work done at home: each kind of it under one activity and one occupation, at that occupation's wage
    G, (_, detail) = v["G"].loc[occ, theta.columns], built.unpaid
    assert (G.values != 0).sum() == len(detail.drop_duplicates(["occupation", "work_activity"])) and G.values.min() >= 0
    assert detail.hours_per_day.sum() == pytest.approx(3.0, abs=0.05) and 3e12 < detail.usd.sum() < 6e12
    assert G.values.sum() == pytest.approx(detail.usd.sum() / (v["Y"].values.sum() * 1e6))
    assert (detail.work_activity.map(built.act.name).str.rstrip(".") == detail.work_activity_name).all()
    f = p.T @ theta.values + G.values.sum(axis=0)
    assert np.allclose(f.T, v["f"].loc[theta.columns].values, atol=1e-12)
    # only information work is placed on software; the rest of the flow to activities needs a body or a person
    s = col("s")[theta.columns]
    assert set(s) == {0.0, 1.0} and list(s.index) == list(built.kinds.index) and set(built.kinds) == {"information", "physical", "people"}
    assert ((s == 1) == (built.kinds == "information")).all()
    k = phi.values.T @ (p * (theta.values @ s.values)[:, None] + (G.values @ s.values)[:, None])      # the third line
    assert np.allclose(k, v["k"].loc[phi.columns].values, atol=1e-12)
    assert np.allclose(v["b"].loc[theta.columns].values, f.T * (1 - s.values)[:, None], atol=1e-12)
    c, a = col("c"), col("a")
    tasks = built.tax[built.tax.level == 2]
    assert list(c.index) == list(phi.columns) == list(built.tax.id[built.tax.level == 1]) and c.between(0, 1).all()
    assert (c * tasks.groupby("parent").size()[c.index]).sum() == pytest.approx((tasks.open_tools != "").sum())
    # of what is not open, the share that is well defined: the taxonomy's tasks again
    closed = tasks[tasks.open_tools == ""]
    score = closed.benchmarkable.map(site.DEFINED)
    assert set(tasks.benchmarkable) == set(site.DEFINED) and a.between(0, 1).all() and (a[c == 1] == 0).all()
    assert (a * (1 - c) * tasks.groupby("parent").size()[c.index]).sum() == pytest.approx(score.sum())
    # and both are counts of the taxonomy's tasks: N says which capability each is part of, t which have a tool, w how far each is defined
    N, has, defined = v["N"].loc[phi.columns], col("t"), col("w")
    assert list(N.columns) == list(has.index) == list(defined.index) == list(tasks.id) and (N.sum(axis=0) == 1).all()
    assert set(has) == {0.0, 1.0} and set(defined) == set(site.DEFINED.values())
    assert np.allclose(c, (N.values @ has.values) / N.values.sum(axis=1))
    lacking = N.values @ (1 - has.values)
    assert np.allclose(a[lacking > 0], (N.values @ (defined.values * (1 - has.values)))[lacking > 0] / lacking[lacking > 0]) and (a[lacking == 0] == 0).all()
    o = k * (a.values * (1 - c.values))[:, None]                                 # the overhang of software capabilities
    assert np.allclose(o, v["o"].loc[phi.columns].values, atol=1e-12) and (0 < o.sum(axis=0)).all() and (o.sum(axis=0) < k.sum(axis=0)).all()
    # the fourth line of the account, and the fifth: what is judged of each activity, from the file of judgments
    m, e = col("m")[theta.columns], col("e")[theta.columns]
    judged = built.judged.loc[theta.columns]
    assert set(judged.well_defined) == set(judged.open) == set(site.DEFINED) and (judged.open_basis != "").eq(judged.open != "no").all()
    assert (m == judged.well_defined.map(site.DEFINED)).all() and (e == judged.open.map(site.DEFINED)).all()
    h = f.T * (m.values * (1 - e.values))[:, None]
    assert np.allclose(h, v["h"].loc[theta.columns].values, atol=1e-12)
    assert np.allclose(site.gap(built), h.sum(axis=0)) and (o.sum(axis=0) < h.sum(axis=0)).all() and (h.sum(axis=0) < f.sum(axis=1)).all()


def test_every_term_has_a_page_with_its_picture_and_its_data(built):
    for key, sheet in built.sheets.items():
        X, html = sheet.values, (site.SITE / sheet.href).read_text()
        assert f'src="{sheet.data_file}"' in html and 'src="matrix.js"' in html and 'id="mx-canvas"' in html
        assert f'width="{X.shape[1]}" height="{X.shape[0]}"' in html
        # what matrix.js draws into and listens to: the margins, the buttons, and the line that says what is marked
        assert all(f'id="{i}"' in html for i in ("mx-top", "mx-left", "mx-zoom-in", "mx-zoom-out", "mx-zoom-all", "mx-unsort", "mx-note"))
        # what the page says of the term: its rows, columns and entries, where it comes from and what it goes into
        spec = html[html.index('<dl class="spec">'):html.index("</dl>")]
        assert "<dt>Rows</dt><dd>" in spec and "<dt>Entries</dt>" in spec and "<dt>Data</dt>" in spec
        assert ("<dt>Columns</dt>" in spec) == (X.shape[1] > 1), key
        assert ("<dt>Computed</dt>" in spec) == (key in site.EQUATIONS) and ("<dt>Source</dt>" in spec) == (key not in site.EQUATIONS), key
        assert ("<dt>Made from</dt>" in spec) == (key in site.USES), key
        for made_from in site.USES.get(key, ()):
            assert f'href="{site.SYMBOL_PAGES[made_from]}"' in spec, (key, made_from)
        users = [k for k in site.TERMS if key in site.USES.get(k, ())]
        assert ("<dt>Used in</dt>" in spec) == bool(users or key == "h"), key
        for user in users:
            assert f'href="{site.SYMBOL_PAGES[user]}"' in spec, (key, user)
        assert f'href="{site.HOME}"' in html and f'<a href="{sheet.href}"' not in html     # it leads back, and not to itself
        assert f'href="{sheet.csv_file}"' in html
        # the data file: every entry of any size, in the page's order, to within its rounding
        data = _data(sheet)
        rows, cols, unit, step = data["rows"]["codes"], data["cols"]["codes"], data["unit"], 3 if data["second"] else 2
        assert rows == [str(c) for c in X.index] and cols == [str(c) for c in X.columns]
        assert all(len(side[k]) == len(side["codes"]) for side in (data["rows"], data["cols"]) for k in ("names", "groups"))
        assert all(isinstance(side["things"], str) and side["things"] for side in (data["rows"], data["cols"]))
        x, got = X.values, np.zeros(X.shape)
        for j, col in enumerate(data["cells"]):
            got[col[0::step], j] = np.array(col[1::step]) * unit
        kept = np.abs(x) >= data["cut"]
        assert not got[~kept].any() and np.abs(got - x)[kept].max() <= unit / 2 + 1e-9, key
        assert kept.any() and data["scale"][0] < data["scale"][1]
        # a tall, narrow matrix has a picture of a fixed shape: its columns locked in view if they are few, and the
        # whole of it stretched to fill the picture, to zoom both ways, if they are many
        assert sheet.thin == (X.shape[0] >= site.THIN * X.shape[1]) == (f'aspect-ratio: {X.shape[1]} / {X.shape[0]}"' not in html), key
        assert data["lock"] == sheet.lock == ('class="mx-frame mx-lock"' in html) == (sheet.thin and X.shape[1] <= site.LOCK_COLUMNS), key
        assert data["stretch"] == (sheet.thin and not sheet.lock) == ("stretched to fill the picture" in html), key
        # totals in the margins are of the whole matrix, and the page has a place for each one it is given
        assert ("colSums" in data) == bool(sheet.sums) == ('id="mx-col-sums"' in html)
        assert ("rowSums" in data) == ("grand" in data) == (sheet.sums == "both") == ('id="mx-row-sums"' in html) == ('id="mx-total"' in html)
        if sheet.sums:
            assert np.allclose(data["colSums"], x.sum(axis=0), rtol=1e-5, atol=1e-9), key
        if sheet.sums == "both":
            assert np.allclose(data["rowSums"], x.sum(axis=1), rtol=1e-5, atol=1e-9) and np.isclose(data["grand"], x.sum(), rtol=1e-5), key
        if x.size <= site.SPARSE_CSV:       # the CSV is the whole table
            csv = pd.read_csv(site.SITE / sheet.csv_file, index_col=0, dtype={0: str})
            assert list(csv.index.astype(str)) == rows and np.allclose(csv.values, x, rtol=1e-5, atol=1e-9), key
            assert "The whole of it as CSV</a>" in html, key
        else:                               # or, of a large matrix, a line for each entry that is not zero
            csv = pd.read_csv(site.SITE / sheet.csv_file, dtype={"row": str, "column": str})
            got = np.zeros(sheet.values.shape)
            at = (sheet.values.index.get_indexer(csv.row), sheet.values.columns.get_indexer(csv.column))
            assert (at[0] >= 0).all() and (at[1] >= 0).all() and len(csv) == (x != 0).sum(), key
            got[at] = csv.value
            assert np.allclose(got, x, rtol=1e-5, atol=1e-9) and "Every entry that is not zero as CSV</a>" in html, key
    assert sorted(k for k, s in built.sheets.items() if s.thin) == sorted("xpkofdYgqFHzvrycasbtwRuhmelC" + site.ALPHA + site.MU + site.RHO + site.LAMBDA + site.ETA + site.TAU + site.PI + site.CHI + site.KAPPA + site.SIGMA + site.ZETA + site.BETA + site.WITH + site.REPLACED + site.LABOUR + site.BOUGHT + site.ILL + site.LIFTS)
    assert [k for k, s in built.sheets.items() if s.thin and not s.lock] == [site.LAMBDA, "R"]
    assert sorted(k for k, s in built.sheets.items() if s.values.size > site.SPARSE_CSV) == ["Q", "R"]
    # the matrices are the model's own
    m, t = built.io, built.io.t
    for key, X in {"A": m.A, "L": m.L, "U": t.U, "V": t.V, "K": m.K, "S": built.capital.shares, "F": built.capital.investment,
                   "W": built.wages[0], "P": built.wage_bill[0], "E": built.survey[0].fillna(0.0), "M": built.survey[1].fillna(0.0),
                   "T": built.survey[2], "d": built.need_dollars[0], "x": built.need_dollars[1], "v": built.need_value_added}.items():
        shown = built.sheets[key].values
        assert np.allclose(shown.values, X.loc[shown.index, shown.columns].values), key
    # a table of whole millions is filed exactly, so its blank cells hold nothing
    assert built.sheets["U"].exact and np.allclose(t.U.values, np.round(t.U.values))
    assert built.sheets["V"].exact and np.allclose(t.V.values, np.round(t.V.values))
    # sectors are grouped, so a picture's blocks are groups, and each group has a label for the margins
    data = _data(built.sheets["A"])
    groups = data["rows"]["groups"]
    assert groups == sorted(groups, key=site.MX.ORDER.index) and set(groups) <= set(data["short"])
    assert data["cols"] == data["rows"] and data["rows"]["things"] == "commodities"
    occ = built.wages[2]
    data = _data(built.sheets["W"])
    assert set(data["cols"]["groups"]) <= set(data["short"]) and len(set(data["cols"]["groups"])) == occ.major.nunique() == len(site.SOC_SHORT)
    # a tall matrix is drawn narrower than a wide one, and ones and zeros have no scale
    t_page, e_page = ((site.SITE / f"matrix-{k}.html").read_text() for k in "TE")
    assert f"minmax(0, {site.MATRIX_WIDTH + 2}px)" in e_page and f"minmax(0, {site.MATRIX_WIDTH + 2}px)" not in t_page
    assert 'class="mx-legend"' in e_page and 'class="mx-legend"' not in t_page


def test_a_cell_of_A_can_be_taken_apart(built):
    sheet = built.sheets["A"]
    html, data = (site.SITE / sheet.href).read_text(), _data(sheet)
    codes, unit = data["rows"]["codes"], data["unit"]
    a = built.io.A.loc[codes, codes].values
    k = site.MX.direct_parts(built.io)[1].loc[codes, codes].values
    got, got_k = np.zeros_like(a), np.zeros_like(a)
    for j, col in enumerate(data["cells"]):
        got[col[0::3], j] = np.array(col[1::3]) * unit
        got_k[col[0::3], j] = np.array(col[2::3]) * unit
    kept = np.abs(a) >= data["cut"]
    assert kept.sum() > 50_000 and np.abs(got_k - k)[kept].max() <= unit / 2 + 1e-12      # the part of each entry that is capital
    # the file behind a cell's derivation: B, of which each entry of any size is kept, and D; together they give A back
    text = (site.SITE / data["parts"]).read_text()
    parts = json.loads(text[text.index("{"):text.rindex("}") + 1])
    purchases, capital, D = site.MX.factors(built.io)
    b, kb, dm = (purchases + capital).loc[codes].values, capital.loc[codes].values, D[codes].values
    got_b, got_kb, got_d = np.zeros_like(b), np.zeros_like(b), np.zeros_like(dm)
    for i_, col in enumerate(parts["B"]):
        got_b[col[0::3], i_] = np.array(col[1::3]) * unit
        got_kb[col[0::3], i_] = np.array(col[2::3]) * unit
    for j, col in enumerate(parts["D"]):
        got_d[col[0::2], j] = np.array(col[1::2]) * unit
    kept_b = np.abs(b) >= parts["cut"]
    assert ((got_b != 0) == kept_b).all() and np.abs(got_b - b)[kept_b].max() <= unit / 2 + 1e-12
    assert np.abs(got_kb - kb)[kept_b].max() <= unit / 2 + 1e-12 and np.abs(got_d - dm).max() <= unit / 2 + 1e-12
    assert len(parts["industries"]) == b.shape[1] and all(isinstance(x, str) and x for x in parts["industries"])
    assert np.abs(got_b @ got_d - a)[kept].max() < 2e-4          # the terms a reader is shown add up to the cell, nearly
    assert 'id="mx-why"' in html
    assert not any('id="mx-why"' in (site.SITE / s.href).read_text() for key, s in built.sheets.items() if key not in "Aoh")


def test_the_order_to_work_in_is_shown_and_a_row_of_it_can_be_taken_apart(built):
    sheet = built.sheets["h"]
    data = _data(sheet)
    # the picture opens sorted by its first column, largest first, on its first rows, as that of software capabilities does and no other
    opening = {"sort": 0, "rows": site.ORDER_ROWS}
    assert data["start"] == opening and data["why"] == "activity" and data["lock"]
    assert _data(built.sheets["o"])["start"] == opening and _data(built.sheets["o"])["why"] == "tasks"
    for key in (site.RHO, site.ETA):
        assert _data(built.sheets[key])["start"] == opening and "why" not in _data(built.sheets[key])
    assert not any("start" in _data(s) or "why" in _data(s) for key, s in built.sheets.items() if key not in ("h", "o", site.RHO, site.ETA))
    # it is on the home page, under the equations and over the table of terms, and on its own page, with the words for a row's parts
    home = (site.SITE / site.HOME).read_text()
    assert home.index("</math>") < home.index('id="order"') < home.index('id="mx-canvas"') < home.index('id="terms"')
    assert f'<script src="{sheet.data_file}"></script><script src="matrix.js"></script>' in home
    for text in (home, (site.SITE / sheet.href).read_text()):
        assert text.count('id="mx-why"') == 1 and text.count('id="mx-canvas"') == 1
    # the file behind a row's parts: its row of f and the unpaid part of it, what is judged of it, and the detailed activities under it
    text = (site.SITE / data["parts"]).read_text()
    parts = json.loads(text[text.index("{"):text.rindex("}") + 1])
    acts = data["rows"]["codes"]
    f, h = built.sheets["f"].values.loc[acts].values, sheet.values.loc[acts].values
    m, e = (np.array([site.DEFINED[x] for x in parts[key]]) for key in ("defined", "open"))
    assert np.allclose(parts["f"], f, atol=1e-8) and np.allclose(np.array(parts["f"]) * (m * (1 - e))[:, None], h, atol=1e-7)
    assert np.allclose(parts["unpaid"], built.unpaid[0].sum()[acts], atol=1e-8) and (np.array(parts["unpaid"]) <= f[:, 0] + 1e-8).all()
    judged = built.judged.loc[acts]
    assert parts["kind"] == list(judged.kind) and parts["basis"] == list(judged.open_basis)
    assert all(bool(b) == (o != "no") for b, o in zip(parts["basis"], parts["open"]))
    fine = built.act[built.act.level == "detailed"]
    assert sum(len(x) for x in parts["detailed"]) == len(fine)
    for i, a in enumerate(acts):
        mine = fine[fine.parent == a]
        assert {x[0] for x in parts["detailed"][i]} == set(mine.name.str.rstrip(".")), a
        flows = [x[1] for x in parts["detailed"][i]]
        assert flows == sorted(flows, reverse=True) and sum(flows) == pytest.approx(mine.flow.sum(), abs=1e-6), a
    # the first of the order, with the needs counted equally
    first = int(np.argmax(h[:, 0]))
    assert data["rows"]["names"][first] == "Clean tools, equipment, facilities, or work areas."
    assert (parts["defined"][first], parts["open"][first], parts["kind"][first]) == ("yes", "no", "physical")


def test_the_gap_is_divided_among_abilities_and_machines_are_judged_in_each(built):
    v = {k: s.values for k, s in built.sheets.items()}
    occ, acts = list(v["p"].index), list(v[site.THETA].columns)
    L, C = v[site.LAMBDA].loc[occ], v[site.GAMMA].loc[acts]
    abilities = list(L.columns)
    ratings, calls, judged = built.abilities
    assert abilities == list(C.columns) == list(judged.index) and len(abilities) == 52 and set(judged.family) == set(site.ABILITY_FAMILY.values())
    # the ratings are importance times level, and the links are O*NET's, the same for every activity under one general activity
    raw = pd.read_csv(site.O.OCC / "onet_abilities.csv")
    chief = raw[raw.onet_soc.str.startswith("11-1011.")]            # the finer occupations O*NET has under one code are averaged
    assert np.allclose(L.loc["11-1011"], (chief.importance * chief.level).groupby(chief.ability).mean()[abilities], atol=0.006)
    assert L.values.max() <= 35 and L.values.min() >= 0
    links = pd.read_csv(site.O.OCC / "onet_ability_activities.csv")
    assert set(np.unique(C.values)) == {0.0, 1.0} and (C.sum(axis=1) > 0).all()
    parent = built.act.parent[acts]
    assert C.groupby(parent.values).nunique().max().max() == 1 and C.groupby(parent.values).first().values.sum() == len(links)
    # alpha: each occupation's gap in each activity, divided among the abilities the activity calls on by the occupation's ratings
    z = (v["m"].iloc[:, 0] * (1 - v["e"].iloc[:, 0]))[acts].values
    called = L.values @ C.values.T
    for way in v["p"].columns:
        gap = (v[site.THETA].loc[occ, acts].values * v["p"][way].values[:, None] + v["G"].loc[occ, acts].values) * z[None, :]
        alpha = np.zeros(len(abilities))
        for k in range(len(abilities)):
            part = np.divide(C.values[:, k][None, :] * L.values[:, k][:, None], called, out=np.zeros_like(called), where=called > 0)
            alpha[k] = (gap * part).sum()
        assert np.allclose(alpha, v[site.ALPHA][way].values, atol=1e-12), way
        # it adds up to the gap, but for the occupations O*NET does not rate
        unrated = gap[(L.sum(axis=1) == 0).values].sum()
        assert alpha.sum() == pytest.approx(v["h"][way].sum() - unrated, abs=1e-9) and unrated < 0.001
    # mu is the judgment on file, and rho is what it leaves
    mu = v[site.MU].iloc[:, 0]
    assert set(judged.machines) == set(site.DEFINED) and (judged.basis.str.len() > 10).all() and (mu == judged.machines.map(site.DEFINED)).all()
    assert np.allclose(v[site.RHO].values, v[site.ALPHA].values * (1 - mu.values)[:, None], atol=1e-12)
    # the home page says what each family comes to, before and after
    home = (site.SITE / site.HOME).read_text()
    section = home[home.index('id="abilities"'):home.index('id="terms"')]
    for family in site.ABILITY_FAMILY.values():
        mine = (judged.family == family).values
        assert (f'<th scope="row">{family}</th><td class="num">{v[site.ALPHA].equal.values[mine].sum() * 100:.1f}</td>'
                f'<td class="num">{v[site.RHO].equal.values[mine].sum() * 100:.1f}</td>') in section, family


def test_a_row_of_the_software_order_can_be_taken_apart_into_its_tasks(built):
    sheet = built.sheets["o"]
    data = _data(sheet)
    assert 'id="mx-why"' in (site.SITE / sheet.href).read_text()
    # the file behind a row's parts: its row of k, its a and c, and its tasks as the taxonomy has them
    text = (site.SITE / data["parts"]).read_text()
    parts = json.loads(text[text.index("{"):text.rindex("}") + 1])
    caps = data["rows"]["codes"]
    k, o = built.sheets["k"].values.loc[caps].values, sheet.values.loc[caps].values
    a, c = np.array(parts["a"]), np.array(parts["c"])
    assert np.allclose(parts["k"], k, atol=1e-8) and np.allclose(np.array(parts["k"]) * (a * (1 - c))[:, None], o, atol=1e-6)
    tasks = built.tax[built.tax.level == 2]
    assert sum(len(x) for x in parts["tasks"]) == len(tasks) == built.sheets["N"].values.shape[1]
    score = {"yes": 1.0, "partly": 0.5, "no": 0.0}
    for i, cap in enumerate(caps):
        mine = tasks[tasks.parent == cap]
        assert [x[0] for x in parts["tasks"][i]] == list(mine.name) and [x[1] for x in parts["tasks"][i]] == list(mine.open_tools), cap
        # a and c can be counted again from the tasks listed, as the page does
        closed = [x for x in parts["tasks"][i] if not x[1]]
        assert c[i] == pytest.approx(1 - len(closed) / len(mine), abs=1e-6), cap
        assert a[i] == pytest.approx(sum(score[x[2]] for x in closed) / len(closed) if closed else 0.0, abs=1e-6), cap
    # the first of that order, with the needs counted equally, and what there is to build in it
    first = int(np.argmax(o[:, 0]))
    assert data["rows"]["names"][first] == "Medical coding, billing and claims"
    assert [x[0] for x in parts["tasks"][first] if not x[1] and x[2] == "yes"] == [
        "Diagnosis and procedure code assignment", "Inpatient case-mix grouping", "Claim edit checking", "Fee schedule pricing"]


def test_the_survey_of_occupations_reaches_most_sectors(built):
    W, info, occ = built.wages
    measured = info.source.str.startswith("oews")
    assert np.allclose(W.sum(axis=1)[measured], 1.0) and not W[~measured].values.any()
    assert occ.title.notna().all() and set(occ.major.map(len) > 0) == {True}
    P, _, _, survey = built.wage_bill
    assert P.values.sum() > survey.wagebill_musd.sum() > 5e6      # rows overlap: sectors share surveyed industries
    E, wage, T, surveyed = built.survey
    assert list(T.index) == list(P.index) and list(T.columns) == list(E.index) == list(surveyed.index)
    assert set(np.unique(T.values)) == {0.0, 1.0} and set(surveyed.group) <= set(site.MX.ORDER)
    groups = list(surveyed.group)
    assert groups == sorted(groups, key=site.MX.ORDER.index)                          # in the page's groups, like sectors
    # the survey counts fewer jobs than it has: some cells are withheld, and some occupations are left out
    o = site.O.oews()
    listed = o[o.O_GROUP.str.lower() == "detailed"]
    assert E.sum().sum() < o.emp[o.OCC_CODE == "00-0000"].sum()
    assert listed.emp.sum() - E.sum().sum() == listed.emp[~listed.OCC_CODE.isin(E.columns)].sum() > 0


def test_the_flow_to_activities_adds_up(built):
    A = built.act
    # the three levels are the same dollar, and with what is unattributed they make it up
    for level in ("general", "intermediate", "detailed"):
        assert A.flow[A.level == level].sum() == pytest.approx(built.act_acct["flowed"], abs=1e-5), level
    assert built.act_acct[["flowed", "sectors_without_occupation_data", "work_not_placed"]].sum() == pytest.approx(1, abs=1e-5)
    by_need = pd.read_csv(site.RESULTS / "activity_flow_by_need.csv", index_col=0)
    assert by_need.mean(axis=1).sum() == pytest.approx(built.act_acct["flowed"], abs=1e-5)


def test_ai_use_is_filed_by_the_same_activities(built):
    d = built
    ai = pd.read_csv(site.RESULTS / "activity_ai.csv", index_col=0)
    I = ai[ai.level == "intermediate"]
    assert set(I.index) == set(d.act.index[d.act.level == "intermediate"])
    assert I.flow_share.sum() == pytest.approx(1) and I.pooled.sum() <= 1
    # a kind of work's figures are the sums of its activities'
    G = ai[ai.level == "general"]
    parent = d.act.parent.reindex(I.index)
    assert np.allclose(I.pooled.groupby(parent).sum().reindex(G.index), G.pooled, atol=1e-6)
    assert np.allclose(I.flow_share.groupby(parent).sum().reindex(G.index), G.flow_share, atol=1e-6)


def test_the_account_is_kept_in_hours_beside_dollars(built):
    v = {k: s.values for k, s in built.sheets.items()}
    def col(key):
        return v[key].iloc[:, 0]
    com, ind = v["A"].index, v["U"].columns
    occ, acts = list(v["p"].index), list(v[site.THETA].columns)
    # hours worked are the production account's, each of its industries divided among the benchmark's by what they paid
    published, under, l = site.HR.published(), site.HR.account_industry(ind), col("l")[ind]
    assert len(published) == 63 and set(under) == set(published.index) and (l >= 0).all()
    assert np.allclose(l.groupby(under.values).sum().reindex(published.index), published.hours_millions)
    paid = built.io.t.VA.loc[site.HR.PAY, ind]
    farms = under.index[under == 1]
    assert len(farms) > 1 and np.allclose(l[farms] / l[farms].sum(), paid[farms] / paid[farms].sum())
    assert l["531HSO"] == 0 and paid["531HSO"] == 0             # nobody is paid to live in a house they own
    # chi: an industry's hours for a dollar of output, mixed into commodities, over the commodity's value added per dollar
    chi, r = col(site.CHI)[com], col("r")[com]
    per_dollar = (l / col("g")[ind]).values @ v["D"].loc[ind, com].values
    made = (r > 1e-9).values
    assert np.allclose(chi[made], per_dollar[made] / r[made] * 1000) and not chi[~made].any() and 5 < chi[made].median() < 30
    # Z: the jobs of the surveyed industries that cover a sector, as shares of a row
    jobs = v["T"].loc[com, v["E"].index].values @ v["E"][occ].values
    has = jobs.sum(axis=1) > 0
    Z = v["Z"].loc[com, occ].values
    assert np.allclose(Z[has], jobs[has] / jobs[has].sum(axis=1, keepdims=True)) and not Z[~has].any() and has.sum() > 380
    # pi, tau and eta: the account's second, third and fourth lines again, in hours
    omega = v[site.OMEGA]
    by_sector = (v["v"].loc[com, omega.index].values * chi.values[:, None]) @ omega.values
    beta, pi = v[site.BETA].loc[com], v[site.PI].loc[occ]
    assert list(beta.columns) == list(omega.columns) and np.allclose(beta.values, by_sector)
    assert list(pi.columns) == list(omega.columns) and np.allclose(pi.values, Z.T @ beta.values)
    assert (pi.sum() < beta.sum()).all() and (pi.sum() > 0.9 * beta.sum()).all()       # the survey reaches most sectors' hours, not all
    X, tau = v["X"].loc[occ, acts], v[site.TAU].loc[acts]
    assert np.allclose(tau.values, v[site.THETA].loc[occ, acts].values.T @ pi.values + X.values.sum(axis=0)[:, None])
    kept = (col("m")[acts] * (1 - col("e")[acts])).values
    eta = v[site.ETA].loc[acts]
    assert np.allclose(eta.values, tau.values * kept[:, None]) and (eta.sum() < tau.sum()).all()
    # unpaid hours are G before a wage: the same cells, each cell's dollars over its hours an occupation's hourly wage
    G = v["G"].loc[occ, acts].values
    at = X.values > 0
    assert (at == (G > 0)).all() and at.sum() == len(built.unpaid[1].groupby(["occupation", "work_activity"]))
    hourly = G[at] / X.values[at] * 1000
    assert 7 < hourly.min() and hourly.max() < 60
    assert np.isclose(X.values.sum() * built.spent / 1000, built.unpaid[1].hours.sum())
    # sigma: the hours a sector takes now for a unit of its own real value added, for each hour it took then
    series = pd.read_csv(site.HR.SERIES)
    assert series.year.min() == site.HR.SINCE and series.year.max() == site.HR.YEAR and series.industry.nunique() == 63
    of_account = site.HR.still_needed()
    assert of_account[13] < 0.05 and of_account[7] > 1 and 0.3 < of_account.median() < 1      # computers; construction
    farms_then, farms_now = (series[(series.industry == 1) & (series.year == y)].iloc[0] for y in (site.HR.SINCE, site.HR.YEAR))
    assert of_account[1] < farms_now.hours_millions / farms_then.hours_millions < 1          # farm hours fell, and farm output rose
    sigma = col(site.SIGMA)[com]
    into = (l / col("g")[ind]).values[:, None] * v["V"].loc[ind, com].values
    made_with = into.sum(axis=0) > 0
    assert np.allclose(sigma[made_with], (of_account[under.values].values @ into)[made_with] / into.sum(axis=0)[made_with])
    assert not sigma[~made_with].any() and made_with.sum() > 390
    # kappa: the mean of sigma over the sectors an activity is done in for pay, weighted by its paid hours in each
    theta = v[site.THETA].loc[occ, acts].values
    for j, way in enumerate(omega.columns):
        placed = (Z * by_sector[:, [j]]) @ theta
        total = placed.sum(axis=0)
        assert np.allclose(v[site.KAPPA].loc[acts, way][total > 0], (sigma.values @ placed)[total > 0] / total[total > 0])
        assert not v[site.KAPPA].loc[acts, way][total == 0].any()
        # as its page writes it: each sector's hours counted at sigma, passed to occupations and activities, over each activity's paid hours
        assert np.allclose(total, theta.T @ pi[way].values)
        written = (sigma.values * beta[way].values) @ Z @ theta
        assert np.allclose(written[total > 0] / total[total > 0], v[site.KAPPA].loc[acts, way][total > 0])
    assert 0.2 < v[site.KAPPA].values[v[site.KAPPA].values > 0].min() and v[site.KAPPA].values.max() < 2
    # the paid hours behind the needs are most of the hours worked, and less than all of them
    behind = pi.spending.sum() * built.spent / 1000 / 1e6
    assert 0.5 * l.sum() < behind < l.sum()
    # an hour counts unpaid work for more than a dollar does
    f = v["f"].loc[acts]
    assert X.values.sum() / tau.equal.sum() > G.sum() / f.equal.sum()
    home = (site.SITE / site.HOME).read_text()
    section = home[home.index('id="hours"'):home.index('id="proposals"')]
    assert section.count("<mtr>") == 4
    assert f"{tau.equal.sum():.0f} hours of work behind them" in section and f"{X.values.sum():.0f} unpaid" in section
    assert f"is {eta.equal.sum():.0f} of the {tau.equal.sum():.0f} hours" in section
    names = built.sheets[site.ETA].row_names
    first = eta.equal.nlargest(site.HOURS_ROWS)
    place = v["h"].equal.rank(ascending=False).astype(int)
    for a, hours in first.items():
        assert f'{markup.escape(names[a])}</th><td class="num">{hours:.1f}</td>' in section and f'<td class="num">{place[a]}</td></tr>' in section, a
    assert section.count("<tr><th scope=\"row\"") == site.HOURS_ROWS + 1 + (built.unpaid[1].hours_per_day >= site.FELT_HOURS).sum()


def test_proposals_are_read_from_their_files_scored_and_given_pages(built, tmp_path):
    v = {k: s.values for k, s in built.sheets.items()}
    acts = list(v[site.THETA].columns)
    props, C, psi, tau = built.proposals, v["C"].loc[acts], v[site.PSI], v[site.TAU].loc[acts]
    files = sorted(site.PROPOSALS.glob("*.toml"))
    assert list(props) == [p.stem for p in files] == list(C.columns) == list(psi.index) and len(props) >= 4
    for key, x in props.items():
        raw = tomllib.loads((site.PROPOSALS / f"{key}.toml").read_text())
        claimed = pd.Series({r["activity"]: r["share"] for r in raw.get("does", [])}, dtype=float)
        assert (x.name, x.what, x.check) == (raw["name"], raw["what"], raw["check"]) and x.cost == raw.get("cost", {}).get("hours")
        assert (C[key][claimed.index] == claimed).all() and np.isclose(C[key].sum(), claimed.sum()) and ((claimed > 0) & (claimed <= 1)).all()
        assert all(r["basis"].strip() for r in raw.get("does", []) + raw.get("replaces", [])) and (raw.get("does") or raw.get("replaces"))
        assert "chance" not in raw, key                                           # each is scored as if it works
    # psi: the hours in what each claims, less what is already open
    left = (1 - v["e"].iloc[:, 0][acts]).values
    assert np.allclose(psi.values, C.values.T @ (tau.values * left[:, None]))
    scores = site.proposal_scores(built)
    assert np.allclose(scores.hours, psi.equal) and np.allclose(scores.a_year, psi.spending * built.spent / 1000)
    assert np.allclose(scores.cents, C.values.T @ (v["f"].loc[acts].equal.values * left) * 100)
    assert (scores.unpaid_a_year <= scores.a_year + 1).all() and np.allclose(scores.back, scores.a_year / scores.cost)
    assert (scores.activities == (C > 0).sum()).all()
    paid = C.mul((tau.equal - v["X"][acts].sum()).values * left, axis=0)
    claims_paid = paid.sum() > 0                               # a proposal that only replaces sectors claims no activity's paid hours
    assert np.allclose(scores.still[claims_paid], (paid.mul(v[site.KAPPA].loc[acts].equal, axis=0).sum() / paid.sum())[claims_paid])
    assert scores.still[claims_paid].between(0.3, 1.3).all() and scores.still[~claims_paid].isna().all()
    # one proposal can lie inside another, and then it comes to less
    assert (C["code-assignment"] <= C["who-owes-whom"]).all() and psi.equal["code-assignment"] < psi.equal["who-owes-whom"]
    home = (site.SITE / site.HOME).read_text()
    section = home[home.index('id="proposals"'):home.index('id="terms"')]
    together = (tau.equal.values * left * C.max(axis=1).values).sum()
    assert f"together these claim\n{together:.0f} of the {tau.equal.sum():.0f} hours" in section and together < psi.equal.sum()
    for key, x in props.items():
        assert f'<a href="{x.href}">{markup.escape(x.name)}</a>' in section, key
        page = (site.SITE / x.href).read_text()
        assert f'<h1 class="long">{markup.escape(x.name)}</h1>' in page and markup.escape(x.what) in page and markup.escape(x.check) in page, key
        assert markup.escape(x.cost_basis) in page and f"proposals/{key}.toml" in page, key
        assert ("Has it been moving" in page) == bool(len(x.does)) == ("All it claims" in page) and ("With all they bought" in page) == bool(len(x.replaces)), key
        if len(x.does):
            assert f'<td class="num">{psi.equal[key]:.2f}</td></tr>' in page and f"took {scores.still[key]:.2f} hours in {site.HR.YEAR}" in page, key
        names = built.sheets[site.TAU].row_names
        for a, row in x.does.iterrows():
            assert markup.escape(names[a]) in page and markup.escape(row.basis) in page, (key, a)
        for start, row in x.replaces.iterrows():
            assert f'<th scope="row">{start}</th>' in page and markup.escape(row.basis) in page, (key, start)
    # a file that is not whole is refused, and the refusal says why
    whole = 'name = "N"\nwhat = "W"\ncheck = "K"\n[[does]]\nactivity = "{a}"\nshare = {share}\nbasis = "{basis}"\n'
    a = acts[0]
    cases = {"share of 1.5": whole.format(a=a, share=1.5, basis="b"), "has no reason": whole.format(a=a, share=0.5, basis=" "),
             "is not a work activity": whole.format(a="9.Z", share=0.5, basis="b"),
             "no check": whole.format(a=a, share=0.5, basis="b").replace('check = "K"', 'check = ""'),
             "claimed twice": whole.format(a=a, share=0.5, basis="b") + whole.format(a=a, share=0.5, basis="b").split("[[does]]", 1)[1].join(["[[does]]", ""]),
             "claims no activity, replaces no sector and lifts no cause": 'name = "N"\nwhat = "W"\ncheck = "K"\n',
             "cost needs hours": whole.format(a=a, share=0.5, basis="b") + "[cost]\nhours = 5\n"}
    sectors = list(v["A"].index)
    replacing = 'name = "N"\nwhat = "W"\ncheck = "K"\n[[replaces]]\nsectors = "{start}"\nshare = {share}\nbasis = "{basis}"\n'
    cases |= {"the start of no sector's code": replacing.format(start="99", share=0.5, basis="b"),
              "33 has a share of 0": replacing.format(start="33", share=0, basis="b"),
              "33 has no reason": replacing.format(start="33", share=0.5, basis=""),
              "replaced twice": replacing.format(start="33", share=0.5, basis="b") + replacing.format(start="33", share=0.5, basis="b").split("[[replaces]]", 1)[1].join(["[[replaces]]", ""])}
    causes = list(built.burden.code)
    lifting = 'name = "N"\nwhat = "W"\ncheck = "K"\n[[lifts]]\ncause = "{cause}"\nshare = {share}\nbasis = "{basis}"\n'
    cases |= {"9999 is not a cause of ill health": lifting.format(cause="9999", share=0.5, basis="b"),
              "1530 has a share of 2": lifting.format(cause="1530", share=2, basis="b"),
              "lifted twice": lifting.format(cause="1530", share=0.5, basis="b") + lifting.format(cause="1530", share=0.5, basis="b").split("[[lifts]]", 1)[1].join(["[[lifts]]", ""])}
    for why, text in cases.items():
        folder = tmp_path / why.replace(" ", "-").replace("'", "").replace(",", "")
        folder.mkdir()
        (folder / "x.toml").write_text(text)
        with pytest.raises(ValueError, match=why):
            site.proposals(acts, folder, sectors, causes)
    (tmp_path / "well").mkdir()
    (tmp_path / "well" / "cure.toml").write_text(lifting.format(cause="1530", share=0.5, basis="b"))
    cure = site.proposals(acts, tmp_path / "well", sectors, causes)["cure"]
    assert cure.does.empty and cure.replaces.empty and cure.lifts.share["1530"] == 0.5
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "fine.toml").write_text(whole.format(a=a, share=1, basis="b"))
    (tmp_path / "ok" / "swap.toml").write_text(replacing.format(start="33", share=0.5, basis="b"))
    read = site.proposals(acts, tmp_path / "ok", sectors)
    fine, swap = read["fine"], read["swap"]
    assert fine.cost is None and fine.does.share[a] == 1 and fine.href == "proposal-fine.html" and fine.replaces.empty
    assert swap.does.empty and swap.replaces.share["33"] == 0.5


def test_hours_are_weighed_by_how_people_say_they_feel(built):
    v = {k: s.values for k, s in built.sheets.items()}
    occ, acts = list(v["p"].index), list(v[site.THETA].columns)
    felt, detail = built.feelings, built.unpaid[1]
    # the extract: a row for each rated code, the shares of time adding up, every mean within its scale
    assert felt.index.str.fullmatch(r"\d{6}").all() and felt.index.is_unique and felt.ratings.sum() > 100_000
    assert np.isclose(felt.share_of_time.sum(), 1, atol=1e-3) and felt.unpleasant.between(0, 1).all()
    assert felt[["happy", "meaningful", "pain", "sad", "stress", "tired"]].stack().between(0, 6).all()
    # a rate is the mean over the codes named, weighted by the time rated in each
    cleaning = felt.loc["020101"]
    assert built.unpleasant("020101") == cleaning.unpleasant and cleaning.ratings > 2000
    both = felt.loc[["020101", "020102"]]
    assert np.isclose(built.unpleasant("020101;020102"), (both.unpleasant * both.share_of_time).sum() / both.share_of_time.sum())
    housework = felt[felt.index.str.startswith("0201")]
    assert np.isclose(built.unpleasant("0201"), (housework.unpleasant * housework.share_of_time).sum() / housework.share_of_time.sum())
    # every kind of unpaid work names codes that were rated, and takes their rate
    work = pd.read_csv(site.M.CONFIG / "unpaid_work.csv", dtype={"time_use_codes": str})
    assert list(detail.activity) == list(work.activity) and work.time_use_codes.str.fullmatch(r"\d{2,6}(;\d{2,6})*").all()
    for codes, rate in zip(work.time_use_codes, detail.unpleasant):
        assert all(felt.index.str.startswith(c).any() for c in codes.split(";")) and rate == built.unpleasant(codes), codes
    at_work, at_home = built.unpleasant(site.WORKING), (detail.hours * detail.unpleasant).sum() / detail.hours.sum()
    assert 0.1 < at_home < at_work < 0.4                         # people rate a job worse than work at home
    # zeta: paid hours at the rate of a job, unpaid hours at the rate of each kind of work at home
    paid = v[site.THETA].loc[occ, acts].values.T @ v[site.PI].loc[occ].values
    home = (detail.hours * detail.unpleasant).groupby(detail.work_activity).sum().reindex(acts).fillna(0.0).values / built.spent * 1000
    zeta, tau = v[site.ZETA].loc[acts], v[site.TAU].loc[acts]
    assert np.allclose(zeta.values, paid * at_work + home[:, None]) and (zeta.values <= tau.values + 1e-12).all()
    assert np.isclose(home.sum(), at_home * v["X"].values.sum())
    html = (site.SITE / site.HOME).read_text()
    section = html[html.index('id="hours"'):html.index('id="proposals"')]
    assert f"unpleasant\n{at_work * 100:.0f}% of the time, and unpaid work at home {at_home * 100:.0f}%" in section
    assert f"{zeta.equal.sum():.1f} are unpleasant" in section and f"{home.sum():.1f} unpaid" in section
    assert f'Working at a job</th><td class="num">{built.time_use["Working"]:.2f}</td><td class="num">{at_work * 100:.0f}%</td>' in section
    for r in detail[detail.hours_per_day >= site.FELT_HOURS].itertuples():
        assert f'{markup.escape(r.activity)}</th><td class="num">{r.hours_per_day:.2f}</td><td class="num">{r.unpleasant * 100:.0f}%</td>' in section, r.activity
    # and each proposal says how many of its hours are unpleasant
    C, left = v["C"].loc[acts], (1 - v["e"].iloc[:, 0][acts]).values
    scores = site.proposal_scores(built)
    assert np.allclose(scores.unpleasant_a_year, C.values.T @ (zeta.spending.values * left) * built.spent / 1000)
    assert (scores.unpleasant_a_year < scores.a_year)[scores.a_year > 0].all()
    for key, x in built.proposals.items():
        assert (f"{site._count(scores.unpleasant_a_year[key])} hours a year, at the rates" in (site.SITE / x.href).read_text()) == bool(len(x.does)), key


def test_the_survey_says_how_each_kind_of_time_feels_and_nothing_weighs_it_in_points(built):
    felt, detail = built.feelings, built.unpaid[1]
    # the extract: the feelings on one scale from 0 to 10, and each code against the same person's other time
    assert np.allclose(felt.points, (felt.happy - felt[["pain", "sad", "stress"]].mean(axis=1) + 6) / 12 * 10, atol=1e-3)
    assert felt.points.between(0, 10).all() and felt.severe.between(0, 1).all()
    assert (felt.compared <= felt.ratings).all() and (felt.compared_time <= felt.share_of_time + 1e-6).all()
    assert (felt.below_rest.notna() == (felt.compared > 0)).all() and felt.below_rest.dropna().between(-10, 10).all()
    assert felt.compared.sum() > 0.75 * felt.ratings.sum()
    # time that is not work is neither a job nor a kind of unpaid work
    rest = built.not_work.split(";")
    work = (site.WORKING, *(c for codes in detail.time_use_codes for c in codes.split(";")))
    assert sorted(rest) == sorted(c for c in felt.index if not c.startswith(work)) and 0.5 < felt.share_of_time[rest].sum() < 0.7
    for codes, r in zip(detail.time_use_codes, detail.itertuples()):
        assert r.severe == built.felt(codes, "severe"), codes
    # the home page says how each kind of time feels, and the site weighs none of it in points or WELLBYs
    home = (site.SITE / site.HOME).read_text()
    section = home[home.index('id="hours"'):home.index('id="proposals"')]
    assert (f'Working at a job</th><td class="num">{built.time_use["Working"]:.2f}</td><td class="num">{built.unpleasant(site.WORKING) * 100:.0f}%</td>'
            f'<td class="num">{built.felt(site.WORKING, "severe") * 100:.0f}%</td></tr>') in section
    for r in detail[detail.hours_per_day >= site.FELT_HOURS].itertuples():
        assert f'<td class="num">{r.unpleasant * 100:.0f}%</td><td class="num">{r.severe * 100:.0f}%</td></tr>' in section, r.activity
    for page in site.SITE.glob("*.html"):
        assert "WELLBY" not in page.read_text(), page.name
    assert "microwellby" not in built.units and not {"ξ", "δ"} & set(built.sheets) and not list(site.M.CONFIG.glob("wellby*"))
    assert site._about(-90_012) == "&minus;90,000" and site._few(-0.09) == "&minus;0.09" and site._few(-0.001) == "0.00"
    assert site._about(306_157) == "306,000" and site._about(4.67e6) == "4.7 million" and site._few(101.02) == "101" and site._few(0.306) == "0.31"


def test_a_proposal_that_works_gives_back_what_its_hours_cost_with_the_jobs_kept_or_lost(built):
    v = {k: s.values for k, s in built.sheets.items()}
    occ, acts, com = list(v["p"].index), list(v[site.THETA].columns), list(v["A"].index)
    ways, props = list(v[site.OMEGA].columns), built.proposals
    r, chi = v["r"].loc[com].iloc[:, 0].values, v[site.CHI].loc[com].iloc[:, 0].values
    A, L = v["A"].loc[com, com].values, v["L"].loc[com, com].values
    # lambda: the hours behind a dollar of each commodity; with what the need dollar buys, upsilon, it comes to all the paid hours
    lam, ups, beta = v[site.LABOUR].loc[com].iloc[:, 0].values, v[site.BOUGHT].loc[com], v[site.BETA].loc[com]
    assert np.allclose(lam, (chi * r) @ L) and np.allclose(L, np.linalg.inv(np.eye(len(com)) - A))
    needs = list(v["d"].columns)
    scale = r @ v["x"].loc[com, needs].values
    assert np.allclose(ups.values, (v["d"].loc[com, needs].values / scale) @ v[site.OMEGA].loc[needs, ways].values)
    assert np.allclose(lam @ ups.values, beta.sum().values) and (lam >= chi * r - 1e-9).all()
    # Psi: the part of each sector a proposal replaces, by the start of its code
    Psi = v[site.REPLACED].loc[com]
    for key, x in props.items():
        want = pd.Series(0.0, index=com)
        for start, share in sorted(x.replaces.share.items(), key=lambda kv: len(kv[0])):
            want[[c for c in com if c.startswith(start)]] = share
        assert (Psi[key] == want).all() and (Psi[key].any() == bool(len(x.replaces))), key
    assert Psi["workshop"].any() and not Psi["shopping"].any() and Psi.values.max() <= 1
    # Pi: the same hours with each proposal in place, never more than now; phi: the hours that saves
    Pi, phi = v[site.WITH].loc[com], v[site.BEHIND]
    for key in props:
        left = 1 - Psi[key].values
        assert np.allclose(Pi[key], (chi * r * left) @ np.linalg.inv(np.eye(len(com)) - A * left[None, :])), key
        assert (Pi[key].values <= lam + 1e-9).all() and np.allclose(phi.loc[key], (lam - Pi[key].values) @ ups.values), key
    assert (phi.loc[[k for k, x in props.items() if x.replaces.empty]] == 0).all().all()
    own = (Psi["workshop"].values[:, None] * beta.values).sum(axis=0)             # the hours worked in the sectors themselves, in the part replaced
    assert (phi.loc["workshop"].values > 1.3 * own).all() and (phi.loc["workshop"].values < beta.sum().values).all()
    # j: the paid hours a proposal would do, in full-time jobs for every million need dollars
    C, left = v["C"].loc[acts], (1 - v["e"].iloc[:, 0][acts]).values
    paid = v[site.THETA].loc[occ, acts].values.T @ v[site.PI].loc[occ, ways].values
    jobs = v[site.JOBS]
    assert np.allclose(jobs.values, (C.values.T @ (paid * left[:, None]) + phi.values) / (site.HOURS_A_YEAR / 1000))
    # the prices: an hour of healthy life from a statistical life, an hour of one's own time from what is paid to save it, an hour's pay from the account
    price, pub = built.prices, site.published_prices()
    assert list(pub.index) == ["life", "life_left", "household_income", "time_share"] and pub.url.str.startswith("https://").all() and pub.source.str.len().min() > 40
    assert np.isclose(price.health, 1 - built.burden.yld_thousands[built.burden.level == 0].sum() * 1e3 / built.people) and 0.8 < price.health < 0.9 and 3.0e8 < built.people < 3.4e8
    assert np.isclose(price.life, pub.value.life / (pub.value.life_left * site.YEAR_HOURS * price.health)) and site.YEAR_HOURS == 8766
    assert np.isclose(price.time, pub.value.time_share * pub.value.household_income / site.HOURS_A_YEAR)
    assert np.isclose(price.pay, built.io.t.VA.loc["V00100"].sum() / site.HR.industry_hours(built.io.t).sum()) and price.time < price.life < price.pay
    assert np.isclose(price.hour_back, price.time / price.life) and np.isclose(price.job_lost, site.HOURS_A_YEAR * price.pay / price.life)
    assert f"{price.hour_back:.2f}" == site.HOUR_BACK and f"{price.job_lost / 1000:.2f}" == site.JOB_LOST
    # epsilon: what all its hours are worth to those who work them; Xi and Omega: that and the healthy life, with the jobs kept and lost
    back = v[site.BACK]
    assert np.allclose(back.values, (v[site.PSI].values + phi.values) * price.hour_back) and list(back.index) == list(props) == list(v[site.PSI].index)
    # iota: the years of healthy life each cause takes, for every million need dollars; Delta: the part of each a proposal would give back
    burden = built.burden.set_index("code")
    last = burden[burden["last"]]
    whole = burden[burden.level == 0].iloc[0]
    assert np.isclose(last.yld_thousands.sum(), whole.yld_thousands, rtol=1e-4) and np.isclose(last.yll_thousands.sum(), whole.yll_thousands, rtol=1e-4)
    assert burden.index.is_unique and (burden.under[burden.level > 0] != "").all() and burden.under[burden.level > 0].isin(burden.index).all()
    assert (burden.level[burden.under[burden.level > 0]].values == burden.level[burden.level > 0].values - 1).all()
    iota, Delta = v[site.ILL].iloc[:, 0], v[site.LIFTS]
    assert list(iota.index) == list(last.index) == list(Delta.index) and list(Delta.columns) == list(props)
    assert np.allclose(iota, (last.yld_thousands + last.yll_thousands) * 1e3 / (built.spent / 1e6))
    assert 80e6 < iota.sum() * built.spent / 1e6 < 150e6                           # about a third of a year for each person
    for key, x in props.items():
        want = pd.Series(0.0, index=last.index)
        for code, share in sorted(x.lifts.share.items(), key=lambda kv: burden.level[kv[0]]):
            want[[c for c in last.index if c == code or code in site._above(c, burden.under)]] = share
        assert (Delta[key] == want).all() and (Delta[key].any() == bool(len(x.lifts))), key
    assert (Delta["first-opinion"] == props["first-opinion"].lifts.share["0"]).all()          # all causes stands for every one of them
    assert Delta["driving"].astype(bool).sum() == 1 and site._above("1530", burden.under)[-1] == "0"
    health = Delta.values.T @ iota.values * site.YEAR_HOURS / 1000
    kept, lost = v[site.KEPT], v[site.LOST]
    assert np.allclose(kept.values, back.values + health[:, None])
    assert np.allclose(lost.values, kept.values - price.job_lost / 1000 * jobs.values) and (lost.values <= kept.values + 1e-9).all()
    assert lost.spending["who-owes-whom"] < 0 < kept.spending["who-owes-whom"]      # paid work: its sign turns on the jobs
    assert lost.spending["shopping"] > 0                                           # unpaid work: it does not
    # in a year, and on the pages
    scores = site.proposal_scores(built)
    assert np.allclose(scores.behind_a_year, phi.spending * built.spent / 1000) and np.allclose(scores.hours_a_year, scores.a_year + scores.behind_a_year)
    assert np.allclose(scores.healthy_years, Delta.values.T @ iota.values * built.spent / 1e6)
    a_year = built.spent / 1000 / site.YEAR_HOURS                                  # an hour of healthy life per thousand need dollars, in years a year
    assert np.allclose(scores.time, back.spending * a_year) and np.allclose(scores.kept, scores.time + scores.healthy_years)
    assert 0.5 < scores.time["driving"] / scores.healthy_years["driving"] < 2      # its hours and the injuries it avoids are of a size
    assert np.allclose(scores.time, scores.hours_a_year * price.hour_back / site.YEAR_HOURS)
    assert np.allclose(scores.jobs, jobs.spending * built.spent / 1e6) and np.allclose(scores.kept, kept.spending * a_year)
    assert np.allclose(scores.lost, lost.spending * a_year) and np.allclose(scores.kept_back, scores.kept / scores.cost * 1000)
    assert np.allclose(scores.lost, scores.kept - scores.jobs * price.job_lost / site.YEAR_HOURS)
    assert 0.5 * site.HR.industry_hours(built.io.t).sum() * 1e6 / site.HOURS_A_YEAR > scores.jobs.max()        # no proposal holds half of all jobs
    home = (site.SITE / site.HOME).read_text()
    section = home[home.index('id="proposals"'):home.index('id="terms"')]
    assert section.count("<mtr>") == 6
    order = [section.index(f'<a href="{props[k].href}">') for k in scores.sort_values("kept", ascending=False).index]
    assert order == sorted(order)
    for key, x in props.items():
        row = (f'<td class="num">{site._count(scores.hours_a_year[key])}</td><td class="num">{site._about(scores.jobs[key])}</td>'
               f'<td class="num">{site._about(scores.time[key])}</td><td class="num">{site._about(scores.healthy_years[key])}</td><td class="num">{site._about(scores.kept[key])}</td><td class="num">{site._about(scores.lost[key])}</td>')
        assert row in section, key
        page = (site.SITE / x.href).read_text()
        assert f"{site._about(scores.jobs[key])} full-time jobs" in page and "<dt>If it works</dt>" in page and "hance it works" not in page, key
        assert ("All it would give back" in page) == bool(len(x.lifts)) == ("<dt>Healthy life</dt>" in page), key
        assert f"{site._about(scores.kept[key])} years of healthy life a year if the jobs are kept, and {site._about(scores.lost[key])} if" in page, key
        assert f"<dd>{site._about(scores.time[key])} years of healthy life a year, at {site.HOUR_BACK} of an hour" in page, key
        assert f"{site._few(scores.kept_back[key])} years of healthy life a year, the jobs kept" in page, key
    # every one of the new terms has its equation on its page, and none has prose under it
    for key in (site.LABOUR, site.BOUGHT, site.WITH, site.BEHIND, site.JOBS, site.BACK, site.KEPT, site.LOST):
        page = (site.SITE / built.sheets[key].href).read_text()
        assert "<dt>Computed</dt>" in page and "<dt>Where</dt>" not in page and "<dt>Note</dt>" not in page and "<dt>Source</dt>" not in page, key
    for key in (site.REPLACED, site.LIFTS, site.ILL):
        page = (site.SITE / built.sheets[key].href).read_text()
        assert "<dt>Source</dt>" in page and "<dt>Computed</dt>" not in page and "<dt>Note</dt>" not in page, key
    healthy = (site.SITE / built.units["healthy-year"].href).read_text()
    assert f"{site.YEAR_HOURS / 1000:.3f}" in healthy and f"{int(built.burden['last'].sum())}" in (site.SITE / built.units["cause"].href).read_text()
    unit = (site.SITE / built.units["job-year"].href).read_text()
    assert f"{site.HOURS_A_YEAR:,} hours" in unit and f"is {site.JOB_LOST} of them" in unit
    hour = (site.SITE / built.units["healthy-hour"].href).read_text()
    assert all(markup.escape(url) in hour for url in pub.url) and "config/prices.csv" in hour and f"worth {site.HOUR_BACK} of an hour" in hour
    for what, dollars, hours in (("An hour of healthy life", f"${price.life:.2f}", "1.00"), ("An hour of a person's own time", f"${price.time:.2f}", site.HOUR_BACK),
                                 ("A statistical life", f"${pub.value.life / 1e6:.1f} million", f"{float(f'{pub.value.life / price.life:.3g}'):,.0f}")):
        assert f'<tr><th scope="row">{what}</th><td class="num">{dollars}</td><td class="num">{hours}</td></tr>' in hour, what


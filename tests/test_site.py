import json
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
    capability_pages = [site.cap_href(k) for k in built.ct.index]
    flow_pages = [site.flow_href(k) for k in built.flow.index]
    assert len(set(flow_pages)) == len(flow_pages) == (built.tax.level == 1).sum()
    activity_pages = [site.act_href(a) for a in built.act.index[built.act.level == "intermediate"]]
    assert len(set(activity_pages)) == len(activity_pages) == 332
    assert pages == sorted(["activities.html", "capabilities.html", "gaps.html", "index.html", "method.html", "needs.html",
                            "sectors.html", "work.html"] + sorted(set(site.SYMBOL_PAGES.values()))
                           + capability_pages + flow_pages + activity_pages)
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


def test_capabilities_page_carries_the_whole_taxonomy(built):
    d = built
    text = (site.SITE / "capabilities.html").read_text()
    assert text.count("data-cap>") == (d.tax.level == 1).sum()
    assert text.count('<tr class="sub') == (d.tax.level == 2).sum()
    ids = re.findall(r'\bid="([^"]+)"', text)
    assert len(ids) == len(set(ids))
    assert set(d.tax.id[d.tax.level <= 1]) <= set(ids)
    # each weighted function links to the capabilities it became
    for k in d.ct.index:
        assert re.search(rf'<tr id="{k}">.*?In the new list: <a href="#', text, re.S), k


def test_activity_pages_add_up_to_the_flows(built):
    d = built
    A = d.act
    I = A[A.level == "intermediate"]
    for a in I.index:
        assert site.flow_terms(d, a, d.act_work).term.sum() == pytest.approx(I.at[a, "flow"], abs=1e-8), a
        assert d.act_children[a].flow.sum() == pytest.approx(I.at[a, "flow"], abs=1e-9), a
    # the three levels are the same dollar, and with what is unattributed they make it up
    for level in ("general", "intermediate", "detailed"):
        assert A.flow[A.level == level].sum() == pytest.approx(d.act_acct["flowed"], abs=1e-5), level
    assert d.act_acct[["flowed", "sectors_without_occupation_data", "work_not_placed"]].sum() == pytest.approx(1, abs=1e-5)
    assert d.act_need.mean(axis=1).sum() == pytest.approx(d.act_acct["flowed"], abs=1e-5)


def _data(sheet):
    text = (site.SITE / sheet.data_file).read_text()
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def test_the_account_is_three_equations_and_a_table_of_every_term(built):
    html = (site.SITE / site.HOME.split("#")[0]).read_text()
    assert html.count('<math display="block"') == 1 and html.count("<mtr>") == 3
    assert f"{built.act_acct.flowed * 100:.1f} cents" in html
    table = html[html.index('id="terms"'):]
    for key, sheet in built.sheets.items():
        assert f'<td class="wrap"><a href="{sheet.href}">' in table, key       # each term is listed, by name
        assert f'<mi><a href="{sheet.href}">' in html, key                     # and its letter is a link wherever it is written
    assert list(built.sheets) == site.TERMS and len(set(site.SYMBOL_PAGES.values())) == len(site.TERMS)
    assert len({name.lower() for name in site.SYMBOL_PAGES.values()}) == len(site.TERMS)   # no two files differ by case alone
    # A is a link to its own page, so the rest of the inverse is the link to L's: two brackets, the I and the exponent
    piece = f'<a href="{site.SYMBOL_PAGES["L"]}" class="inv'
    for name in (site.HOME.split("#")[0], site.SYMBOL_PAGES["x"]):
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
    theta = v[site.THETA]
    assert list(theta.index) == list(occ) and set(np.round(theta.sum(axis=1), 9)) == {0.0, 1.0}
    f = v["v"].loc[com].mean(axis=1).values @ v["W"].values @ theta.values      # the second line of the account
    assert np.allclose(f, col("f")[theta.columns], atol=1e-9)
    assert f.sum() == pytest.approx(built.act_acct.flowed, abs=1e-5)
    assert list(v["c"].index) == list(theta.columns) and v["c"].values.min() >= 0 and v["c"].values.max() <= 1


def test_every_term_has_a_page_with_its_picture_and_its_data(built):
    for key, sheet in built.sheets.items():
        X, html = sheet.values, (site.SITE / sheet.href).read_text()
        assert f'src="{sheet.data_file}"' in html and 'src="matrix.js"' in html and 'id="mx-canvas"' in html
        assert f'width="{X.shape[1]}" height="{X.shape[0]}"' in html
        # what matrix.js draws into and listens to: the margins, the buttons, and the line that says what is marked
        assert all(f'id="{i}"' in html for i in ("mx-top", "mx-left", "mx-zoom-in", "mx-zoom-out", "mx-zoom-all", "mx-unsort", "mx-note"))
        # what the page says of the term: its rows, columns and entries, where it comes from and what it goes into
        spec = html[html.index('<dl class="spec">'):html.index("</dl>")]
        assert f"<dt>Rows</dt><dd>{X.shape[0]:,} " in spec and "<dt>Entries</dt>" in spec and "<dt>Data</dt>" in spec
        assert ("<dt>Columns</dt>" in spec) == (X.shape[1] > 1), key
        assert ("<dt>Computed</dt>" in spec) == (key in site.EQUATIONS) and ("<dt>Source</dt>" in spec) == (key not in site.EQUATIONS), key
        assert ("<dt>Made from</dt>" in spec) == (key in site.USES), key
        for made_from in site.USES.get(key, ()):
            assert f'href="{site.SYMBOL_PAGES[made_from]}"' in spec, (key, made_from)
        users = [k for k in site.TERMS if key in site.USES.get(k, ())]
        assert ("<dt>Used in</dt>" in spec) == bool(users or key in "fc"), key
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
        assert kept.sum() > 100 and data["scale"][0] < data["scale"][1]
        # a tall, narrow matrix has its columns locked in view
        assert data["lock"] == sheet.thin == ('class="mx-frame mx-lock"' in html) == (X.shape[0] >= site.THIN * X.shape[1]), key
        # totals in the margins are of the whole matrix, and the page has a place for each one it is given
        assert ("colSums" in data) == bool(sheet.sums) == ('id="mx-col-sums"' in html)
        assert ("rowSums" in data) == ("grand" in data) == (sheet.sums == "both") == ('id="mx-row-sums"' in html) == ('id="mx-total"' in html)
        if sheet.sums:
            assert np.allclose(data["colSums"], x.sum(axis=0), rtol=1e-5, atol=1e-9), key
        if sheet.sums == "both":
            assert np.allclose(data["rowSums"], x.sum(axis=1), rtol=1e-5, atol=1e-9) and np.isclose(data["grand"], x.sum(), rtol=1e-5), key
        csv = pd.read_csv(site.SITE / sheet.csv_file, index_col=0, dtype={0: str})
        assert list(csv.index.astype(str)) == rows and np.allclose(csv.values, x, rtol=1e-5, atol=1e-9), key
    assert sorted(k for k, s in built.sheets.items() if s.thin) == sorted("xfdYgqFHzvryc")
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
    assert data["cols"] == data["rows"] and groups == sorted(groups, key=site.MX.ORDER.index) and set(groups) <= set(data["short"])
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
    assert not any('id="mx-why"' in (site.SITE / s.href).read_text() for key, s in built.sheets.items() if key != "A")


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


def test_ai_use_sits_beside_the_work(built):
    d = built
    I = d.ai[d.ai.level == "intermediate"]
    assert set(I.index) == set(d.act.index[d.act.level == "intermediate"])
    assert I.flow_share.sum() == pytest.approx(1) and I.pooled.sum() <= 1
    # a kind of work's figures are the sums of its activities'
    G = d.ai[d.ai.level == "general"]
    parent = d.act.parent.reindex(I.index)
    assert np.allclose(I.pooled.groupby(parent).sum().reindex(G.index), G.pooled, atol=1e-6)
    assert np.allclose(I.flow_share.groupby(parent).sum().reindex(G.index), G.flow_share, atol=1e-6)
    home = (site.SITE / "index.html").read_text()
    assert 'id="ai"' in home and "Means: share of AI use" in home
    assert 'id="ai"' in (site.SITE / site.act_href(I.index[0])).read_text()


def test_home_page_leads_with_the_work(built):
    d = built
    text = (site.SITE / "index.html").read_text()
    assert text.index('id="demand"') < text.index('id="means"')
    for a in d.act.index[d.act.level == "intermediate"]:
        assert f'href="{site.act_href(a)}"' in text, a
    assert text.count("data-cap>") == (d.act.level == "general").sum()


def test_home_page_balances_every_capability(built):
    d = built
    text = (site.SITE / "index.html").read_text()
    # every capability is on the balance, under its domain, linked to its derivation
    for k in d.flow.index:
        assert f'href="{site.flow_href(k)}"' in text, k
    assert text.count('data-group="b-') == (d.tax.level == 0).sum() + len(d.flow)
    assert d.balance.flow.sum() == pytest.approx(d.flow.flow.sum())
    assert (d.balance.open <= d.balance.tasks).all() and (d.balance.bench <= d.balance.tasks).all()
    # the old function ranking no longer leads the home page
    assert "Demand: exposure" not in text


def test_leaderboards_sit_on_real_capabilities(built):
    d = built
    assert set(d.boards.capability) <= set(d.flow.index)
    assert set(d.boards.function) <= set(d.ct.index)
    # the same boards the 18 functions carry
    assert set(d.boards.board) == set(d.caps.board.dropna())
    for b in d.boards.itertuples():
        assert b.capability in set(d.tax_func.node[d.tax_func.function == b.function]), b.board


def test_flow_pages_add_up_to_the_flows(built):
    d = built
    for k in d.flow.index:
        assert site.flow_terms(d, k).term.sum() == pytest.approx(d.flow.at[k, "flow"], abs=1e-8), k
        assert d.flow_need.loc[k].mean() == pytest.approx(d.flow.at[k, "flow"], abs=1e-9), k
    # the flows and what could not be attributed make up the need dollar
    assert d.flow.flow.sum() == pytest.approx(d.flow_acct.at["flowed", "flow"], abs=1e-5)
    assert d.flow_acct.flow.sum() == pytest.approx(1, abs=1e-5)
    assert d.flow.flow_distinctive.sum() == pytest.approx(d.flow.flow.sum(), abs=1e-8)


def test_capability_pages_add_up_to_the_bars(built):
    d = built
    for k in d.ct.index:
        assert site.weight_terms(d, k).term.sum() == pytest.approx(d.ct.at[k, "volume weight"], abs=6e-5), k
        assert site.exposure_terms(d, k).term.sum() == pytest.approx(d.ct.at[k, "exposure"], abs=6e-5), k
        # the per-need sums average to the bars as well
        assert d.cbn.loc[k].mean() == pytest.approx(d.ct.at[k, "volume weight"], abs=6e-5), k
        xt = site.exposure_terms(d, k)
        assert d.sbn.loc[xt.index].sum().mean() == pytest.approx(d.ct.at[k, "exposure"], abs=1e-4), k


def test_every_scored_kind_has_an_entry(built):
    d = built
    for k in d.ct.index:
        text = (site.SITE / site.cap_href(k)).read_text()
        kinds = set(site.weight_terms(d, k).archetype)
        assert {a for a in re.findall(r'<article class="score" id="score-([^"]+)"', text)} == kinds, k


def test_score_rationale_config_is_consistent():
    r = pd.read_csv(site.CONFIG / "score_rationale.csv", dtype=str)
    assert list(r.columns) == ["archetype", "capability", "rationale", "sources"]
    scores = pd.read_csv(site.CONFIG / "archetype_capabilities.csv").set_index("archetype")
    assert set(r.archetype) <= set(scores.index)
    assert set(r.capability) <= set(scores.columns)
    assert not r.duplicated(["archetype", "capability"]).any()

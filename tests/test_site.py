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
                            "sectors.html", "work.html"] + capability_pages + flow_pages + activity_pages)
    for name in pages:
        text = (site.SITE / name).read_text()
        assert ">nan<" not in text and "nan%" not in text, name
        for href in re.findall(r'(?:href|src)="([^"#]+)(?:#[^"]*)?"', text):
            if href.startswith(("http://", "https://")):
                continue
            assert (site.SITE / href).exists(), f"{name}: broken link {href}"
        # every anchor used, on another page or this one, exists on its target
        for target, anchor in re.findall(r'href="([a-z-]*\.html)?#([^"]+)"', text):
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

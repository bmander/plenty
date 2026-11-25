import re
import pandas as pd
import pytest
from plenty import site


@pytest.fixture(scope="module")
def built():
    site.main()
    return site.Data()


def test_site_builds_and_links_resolve(built):
    pages = sorted(p.name for p in site.SITE.glob("*.html"))
    capability_pages = sorted(site.cap_href(k) for k in built.ct.index)
    assert pages == sorted(["capabilities.html", "gaps.html", "index.html", "method.html", "needs.html",
                            "sectors.html", "work.html"] + capability_pages)
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

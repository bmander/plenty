"""AI as a means: three vendors' usage figures, aligned to this project's work activities."""
import numpy as np
import pandas as pd
import pytest
from plenty import ai as AI, work as W


@pytest.fixture(scope="module")
def use():
    return AI.use()


def test_every_source_maps_onto_our_activities(use):
    H = W.hierarchy()
    assert list(use.index) == sorted(H.iwa.unique()) and len(use) == 332
    ids = AI.legacy_iwa_ids()
    assert ids.notna().all() and ids.is_unique and set(ids) == set(H.iwa)
    for level, n in (("detailed", 2087), ("intermediate", 332), ("general", 41)):
        a = AI.anthropic(level)
        assert a.index.is_unique and len(a) <= n


def test_shares_are_shares(use):
    for c in ("claude", "claude_api", "chatgpt", "copilot", "copilot_action", "pooled"):
        assert (use[c] >= 0).all() and use[c].sum() <= 1 + 1e-6, c
        assert use[c].sum() > 0.85, c          # nearly all of each source's use is placed
    assert np.allclose(use.pooled, use[list(AI.SOURCES)].mean(axis=1))
    other = AI.openai()[1]
    assert use.chatgpt.sum() + other == pytest.approx(1, abs=1e-3)


def test_claude_is_restricted_to_work_without_changing_its_total():
    raw = pd.read_csv(AI.AI / "anthropic_onet.csv")
    us = raw[(raw.source == "claude_ai") & (raw.geo_id == "USA") & (raw.metric_id == "pct") & (raw.hierarchy_level == 2)]
    published = us.groupby("node_name").value.mean().sum() / 100
    a = AI.anthropic()
    assert a.claude.sum() == pytest.approx(published, abs=1e-6)


def test_the_sources_agree_with_each_other_more_than_with_chance(use):
    r = use[list(AI.SOURCES)].corr(method="spearman")
    assert (r.values[np.triu_indices(3, 1)] > 0.5).all()


def test_ai_use_is_where_you_would_expect(use):
    H = W.hierarchy().drop_duplicates("iwa").set_index("iwa")
    by_kind = use.pooled.groupby(H.gwa_name).sum()
    assert by_kind["Getting Information"] > 10 * by_kind["Handling and Moving Objects"]
    assert by_kind["Working with Computers"] > by_kind["Operating Vehicles, Mechanized Devices, or Equipment"]
    top = H.iwa_name[use.pooled.nlargest(3).index].tolist()
    assert "Edit written materials or documents." in top

"""The two published tables about households (data/households), and the judgment that places them."""
import pandas as pd
from plenty import model as M

DATA, CONFIG = M.ROOT / "data" / "households", M.CONFIG


def test_time_use_is_a_whole_day_and_every_kind_of_unpaid_work_is_in_it():
    t = pd.read_csv(DATA / "time_use_2017.csv")
    assert t.activity[0] == "Total, all activities" and t.hours_per_day[0] == 24.0
    major = ["Personal care activities", "Household activities", "Purchasing goods and services", "Leisure and sports"]
    assert set(major) <= set(t.activity) and t.hours_per_day.between(0, 24).all()
    work = pd.read_csv(CONFIG / "unpaid_work.csv")
    named_once = t.activity.value_counts()
    assert not work.activity.duplicated().any() and (named_once.reindex(work.activity) == 1).all()
    # nothing is counted twice: no kind of work listed is a part of another that is listed
    assert not {"Household activities", "Housework", "Food preparation and cleanup", "Caring for and helping household members"} & set(work.activity)


def test_spending_by_income_has_every_item_placed_on_a_need():
    s = pd.read_csv(DATA / "spending_quintiles_2017.csv").set_index("item")
    assert list(s.columns) == ["all", "lowest", "second", "third", "fourth", "highest"] and s.index.is_unique
    assert s.at["Average annual expenditures", "lowest"] < s.at["Average annual expenditures", "highest"]
    placed = pd.read_csv(CONFIG / "spending_needs.csv")
    needs = pd.read_csv(CONFIG / "needs.csv")
    assert set(placed["item"]) <= set(s.index) and not placed["item"].duplicated().any()
    assert set(placed.need) <= set(needs.need[needs.include == 1])
    # the items placed are a part of what the poorest fifth spend, and most of it
    spent = s.lowest.astype(float)[placed["item"]].sum()
    assert 0.7 < spent / float(s.at["Average annual expenditures", "lowest"]) < 1

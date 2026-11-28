"""Write the inputs the domain authors worked from: input/products.csv (every O*NET product with
its category, how many occupations list it and examples) and input/categories.csv (which domains
each O*NET category was assigned to in structure.json)."""
import json, pathlib, sys
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from plenty import occupations as O

sw = pd.read_csv(O.OCC / "onet_software_skills.csv").fillna("")
titles = pd.read_csv(O.OCC / "onet_occupations.csv").set_index("O*NET-SOC Code").Title
sw["occ_title"] = sw["O*NET-SOC Code"].map(titles)
prod = sw.groupby(["Workplace Example", "Element Name"]).agg(
    n_occupations=("O*NET-SOC Code", "nunique"),
    example_occupations=("occ_title", lambda s: "; ".join(sorted(set(s))[:4])),
    hot=("Hot Technology", lambda s: "Y" if (s == "Y").any() else "")).reset_index()
prod.columns = ["product", "onet_category", "n_occupations", "example_occupations", "hot"]
prod = prod.sort_values(["onet_category", "n_occupations"], ascending=[True, False])
prod.to_csv(HERE / "input" / "products.csv", index=False)

s = json.loads((HERE / "structure.json").read_text())
m = pd.DataFrame([(c, d["id"]) for d in s["domains"] for c in d["onet_categories"]], columns=["onet_category", "domain"])
assert set(m.onet_category) == set(prod.onet_category), "structure.json must assign every O*NET category"
out = m.groupby("onet_category").domain.agg("; ".join).to_frame("domains")
out["n_products"] = prod.groupby("onet_category").size()
out["grab_bag"] = out.index.isin(s["grab_bag_categories"])
out.sort_values("n_products", ascending=False).to_csv(HERE / "input" / "categories.csv")
print(len(prod), "product rows,", len(out), "categories")

"""Generate config/basket.csv: which need each consumed commodity serves.

Run once to seed the file; after that config/basket.csv is the source of truth and can be
edited by hand. First matching rule wins. Prefixes are BEA 2017 detail commodity codes.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from flourishing import model as M

RULES = [  # (need, prefixes)
    ("accounting", ["S00401", "S00402", "S00300", "S00900", "4200ID"]),
    ("defense", ["S00500"]),
    ("federal_civil", ["S00600", "S00102"]),
    ("education", ["GSLGE", "611", "624400"]),
    ("health", ["GSLGH", "621", "622", "623", "624100", "3254", "334510", "334517", "339112",
                "339113", "339114", "339115", "339116", "446000", "424200"]),
    ("safety", ["GSLGO", "561600", "624A00"]),
    ("water_sanitation", ["221300", "S00203", "562000", "325610", "325620", "322291"]),
    ("energy", ["221100", "221200", "324190", "212100", "486000", "335911", "335912"]),
    ("discretionary", ["312120", "312130", "312140", "312200", "111400", "339910", "713200",
                       "721000", "561500", "48A000", "336213", "336214", "336612", "541940",
                       "311111", "311119", "812100", "812900", "814000", "33299A", "483000"]),
    ("finance_legal", ["52", "541100", "541200", "531ORE", "533000", "550000"]),
    ("food", ["111", "112", "114", "115", "311", "312110", "445000", "424400", "722"]),
    ("clothing", ["313", "315", "316", "448000", "812300"]),
    ("mobility", ["3361", "3362", "3363", "336991", "336999", "336411", "326210", "441000",
                  "423100", "447000", "324110", "424700", "811100", "532100", "485000",
                  "482000", "481000"]),
    ("communication", ["517", "518", "519", "3341", "3342", "511200", "511110", "491000",
                       "492000", "5415"]),
    ("meaning", ["813", "711", "712", "7131", "7139", "512", "515", "5111", "339920",
                 "339930", "334300", "334610", "323", "322230", "339940", "812200", "541920",
                 "532A00"]),
    ("margin", ["452000", "454000", "4B0000", "423", "424A00", "425000", "484000", "493000"]),
    ("shelter", ["531HS", "23", "337", "3352", "3351", "3334", "333112", "333991", "3219",
                 "327", "332", "314", "444000", "561700", "811400", "811200", "3255",
                 "3259", "326", "339990", "339950", "322", "331", "335", "333", "334",
                 "321", "532400", "5414", "3251", "3253", "2123"]),
    ("discretionary", ["5417", "5418", "5613", "5614", "5619"]),
]


def classify(code):
    for need, prefixes in RULES:
        if any(code.startswith(p) for p in prefixes):
            return need
    return "none"


def main():
    t = M.load_tables()
    rows = []
    for c in t.commodities:
        pce = t.F.at[c, "F01000"]
        gov = t.F.at[c, "F10C00"] + t.F.at[c, "F07C00"] + t.F.at[c, "F06C00"]
        need = classify(c)
        if pce == 0 and gov == 0 and need not in ("accounting",):
            need = "none"
        rows.append(dict(commodity=c, name=t.names[c], need=need,
                         pce_musd=round(pce), gov_consumption_musd=round(gov)))
    df = pd.DataFrame(rows)
    df.to_csv(M.CONFIG / "basket.csv", index=False)
    s = df.groupby("need")[["pce_musd", "gov_consumption_musd"]].sum().sort_values("pce_musd", ascending=False)
    print((s / 1e3).round(0))
    unm = df[(df.need == "none") & ((df.pce_musd != 0) | (df.gov_consumption_musd != 0))]
    print("unclassified with consumption:\n", unm.to_string())

if __name__ == "__main__":
    main()

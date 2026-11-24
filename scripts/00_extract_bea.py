"""Extract BEA 2017 detail tables from the USEPA/useeior R package (.rda) to CSV.

Usage: python scripts/00_extract_bea.py <path-to-useeior/data> <out-dir>
"""
import sys, pathlib
import rdata

src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
names = [
    "Detail_Make_2017_AfterRedef_17sch",
    "Detail_Use_2017_PRO_AfterRedef_17sch",
    "Detail_CommodityCodeName_2017",
    "Detail_IndustryCodeName_2017",
    "Detail_FinalDemandCodeName_2017",
    "Detail_ValueAddedCodeName_2017",
]
for n in names:
    obj = rdata.read_rda(src / f"{n}.rda")
    df = obj[n]
    df.to_csv(out / f"{n}.csv")
    print(n, df.shape)

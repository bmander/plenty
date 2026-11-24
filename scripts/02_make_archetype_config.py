"""Generate config/sector_archetypes.csv: an engineering archetype for each BEA commodity.

Run once to seed; the CSV is then the source of truth. First matching rule wins.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from plenty import model as M

RULES = [
    ("accounting", ["S00401", "S00402", "S00300", "S00900", "4200ID"]),
    ("crop_farming", ["111"]), ("animal_farming", ["112"]), ("forestry_fishing", ["113", "114", "115"]),
    ("oil_gas_extraction", ["211", "213111"]), ("mining", ["212", "21311A"]),
    ("electric_utility", ["2211"]), ("gas_utility", ["2212"]), ("water_utility", ["2213", "S00203"]),
    ("construction", ["23"]),
    ("wood_furniture", ["321", "337"]), ("nonmetallic_minerals", ["327"]),
    ("primary_metals", ["331"]),
    ("fluid_machinery", ["332410", "333611", "333618", "333912", "333914", "333413", "333414",
                         "333415", "33399B"]),
    ("fabricated_metals", ["332"]), ("machinery", ["333"]),
    ("semiconductors", ["334413"]), ("instruments", ["3345", "3391"]), ("electronics", ["334"]),
    ("electrical_equipment", ["335"]), ("motor_vehicles", ["3361", "3362", "3363"]),
    ("aerospace", ["3364"]), ("ships_rail_other", ["3365", "3366", "3369"]),
    ("misc_manufacturing", ["3399"]),
    ("food_processing", ["311", "312"]), ("textiles_apparel", ["313", "314", "315", "316"]),
    ("paper_printing", ["322", "323"]), ("petroleum_refining", ["324"]),
    ("pharma_bio", ["3254"]), ("bulk_chemicals", ["3251", "3252", "3253"]),
    ("formulated_chemicals", ["3255", "3256", "3259"]), ("plastics_rubber", ["326"]),
    ("trade", ["42", "44", "45", "4B"]),
    ("air_transport", ["481"]), ("rail_transport", ["482"]), ("water_transport", ["483"]),
    ("truck_transport", ["484", "492"]), ("transit", ["485", "48A"]), ("pipelines", ["486"]),
    ("warehousing_postal", ["493", "491"]),
    ("software_data", ["5112", "518", "5415", "519130"]), ("telecom", ["517"]),
    ("media_publishing", ["511", "512", "515", "519"]),
    ("finance_insurance", ["52"]), ("real_estate_housing", ["531", "532", "533"]),
    ("engineering_rd", ["5413", "5417"]), ("professional_admin", ["54", "55", "561"]),
    ("waste_management", ["562"]),
    ("education", ["61", "GSLGE"]), ("health_services", ["621", "622", "623", "GSLGH"]),
    ("social_services", ["624"]), ("arts_recreation", ["71"]), ("hospitality", ["72"]),
    ("repair_maintenance", ["811"]), ("personal_civic", ["812", "813", "814"]),
    ("government", ["S005", "S006", "GSLGO", "S00102"]),
]

def main():
    t = M.load_tables()
    rows = []
    for c in t.commodities:
        a = next((a for a, ps in RULES if any(c.startswith(p) for p in ps)), None)
        if a is None:
            raise SystemExit(f"no archetype for {c} {t.names[c]}")
        rows.append(dict(commodity=c, name=t.names[c], archetype=a))
    df = pd.DataFrame(rows)
    df.to_csv(M.CONFIG / "sector_archetypes.csv", index=False)
    caps = pd.read_csv(M.CONFIG / "archetype_capabilities.csv")
    missing = set(df.archetype) - set(caps.archetype)
    print("archetypes:", df.archetype.nunique(), "| missing capability rows:", missing,
          "| unused rows:", set(caps.archetype) - set(df.archetype))

if __name__ == "__main__":
    main()

"""Fetch labor-force data by Census tract for King County, as a real proxy for
the "labor availability" factor industrial site selection weighs (the posting
calls out labor comparisons specifically). Uses the Census Bureau's public ACS
5-year API (no key required for this volume) joined to real TIGER/Line tract
boundaries via pygris.

Variables pulled (ACS 5-year 2022, table B23025 - Employment Status):
  B23025_003E - civilian labor force (16+)
  B23025_004E - civilian labor force, employed
"""
import os
import requests
import pandas as pd
import geopandas as gpd
from pygris import tracts
from dotenv import load_dotenv

load_dotenv("/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/.env")
CENSUS_API_KEY = os.environ["CENSUS_API_KEY"]

OUT = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/data/raw"

KING_COUNTY_FIPS = {"state": "53", "county": "033"}
ACS_YEAR = 2022
ACS_VARS = ["B23025_003E", "B23025_004E"]  # labor force, employed


def main():
    print("Fetching King County tract boundaries (TIGER/Line via pygris)...")
    tr = tracts(state=KING_COUNTY_FIPS["state"], county=KING_COUNTY_FIPS["county"], cb=True, cache=True, year=ACS_YEAR)
    tr = tr.to_crs("EPSG:2926")
    print(f"  {len(tr)} tracts")

    print("Fetching ACS labor-force variables from the Census API...")
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
    params = {
        "get": ",".join(ACS_VARS),
        "for": "tract:*",
        "in": f"state:{KING_COUNTY_FIPS['state']} county:{KING_COUNTY_FIPS['county']}",
        "key": CENSUS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    for v in ACS_VARS:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    print(f"  {len(df)} tract rows from ACS")

    merged = tr.merge(df[["GEOID"] + ACS_VARS], on="GEOID", how="left")
    merged = merged.rename(columns={"B23025_003E": "labor_force", "B23025_004E": "labor_force_employed"})
    out_cols = ["GEOID", "labor_force", "labor_force_employed", "geometry"]
    merged = merged[out_cols]
    merged.to_file(f"{OUT}/labor_tracts.gpkg", driver="GPKG")
    print(f"Saved {len(merged)} tracts with labor data -> labor_tracts.gpkg")


if __name__ == "__main__":
    main()

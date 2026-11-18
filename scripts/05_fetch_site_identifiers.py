"""Enrich scored candidate parcels with human-readable identifiers: street
address, property/business name, and a decoded present-use description --
pulled from King County's own public "Parcels with Address, Property and
Ownership Information" layer, joined by PIN. This replaces bare PIN numbers
as the primary way a person reads a site in the dashboard.
"""
import requests
import pandas as pd
import geopandas as gpd

BASE = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability"
SCORED_PATH = f"{BASE}/data/processed/parcels_scored.geojson"
ADDR_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/PARCEL_ADDRESS_PUB_AREA_3069/FeatureServer/0/query"


def main():
    gdf = gpd.read_file(SCORED_PATH)
    pins = gdf["PIN"].astype(str).unique().tolist()
    print(f"Fetching address/name/use for {len(pins)} candidate parcels...")

    rows = []
    batch = 400
    for i in range(0, len(pins), batch):
        chunk = pins[i:i + batch]
        where = "PIN IN (" + ",".join(f"'{p}'" for p in chunk) + ")"
        p = {
            "where": where,
            "outFields": "PIN,ADDR_FULL,CTYNAME,ZIP5,PROP_NAME,PREUSE_DESC",
            "f": "json",
        }
        r = requests.post(ADDR_URL, data=p, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        rows.extend(f["attributes"] for f in feats)
        print(f"  fetched {len(rows)} / {len(pins)}")

    addr_df = pd.DataFrame(rows).drop_duplicates(subset="PIN")
    for col in ["ADDR_FULL", "PROP_NAME", "PREUSE_DESC", "CTYNAME"]:
        addr_df[col] = addr_df[col].astype(str).str.strip().replace({"None": None, "": None})

    gdf["PIN"] = gdf["PIN"].astype(str)
    merged = gdf.merge(addr_df, on="PIN", how="left")

    def has_text(v):
        return pd.notna(v) and str(v).strip() != ""

    # Build one clean display label per site: prefer the property/business
    # name; fall back to the street address; fall back to the PIN as a last
    # resort (a handful of parcels have neither on file).
    def label(row):
        if has_text(row["PROP_NAME"]):
            return str(row["PROP_NAME"]).title()
        if has_text(row["ADDR_FULL"]):
            return str(row["ADDR_FULL"]).title()
        return f"Parcel {row['PIN']}"

    def address(row):
        if has_text(row["ADDR_FULL"]) and has_text(row["CTYNAME"]):
            return f"{str(row['ADDR_FULL']).title()}, {str(row['CTYNAME']).title()}"
        if has_text(row["ADDR_FULL"]):
            return str(row["ADDR_FULL"]).title()
        return "Address not on file"

    merged["site_label"] = merged.apply(label, axis=1)
    merged["address_full"] = merged.apply(address, axis=1)
    merged["use_description"] = merged["PREUSE_DESC"].apply(lambda v: str(v).strip() if has_text(v) else "Not on file")

    no_name = merged["PROP_NAME"].isna().sum()
    no_addr = merged["ADDR_FULL"].isna().sum()
    print(f"  {no_name} of {len(merged)} parcels have no property name on file")
    print(f"  {no_addr} of {len(merged)} parcels have no street address on file")

    merged.to_file(SCORED_PATH, driver="GeoJSON")
    print(f"Updated {SCORED_PATH} with site_label, address_full, use_description")


if __name__ == "__main__":
    main()

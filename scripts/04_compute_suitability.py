"""Join parcels + transportation + labor data and compute per-parcel suitability
component scores for industrial/warehouse site selection in the Kent Valley /
South King County corridor.

This script outputs the four RAW normalized component scores (0-1) per parcel,
NOT a single baked-in composite score -- the composite is computed live in the
Streamlit dashboard from user-adjustable weights, the same way an ArcGIS
Dashboard would let an analyst re-weight criteria on the fly for a client call.

Zoning classification caveat (documented, not hidden): King County's parcel
extract spans ~40 different municipal zoning code systems with ~900 distinct
codes. The INDUSTRIAL_ZONING_CODES list below is a best-effort, non-authoritative
set built from well-documented public zoning conventions for the cities in this
study area (Seattle, Kent, Auburn, Renton, Tukwila, SeaTac). A real engagement
would confirm every code against each jurisdiction's own zoning ordinance before
using this as a filter -- exactly the kind of "verify data sources, assumptions,
and results before review" step the role itself calls out.
"""
import geopandas as gpd
import pandas as pd

RAW = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/data/raw"
PROCESSED = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/data/processed"

# High-confidence industrial zoning codes for South King County jurisdictions.
# Exact matches and prefixes, kept deliberately conservative (see module docstring).
INDUSTRIAL_EXACT = {
    "I", "I1", "I2", "I3", "I-C", "I-SO",
    "M1", "M2", "M3", "M-1",
    "IL", "IM", "IH",
    "IG1", "IG2", "IB", "IND", "LI", "HI", "MI",
}
INDUSTRIAL_PREFIXES = ("IG", "IC-", "M1 ", "M2 ", "M3 ")

MIN_LOT_SQFT = 20_000       # ~0.46 acres - below this, not a realistic warehouse site
MAX_LOT_SQFT = 500_000      # ~11.5 acres - generous upper end for this market, caps the score
HIGHWAY_CUTOFF_FT = 10_560  # 2 miles - beyond this, highway-access score floors at 0
RAIL_CUTOFF_FT = 7_920      # 1.5 miles


def is_industrial_zoning(code):
    if not isinstance(code, str):
        return False
    c = code.strip()
    if c in INDUSTRIAL_EXACT:
        return True
    return c.startswith(INDUSTRIAL_PREFIXES)


def minmax(series, lo, hi):
    clipped = series.clip(lower=lo, upper=hi)
    return (clipped - lo) / (hi - lo)


def nearest_distance(points_gdf, lines_gdf):
    joined = gpd.sjoin_nearest(points_gdf, lines_gdf[["geometry"]], distance_col="dist_ft", how="left")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined["dist_ft"]


def main():
    print("Loading parcels...")
    geom = gpd.read_file(f"{RAW}/parcels_geometry.gpkg")
    attrs = pd.read_csv(f"{RAW}/parcels_attributes.csv", dtype={"PIN": str})
    geom["PIN"] = geom["PIN"].astype(str)
    parcels = geom.merge(attrs, on="PIN", how="inner")
    print(f"  {len(parcels)} parcels with attributes")

    parcels["is_industrial"] = parcels["CURRENTZONING"].apply(is_industrial_zoning)
    candidates = parcels[parcels["is_industrial"]].copy()
    candidates = candidates[candidates["SQFTLOT"] >= MIN_LOT_SQFT].copy()
    print(f"  {len(candidates)} industrial-zoned parcels >= {MIN_LOT_SQFT} sqft (candidate set)")

    candidates["centroid"] = candidates.geometry.centroid
    centroids = gpd.GeoDataFrame(candidates[["PIN"]], geometry=candidates["centroid"], crs=candidates.crs)

    print("Scoring lot size...")
    candidates["score_lotsize"] = minmax(candidates["SQFTLOT"], MIN_LOT_SQFT, MAX_LOT_SQFT)

    print("Scoring highway access...")
    highways = gpd.read_file(f"{RAW}/highways.gpkg")
    hwy_dist = nearest_distance(centroids, highways)
    candidates["dist_highway_ft"] = hwy_dist.values
    candidates["score_highway"] = 1 - minmax(candidates["dist_highway_ft"], 0, HIGHWAY_CUTOFF_FT)

    print("Scoring rail access...")
    rail = gpd.read_file(f"{RAW}/railways.gpkg")
    rail_dist = nearest_distance(centroids, rail)
    candidates["dist_rail_ft"] = rail_dist.values
    candidates["score_rail"] = 1 - minmax(candidates["dist_rail_ft"], 0, RAIL_CUTOFF_FT)

    print("Scoring labor availability...")
    labor = gpd.read_file(f"{RAW}/labor_tracts.gpkg")
    joined = gpd.sjoin(centroids, labor[["labor_force_employed", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    candidates["labor_force_employed"] = joined["labor_force_employed"].values
    lo, hi = candidates["labor_force_employed"].min(), candidates["labor_force_employed"].max()
    candidates["score_labor"] = minmax(candidates["labor_force_employed"], lo, hi)

    before = len(candidates)
    candidates = candidates[candidates["score_labor"].notna()].copy()
    dropped = before - len(candidates)
    if dropped:
        print(f"  dropped {dropped} parcel(s) whose centroid fell outside every census tract (edge rounding)")

    out = candidates.drop(columns=["centroid"]).to_crs(epsg=4326)
    out_path = f"{PROCESSED}/parcels_scored.geojson"
    out.to_file(out_path, driver="GeoJSON")
    print(f"Saved {len(out)} scored candidate parcels -> {out_path}")


if __name__ == "__main__":
    main()

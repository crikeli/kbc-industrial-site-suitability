"""Fetch King County parcel geometry + assessor attributes for the Kent Valley /
South King County industrial corridor (Tukwila, Kent, Auburn, Renton, SeaTac) --
the largest industrial/warehouse submarket in the Pacific Northwest, and exactly
the kind of area a KBC-style industrial site-selection engagement would study.

Two real, public King County services, joined by PIN:
  - PARCEL_AREA_439 (geometry only: PIN, MAJOR, MINOR, Shape__Area)
  - PARCEL_EXTR_213 (Assessor extract table: CURRENTZONING, PRESENTUSE, SQFTLOT, PROPTYPE)
Both are live ArcGIS REST FeatureServers behind King County's public GIS Open Data
hub -- no API key, no ArcGIS license needed to read them.
"""
import time
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

OUT = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/data/raw"

PARCEL_GEOM_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/PARCEL_AREA_439/FeatureServer/0/query"
PARCEL_ATTR_URL = "https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/PARCEL_EXTR_213/FeatureServer/0/query"

# Kent Valley / South King County industrial corridor, WGS84 bbox
BBOX = {"xmin": -122.33, "ymin": 47.22, "xmax": -122.14, "ymax": 47.50}


def fetch_all_pages(url, params, page_size=1000):
    # The server caps at its own maxRecordCount (often 1000) regardless of what
    # we request, so stop on an EMPTY page, not a short one.
    offset = 0
    all_features = []
    while True:
        p = dict(params)
        p.update({"resultOffset": offset, "resultRecordCount": page_size, "f": "json"})
        r = requests.get(url, params=p, timeout=60)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        if not feats:
            break
        all_features.extend(feats)
        print(f"  fetched {len(all_features)} so far (offset={offset})")
        offset += len(feats)
        time.sleep(0.2)
    return all_features


def main():
    print("Fetching parcel geometry (PARCEL_AREA_439)...")
    geom_params = {
        "where": "1=1",
        "outFields": "PIN,MAJOR,MINOR,Shape__Area",
        "geometry": f"{BBOX['xmin']},{BBOX['ymin']},{BBOX['xmax']},{BBOX['ymax']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 2926,
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
    }
    geom_feats = fetch_all_pages(PARCEL_GEOM_URL, geom_params)
    print(f"Total parcel geometries: {len(geom_feats)}")

    rows = []
    geoms = []
    for f in geom_feats:
        attrs = f["attributes"]
        geom = f.get("geometry")
        if geom is None or "rings" not in geom:
            continue
        geoms.append({"type": "Polygon", "coordinates": geom["rings"]})
        rows.append(attrs)
    gdf = gpd.GeoDataFrame(rows, geometry=[shape(g) for g in geoms], crs="EPSG:2926")
    gdf.to_file(f"{OUT}/parcels_geometry.gpkg", driver="GPKG")
    print(f"Saved {len(gdf)} parcel geometries -> parcels_geometry.gpkg")

    # Fetch assessor attributes for exactly these PINs, batched (URL length limits).
    pins = gdf["PIN"].dropna().unique().tolist()
    print(f"Fetching assessor attributes for {len(pins)} PINs...")
    attr_rows = []
    batch = 400
    for i in range(0, len(pins), batch):
        chunk = pins[i:i + batch]
        where = "PIN IN (" + ",".join(f"'{p}'" for p in chunk) + ")"
        p = {
            "where": where,
            "outFields": "PIN,CURRENTZONING,PRESENTUSE,SQFTLOT,PROPTYPE",
            "f": "json",
        }
        r = requests.post(PARCEL_ATTR_URL, data=p, timeout=60)
        r.raise_for_status()
        feats = r.json().get("features", [])
        attr_rows.extend(f["attributes"] for f in feats)
        print(f"  attributes fetched: {len(attr_rows)} / {len(pins)}")
        time.sleep(0.2)

    attrs_df = pd.DataFrame(attr_rows).drop_duplicates(subset="PIN")
    attrs_df.to_csv(f"{OUT}/parcels_attributes.csv", index=False)
    print(f"Saved {len(attrs_df)} parcel attribute rows -> parcels_attributes.csv")


if __name__ == "__main__":
    main()

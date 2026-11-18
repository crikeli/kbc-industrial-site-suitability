"""Fetch real highway and freight-rail geometry for the Kent Valley / South King
County study area from OpenStreetMap (via osmnx), as the two access criteria a
real industrial site-selection analysis weighs heavily: proximity to the freeway
network (I-5, I-405, SR-167, SR-18) and to freight rail (BNSF/UP mainlines serving
the Kent Valley's intermodal-adjacent warehouse market).
"""
import osmnx as ox
import geopandas as gpd

OUT = "/Users/kelinchristi/Desktop/Desktop - Kelin’s MacBook Air/kbc-industrial-site-suitability/data/raw"

# Same bbox as 01_fetch_parcels.py (Kent Valley / South King County)
BBOX = {"xmin": -122.33, "ymin": 47.22, "xmax": -122.14, "ymax": 47.50}

ox.settings.use_cache = True
ox.settings.log_console = True


def main():
    west, south, east, north = BBOX["xmin"], BBOX["ymin"], BBOX["xmax"], BBOX["ymax"]
    bbox = (west, south, east, north)

    print("Fetching motorway/trunk highway network from OSM...")
    highway_filter = '["highway"~"motorway|motorway_link|trunk|trunk_link"]'
    G = ox.graph_from_bbox(bbox, custom_filter=highway_filter, simplify=True, retain_all=True)
    edges = ox.graph_to_gdfs(G, nodes=False)
    edges = edges.reset_index()[["geometry", "highway", "name"]].to_crs("EPSG:2926")
    edges.to_file(f"{OUT}/highways.gpkg", driver="GPKG")
    print(f"Saved {len(edges)} highway segments -> highways.gpkg")

    print("Fetching freight rail lines from OSM...")
    rail = ox.features_from_bbox(bbox, tags={"railway": "rail"})
    rail = rail[rail.geometry.type.isin(["LineString", "MultiLineString"])]
    rail = rail.reset_index()[["geometry"]].to_crs("EPSG:2926")
    rail.to_file(f"{OUT}/railways.gpkg", driver="GPKG")
    print(f"Saved {len(rail)} rail segments -> railways.gpkg")


if __name__ == "__main__":
    main()

"""KBC-style industrial site-suitability dashboard for the Kent Valley / South
King County corridor -- the open-source analog of the ArcGIS Online Dashboards
/ Experience Builder apps the role's posting asks for, built in Streamlit.

Run with: streamlit run app.py
"""
import geopandas as gpd
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

DATA_PATH = "../data/processed/parcels_scored.geojson"

st.set_page_config(page_title="Industrial Site Suitability — Kent Valley, WA", layout="wide")


@st.cache_data
def load_data():
    gdf = gpd.read_file(DATA_PATH)
    return gdf


def score_color(score):
    if score >= 0.75:
        return "#1a9850"
    if score >= 0.5:
        return "#91cf60"
    if score >= 0.25:
        return "#fee08b"
    return "#d73027"


def main():
    gdf = load_data()

    st.title("Industrial Site Suitability — Kent Valley / South King County")
    st.caption(
        "Real City/County GIS data (King County parcels & assessor records, OpenStreetMap "
        "highways & rail, Census ACS labor force) scored for warehouse/logistics site "
        "selection. Built as a portfolio project for KBC Advisors' GIS Analyst role — "
        "see README for methodology and data-source notes."
    )

    with st.sidebar:
        st.header("Criteria weights")
        st.caption("Adjust how much each factor matters — the map and rankings update live.")
        w_lotsize = st.slider("Lot size", 0.0, 1.0, 0.25, 0.05)
        w_highway = st.slider("Highway access", 0.0, 1.0, 0.30, 0.05)
        w_rail = st.slider("Rail access", 0.0, 1.0, 0.20, 0.05)
        w_labor = st.slider("Labor availability", 0.0, 1.0, 0.25, 0.05)

        total_w = w_lotsize + w_highway + w_rail + w_labor
        if total_w == 0:
            st.warning("Set at least one weight above zero.")
            return

        st.divider()
        min_score = st.slider("Minimum composite score to show", 0.0, 1.0, 0.0, 0.05)

    gdf = gdf.copy()
    gdf["composite_score"] = (
        w_lotsize * gdf["score_lotsize"]
        + w_highway * gdf["score_highway"]
        + w_rail * gdf["score_rail"]
        + w_labor * gdf["score_labor"]
    ) / total_w
    gdf = gdf.sort_values("composite_score", ascending=False)

    visible = gdf[gdf["composite_score"] >= min_score]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Candidate parcels", len(gdf))
    col2.metric("Shown at current filter", len(visible))
    col3.metric("Top score", f"{gdf['composite_score'].max():.2f}" if len(gdf) else "—")
    col4.metric("Median lot size (sqft)", f"{int(gdf['SQFTLOT'].median()):,}" if len(gdf) else "—")

    map_col, table_col = st.columns([2, 1])

    with map_col:
        center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]
        m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
        for _, row in visible.iterrows():
            c = row.geometry.centroid
            folium.CircleMarker(
                location=[c.y, c.x],
                radius=5 + 4 * row["composite_score"],
                color="#333333",
                weight=1,
                fill=True,
                fill_color=score_color(row["composite_score"]),
                fill_opacity=0.85,
                popup=folium.Popup(
                    f"<b>PIN:</b> {row['PIN']}<br>"
                    f"<b>Composite score:</b> {row['composite_score']:.2f}<br>"
                    f"<b>Lot size:</b> {int(row['SQFTLOT']):,} sqft<br>"
                    f"<b>Zoning:</b> {row['CURRENTZONING']}<br>"
                    f"<b>Highway dist:</b> {row['dist_highway_ft']:.0f} ft<br>"
                    f"<b>Rail dist:</b> {row['dist_rail_ft']:.0f} ft",
                    max_width=250,
                ),
            ).add_to(m)
        st_folium(m, width=None, height=560, returned_objects=[])

    with table_col:
        st.subheader("Top candidate sites")
        top = visible.head(15)[
            ["PIN", "composite_score", "SQFTLOT", "CURRENTZONING", "dist_highway_ft", "dist_rail_ft"]
        ].rename(
            columns={
                "composite_score": "Score",
                "SQFTLOT": "Lot sqft",
                "CURRENTZONING": "Zoning",
                "dist_highway_ft": "Hwy ft",
                "dist_rail_ft": "Rail ft",
            }
        )
        top["Score"] = top["Score"].round(2)
        top["Hwy ft"] = top["Hwy ft"].round(0)
        top["Rail ft"] = top["Rail ft"].round(0)
        st.dataframe(top, hide_index=True, use_container_width=True)

    st.divider()
    st.caption(
        "Methodology note: zoning classification uses a best-effort, non-authoritative "
        "mapping of King County's ~900 distinct municipal zoning codes to 'industrial' — "
        "see scripts/04_compute_suitability.py and README.md. Highway/rail distances are "
        "straight-line proxies, not drive-time; a production engagement would use network "
        "routing."
    )


if __name__ == "__main__":
    main()

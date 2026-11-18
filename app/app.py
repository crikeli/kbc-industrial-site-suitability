"""KBC-style industrial site-suitability dashboard for the Kent Valley / South
King County corridor -- the open-source analog of the ArcGIS Online Dashboards
/ Experience Builder apps the role's posting asks for, built in Streamlit.

Run with: streamlit run app.py
"""
import os
import geopandas as gpd
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(APP_DIR, "..", "data", "processed", "parcels_scored.geojson")

st.set_page_config(page_title="Industrial Site Suitability — Kent Valley, WA", layout="wide")

# Single-hue sequential ramp (ColorBrewer "Blues") for the composite score.
# Deliberately NOT red/yellow/green: red-green is the most common CVD
# confusion pair, and a magnitude score should be one hue light->dark, not
# a multi-hue "traffic light."
SCORE_BINS = [
    (0.0, 0.2, "#eff3ff", "Poor (0.0–0.2)"),
    (0.2, 0.4, "#bdd7e7", "Below average (0.2–0.4)"),
    (0.4, 0.6, "#6baed6", "Fair (0.4–0.6)"),
    (0.6, 0.8, "#3182bd", "Good (0.6–0.8)"),
    (0.8, 1.01, "#08519c", "Excellent (0.8–1.0)"),
]


VACANT_COLOR = "#f2a900"  # amber ring -- a secondary channel, not a hue swap,
# so vacancy reads as its own signal without competing with the blue score fill.


@st.cache_data
def load_data():
    gdf = gpd.read_file(DATA_PATH)
    gdf["is_vacant"] = gdf["use_description"].str.contains("Vacant", case=False, na=False)
    return gdf


def score_color(score):
    for lo, hi, color, _ in SCORE_BINS:
        if lo <= score < hi:
            return color
    return SCORE_BINS[-1][2]


def compute_scores(gdf, weights):
    w_lotsize, w_highway, w_rail, w_labor = weights
    total_w = w_lotsize + w_highway + w_rail + w_labor
    gdf = gdf.copy()
    gdf["composite_score"] = (
        w_lotsize * gdf["score_lotsize"]
        + w_highway * gdf["score_highway"]
        + w_rail * gdf["score_rail"]
        + w_labor * gdf["score_labor"]
    ) / total_w
    return gdf.sort_values("composite_score", ascending=False)


def render_legend(m):
    swatches = "".join(
        f'<div style="display:flex;align-items:center;margin-bottom:4px;">'
        f'<span style="width:14px;height:14px;background:{color};border:1px solid #333;'
        f'display:inline-block;margin-right:6px;border-radius:3px;"></span>'
        f'<span style="font-size:12px;color:#222;">{label}</span></div>'
        for _, _, color, label in SCORE_BINS
    )
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                background: white; padding: 10px 12px; border-radius: 6px;
                border: 1px solid #999; box-shadow: 0 1px 4px rgba(0,0,0,0.3);">
        <div style="font-size:12px;font-weight:700;color:#222;margin-bottom:6px;">
            Composite score
        </div>
        {swatches}
        <div style="border-top:1px solid #ddd;margin:8px 0 6px;"></div>
        <div style="display:flex;align-items:center;">
            <span style="width:14px;height:14px;background:transparent;border:3px solid {VACANT_COLOR};
            display:inline-block;margin-right:6px;border-radius:50%;"></span>
            <span style="font-size:12px;color:#222;">Vacant lot</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))


def render_dashboard_tab(gdf):
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
            st.stop()

        st.divider()
        min_score = st.slider("Minimum composite score to show", 0.0, 1.0, 0.0, 0.05)

        st.divider()
        st.header("Availability")
        vacant_only = st.checkbox("Vacant lots only")
        st.caption(
            "Vacant lots are outlined in amber on the map either way — this just "
            "filters the table and map down to them."
        )

    scored = compute_scores(gdf, (w_lotsize, w_highway, w_rail, w_labor))
    visible = scored[scored["composite_score"] >= min_score]
    if vacant_only:
        visible = visible[visible["is_vacant"]]

    vacant_count = int(scored["is_vacant"].sum())
    vacant_acres = scored.loc[scored["is_vacant"], "SQFTLOT"].sum() / 43560

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Candidate parcels", len(scored))
    c2.metric("Shown at current filter", len(visible))
    c3.metric("Top score", f"{scored['composite_score'].max():.2f}" if len(scored) else "—")
    c4.metric("Median score (shown)", f"{visible['composite_score'].median():.2f}" if len(visible) else "—")
    c5.metric("Median lot size (sqft)", f"{int(scored['SQFTLOT'].median()):,}" if len(scored) else "—")
    c6.metric(
        "Vacant land available",
        f"{vacant_acres:,.0f} ac",
        help=f"{vacant_count} of {len(scored)} candidates ({vacant_count / len(scored) * 100:.0f}%) are vacant on file.",
    )

    st.subheader("Site map")
    center = [scored.geometry.centroid.y.mean(), scored.geometry.centroid.x.mean()]
    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
    for _, row in visible.iterrows():
        c = row.geometry.centroid
        vacant_line = (
            "<b style='color:#b57b00'>⬤ VACANT — no existing tenant to relocate</b><br>"
            if row["is_vacant"]
            else ""
        )
        folium.CircleMarker(
            location=[c.y, c.x],
            radius=(6 if row["is_vacant"] else 5) + 4 * row["composite_score"],
            color=VACANT_COLOR if row["is_vacant"] else "#1a1a1a",
            weight=3 if row["is_vacant"] else 1,
            fill=True,
            fill_color=score_color(row["composite_score"]),
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>{row['site_label']}</b><br>"
                f"{row['address_full']}<br>"
                f"{vacant_line}"
                f"<b>Use on file:</b> {row['use_description']}<br>"
                f"<b>Composite score:</b> {row['composite_score']:.2f}<br>"
                f"<b>Lot size:</b> {int(row['SQFTLOT']):,} sqft<br>"
                f"<b>Zoning:</b> {row['CURRENTZONING']}<br>"
                f"<b>Highway dist:</b> {row['dist_highway_ft']:.0f} ft<br>"
                f"<b>Rail dist:</b> {row['dist_rail_ft']:.0f} ft<br>"
                f"<span style='color:#888'>PIN: {row['PIN']}</span>",
                max_width=280,
            ),
        ).add_to(m)
    render_legend(m)
    st_folium(m, width=None, height=680, returned_objects=[])

    st.subheader("Candidate sites")
    st.caption(f"Showing all {len(visible)} sites at the current filter, ranked by composite score.")

    # Only the seven fields an analyst scans to rank sites at a glance. Highway/rail
    # distance stay in the map popup (per-site detail) rather than the grid, so
    # every column here fits on screen without horizontal scrolling.
    table = visible[
        ["site_label", "address_full", "use_description", "is_vacant", "composite_score", "SQFTLOT", "CURRENTZONING"]
    ].rename(
        columns={
            "site_label": "Site",
            "address_full": "Address",
            "use_description": "Use on file",
            "is_vacant": "Vacant",
            "composite_score": "Score",
            "SQFTLOT": "Lot sqft",
            "CURRENTZONING": "Zoning",
        }
    )

    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=560,
        column_config={
            "Site": st.column_config.TextColumn(width="medium"),
            "Address": st.column_config.TextColumn(width="medium"),
            "Use on file": st.column_config.TextColumn(width="medium"),
            "Vacant": st.column_config.CheckboxColumn(width="small"),
            # Plain number, not a progress bar: Streamlit's built-in ProgressColumn
            # uses the app's accent color, which would introduce a second,
            # uncontrolled color channel that clashes with the map's blue scale.
            "Score": st.column_config.NumberColumn(format="%.2f"),
            "Lot sqft": st.column_config.NumberColumn(format="%d"),
            "Zoning": st.column_config.TextColumn(width="small"),
        },
    )
    st.caption(
        "Site name/address/use are King County Assessor records on file for each "
        "parcel — not independently verified. ~4% of candidates have no property "
        "name on file and ~27% have no street address on file; those fall back to "
        "a generic label. Highway/rail distance are in each site's map popup. See "
        "the Methodology tab for data sources and caveats."
    )


def render_methodology_tab():
    st.header("Methodology & why this exists")

    st.markdown(
        """
This dashboard is a portfolio project built for KBC Advisors' **GIS Analyst
(Location Intelligence)** posting. KBC is an industrial real estate advisory
firm, and the role's core duty is running location analyses — suitability,
site selection, gap analysis — from data pull to client-ready product, in
ArcGIS Online, Dashboards, and Python automation.

This app is the same analytical job, built with the open-source stack I
actually have (Python, GeoPandas, Streamlit) instead of ArcGIS. The
site-selection *logic* — multi-criteria scoring, live re-weighting, a
client-facing map and ranked list — is the same regardless of which GIS
platform runs it.
"""
    )

    st.subheader("Why the Kent Valley corridor")
    st.markdown(
        """
Tukwila, Kent, Auburn, Renton, and SeaTac make up the real largest
industrial/warehouse submarket in the Pacific Northwest — not an arbitrary
study area, but the actual market this kind of analysis would be run on.
"""
    )

    st.subheader("The four scoring criteria")
    st.markdown(
        """
Every candidate parcel is industrial-zoned and above a minimum lot size, then
scored 0–1 on each criterion below. **The dashboard does not bake in a single
composite number** — it computes the weighted composite live from the
sliders you set, the same way an analyst would re-weight a model on a client
call.

| Criterion | What it measures | Source |
|---|---|---|
| Lot size | Larger lots score higher, capped at ~11.5 acres | King County Assessor (`SQFTLOT`) |
| Highway access | Inverse distance to the nearest motorway/trunk road | OpenStreetMap, via `osmnx` |
| Rail access | Inverse distance to the nearest freight rail line | OpenStreetMap, via `osmnx` |
| Labor availability | Local census-tract labor force, employed | US Census ACS 5-year (2022) |
"""
    )

    st.subheader("Data sources")
    st.markdown(
        """
| Source | Provides | Access |
|---|---|---|
| King County Assessor / GIS | Parcel geometry, zoning, lot size, address, property name, use description | Public ArcGIS REST FeatureServers |
| OpenStreetMap | Highway network, freight rail lines | Overpass API via `osmnx` |
| US Census ACS 5-year (2022) | Labor force by tract | Census API (free key) |

No ArcGIS license, Salesforce, or CoStar access was available for this
project, so public data stands in for the posting's named sources — the
data-cleaning and multi-source-join problem is the same either way.
"""
    )

    st.subheader("Value prop: surfacing vacancy, not just zoning")
    st.markdown(
        """
Zoning tells you what's *allowed* on a parcel. It says nothing about whether
the parcel is actually *available* — the CarMax dealership and the condo
complex flagged below are both zoned industrial right now. The dashboard
answers the availability question directly, using King County's own
Assessor-reported use status (not an inference): **347 of 1,809 candidates
(19.2%) are currently vacant, totaling roughly 1,576 acres** of ready-to-move
industrial-zoned land in the corridor.

That distinction is the actual deal-speed lever in industrial site selection:

- **A vacant, high-scoring parcel is a near-term development target** — no
  tenant to relocate, no building to tear down, a client could move on it
  this quarter.
- **A non-vacant, high-scoring parcel is a land-banking note, not a live
  deal** — same suitability score, a completely different client
  conversation and timeline.
- Rolling this up to a single number — "~1,576 vacant acres currently
  available in the Kent Valley corridor" — is exactly the kind of headline
  market-intelligence figure a Location Intelligence analyst would hand
  straight to a client pitch or market report, not just an internal QA
  flag.

In the dashboard, vacant lots get their own visual channel (an amber ring,
not a color swap) so they stay visible against the composite-score scale
rather than competing with it, plus a sidebar toggle to filter down to vacant
sites only.
"""
    )

    st.subheader("Honesty notes — read before trusting a number here")
    st.warning(
        "**Zoning classification is a best-effort mapping, not an authoritative one.** "
        "King County's parcel data spans roughly 40 municipal zoning systems and ~900 "
        "distinct codes, with no public decode table for which ones mean 'industrial' "
        "across jurisdictions. This project uses an explicit, documented list of "
        "high-confidence codes (I1/I2/I3, M1/M2/M3, IL/IM/IH, etc.) built from standard "
        "Washington municipal zoning conventions. A real engagement would verify every "
        "code against each city's own ordinance before using it as a filter."
    )
    st.warning(
        "**Highway/rail distances are straight-line, not drive-time.** A production "
        "version would route against the actual road network (e.g. OSRM) for true "
        "travel distance."
    )
    st.warning(
        "**Zoning does not mean available.** Adding real site names surfaced that some "
        "high-scoring 'industrial-zoned' candidates are long-established car dealerships "
        "or even a condominium complex — legally zoned right, but not realistically "
        "redevelopable without a willing seller and a teardown. A real engagement would "
        "cross-reference the use description against active listings before calling a "
        "parcel a true candidate."
    )

    st.subheader("Code & reproducibility")
    st.markdown(
        "Full pipeline, scripts, and write-up: "
        "[github.com/crikeli/kbc-industrial-site-suitability]"
        "(https://github.com/crikeli/kbc-industrial-site-suitability)"
    )


def main():
    gdf = load_data()

    st.title("Industrial Site Suitability — Kent Valley / South King County")
    st.caption(
        "Real City/County GIS data scored for warehouse/logistics site selection. "
        "Built as a portfolio project for KBC Advisors' GIS Analyst role."
    )

    tab_dashboard, tab_methodology = st.tabs(["Dashboard", "Methodology"])
    with tab_dashboard:
        render_dashboard_tab(gdf)
    with tab_methodology:
        render_methodology_tab()


if __name__ == "__main__":
    main()

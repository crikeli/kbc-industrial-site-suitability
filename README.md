# Industrial Site Suitability — Kent Valley, WA

A portfolio project built for KBC Advisors' **GIS Analyst (Location Intelligence)**
posting ([role](https://www.kbcadvisors.com/open-opportunities/gis-analyst)),
using real public GIS data to run the kind of site-suitability analysis the
role's own duty list describes: "run location analyses independently, from
data pull to client-ready product," supporting "suitability, site selection,
center of gravity, and gap analysis."

**[Live dashboard →](https://kbc-industrial-site-suitability-v7yfwds8zpmcugmlgesvnx.streamlit.app/)**
— drag the criteria-weight sliders and watch the map and rankings update live,
or toggle "Vacant lots only" to see which high-scoring sites are actually
available land right now (~1,576 vacant acres in the corridor) vs. already
built out. The app has a dedicated **Methodology tab** with the full write-up,
data sources, and honesty notes.

## Why this project, and why this area

KBC is an industrial real estate advisory firm. The **Kent Valley / South King
County corridor** (Tukwila, Kent, Auburn, Renton, SeaTac) is the real largest
industrial/warehouse submarket in the Pacific Northwest — not an arbitrary
study area, but the actual market this kind of analysis would be run on.

## On ArcGIS vs. this stack

The posting asks for hands-on **ArcGIS Online, ArcGIS Pro, Experience Builder,
and Dashboards**. This project is built entirely in **Python + Streamlit**
instead, because that's the stack I have. The site-selection *logic* —
multi-criteria scoring, live re-weighting, client-facing map output — is the
same regardless of which GIS platform runs it; the Streamlit dashboard here is
meant as a direct, honest analog to an ArcGIS Dashboard, not a claim of ArcGIS
experience I don't have. The posting's **preferred** qualifications (Python,
automation scripts, SQL) are the parts of the role this project actually
demonstrates most directly.

## Data — all real, all public, no license required

| Source | What it provides | Access |
|---|---|---|
| King County Assessor / GIS (`PARCEL_AREA_439`, `PARCEL_EXTR_213`) | Parcel geometry, zoning, lot size | Public ArcGIS REST FeatureServer |
| OpenStreetMap (via `osmnx`) | Motorway/trunk highway network | Overpass API |
| OpenStreetMap (via `osmnx`) | Freight rail lines | Overpass API |
| US Census ACS 5-year (2022), table B23025 | Labor force by tract | Census API (free key) |

No ArcGIS license, Salesforce, or CoStar access was available for this
project, so public substitutes stand in for the posting's named sources —
the data-cleaning and multi-source-join problem is the same either way.

## Method

1. **`01_fetch_parcels.py`** — pulls parcel geometry and Assessor attributes
   (zoning, lot size, present use) for the study area directly from King
   County's live REST services, joined by parcel PIN. ~127,000 parcels,
   ~1,800 of them industrial-zoned.
2. **`02_fetch_transportation.py`** — pulls the real highway and rail network
   for the study area from OpenStreetMap.
3. **`03_fetch_labor_census.py`** — pulls Census tract boundaries and ACS
   labor-force counts.
4. **`04_compute_suitability.py`** — filters to industrial-zoned parcels above
   a minimum lot size, then scores each candidate 0–1 on four criteria: lot
   size, highway-access distance, rail-access distance, and local labor
   force. **Outputs the four raw component scores, not a single baked-in
   number** — composite scoring happens live in the dashboard.
5. **`05_fetch_site_identifiers.py`** — enriches every candidate with a real
   street address, property/business name, and King County's own decoded
   present-use description (pulled from the County's public parcel-address
   layer), so the dashboard shows "Williams Concrete, 25232 74th Ave S, Kent"
   instead of a bare PIN.
6. **`app/app.py`** — a Streamlit dashboard with a slider per criterion.
   Dragging a weight re-ranks every parcel and redraws the map instantly —
   the same kind of live re-weighting an analyst would do on a client call.

## Two honesty notes (documented in code, not hidden)

- **Zoning classification is a best-effort mapping, not an authoritative
  one.** King County's parcel data spans ~40 municipal zoning systems and
  ~900 distinct codes with no public decode table for which ones mean
  "industrial" across jurisdictions. `04_compute_suitability.py` uses an
  explicit, documented list of high-confidence codes (I1/I2/I3, M1/M2/M3,
  IL/IM/IH, etc.) built from standard Washington municipal zoning
  conventions. A real engagement would verify every code against each
  city's own ordinance before using it — exactly the "verify data sources,
  assumptions, and results before review" step the role calls out.
- **Highway/rail distances are straight-line, not drive-time.** A production
  version would route against the actual road network (e.g. OSRM) for true
  travel distance; the straight-line proxy is stated as such everywhere it's
  used.

Adding real identifiers also surfaced a genuine finding worth stating plainly:
zoning alone doesn't mean a parcel is *available* industrial land. Some
high-scoring candidates are long-established car dealerships (e.g. a CarMax,
a Honda dealer) or even a condominium complex — legally zoned industrial, but
not realistically redevelopable without a willing seller and a teardown. A
real engagement would cross-reference `use_description` against something
like active listings before calling a parcel a true "candidate."

## Running it locally

```bash
conda create -n kbc-industrial-site-suitability -c conda-forge python=3.11 geopandas osmnx streamlit folium requests shapely pyproj -y
conda activate kbc-industrial-site-suitability
pip install streamlit-folium pygris python-dotenv

# in scripts/: get a free Census API key at https://api.census.gov/data/key_signup.html
echo "CENSUS_API_KEY=your_key_here" > .env

cd scripts
python 01_fetch_parcels.py
python 02_fetch_transportation.py
python 03_fetch_labor_census.py
python 04_compute_suitability.py

cd ../app
streamlit run app.py
```

## Deployment

Deployed to Streamlit Community Cloud:
https://kbc-industrial-site-suitability-v7yfwds8zpmcugmlgesvnx.streamlit.app/

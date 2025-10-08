# app.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px

#TODO Refactor & Optimize
#TODO Fix IDE alerts

# Config
DATA_FILE = "EFSP_Dashboard_Data.xlsx"
KEY_COLUMNS = [
    "KEY",
    "review_status",
    "SubmissionDate",
    "Geopoint1-Latitude",
    "Geopoint1-Longitude",
    "geopoint-Latitude",
    "geopoint-Longitude",
    "Surveyor_Id",
    "Surveyor_Name",
    "Province",
    "District",
    "Village",
    "external_verification",
    "duration"
]

# Helper functions
@st.cache_data
def load_excel_file(file_path: str) -> pd.DataFrame:
    """Load Excel file, align columns by name, clean and add lat/lon."""
    try:
        df = pd.read_excel(file_path, engine="openpyxl")
    except Exception as e:
        st.error(f"Could not read {file_path}: {e}")
        return pd.DataFrame(columns=KEY_COLUMNS)

    # Ensure all KEY_COLUMNS are present
    for col in KEY_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    # Normalize SubmissionDate
    if "SubmissionDate" in df.columns:
        df["SubmissionDate"] = pd.to_datetime(df["SubmissionDate"], errors="coerce")

#TODO: Return the records that do not have neither GPS Points
    # Geopoint1 coordinates, fallback to geopoing
    def pick_lat(row):
        if pd.notna(row.get("Geopoint1-Latitude")) and pd.notna(row.get("Geopoint1-Longitude")):
            return row["Geopoint1-Latitude"], row["Geopoint1-Longitude"]
        if pd.notna(row.get("geopoint-Latitude")) and pd.notna(row.get("geopoint-Longitude")):
            return row["geopoint-Latitude"], row["geopoint-Longitude"]
        return (pd.NA, pd.NA)

    coords = df.apply(pick_lat, axis=1, result_type="expand")
    coords.columns = ["lat", "lon"]
    df = pd.concat([df, coords], axis=1)

    # external_verification -> numeric
    if "external_verification" in df.columns:
        df["external_verification"] = pd.to_numeric(df["external_verification"], errors="coerce").fillna(0).astype(int)

    # Fill empty strings/nulls with "Not provided" for display columns (except lat/lon, numeric fields)
    display_fill_cols = [c for c in df.columns if c not in ["lat", "lon", "SubmissionDate", "external_verification", "duration"]]
    df[display_fill_cols] = df[display_fill_cols].fillna("Not provided")

    return df

def percent(part, whole):
    return round(100 * (part / whole), 1) if whole else 0.0

# Load data
st.set_page_config(page_title="Surveyor Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("Surveyor Submissions Dashboard")

df = load_excel_file(DATA_FILE)

if df.empty:
    st.warning(f"No data found in `{DATA_FILE}`.")
    st.stop()

# SECTION Sidebar Filters
st.sidebar.header("Filters")

# Surveyor filter
surveyor_list = ["All Surveyors"] + sorted(df["Surveyor_Name"].dropna().unique().tolist())
selected_surveyor = st.sidebar.selectbox("Select Surveyor", surveyor_list)

# Date filter
min_date = df["SubmissionDate"].min()
max_date = df["SubmissionDate"].max()
if pd.notna(min_date) and pd.notna(max_date):
    date_range = st.sidebar.date_input("Submission date range", [min_date.date(), max_date.date()])
else:
    date_range = None

# Province filter
province_list = ["All Provinces"] + sorted(df["Province"].dropna().unique().tolist())
selected_province = st.sidebar.selectbox("Select Province", province_list)

# District filter (depends on Province)
if selected_province != "All Provinces":
    district_list = ["All Districts"] + sorted(df[df["Province"] == selected_province]["District"].dropna().unique().tolist())
else:
    district_list = ["All Districts"] + sorted(df["District"].dropna().unique().tolist())
selected_district = st.sidebar.selectbox("Select District", district_list)

# Village filter (depends on District)
if selected_district != "All Districts":
    village_list = ["All Villages"] + sorted(df[df["District"] == selected_district]["Village"].dropna().unique().tolist())
else:
    village_list = ["All Villages"] + sorted(df["Village"].dropna().unique().tolist())
selected_village = st.sidebar.selectbox("Select Village", village_list)

# Apply Filters
filtered = df.copy()

# Surveyor filter
if selected_surveyor != "All Surveyors":
    filtered = filtered[filtered["Surveyor_Name"] == selected_surveyor]

# Date range filter
if date_range and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["SubmissionDate"].isna()) |
        ((filtered["SubmissionDate"].dt.date >= start) & (filtered["SubmissionDate"].dt.date <= end))
    ]

# Province filter
if selected_province != "All Provinces":
    filtered = filtered[filtered["Province"] == selected_province]

# District filter
if selected_district != "All Districts":
    filtered = filtered[filtered["District"] == selected_district]

# Village filter
if selected_village != "All Villages":
    filtered = filtered[filtered["Village"] == selected_village]

# SECTION Key Metrics
total_sub = len(filtered)
total_verified = int(filtered["external_verification"].sum()) if "external_verification" in filtered.columns else 0
pct_verified = percent(total_verified, total_sub)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total submissions", total_sub)
col2.metric("Externally verified", f"{total_verified} ({pct_verified}%)")
col3.metric("Unique provinces", filtered["Province"].nunique() if "Province" in filtered.columns else 0)
col4.metric("Unique villages", filtered["Village"].nunique() if "Village" in filtered.columns else 0)

st.markdown("---")


# SECTION: Charts
st.header("Overview Charts")

# Submissions per surveyor (filtered dataset)
subs_by_surveyor = filtered.groupby("Surveyor_Name", dropna=False).size().reset_index(name="count")
fig1 = px.bar(subs_by_surveyor.sort_values("count", ascending=False),
              x="Surveyor_Name", y="count", title="Submissions per Surveyor")
st.plotly_chart(fig1, use_container_width=True)

# Externally Verified vs not
verif_counts = filtered["external_verification"].value_counts().rename_axis("verified").reset_index(name="count")
if 0 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified":0,"count":0}])], ignore_index=True)
if 1 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified":1,"count":0}])], ignore_index=True)
verif_counts = verif_counts.sort_values("verified")
verif_counts["label"] = verif_counts["verified"].map({0: "Beneficiary Verified", 1: "Externally verified"})
fig2 = px.pie(verif_counts, names="label", values="count", title="External verification distribution")
st.plotly_chart(fig2, use_container_width=True)

# Submissions over time
if filtered["SubmissionDate"].notna().any():
    times = filtered.dropna(subset=["SubmissionDate"]).copy()
    times["date_only"] = times["SubmissionDate"].dt.date
    times_by_date = times.groupby("date_only").size().reset_index(name="count")
    fig3 = px.line(times_by_date, x="date_only", y="count", title="Submissions over time")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No valid SubmissionDate values to plot timeline.")

st.markdown("---")

# SECTION Map
st.header("Map of Submissions")

map_df = filtered.copy()
map_df = map_df[map_df["lat"].notna() & map_df["lon"].notna()].copy()

if map_df.empty:
    st.info("No GPS points available for the current filters.")
else:
    view_mode = st.radio(
        "Map View Mode:",
        ["Default View", "Line View", "Label View"],
        horizontal=True
    )

    def get_color(ev):
        return "red" if int(ev) == 1 else "green"

    map_df["color"] = map_df["external_verification"].apply(get_color)

    # Initialize Folium map
    m = folium.Map(
        location=[map_df["lat"].mean(), map_df["lon"].mean()],
        zoom_start=9
    )

    # Specific surveyor or all
    if selected_surveyor != "All Surveyors":
        df_plot = map_df[map_df["Surveyor_Name"] == selected_surveyor].sort_values("SubmissionDate").copy()
        df_plot["Order"] = range(1, len(df_plot)+1)
    else:
        df_plot = map_df.copy()
        df_plot["Order"] = range(1, len(df_plot)+1)

    # Default and Label View
    if view_mode in ["Default View", "Label View"]:
        from folium.plugins import MarkerCluster

        cluster = MarkerCluster().add_to(m)
        for idx, row in df_plot.iterrows():
            # Convert duration from seconds to minutes
            if pd.notna(row['duration']):
                duration_min = round(row['duration'] / 60)  # integer minutes
            else:
                duration_min = "Not provided"

            popup_text = f"""
            <b>KEY:</b> {row['KEY']}<br>
            <b>Order:</b> {row['Order']}<br>
            <b>SubmissionDate:</b> {row['SubmissionDate']}<br>
            <b>Province:</b> {row['Province']}<br>
            <b>District:</b> {row['District']}<br>
            <b>Village:</b> {row['Village']}<br>
            <b>Duration (min):</b> {duration_min}
            """
            if view_mode == "Label View":
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=15,
                    color="black",
                    fill=True,
                    fill_color=get_color(row["external_verification"]),
                    fill_opacity=0.9,
                    popup=folium.Popup(popup_text, max_width=300)
                ).add_to(m)
                folium.map.Marker(
                    [row["lat"], row["lon"]],
                    icon=folium.DivIcon(html=f"""<div style="font-size:14px; color:white; font-weight:bold; text-align:center">{row['Order']}</div>""")
                ).add_to(m)
            else:
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=10,
                    color="black",
                    fill=True,
                    fill_color=get_color(row["external_verification"]),
                    fill_opacity=0.8,
                    popup=folium.Popup(popup_text, max_width=300)
                ).add_to(cluster)

    # Line View
    if view_mode == "Line View" and selected_surveyor != "All Surveyors":
        coords = df_plot[["lat", "lon"]].values.tolist()
        folium.PolyLine(coords, color="blue", weight=4, opacity=0.7).add_to(m)
        for idx, row in df_plot.iterrows():
            duration_min = f"{int(row['duration'])} min" if pd.notna(row['duration']) else "Not provided"
            popup_text = f"""
            <b>KEY:</b> {row['KEY']}<br>
            <b>Order:</b> {row['Order']}<br>
            <b>SubmissionDate:</b> {row['SubmissionDate']}<br>
            <b>Province:</b> {row['Province']}<br>
            <b>District:</b> {row['District']}<br>
            <b>Village:</b> {row['Village']}<br>
            <b>Duration:</b> {duration_min}
            """
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=12,
                color="black",
                fill=True,
                fill_color=get_color(row["external_verification"]),
                fill_opacity=0.9,
                popup=folium.Popup(popup_text, max_width=300)
            ).add_to(m)

    st_folium(m, width=1000, height=600)

# SECTION: KEY selector to view record details #TODO: Change to search input
# st.header("Record Explorer")
#
# key_options = ["-- Select a record by KEY (or leave blank) --"] + filtered["KEY"].astype(str).tolist()
# selected_key = st.selectbox("Select KEY to view details", key_options)
#
# def show_record_details(df_all, key):
#     if key == "-- Select a record by KEY (or leave blank) --":
#         st.info("Select a KEY to see the full record details.")
#         return
#     rec = df_all[df_all["KEY"].astype(str) == str(key)]
#     if rec.empty:
#         st.warning("KEY not found in current filtered dataset.")
#         return
#
#     for i, row in rec.iterrows():
#         st.subheader(f"Record KEY: {row['KEY']}")
#         st.markdown(f"**Surveyor:** {row.get('Surveyor_Name', 'Not provided')}")
#         st.markdown(f"**Province / District / Village:** {row.get('Province', 'Not provided')} / {row.get('District', 'Not provided')} / {row.get('Village', 'Not provided')}")
#         sd = row.get("SubmissionDate")
#         st.markdown(f"**SubmissionDate:** {sd if pd.isna(sd) == False else 'Not provided'}")
#         st.markdown(f"**Review status:** {row.get('review_status', 'Not provided')}")
#         st.markdown(f"**External verification:** { 'Yes' if int(row.get('external_verification',0))==1 else 'No' }")
#         st.markdown(f"**Duration:** {row.get('duration', 'Not provided')}")
#
#         # Show coordinates
#         if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
#             st.markdown(f"**Coordinates (lat,lon):** {row['lat']}, {row['lon']}")
#             st.map(pd.DataFrame({"lat":[row['lat']],"lon":[row['lon']]}))
#         else:
#             st.markdown("**Coordinates:** Not provided")
#         st.markdown("---")
#
# show_record_details(filtered, selected_key)

# SECTION: Table Summary
st.header("Tabular View")
display_cols = [
    "KEY", "Surveyor_Name", "Surveyor_Id", "SubmissionDate",
    "Province", "District", "Village",
    "external_verification", "review_status", "duration"
]
df_display = filtered[display_cols].copy()
df_display["external_verification"] = df_display["external_verification"].map({1: "Yes", 0: "No"}).fillna("No")
st.markdown(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
st.caption("Note: Empty fields show 'Not provided'.")
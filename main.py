# app.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px

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

    for col in KEY_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    # Normalize SubmissionDate
    if "SubmissionDate" in df.columns:
        df["SubmissionDate"] = pd.to_datetime(df["SubmissionDate"], errors="coerce")

    # Pick lat/lon from available columns
    def pick_latlon(row):
        if pd.notna(row.get("Geopoint1-Latitude")) and pd.notna(row.get("Geopoint1-Longitude")):
            return row["Geopoint1-Latitude"], row["Geopoint1-Longitude"]
        if pd.notna(row.get("geopoint-Latitude")) and pd.notna(row.get("geopoint-Longitude")):
            return row["geopoint-Latitude"], row["geopoint-Longitude"]
        return (pd.NA, pd.NA)

    coords = df.apply(pick_latlon, axis=1, result_type="expand")
    coords.columns = ["lat", "lon"]
    df = pd.concat([df, coords], axis=1)

    # Clean numeric fields
    if "external_verification" in df.columns:
        df["external_verification"] = pd.to_numeric(df["external_verification"], errors="coerce").fillna(0).astype(int)

    display_fill_cols = [c for c in df.columns if c not in ["lat", "lon", "SubmissionDate", "external_verification", "duration"]]
    df[display_fill_cols] = df[display_fill_cols].fillna("Not provided")

    return df


def percent(part, whole):
    return round(100 * (part / whole), 1) if whole else 0.0


# Streamlit Config
st.set_page_config(page_title="Surveyor Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("Surveyor Submissions Dashboard")

# Load data
df = load_excel_file(DATA_FILE)

if df.empty:
    st.warning(f"No data found in `{DATA_FILE}`.")
    st.stop()

# --- SIDEBAR FILTERS ---
st.sidebar.header("Filters")

# Surveyor filter
surveyor_list = ["All Surveyors"] + sorted(df["Surveyor_Name"].dropna().unique().tolist())
selected_surveyor = st.sidebar.selectbox("Select Surveyor", surveyor_list)

# Date range filter
min_date = df["SubmissionDate"].min()
max_date = df["SubmissionDate"].max()
if pd.notna(min_date) and pd.notna(max_date):
    date_range = st.sidebar.date_input(
        "Submission date range",
        [min_date.date(), max_date.date()],
        min_value=min_date.date(),
        max_value=max_date.date()
    )
else:
    date_range = None


# --- APPLY FILTERS ---
filtered = df.copy()

if selected_surveyor != "All Surveyors":
    filtered = filtered[filtered["Surveyor_Name"] == selected_surveyor]

if date_range and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["SubmissionDate"].isna()) |
        ((filtered["SubmissionDate"].dt.date >= start) & (filtered["SubmissionDate"].dt.date <= end))
    ]

# --- METRICS ---
# --- METRICS ---
total_sub = len(filtered)
total_verified = int(filtered["external_verification"].sum()) if "external_verification" in filtered.columns else 0
pct_verified = percent(total_verified, total_sub)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total submissions", total_sub)
col2.metric("Externally verified", f"{total_verified} ({pct_verified}%)")
col3.metric("Unique provinces", filtered["Province"].nunique() if "Province" in filtered.columns else 0)
col4.metric("Unique villages", filtered["Village"].nunique() if "Village" in filtered.columns else 0)


# --- CHARTS ---
st.header("Overview Charts")

subs_by_surveyor = filtered.groupby("Surveyor_Name", dropna=False).size().reset_index(name="count")
fig1 = px.bar(subs_by_surveyor.sort_values("count", ascending=False),
              x="Surveyor_Name", y="count", title="Submissions per Surveyor")
st.plotly_chart(fig1, use_container_width=True)

verif_counts = filtered["external_verification"].value_counts().rename_axis("verified").reset_index(name="count")
if 0 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified": 0, "count": 0}])], ignore_index=True)
if 1 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified": 1, "count": 0}])], ignore_index=True)

verif_counts["label"] = verif_counts["verified"].map({0: "Beneficiary Verified", 1: "Externally Verified"})
fig2 = px.pie(verif_counts, names="label", values="count", title="External Verification Distribution")
st.plotly_chart(fig2, use_container_width=True)

if filtered["SubmissionDate"].notna().any():
    times = filtered.dropna(subset=["SubmissionDate"]).copy()
    times["date_only"] = times["SubmissionDate"].dt.date
    times_by_date = times.groupby("date_only").size().reset_index(name="count")
    fig3 = px.line(times_by_date, x="date_only", y="count", title="Submissions Over Time")
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No valid SubmissionDate values to plot timeline.")

st.markdown("---")

# --- MAP SECTION ---
st.header("Map of Submissions")

map_df = filtered.copy()
map_df = map_df[map_df["lat"].notna() & map_df["lon"].notna()].copy()

if map_df.empty:
    st.info("No GPS points available for the current filters.")
else:
    # Restrict map view modes
    if selected_surveyor == "All Surveyors":
        st.info("Select a specific surveyor to show their route based on submission date.")
        view_mode = "Default View"
    else:
        view_mode = st.radio(
            "Map View Mode:",
            ["Default View", "Route View"],
            horizontal=True
        )

    def get_color(ev):
        return "red" if int(ev) == 1 else "green"

    map_df["color"] = map_df["external_verification"].apply(get_color)

    # Initialize map
    m = folium.Map(
        location=[map_df["lat"].mean(), map_df["lon"].mean()],
        zoom_start=9
    )

    # Prepare dataset for plotting
    if selected_surveyor != "All Surveyors":
        df_plot = map_df.sort_values("SubmissionDate").copy()
    else:
        df_plot = map_df.copy()

    df_plot["Order"] = range(1, len(df_plot) + 1)

    # --- Default View ---
    if view_mode == "Default View":
        from folium.plugins import MarkerCluster
        cluster = MarkerCluster().add_to(m)
        for _, row in df_plot.iterrows():
            popup_text = f"""
            <b>KEY:</b> {row['KEY']}<br>
            <b>SubmissionDate:</b> {row['SubmissionDate']}<br>
            <b>Surveyor:</b> {row['Surveyor_Name']}<br>
            <b>Duration (min):</b> {round(row['duration']/60) if pd.notna(row['duration']) else 'Not provided'}
            """
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=10,
                color="black",
                fill=True,
                fill_color=get_color(row["external_verification"]),
                fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=300)
            ).add_to(cluster)

    # --- Route View (only for a single surveyor) ---
    elif view_mode == "Route View" and selected_surveyor != "All Surveyors":
        points = []
        for _, row in df_plot.iterrows():
            popup_text = f"""
            <b>KEY:</b> {row['KEY']}<br>
            <b>Order:</b> {row['Order']}<br>
            <b>SubmissionDate:</b> {row['SubmissionDate']}<br>
            <b>Duration (min):</b> {round(row['duration']/60) if pd.notna(row['duration']) else 'Not provided'}
            """
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=14,
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

            points.append((row["lat"], row["lon"]))

        # Add connecting line
        if len(points) > 1:
            folium.PolyLine(points, color="blue", weight=3, opacity=0.7).add_to(m)

    st_folium(m, width=1000, height=600)

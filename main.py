# app.py
import streamlit as st
import pandas as pd
import glob
import os
import pydeck as pdk
from datetime import datetime

# ---------- Config ----------
DATA_FOLDER = "."  # folder with your .xlsx files
KEY_COLUMNS = [
    "KEY",
    "review_status",
    "surveyor_comments",
    "door_tag_photo_directly_from_the_door_tag",
    "door_tag_photo_of_the_door_from_an_angle",
    "TA",
    "AA",
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
    "benef_name_full",
    "external_verification",
    # external verification related
    "name_community_elder",
    "phonenumber_community_elder",
    "community_elder_verification",
    "community_elder_verification_photo",
]

LINK_COLUMNS = [
    "surveyor_comments",
    "door_tag_photo_directly_from_the_door_tag",
    "door_tag_photo_of_the_door_from_an_angle",
    "TA",
    "AA",
    "community_elder_verification_photo",
]

# ---------- Helper functions ----------
@st.cache_data
def load_and_combine_excel_files(folder_path: str) -> pd.DataFrame:
    """Load all .xlsx files in folder_path, align columns by name, concat, and clean."""
    files = glob.glob(os.path.join(folder_path, "*.xlsx"))
    dfs = []
    for f in files:
        try:
            # read the first sheet
            df = pd.read_excel(f, engine="openpyxl")
        except Exception as e:
            st.warning(f"Could not read {f}: {e}")
            continue
        # Normalize: keep only known columns (if present), preserve others too
        # Ensure all KEY_COLUMNS are present
        for col in KEY_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        df["__source_file"] = os.path.basename(f)
        dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=KEY_COLUMNS + ["__source_file"])
    combined = pd.concat(dfs, ignore_index=True, sort=False)

    # Normalize SubmissionDate
    if "SubmissionDate" in combined.columns:
        combined["SubmissionDate"] = pd.to_datetime(combined["SubmissionDate"], errors="coerce")

    # Prefer Geopoint1 coordinates, but keep both for reference
    def pick_lat(row):
        if pd.notna(row.get("Geopoint1-Latitude")) and pd.notna(row.get("Geopoint1-Longitude")):
            return row["Geopoint1-Latitude"], row["Geopoint1-Longitude"]
        if pd.notna(row.get("geopoint-Latitude")) and pd.notna(row.get("geopoint-Longitude")):
            return row["geopoint-Latitude"], row["geopoint-Longitude"]
        return (pd.NA, pd.NA)

    coords = combined.apply(pick_lat, axis=1, result_type="expand")
    coords.columns = ["lat", "lon"]
    combined = pd.concat([combined, coords], axis=1)

    # external_verification -> numeric if possible (0/1)
    if "external_verification" in combined.columns:
        combined["external_verification"] = pd.to_numeric(combined["external_verification"], errors="coerce").fillna(0).astype(int)

    # Fill empty strings/nulls with "Not provided" for display columns (but keep lat/lon numeric NaN)
    display_fill_cols = [c for c in combined.columns if c not in ["lat", "lon", "SubmissionDate", "external_verification"]]
    combined[display_fill_cols] = combined[display_fill_cols].fillna("Not provided")
    # For numeric lat/lon, keep NaN where missing
    return combined

def make_link_markdown(url: str, label="Link"):
    if not url or url == "Not provided" or pd.isna(url):
        return "Not provided"
    # sanitize
    url = str(url).strip()
    return f"[{label}]({url})"

def percent(part, whole):
    return round(100 * (part / whole), 1) if whole else 0.0

# ---------- Load data ----------
st.set_page_config(page_title="Surveyor Dashboard", layout="wide", initial_sidebar_state="expanded")
st.title("Surveyor Submissions Dashboard")

df = load_and_combine_excel_files(DATA_FOLDER)

if df.empty:
    st.warning(f"No data found in folder `{DATA_FOLDER}`. Please ensure it contains .xlsx files.")
    st.stop()

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
surveyor_list = ["All Surveyors"] + sorted(df["Surveyor_Name"].unique().tolist())
selected_surveyor = st.sidebar.selectbox("Select Surveyor", surveyor_list)

min_date = df["SubmissionDate"].min()
max_date = df["SubmissionDate"].max()
if pd.notna(min_date) and pd.notna(max_date):
    date_range = st.sidebar.date_input("Submission date range", [min_date.date(), max_date.date()])
else:
    date_range = None

# Apply filters
filtered = df.copy()
if selected_surveyor != "All Surveyors":
    filtered = filtered[filtered["Surveyor_Name"] == selected_surveyor]

if date_range and len(date_range) == 2:
    start, end = date_range
    # include the end day
    filtered = filtered[
        (filtered["SubmissionDate"].isna()) |
        ((filtered["SubmissionDate"].dt.date >= start) & (filtered["SubmissionDate"].dt.date <= end))
    ]

# ---------- Key Metrics ----------
total_sub = len(filtered)
total_verified = int(filtered["external_verification"].sum()) if "external_verification" in filtered.columns else 0
pct_verified = percent(total_verified, total_sub)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total submissions", total_sub)
col2.metric("Externally verified", f"{total_verified} ({pct_verified}%)")
col3.metric("Unique provinces", filtered["Province"].nunique() if "Province" in filtered.columns else 0)
col4.metric("Unique villages", filtered["Village"].nunique() if "Village" in filtered.columns else 0)

st.markdown("---")

# ---------- Charts ----------
st.header("Overview Charts")
import plotly.express as px

# submissions per surveyor (global)
if selected_surveyor == "All Surveyors":
    subs_by_surveyor = df.groupby("Surveyor_Name", dropna=False).size().reset_index(name="count")
    fig1 = px.bar(subs_by_surveyor.sort_values("count", ascending=False),
                  x="Surveyor_Name", y="count", title="Submissions per Surveyor")
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.write(f"Showing data for **{selected_surveyor}**")

# Verified vs not
verif_counts = filtered["external_verification"].value_counts().rename_axis("verified").reset_index(name="count")
# ensure both categories exist
if 0 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified":0,"count":0}])], ignore_index=True)
if 1 not in verif_counts["verified"].values:
    verif_counts = pd.concat([verif_counts, pd.DataFrame([{"verified":1,"count":0}])], ignore_index=True)
verif_counts = verif_counts.sort_values("verified")
verif_counts["label"] = verif_counts["verified"].map({0: "Not verified / empty", 1: "Externally verified"})

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

# ---------- Map ----------
st.header("Map of Submissions")

# Build map points
map_df = filtered.copy()
map_df = map_df[map_df["lat"].notna() & map_df["lon"].notna()].copy()

if map_df.empty:
    st.info("No GPS points available for the current filters.")
else:
    # color by external_verification
    def color_row(ev):
        try:
            v = int(ev)
            if v == 1:
                return [255, 0, 0]  # red
        except Exception:
            pass
        return [0, 200, 0]  # green-ish

    map_df["color"] = map_df["external_verification"].apply(color_row)

    # pydeck layer
    tooltip = {
        "html": "<b>KEY:</b> {KEY} <br/>"
                "<b>Beneficiary:</b> {benef_name_full} <br/>"
                "<b>Province:</b> {Province} <br/>"
                "<b>District:</b> {District} <br/>"
                "<b>Village:</b> {Village}",
        "style": {"backgroundColor": "steelblue", "color": "white"}
    }

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        pickable=True,
        get_position='[lon, lat]',
        get_fill_color="color",
        get_radius=50,
        radiusScale=10,
        radiusMinPixels=3,
        radiusMaxPixels=40,
        tooltip=tooltip,
    )

    # initial view state: center on mean coords
    view_state = pdk.ViewState(
        latitude=map_df["lat"].mean(),
        longitude=map_df["lon"].mean(),
        zoom=8,
        pitch=0,
    )

    r = pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
    st.pydeck_chart(r)

    st.caption("""Hover over points to see KEY and basic info.

    Note: Streamlit/pydeck shows tooltips on hover/pick. 
    To view full details of any record, select the KEY from the selector below.""")

st.markdown("---")

# ---------- KEY selector to view record details ----------
st.header("Record Explorer")

# create a list of KEYs for selector
key_options = ["-- Select a record by KEY (or leave blank) --"] + map_df["KEY"].astype(str).tolist() + \
              [k for k in filtered["KEY"].astype(str).tolist() if k not in map_df["KEY"].astype(str).tolist()]

selected_key = st.selectbox("Select KEY to view details", key_options)

def render_media_links(row):
    """Return markdown block with links and inline previews where possible (images/audio)."""
    md = []
    for col in LINK_COLUMNS:
        if col in row.index:
            val = row[col]
            if val == "Not provided" or pd.isna(val):
                md.append(f"**{col}:** Not provided  ")
            else:
                # show as link; for images show inline small preview
                url = str(val).strip()
                if any(url.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]):
                    # image
                    md.append(f"**{col}:** [{os.path.basename(url)}]({url})  ")
                    # show preview
                    md.append(f"![img preview]({url}){{width=200}}  ")
                elif any(url.lower().endswith(ext) for ext in [".mp3", ".wav", ".ogg", ".m4a"]):
                    md.append(f"**{col}:** [{os.path.basename(url)}]({url})  ")
                    # Streamlit has st.audio; we'll show audio below separately
                else:
                    md.append(f"**{col}:** [{os.path.basename(url)}]({url})  ")
    return "\n".join(md)

def show_record_details(df_all, key):
    if key == "-- Select a record by KEY (or leave blank) --":
        st.info("Select a KEY to see the full record details, media and verification info.")
        return
    rec = df_all[df_all["KEY"].astype(str) == str(key)]
    if rec.empty:
        st.warning("KEY not found in current filtered dataset.")
        return
    # if multiple records with same KEY, show all
    for i, row in rec.iterrows():
        st.subheader(f"Record KEY: {row['KEY']}")
        st.markdown(f"**Surveyor:** {row.get('Surveyor_Name', 'Not provided')}")
        st.markdown(f"**Beneficiary:** {row.get('benef_name_full', 'Not provided')}")
        st.markdown(f"**Province / District / Village:** {row.get('Province', 'Not provided')} / {row.get('District', 'Not provided')} / {row.get('Village', 'Not provided')}")
        sd = row.get("SubmissionDate")
        st.markdown(f"**SubmissionDate:** {sd if pd.isna(sd) == False else 'Not provided'}")
        st.markdown(f"**Review status:** {row.get('review_status', 'Not provided')}")
        st.markdown(f"**External verification:** { 'Yes' if int(row.get('external_verification',0))==1 else 'No' }")
        # If verified show elder info conditionally
        if int(row.get('external_verification', 0)) == 1:
            st.markdown("**External verification details:**")
            st.markdown(f"- Name: {row.get('name_community_elder', 'Not provided')}")
            st.markdown(f"- Phone(s): {row.get('phonenumber_community_elder', 'Not provided')}")
            st.markdown(f"- Verification notes: {row.get('community_elder_verification', 'Not provided')}")
        # Show coordinates
        if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
            st.markdown(f"**Coordinates (lat,lon):** {row['lat']}, {row['lon']}")
            # tiny map for this single point
            st.map(pd.DataFrame({"lat":[row['lat']],"lon":[row['lon']]}))
        else:
            st.markdown("**Coordinates:** Not provided")

        # Show media links + audio players if available
        media_md = render_media_links(row)
        if media_md:
            st.markdown(media_md, unsafe_allow_html=True)

        # For audio links, use st.audio if available
        for col in LINK_COLUMNS:
            val = row.get(col, "Not provided")
            if isinstance(val, str) and any(val.lower().endswith(ext) for ext in [".mp3", ".wav", ".ogg", ".m4a"]):
                try:
                    st.audio(val)
                except Exception as e:
                    st.write(f"Audio: [{val}]({val})")
        st.markdown("---")

# show details for the selected key
show_record_details(filtered, selected_key)

# ---------- Table Summary ----------
st.header("Tabular View (clickable links)")

# prepare display DataFrame
display_cols = [
    "KEY", "Surveyor_Name", "Surveyor_Id", "SubmissionDate",
    "Province", "District", "Village", "benef_name_full",
    "external_verification", "review_status"
]
# extend with link columns
display_cols += [c for c in LINK_COLUMNS if c in filtered.columns]

df_display = filtered[display_cols].copy()

# make human-friendly external verification
df_display["external_verification"] = df_display["external_verification"].map({1: "Yes", 0: "No"}).fillna("No")

# make links markdown
for col in LINK_COLUMNS:
    if col in df_display.columns:
        df_display[col] = df_display[col].apply(lambda x: make_link_markdown(x, label="Open") if x != "Not provided" else "Not provided")

# Render as HTML table so links are clickable
st.markdown(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)

st.caption("Note: Click 'Open' links to view media. Empty fields show 'Not provided'.")

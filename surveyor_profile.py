import streamlit as st
import pandas as pd
import folium
import datetime
import matplotlib.pyplot as plt
from streamlit_folium import st_folium

# -------------------------------------
# Load data
# -------------------------------------
df = pd.read_excel("../EFSP_Outcome_Monitoring_with_verification.xlsx")

# -------------------------------------
# Sidebar – select surveyor
# -------------------------------------
surveyors = sorted(df["Surveyor_Name"].dropna().unique())
selected_surveyor = st.sidebar.selectbox("Select a Surveyor", surveyors)

# -------------------------------------
# Filter data for selected surveyor
# -------------------------------------
filtered = df[df["Surveyor_Name"] == selected_surveyor]

# -------------------------------------
# Summary stats
# -------------------------------------
total = len(filtered)
verified = filtered["external_verification"].sum()
pct_verified = round((verified / total) * 100, 1) if total > 0 else 0

# -------------------------------------
# Header and Metrics
# -------------------------------------
st.title(f"Surveyor Profile: {selected_surveyor}")

col1, col2, col3 = st.columns(3)
col1.metric("Total Records", total)
col2.metric("Externally Verified", verified)
col3.metric("Percentage %", f"{pct_verified}%")

# -------------------------------------
# Custom Bar Chart (horizontal, red/green)
# -------------------------------------
st.subheader("Verification Status")

# Prepare data
verified_counts = filtered["external_verification"].value_counts().rename({
    1: "Externally Verified",
    0: "Verified through Beneficiary"
}).reindex(["Externally Verified", "Verified by Respondent"], fill_value=0)

# Define custom colors (red for external, green for beneficiary)
colors = ["red", "green"]

# Create horizontal bar chart
fig, ax = plt.subplots(figsize=(6, 3))
bars = ax.barh(verified_counts.index, verified_counts.values, color=colors)

# Add value labels
for bar in bars:
    width = bar.get_width()
    ax.text(width + 0.2, bar.get_y() + bar.get_height() / 2,
            f"{int(width)}", va='center')

# Style
ax.set_xlabel("Number of Records")
ax.set_ylabel("Verification Type")
ax.set_title("External vs Beneficiary Verification")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
st.pyplot(fig)

# -------------------------------------
# Map with Folium (red/green markers)
# -------------------------------------
if {"Geopoint1-Latitude", "Geopoint1-Longitude"}.issubset(filtered.columns):
    st.subheader("GPS Points Map")

    gps_df = filtered.dropna(subset=["Geopoint1-Latitude", "Geopoint1-Longitude"])
    gps_df = gps_df[
        (gps_df["Geopoint1-Latitude"] != 0) &
        (gps_df["Geopoint1-Longitude"] != 0)
    ]

    if gps_df.empty:
        st.warning("No valid GPS points found for this surveyor.")
    else:
        # Center map on average location
        center_lat = gps_df["Geopoint1-Latitude"].mean()
        center_lon = gps_df["Geopoint1-Longitude"].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

        # Add markers for each point
        for _, row in gps_df.iterrows():
            lat = row["Geopoint1-Latitude"]
            lon = row["Geopoint1-Longitude"]
            color = "red" if row.get("external_verification", 0) == 1 else "green"

            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=(
                    f"<b>Lat:</b> {lat:.6f}<br>"
                    f"<b>Lon:</b> {lon:.6f}<br>"
                    f"<b>Verified:</b> {'Yes' if row.get('external_verification', 0) == 1 else 'No'}"
                ),
            ).add_to(m)

        st_folium(m, width=700, height=500)
else:
    st.warning("No GPS columns found ('Geopoint1-Latitude' and 'Geopoint1-Longitude').")

# -------------------------------------
# Raw data table
# -------------------------------------
st.subheader(f"Raw Data submitted by {selected_surveyor}")
st.dataframe(filtered)

# -------------------------------------
# Notes section
# -------------------------------------
st.subheader("Notes")
notes = st.text_area("Enter notes or observations for this surveyor:")

if st.button("Save Notes"):
    if notes.strip():  # only save if not empty
        note_entry = pd.DataFrame({
            "Surveyor_Name": [selected_surveyor],
            "Timestamp": [datetime.datetime.now()],
            "Notes": [notes]
        })
        # Append to a CSV
        note_entry.to_csv("surveyor_notes.csv", mode="a", index=False, header=not pd.io.common.file_exists("surveyor_notes.csv"))
        st.success("Notes saved successfully!")

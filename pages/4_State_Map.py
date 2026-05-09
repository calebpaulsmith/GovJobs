from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from src.ui_data import (
    app_connection,
    current_location_coverage,
    multi_location_jobs,
    non_mappable_current_postings,
    opm_state_counts,
    remote_anywhere_jobs,
    remote_counts,
    state_counts,
    work_location_points,
)


US_CENTER = (39.8283, -98.5795)
REPO = Path(__file__).resolve().parents[1]
PUBLIC_MAP_DATA = REPO / "public_map" / "static" / "data"

POLYGON_LAYER_FILES = {
    "State polygons": "states.geojson",
    "Locality pay polygons": "localities.geojson",
    "County polygons": "counties.geojson",
    "Metro/CBSA polygons": "metros.geojson",
}

POLYGON_LAYER_STYLES = {
    "State polygons": {"color": "#2563EB", "fillColor": "#60A5FA", "weight": 1.0, "fillOpacity": 0.08},
    "Locality pay polygons": {"color": "#7C3AED", "fillColor": "#A78BFA", "weight": 1.6, "fillOpacity": 0.12},
    "County polygons": {"color": "#64748B", "fillColor": "#CBD5E1", "weight": 0.45, "fillOpacity": 0.02},
    "Metro/CBSA polygons": {"color": "#DC2626", "fillColor": "#FCA5A5", "weight": 0.9, "fillOpacity": 0.03},
}

POLYGON_TOOLTIP_FIELDS = {
    "State polygons": (["name", "state", "postings", "locality_code", "pay_vs_col"], ["State", "Code", "Postings", "Dominant locality", "Pay/COL"]),
    "Locality pay polygons": (["name", "code", "adjustment_pct", "county_count", "postings"], ["Locality", "Code", "Adjustment %", "Counties", "Postings"]),
    "County polygons": (["name", "state", "fips", "locality_code", "postings"], ["County", "State", "FIPS", "Locality", "Postings"]),
    "Metro/CBSA polygons": (["name", "cbsa_code", "cbsa_type", "postings"], ["Metro/CBSA", "Code", "Type", "Postings"]),
}


@st.cache_data(show_spinner=False)
def _load_public_map_geojson(file_name: str) -> dict[str, Any] | None:
    path = PUBLIC_MAP_DATA / file_name
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@st.cache_data(show_spinner=False)
def _load_public_map_manifest() -> dict[str, Any] | None:
    return _load_public_map_geojson("manifest.json")


def _geojson_feature_count(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 0
    features = payload.get("features")
    return len(features) if isinstance(features, list) else 0


def _style_for_layer(layer_name: str) -> dict[str, Any]:
    return dict(POLYGON_LAYER_STYLES[layer_name])


def _tooltip_for_layer(layer_name: str) -> folium.GeoJsonTooltip:
    fields, aliases = POLYGON_TOOLTIP_FIELDS[layer_name]
    return folium.GeoJsonTooltip(
        fields=fields,
        aliases=aliases,
        sticky=True,
        localize=True,
        labels=True,
    )


def _add_public_polygon_layers(map_obj: folium.Map, selected_layers: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for layer_name in selected_layers:
        file_name = POLYGON_LAYER_FILES[layer_name]
        payload = _load_public_map_geojson(file_name)
        count = _geojson_feature_count(payload)
        counts[layer_name] = count
        if not payload or count == 0:
            continue
        folium.GeoJson(
            payload,
            name=layer_name,
            overlay=True,
            control=True,
            show=True,
            style_function=lambda _feature, name=layer_name: _style_for_layer(name),
            highlight_function=lambda _feature: {
                "weight": 3,
                "color": "#111827",
                "fillOpacity": 0.18,
            },
            tooltip=_tooltip_for_layer(layer_name),
        ).add_to(map_obj)
    return counts


def _work_location_map(
    points,
    *,
    center: tuple[float, float],
    selected_polygon_layers: list[str],
    zoom_start: int = 5,
) -> tuple[folium.Map, dict[str, int]]:
    map_obj = folium.Map(location=center, zoom_start=zoom_start, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles (c) Esri",
        name="Esri streets",
        overlay=False,
        control=True,
    ).add_to(map_obj)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles (c) Esri",
        name="Esri imagery",
        overlay=False,
        control=True,
    ).add_to(map_obj)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False, control=True).add_to(map_obj)

    polygon_counts = _add_public_polygon_layers(map_obj, selected_polygon_layers)

    cluster = MarkerCluster(
        name="Work locations",
        options={
            "spiderfyOnMaxZoom": True,
            "showCoverageOnHover": False,
            "disableClusteringAtZoom": 15,
        },
    ).add_to(map_obj)
    bounds: list[list[float]] = []
    duplicate_groups = _duplicate_coordinate_groups(points)
    seen_by_coordinate: dict[tuple[float, float], int] = {}
    for row in points.itertuples(index=False):
        actual_lat = float(row.latitude)
        actual_lon = float(row.longitude)
        coord_key = _coordinate_key(actual_lat, actual_lon)
        duplicate_count = duplicate_groups.get(coord_key, 1)
        duplicate_index = seen_by_coordinate.get(coord_key, 0)
        seen_by_coordinate[coord_key] = duplicate_index + 1
        lat, lon = _display_coordinate(
            actual_lat,
            actual_lon,
            duplicate_index=duplicate_index,
            duplicate_count=duplicate_count,
        )
        bounds.append([lat, lon])
        color = "#0F766E" if not bool(row.is_multi_location) else "#B45309"
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color=color,
            fill=True,
            fill_opacity=0.82,
            popup=folium.Popup(
                folium.IFrame(
                    html=_popup_html(
                        row,
                        duplicate_count=duplicate_count,
                        actual_lat=actual_lat,
                        actual_lon=actual_lon,
                    ),
                    width=540,
                    height=560,
                ),
                max_width=560,
            ),
            tooltip=str(row.title or "Posting"),
        ).add_to(cluster)
    if bounds:
        map_obj.fit_bounds(bounds, padding=(24, 24))
    folium.LayerControl(collapsed=False).add_to(map_obj)
    return map_obj, polygon_counts


def _popup_html(
    row: Any,
    *,
    duplicate_count: int = 1,
    actual_lat: float | None = None,
    actual_lon: float | None = None,
) -> str:
    title = html.escape(str(row.title or "Untitled"))
    agency = html.escape(str(row.agency or "Unknown agency"))
    location = html.escape(str(row.location_text or row.city or row.state or "Unknown location"))
    all_locations_html = _locations_html(getattr(row, "all_locations", None), current_location=location)
    url = _job_url(row)
    escaped_url = html.escape(url)
    link = (
        f"""
        <p style="margin:10px 0;">
          <a href="{escaped_url}" target="_blank" rel="noopener noreferrer"
             style="display:block;background:#0F766E;color:white;text-align:center;font-weight:700;
                    padding:9px 12px;border-radius:6px;text-decoration:none;">
            Open USAJOBS posting
          </a>
        </p>
        <p style="font-size:11px;word-break:break-all;margin-top:4px;">
          <strong>URL:</strong> <a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_url}</a>
        </p>
        """
        if url
        else ""
    )
    summary = _popup_text(getattr(row, "summary", None), limit=520)
    qualifications = _popup_text(
        getattr(row, "specialized_experience", None) or getattr(row, "qualifications", None),
        limit=620,
    )
    summary_html = f"<h4>Summary</h4><p>{summary}</p>" if summary else ""
    qualifications_html = f"<h4>Qualifications</h4><p>{qualifications}</p>" if qualifications else ""
    duplicate_note = (
        "<p><em>Several postings share this exact coordinate; points are slightly separated on the map so each can be selected.</em></p>"
        if duplicate_count > 1
        else ""
    )
    coordinate_note = (
        f"<p><small>Source coordinate: {actual_lat:.6f}, {actual_lon:.6f}</small></p>"
        if actual_lat is not None and actual_lon is not None
        else ""
    )
    return f"""
    <div style="font-family:Arial,sans-serif;font-size:13px;line-height:1.35;max-width:500px;">
    <h3 style="margin:0 0 6px 0;font-size:16px;">{title}</h3>
    {link}
    <p>{agency}</p>
    <p><strong>Clicked location:</strong> {location}</p>
    {all_locations_html}
    <p>Series {html.escape(str(row.series or ''))} | Grade {html.escape(str(row.grade_high or ''))}</p>
    <p>{'Multi-location posting' if bool(row.is_multi_location) else 'Single mapped location'}</p>
    {summary_html}
    {qualifications_html}
    {duplicate_note}
    {coordinate_note}
    </div>
    """


def _job_url(row: Any) -> str:
    raw_url = str(getattr(row, "url", None) or "").strip()
    if raw_url:
        return raw_url.replace("https://www.usajobs.gov:443/", "https://www.usajobs.gov/")
    return ""


def _popup_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "..."
    return html.escape(text)


def _locations_html(value: Any, *, current_location: str) -> str:
    raw_locations = [item.strip() for item in str(value or "").split("|") if item.strip()]
    if not raw_locations and current_location:
        raw_locations = [current_location]
    locations = list(dict.fromkeys(raw_locations))
    if not locations:
        return ""
    items = "".join(f"<li>{html.escape(location)}</li>" for location in locations)
    return f"""
    <h4>Named Locations</h4>
    <div style="max-height:140px;overflow-y:auto;border-left:3px solid #D1D5DB;padding-left:8px;">
      <ul style="margin:0;padding-left:16px;">{items}</ul>
    </div>
    """


def _duplicate_coordinate_groups(points) -> dict[tuple[float, float], int]:
    groups: dict[tuple[float, float], int] = {}
    for row in points.itertuples(index=False):
        key = _coordinate_key(float(row.latitude), float(row.longitude))
        groups[key] = groups.get(key, 0) + 1
    return groups


def _coordinate_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 6), round(lon, 6))


def _display_coordinate(
    lat: float,
    lon: float,
    *,
    duplicate_index: int,
    duplicate_count: int,
) -> tuple[float, float]:
    if duplicate_count <= 1:
        return lat, lon
    radius_degrees = 0.00009 if duplicate_count <= 5 else 0.00013
    angle = (2 * math.pi * duplicate_index) / duplicate_count
    lat_offset = radius_degrees * math.sin(angle)
    lon_scale = max(math.cos(math.radians(lat)), 0.2)
    lon_offset = (radius_degrees * math.cos(angle)) / lon_scale
    return lat + lat_offset, lon + lon_offset


def _map_center(points) -> tuple[float, float]:
    return (float(points["latitude"].mean()), float(points["longitude"].mean()))


def _bounds_from_map_state(map_state: Any) -> dict[str, float] | None:
    if not isinstance(map_state, dict):
        return None
    bounds = map_state.get("bounds")
    if not isinstance(bounds, dict):
        return None
    south_west = bounds.get("_southWest") or bounds.get("southWest") or bounds.get("southwest")
    north_east = bounds.get("_northEast") or bounds.get("northEast") or bounds.get("northeast")
    if isinstance(south_west, dict) and isinstance(north_east, dict):
        return {
            "south": float(south_west["lat"]),
            "west": float(south_west["lng"]),
            "north": float(north_east["lat"]),
            "east": float(north_east["lng"]),
        }
    return None


st.set_page_config(
    page_title="Work Location Map",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.6rem;
        padding-left: 0.8rem;
        padding-right: 0.8rem;
        max-width: 100%;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Work Location Map")

conn = app_connection()
toolbar = st.columns([1, 1, 4])
with toolbar[0]:
    source_layer = st.radio(
        "Data source",
        ["USAJOBS postings", "OPM workforce"],
        horizontal=True,
        label_visibility="collapsed",
    )

if source_layer == "USAJOBS postings":
    with toolbar[1]:
        with st.popover("Map Filters", use_container_width=True):
            map_source = st.selectbox("Posting source", ["All", "usajobs_search", "usajobs_historic"])
            include_multi = st.checkbox("Include multi-location postings", value=True)
            selected_polygon_layers = st.multiselect(
                "Public map polygon overlays",
                list(POLYGON_LAYER_FILES),
                default=["State polygons", "Locality pay polygons"],
                help=(
                    "Uses the same exported GeoJSON bundle as the public map "
                    "under public_map/static/data/."
                ),
            )
    points = work_location_points(conn, include_multi_location=include_multi, source=map_source)
    coverage = current_location_coverage(conn)

    center = _map_center(points) if not points.empty else US_CENTER
    map_obj, polygon_counts = _work_location_map(
        points,
        center=center,
        selected_polygon_layers=selected_polygon_layers,
        zoom_start=5 if not points.empty else 4,
    )
    map_state = st_folium(
        map_obj,
        height=860,
        use_container_width=True,
        returned_objects=["bounds", "zoom", "center"],
        key="work_location_folium_map",
    )
    bounds = _bounds_from_map_state(map_state)
    zoom = int(map_state.get("zoom") or 4) if isinstance(map_state, dict) else 4
    manifest = _load_public_map_manifest()
    manifest_generated = (manifest or {}).get("generated_at")
    polygon_summary = " | ".join(
        f"{label.replace(' polygons', '').replace('/CBSA', '')}: {polygon_counts.get(label, 0):,}"
        for label in selected_polygon_layers
    )
    with toolbar[2]:
        st.caption(
            f"Mapped work locations: {len(points):,} | Current mapped: {coverage['mapped_postings']:,} | "
            f"Current unmapped: {coverage['unmapped_non_remote_postings']:,} | Remote: {coverage['remote_postings']:,}"
        )
        if polygon_summary:
            st.caption(
                f"Public map overlays: {polygon_summary}"
                + (f" | Bundle generated: {manifest_generated}" if manifest_generated else "")
            )
        elif not (PUBLIC_MAP_DATA / "manifest.json").exists():
            st.caption("Public map overlays unavailable. Run `python scripts/export_public_map.py` to build the local bundle.")

    with st.popover("Map Review Panel", use_container_width=True):
        st.metric("Mapped work locations", f"{len(points):,}")
        coverage_cols = st.columns(3)
        coverage_cols[0].metric("Current Mapped", f"{coverage['mapped_postings']:,}")
        coverage_cols[1].metric("Current Unmapped", f"{coverage['unmapped_non_remote_postings']:,}")
        coverage_cols[2].metric("Remote", f"{coverage['remote_postings']:,}")
        if selected_polygon_layers:
            st.subheader("Public Map Polygon Overlays")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Layer": layer,
                            "File": POLYGON_LAYER_FILES[layer],
                            "Features": polygon_counts.get(layer, 0),
                        }
                        for layer in selected_polygon_layers
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        if points.empty:
            st.info(
                "No coordinate-level work locations are available yet. The base map is ready; current Search imports can add latitude/longitude points when the API provides them."
            )
        if not include_multi:
            st.caption("Multi-location postings are hidden from the point layer.")
        if zoom < 6:
            st.info(
                "Zoom closer to review current postings that have named locations but no coordinates, plus remote-anywhere postings."
            )
        else:
            unmapped = non_mappable_current_postings(conn, bounds=bounds)
            st.subheader("Unmapped Current Postings In View")
            if unmapped.empty:
                st.caption("No current non-remote postings without coordinates match this map view.")
            else:
                st.dataframe(unmapped, use_container_width=True, hide_index=True)

            remote_jobs = remote_anywhere_jobs(conn)
            st.subheader("Remote Anywhere Postings")
            if remote_jobs.empty:
                st.caption("No remote-anywhere postings imported.")
            else:
                st.dataframe(remote_jobs, use_container_width=True, hide_index=True)

        st.subheader("Mapped Point Data")
        if points.empty:
            st.caption("No mapped point rows yet.")
        else:
            st.dataframe(points, use_container_width=True, hide_index=True)

        remote = remote_counts(conn)
        if not remote.empty:
            st.subheader("Remote And Telework Summary")
            st.bar_chart(remote.set_index("label"))
        multi_jobs = multi_location_jobs(conn)
        if not multi_jobs.empty:
            st.subheader("Multi-Location Postings")
            st.dataframe(multi_jobs, use_container_width=True, hide_index=True)
else:
    with toolbar[1]:
        with st.popover("Map Filters", use_container_width=True):
            metric = st.selectbox("OPM metric", ["employment", "accessions", "separations"])
    states = opm_state_counts(conn, metric=metric)
    color_column = {
        "employment": "workforce_count",
        "accessions": "accessions",
        "separations": "separations",
    }[metric]
    legend = {
        "employment": "OPM workforce count",
        "accessions": "OPM accessions",
        "separations": "OPM separations",
    }[metric]
    if states.empty:
        st.info("No state-normalized OPM workforce data available.")
    else:
        fig = px.choropleth(
            states,
            locations="state",
            locationmode="USA-states",
            color=color_column,
            scope="usa",
            color_continuous_scale="Teal",
            labels={color_column: legend},
        )
        fig.update_layout(height=820, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        with toolbar[2]:
            st.caption(f"{legend} by state. OPM workforce, accessions, and separations are not USAJOBS postings.")
        with st.popover("Map Review Panel", use_container_width=True):
            st.dataframe(states, use_container_width=True, hide_index=True)

conn.close()

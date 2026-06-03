# =============================================================================
# Application Géospatiale Web — Région Eddakhla-Oued Eddahab
# GIS Programming 2025-2026 | Pr. Abdelhamid FADIL | EHTP
# Réalisé par : Youssef OUDADDA & Hiba Farchi
# =============================================================================

import os
import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.express as px
import requests
import rasterio
from rasterio.mask import mask

# configuration de la page
st.set_page_config(
    page_title="GeoApp Eddakhla",
    page_icon="🗺️",
    layout="wide"
)

# chemins vers les fichiers de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

PATH_REGIONS   = os.path.join(DATA_DIR, "Regions_WGS84.shp")
PATH_PROVINCES = os.path.join(DATA_DIR, "Provinces_WGS84.shp")
PATH_COMMUNES  = os.path.join(DATA_DIR, "communes_WGS84.shp")
PATH_MNT       = os.path.join(DATA_DIR, "mnt_maroc.tif")

# region cible du projet
REGION_CIBLE = "Eddakhla-Oued Eddahab"

# =============================================================================
# CHARGEMENT DES SHAPEFILES
# =============================================================================

@st.cache_data
def load_shapefiles():
    gdf_reg  = gpd.read_file(PATH_REGIONS,   encoding='utf-8')
    gdf_prov = gpd.read_file(PATH_PROVINCES, encoding='utf-8')
    gdf_comm = gpd.read_file(PATH_COMMUNES,  encoding='utf-8')
    return gdf_reg, gdf_prov, gdf_comm

# fonction pour normaliser les noms (enlever espaces, tirets, mettre en minuscules)
# utile pour comparer les noms de provinces entre les deux shapefiles
def normalize(val):
    if val is None:
        return ""
    return str(val).strip().lower().replace(" ", "").replace("-", "")

try:
    gdf_regions, gdf_provinces, gdf_communes = load_shapefiles()
    gdf_communes = gdf_communes.copy()
    gdf_communes["norm_prov"] = gdf_communes["FIRST_prov"].apply(normalize)
except Exception as e:
    st.error(f"Erreur lors du chargement des shapefiles : {e}")
    st.stop()

# =============================================================================
# SIDEBAR — NAVIGATION
# =============================================================================

st.sidebar.title("🗺️ Navigation")
st.sidebar.markdown("**Projet GIS Programming 2025-2026**")
st.sidebar.markdown("Youssef OUDADDA & Hiba Farchi")
st.sidebar.markdown("---")

# liste des regions (toutes les 12 regions du Maroc)
regions_liste = sorted(gdf_regions["libelle_fr"].dropna().unique().tolist())
idx_defaut = regions_liste.index(REGION_CIBLE) if REGION_CIBLE in regions_liste else 0

selected_region = st.sidebar.selectbox(
    "Région",
    options=regions_liste,
    index=idx_defaut
)

# verifier si la region selectionnee est notre region cible
region_dispo = (selected_region == REGION_CIBLE)

# si ce n'est pas Eddakhla, on affiche un message et on s'arrete la
if not region_dispo:
    st.sidebar.warning("⚠️ Données disponibles uniquement pour Eddakhla-Oued Eddahab")
    st.title(f"🗺️ {selected_region}")
    st.info(
        f"Les données détaillées (carte, relief, météo) ne sont disponibles "
        f"que pour la région **{REGION_CIBLE}**.\n\n"
        f"Veuillez sélectionner **{REGION_CIBLE}** dans le menu pour accéder à l'application complète."
    )
    st.stop()

# --- a partir d'ici on est sur Eddakhla-Oued Eddahab ---

# recuperer le code_reg de la region
code_reg = gdf_regions.loc[
    gdf_regions["libelle_fr"] == selected_region, "code_reg"
].iloc[0]

# filtrer les provinces de cette region
gdf_prov_filtered = gdf_provinces[gdf_provinces["code_reg"] == code_reg]
provinces_liste = sorted(gdf_prov_filtered["libelle_fr"].dropna().unique().tolist())

selected_province = st.sidebar.selectbox("Province", options=provinces_liste)

# filtrer les communes de cette province
norm_prov = normalize(selected_province)
gdf_comm_filtered = gdf_communes[gdf_communes["norm_prov"] == norm_prov]
communes_liste = sorted(gdf_comm_filtered["FIRST_com_"].dropna().unique().tolist())

selected_commune = st.sidebar.selectbox("Commune", options=communes_liste)

st.sidebar.markdown("---")

# niveau d'analyse : region, province ou commune
niveau = st.sidebar.radio(
    "Niveau d'analyse",
    options=["Région", "Province", "Commune"]
)

# parametre climatique a afficher
parametre = st.sidebar.radio(
    "Paramètre climatique",
    options=["Température (°C)", "Précipitations (mm)"]
)

# =============================================================================
# DETERMINATION DE L'ENTITE ACTIVE
# =============================================================================

if niveau == "Région":
    active_gdf  = gdf_regions[gdf_regions["libelle_fr"] == selected_region].copy()
    active_name = selected_region

elif niveau == "Province":
    active_gdf  = gdf_prov_filtered[gdf_prov_filtered["libelle_fr"] == selected_province].copy()
    active_name = selected_province

else:  # Commune
    active_gdf  = gdf_comm_filtered[gdf_comm_filtered["FIRST_com_"] == selected_commune].copy()
    active_name = selected_commune

# verifier le CRS (doit etre EPSG:4326)
if active_gdf.crs is None:
    active_gdf = active_gdf.set_crs("EPSG:4326")
elif active_gdf.crs.to_epsg() != 4326:
    active_gdf = active_gdf.to_crs("EPSG:4326")

# calculer le centroide (point central de la geometrie)
active_geometry = active_gdf.geometry.unary_union
centroid = active_geometry.centroid
lat_c = centroid.y
lon_c = centroid.x

# =============================================================================
# CALCUL SUPERFICIE
# =============================================================================

try:
    # reprojeter en EPSG:3857 pour avoir des unites metriques
    area_km2 = active_gdf.to_crs(epsg=3857).area.sum() / 1e6
except Exception:
    area_km2 = None

# =============================================================================
# EXTRACTION STATISTIQUES RASTER (Rasterio)
# =============================================================================

@st.cache_data
def get_raster_stats(geojson_geom, raster_path):
    """
    Decoupe le raster MNT selon la geometrie de l'entite selectionnee
    et calcule les statistiques d'altitude.
    """
    try:
        with rasterio.open(raster_path) as src:
            geoms = [geojson_geom]
            out_image, out_transform = mask(src, geoms, crop=True, nodata=-9999)
            band_data = out_image[0]
            # on garde uniquement les pixels valides (pas les nodata)
            valid_pixels = band_data[band_data != -9999]
            if valid_pixels.size == 0:
                return None
            return {
                "min":  float(np.min(valid_pixels)),
                "max":  float(np.max(valid_pixels)),
                "mean": float(np.mean(valid_pixels)),
                "std":  float(np.std(valid_pixels))
            }
    except Exception:
        return None

raster_stats = get_raster_stats(active_geometry.__geo_interface__, PATH_MNT)

# =============================================================================
# DONNEES METEO — API Open-Meteo
# =============================================================================

@st.cache_data(ttl=3600)
def get_meteo(lat, lon):
    """
    Recupere les previsions meteo sur 15 jours depuis l'API Open-Meteo.
    L'API est gratuite et ne necessite pas de cle d'authentification.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&forecast_days=15&timezone=auto"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        daily = r.json()["daily"]
        df = pd.DataFrame({
            "Date":                pd.to_datetime(daily["time"]).strftime("%d/%m/%Y"),
            "Temp Max (°C)":       daily["temperature_2m_max"],
            "Temp Min (°C)":       daily["temperature_2m_min"],
            "Précipitations (mm)": daily["precipitation_sum"],
        })
        df["Temp Moy (°C)"] = (df["Temp Max (°C)"] + df["Temp Min (°C)"]) / 2
        return df
    except Exception as e:
        return None

df_meteo = get_meteo(lat_c, lon_c)

# =============================================================================
# AFFICHAGE PRINCIPAL
# =============================================================================

st.title(f"🗺️ {active_name}")
st.caption(f"Région Eddakhla-Oued Eddahab — Niveau : {niveau}")

# metriques en haut de page
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Superficie", f"{area_km2:,.0f} km²" if area_km2 else "—")
with col2:
    st.metric("Altitude moyenne", f"{raster_stats['mean']:.0f} m" if raster_stats else "—")
with col3:
    st.metric("Latitude", f"{lat_c:.3f} °N")
with col4:
    st.metric("Longitude", f"{lon_c:.3f} °")

st.markdown("---")

# onglets
tab1, tab2, tab3 = st.tabs(["🗺️ Carte Interactive", "📊 Graphiques Climatiques", "⛰️ Statistiques Relief"])

# =============================================================================
# ONGLET 1 — CARTE FOLIUM
# =============================================================================

with tab1:
    st.subheader(f"Carte de {active_name}")

    # creer la carte centree sur l'entite active
    m = folium.Map(
        location=[lat_c, lon_c],
        zoom_start=8,
        tiles="OpenStreetMap",
        control_scale=True
    )

    # ajouter la couche WMS du MNT SRTM (Terrestris)
    folium.WmsTileLayer(
        url="https://ows.terrestris.de/osm/service",
        layers="SRTM30-Colored-Hillshade",
        fmt="image/png",
        transparent=True,
        name="MNT SRTM",
        overlay=True,
        opacity=0.6,
        attr="© Terrestris / SRTM30"
    ).add_to(m)

    # afficher le contour de l'entite selectionnee
    folium.GeoJson(
        active_gdf.__geo_interface__,
        style_function=lambda x: {
            "fillColor": "#00000000",
            "color": "#d35400",
            "weight": 3,
            "fillOpacity": 0.0
        },
        name=f"Contour {active_name}"
    ).add_to(m)

    # marqueur au centre
    folium.Marker(
        location=[lat_c, lon_c],
        popup=f"{active_name}\nLat: {lat_c:.4f} | Lon: {lon_c:.4f}",
        tooltip=active_name
    ).add_to(m)

    # recadrer la carte sur l'emprise de l'entite
    minx, miny, maxx, maxy = active_gdf.geometry.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]])

    folium.LayerControl().add_to(m)

    st_folium(m, height=500, use_container_width=True)

    st.caption("Sources : OpenStreetMap | MNT SRTM30 via Terrestris WMS")

# =============================================================================
# ONGLET 2 — GRAPHIQUES CLIMATIQUES
# =============================================================================

with tab2:
    st.subheader(f"Prévisions météo 15 jours — {active_name}")
    st.caption(f"Source : Open-Meteo API | Coordonnées : {lat_c:.4f}°N, {lon_c:.4f}°")

    if df_meteo is None:
        st.error("Impossible de récupérer les données météo. Vérifiez votre connexion internet.")
    else:
        if parametre == "Température (°C)":
            # graphique courbe pour la temperature
            fig = px.line(
                df_meteo,
                x="Date",
                y=["Temp Max (°C)", "Temp Min (°C)", "Temp Moy (°C)"],
                title=f"Prévisions Températures 15 jours — {active_name}",
                markers=True,
                color_discrete_sequence=["#e74c3c", "#3498db", "#2ecc71"]
            )
            fig.update_layout(
                xaxis_title="Date (JJ/MM/AAAA)",
                yaxis_title="Température (°C)",
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

        else:
            # graphique barres pour les precipitations
            fig = px.bar(
                df_meteo,
                x="Date",
                y="Précipitations (mm)",
                title=f"Prévisions Précipitations 15 jours — {active_name}",
                color_discrete_sequence=["#2980b9"]
            )
            fig.update_layout(
                xaxis_title="Date (JJ/MM/AAAA)",
                yaxis_title="Précipitations cumulées (mm)",
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

        # tableau des donnees brutes
        with st.expander("Voir les données brutes"):
            st.dataframe(df_meteo, use_container_width=True, hide_index=True)

# =============================================================================
# ONGLET 3 — STATISTIQUES DU RELIEF
# =============================================================================

with tab3:
    st.subheader(f"Statistiques altimètriques — {active_name}")
    st.caption("Extraction via rasterio.mask sur le fichier mnt_maroc.tif")

    if raster_stats is None:
        st.warning("Impossible d'extraire les statistiques raster pour cette entité.")
    else:
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Altitude min", f"{raster_stats['min']:.0f} m")
        col_b.metric("Altitude max", f"{raster_stats['max']:.0f} m")
        col_c.metric("Altitude moyenne", f"{raster_stats['mean']:.0f} m")
        col_d.metric("Écart-type", f"{raster_stats['std']:.0f} m")

        st.markdown("---")

        # graphique simple des statistiques
        df_stats = pd.DataFrame({
            "Statistique": ["Min", "Moyenne", "Max"],
            "Altitude (m)": [raster_stats["min"], raster_stats["mean"], raster_stats["max"]]
        })
        fig_s = px.bar(
            df_stats,
            x="Statistique",
            y="Altitude (m)",
            title=f"Profil altimétrique — {active_name}",
            color="Statistique",
            color_discrete_sequence=["#3498db", "#2ecc71", "#e74c3c"],
            text_auto=".0f"
        )
        fig_s.update_layout(showlegend=False)
        st.plotly_chart(fig_s, use_container_width=True)

# =============================================================================
# EXPORT
# =============================================================================

st.markdown("---")
st.subheader("📥 Export")

col_e1, col_e2 = st.columns(2)

with col_e1:
    geojson_str = active_gdf.to_json()
    st.download_button(
        label=f"Télécharger {active_name} (GeoJSON)",
        data=geojson_str,
        file_name=f"{active_name.replace(' ', '_')}.geojson",
        mime="application/geo+json"
    )

with col_e2:
    if df_meteo is not None:
        csv_str = df_meteo.to_csv(index=False)
        st.download_button(
            label="Télécharger données météo (CSV)",
            data=csv_str,
            file_name=f"meteo_{active_name.replace(' ', '_')}.csv",
            mime="text/csv"
        )

# =============================================================================
# CREDITS
# =============================================================================

st.markdown("---")
st.markdown(
    "**Sources :** HCP Maroc (shapefiles) | "
    "[Terrestris WMS](https://ows.terrestris.de) (MNT SRTM) | "
    "[Open-Meteo](https://open-meteo.com) (météo) | "
    "[OpenStreetMap](https://www.openstreetmap.org)  \n"
    "**Projet GIS Programming 2025-2026** | Pr. Abdelhamid FADIL | EHTP  \n"
    "**Réalisé par :** Youssef OUDADDA & Hiba Farchi"
)

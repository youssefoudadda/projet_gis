# Application Géospatiale Web — Région Eddakhla-Oued Eddahab

**GIS Programming 2025-2026** | Pr. Abdelhamid FADIL | EHTP  
**Réalisé par :** Youssef OUDADDA & Hiba Farchi

Application web interactive développée avec Streamlit pour visualiser les données géospatiales et météorologiques de la région **Eddakhla-Oued Eddahab**.

🔗 **Application déployée :** *(lien à ajouter après déploiement)*

---

## Fonctionnalités

- Navigation administrative : Région → Province → Commune
- Carte interactive avec MNT SRTM (Folium + WMS)
- Prévisions météo 15 jours (température et précipitations)
- Statistiques d'altitude extraites depuis le raster MNT
- Export GeoJSON et CSV

---

## Structure du projet

```
projet_gis_eddakhla/
├── .streamlit/
│   └── config.toml
├── data/
│   ├── Regions_WGS84.shp
│   ├── Provinces_WGS84.shp
│   └── communes_WGS84.shp
├── app.py
├── generate_dem.py
└── requirements.txt
```

---

## Installation et lancement

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
python generate_dem.py       # génère mnt_maroc.tif
streamlit run app.py
```

---

## Sources des données

- **HCP Maroc** : shapefiles administratifs (Régions, Provinces, Communes)
- **Terrestris WMS** : MNT SRTM30 (`https://ows.terrestris.de/osm/service`)
- **Open-Meteo API** : prévisions météo (`https://open-meteo.com`)
- **OpenStreetMap** : fond cartographique

---

## Région étudiée

**Eddakhla-Oued Eddahab** — extrême sud du Maroc, zone saharienne  
2 provinces : Oued-Ed-Dahab, Aousserd  
13 communes : Dakhla, Bir Anzarane, Gleibat El Foula, Mijik, Oum Dreyga, El Argoub, Imlili, Lagouira, Aghouinite, Aousserd, Tichla, Zoug, Bir Gandouz

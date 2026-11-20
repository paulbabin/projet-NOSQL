import math
import os
import subprocess
import sys
import folium
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pymongo import MongoClient
import requests
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="SAÉ Olist - NoSQL & Dashboard", layout="wide")
st.title("📊 Migration NoSQL & Tableau de Bord Décisionnel — Olist")


# ==============================================================================
# FONCTIONS UTILITAIRES & CACHE
# ==============================================================================
@st.cache_data
def load_excel_sheets(path):
  if not os.path.exists(path):
    return None
  return pd.read_excel(path, sheet_name=None)


@st.cache_data
def get_brazil_geojson():
  url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
  return requests.get(url, timeout=15).json()


def haversine_km(lat1, lon1, lat2, lon2):
  """Calcule la distance à vol d'oiseau (en km) entre vendeur et client."""
  if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
    return np.nan
  r = 6371.0
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)
  a = (
      math.sin(dphi / 2) ** 2
      + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  )
  return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@st.cache_data
def load_mongo_operational_data():
  """Charge les données nécessaires aux graphiques complémentaires et cartes MongoDB."""
  client = MongoClient("mongodb://127.0.0.1:27017/")
  db = client["olist"]

  # 1. Référentiels
  sellers = pd.DataFrame(list(db.sellers.find({}, {"_id": 0})))
  customers = pd.DataFrame(list(db.customers.find({}, {"_id": 0})))
  products = pd.DataFrame(
      list(
          db.products.find(
              {},
              {
                  "_id": 0,
                  "product_id": 1,
                  "product_category_name": 1,
                  "product_category_name_english": 1,
              },
          )
      )
  )

  # Coordonnées géographiques par préfixe postal (si collection geolocation présente)
  if "geolocation" in db.list_collection_names():
    geo = pd.DataFrame(list(db.geolocation.find({}, {"_id": 0})))
    # Harmonisation des noms de colonnes lat/lng selon ta migration
    lat_col = (
        "geolocation_lat"
        if "geolocation_lat" in geo.columns
        else ("lat_moyenne" if "lat_moyenne" in geo.columns else None)
    )
    lng_col = (
        "geolocation_lng"
        if "geolocation_lng" in geo.columns
        else ("lng_moyenne" if "lng_moyenne" in geo.columns else None)
    )
    if (
        "geolocation_zip_code_prefix" in geo.columns
        and lat_col
        and lng_col
    ):
      geo_zip = (
          geo.groupby("geolocation_zip_code_prefix", as_index=False)
          .agg(lat=(lat_col, "mean"), lng=(lng_col, "mean"))
      )
    else:
      geo_zip = pd.DataFrame(
          columns=["geolocation_zip_code_prefix", "lat", "lng"]
      )
  else:
    geo_zip = pd.DataFrame(
        columns=["geolocation_zip_code_prefix", "lat", "lng"]
    )

  # 2. Extraction aplatie des commandes via pipeline MongoDB
  pipeline = [
      {
          "$project": {
              "_id": 0,
              "order_id": 1,
              "customer_id": 1,
              "order_status": 1,
              "order_purchase_timestamp": 1,
              "order_delivered_carrier_date": 1,
              "order_delivered_customer_date": 1,
              "order_estimated_delivery_date": 1,
              "items": 1,
              "note_moyenne_cmd": {"$avg": "$reviews.review_score"},
          }
      },
      {"$unwind": "$items"},
      {
          "$project": {
              "order_id": 1,
              "customer_id": 1,
              "order_status": 1,
              "order_purchase_timestamp": 1,
              "order_delivered_carrier_date": 1,
              "order_delivered_customer_date": 1,
              "order_estimated_delivery_date": 1,
              "note_moyenne_cmd": 1,
              "seller_id": "$items.seller_id",
              "product_id": "$items.product_id",
              "ca_item": {"$add": ["$items.price", "$items.freight_value"]},
          }
      },
  ]
  orders_items = pd.DataFrame(list(db.orders.aggregate(pipeline)))
  client.close()

  # Conversions dates et délais
  for col in [
      "order_purchase_timestamp",
      "order_delivered_carrier_date",
      "order_delivered_customer_date",
      "order_estimated_delivery_date",
  ]:
    orders_items[col] = pd.to_datetime(orders_items[col], errors="coerce")

  orders_items["delai_livraison_j"] = (
      orders_items["order_delivered_customer_date"]
      - orders_items["order_purchase_timestamp"]
  ).dt.total_seconds() / 86400.0
  orders_items["delai_traitement_j"] = (
      orders_items["order_delivered_carrier_date"]
      - orders_items["order_purchase_timestamp"]
  ).dt.total_seconds() / 86400.0
  orders_items["en_retard"] = (
      orders_items["order_delivered_customer_date"]
      > orders_items["order_estimated_delivery_date"]
  ).astype(float)
  orders_items.loc[
      orders_items["order_delivered_customer_date"].isna(), "en_retard"
  ] = np.nan

  # Jointures avec produits, clients, vendeurs et coordonnées GPS
  products["categorie"] = (
      products["product_category_name_english"]
      .fillna(products["product_category_name"])
      .fillna("Inconnue")
  )
  orders_items = orders_items.merge(
      products[["product_id", "categorie"]], on="product_id", how="left"
  )

  customers_geo = customers.merge(
      geo_zip,
      left_on="customer_zip_code_prefix",
      right_on="geolocation_zip_code_prefix",
      how="left",
  ).rename(columns={"lat": "cust_lat", "lng": "cust_lng"})
  orders_items = orders_items.merge(
      customers_geo[
          ["customer_id", "customer_state", "customer_city", "cust_lat", "cust_lng"]
      ],
      on="customer_id",
      how="left",
  )

  sellers_geo = sellers.merge(
      geo_zip,
      left_on="seller_zip_code_prefix",
      right_on="geolocation_zip_code_prefix",
      how="left",
  ).rename(columns={"lat": "seller_lat", "lng": "seller_lng"})
  orders_items = orders_items.merge(
      sellers_geo[
          ["seller_id", "seller_state", "seller_city", "seller_lat", "seller_lng"]
      ],
      on="seller_id",
      how="left",
  )

  # Calcul de la distance vendeur-client
  orders_items["distance_km"] = orders_items.apply(
      lambda r: haversine_km(
          r["seller_lat"], r["seller_lng"], r["cust_lat"], r["cust_lng"]
      ),
      axis=1,
  )

  return orders_items, sellers_geo


# ==============================================================================
# CRÉATION DES 3 ONGLETS
# ==============================================================================
tab1, tab2, tab3 = st.tabs([
    "⚙️ 1. Exécution & Comparaison SQL / MongoDB",
    "📈 2. Graphiques Décisionnels",
    "🗺️ 3. Cartographie Folium",
])

# ==============================================================================
# ONGLET 1 : PIPELINE D'EXÉCUTION ET COMPARAISON
# ==============================================================================
with tab1:
  st.header("Exécution du pipeline et vérification de migration")
  st.write(
      "Clique sur le bouton ci-dessous pour exécuter séquentiellement "
      "`partie1.py`, `partie2.py`, `partie3.py` et `comparaison.py`."
  )

  if "logs_comparaison" not in st.session_state:
    st.session_state["logs_comparaison"] = None

  if st.button("🚀 Lancer tout le pipeline (Parties 1, 2, 3 + Comparaison)"):
    scripts = [
        "partie1_req_SQL.py",
        "partie2.py",
        "partie3_req_mongodb.py",
        "comparaison.py",
    ]
    succes_global = True

    with st.spinner(
        "Exécution en cours (SQLite → Migration MongoDB → Requêtes MongoDB →"
        " Comparaison)... Merci de patienter."
    ):
      for script in scripts:
        if not os.path.exists(script):
          st.error(f"Fichier introuvable : `{script}`")
          succes_global = False
          break

        res = subprocess.run(
            [sys.executable, script], capture_output=True, text=True
        )
        if res.returncode != 0:
          st.error(f"❌ Erreur lors de l'exécution de `{script}` :")
          st.code(res.stderr)
          succes_global = False
          break
        elif script == "comparaison.py":
          st.session_state["logs_comparaison"] = res.stdout

    if succes_global:
      st.success("✅ Pipeline terminé avec succès !")
      st.cache_data.clear()  # Rafraîchit les caches avec les nouveaux Excel/Mongo

  if st.session_state["logs_comparaison"]:
    st.subheader("📋 Résultat du script `comparaison.py`")
    st.code(st.session_state["logs_comparaison"])

  st.divider()
  st.subheader("👀 Aperçu visuel côte à côte des fichiers Excel générés")
  sql_sheets = load_excel_sheets("resultats_sql.xlsx")
  mongo_sheets = load_excel_sheets("resultats_mongodb.xlsx")

  if sql_sheets and mongo_sheets:
    feuille = st.selectbox(
        "Sélectionne une requête (feuille Excel) à comparer :",
        list(sql_sheets.keys()),
    )
    col1, col2 = st.columns(2)
    with col1:
      st.markdown(f"**SQLite (`resultats_sql.xlsx` — feuille `{feuille}`)**")
      st.dataframe(sql_sheets[feuille].head(15), use_container_width=True)
    with col2:
      st.markdown(
          f"**MongoDB (`resultats_mongodb.xlsx` — feuille `{feuille}`)**"
      )
      if feuille in mongo_sheets:
        st.dataframe(mongo_sheets[feuille].head(15), use_container_width=True)
      else:
        st.warning(f"La feuille `{feuille}` est absente du fichier MongoDB.")
  else:
    st.info(
        "Les fichiers `resultats_sql.xlsx` et `resultats_mongodb.xlsx` ne sont"
        " pas encore générés. Lance le pipeline ci-dessus."
    )
# ==============================================================================
# ONGLET 2 : GRAPHIQUES PANDAS / MATPLOTLIB (À PARTIR DES EXCEL)
# ==============================================================================
with tab2:
  st.header("Indicateurs clés pour les décideurs Olist")
  sheets = load_excel_sheets("resultats_mongodb.xlsx") or load_excel_sheets(
      "resultats_sql.xlsx"
  )

  if not sheets:
    st.warning(
        "⚠️ Génère d'abord les fichiers Excel dans l'onglet 1 pour afficher les"
        " graphiques."
    )
  else:
    col_g1, col_g2 = st.columns(2)

    # 1. Histogramme des délais de livraison (requête d)
    with col_g1:
      st.subheader("1. Délais moyens de livraison par État (Requête d)")
      df_d = sheets["d"]
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.hist(
          df_d["delai_moyen_jours"],
          bins=10,
          color="#2b5c8f",
          edgecolor="white",
      )
      ax.set_xlabel("Délai moyen de livraison (jours)")
      ax.set_ylabel("Nombre d'États")
      ax.set_title("Distribution des délais moyens par État")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Identifier les disparités régionales de"
          " transport afin de renforcer les partenariats logistiques dans les"
          " États les plus lents."
      )

    # 2. Courbe de tendance du chiffre d'affaires mensuel (requête a)
    with col_g2:
      st.subheader("2. Évolution mensuelle du chiffre d'affaires (Requête a)")
      df_a = sheets["a"]
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.plot(
          df_a["mois"],
          df_a["chiffre_affaires"],
          marker="o",
          color="#1f77b4",
          linewidth=2,
      )
      ax.set_xlabel("Mois")
      ax.set_ylabel("Chiffre d'affaires (R$)")
      ax.set_title("Tendance du CA mensuel (commandes livrées)")
      plt.xticks(rotation=45, ha="right")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Piloter la croissance globale de la"
          " plateforme et anticiper les pics saisonniers (ex. Black Friday)"
          " pour dimensionner les infrastructures."
      )

    st.divider()
    col_g3, col_g4 = st.columns(2)

    # 3. Camembert de la répartition des moyens de paiement (requête j)
    with col_g3:
      st.subheader("3. Répartition des moyens de paiement (Requête j)")
      df_j = sheets["j"]
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.pie(
          df_j["pct_valeur"],
          labels=df_j["moyen_paiement"],
          autopct="%1.1f%%",
          startangle=140,
      )
      ax.set_title("Part de la valeur totale encaissée par moyen de paiement")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Adapter les facilités de paiement et"
          " négocier les commissions bancaires selon le poids dominant de la"
          " carte de crédit."
      )

    # 4. Note moyenne selon le retard (requête i1)
    with col_g4:
      st.subheader("4. Note moyenne selon la tranche de retard (Requête i1)")
      df_i1 = sheets["i1"]
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.bar(
          df_i1["tranche_retard"],
          df_i1["note_moyenne"],
          color=["#2ca02c", "#ffbb78", "#ff7f0e", "#d62728"],
      )
      ax.set_ylim(0, 5.5)
      ax.set_ylabel("Note moyenne (/5)")
      ax.set_title("Impact du retard de livraison sur la satisfaction client")
      plt.xticks(rotation=20, ha="right")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Quantifier la chute brutale de satisfaction"
          " dès le 1er jour de retard pour prioriser les alertes proactives"
          " auprès des clients."
      )

    st.divider()
    col_g5, col_g6 = st.columns(2)

    # 5. Top catégories (requête c)
    with col_g5:
      st.subheader("5. Top 10 des catégories par chiffre d'affaires (Requête c)")
      df_c = sheets["c"].sort_values("chiffre_affaires", ascending=True)
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.barh(df_c["categorie"], df_c["chiffre_affaires"], color="#4c72b0")
      ax.set_xlabel("Chiffre d'affaires (R$)")
      ax.set_title("Top 10 catégories anglaises")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Concentrer les budgets marketing et"
          " l'acquisition de nouveaux vendeurs sur les catégories locomotives"
          " de revenus."
      )

    # 6. Taux de clients récurrents par État (requête l)
    with col_g6:
      st.subheader("6. Taux de clients récurrents par État (Requête l)")
      df_l = sheets["l"].head(15)
      fig, ax = plt.subplots(figsize=(6, 4))
      ax.bar(df_l["state"], df_l["taux_recurence_pct"], color="#55a868")
      ax.set_xlabel("État client")
      ax.set_ylabel("Taux de récurrence (%)")
      ax.set_title("Top 15 États par fidélité client")
      st.pyplot(fig)
      st.caption(
          "**Décision éclairée :** Orienter les campagnes de fidélisation et de"
          " relance CRM dans les États où le rachat reste faible."
      )


# ==============================================================================
# ONGLET 3 : CARTOGRAPHIE FOLIUM
# ==============================================================================
with tab3:
  st.header("Cartographie interactive du réseau Olist")
  sheets = load_excel_sheets("resultats_mongodb.xlsx") or load_excel_sheets(
      "resultats_sql.xlsx"
  )

  try:
    df_ops, sellers_geo = load_mongo_operational_data()
    mongo_ok = True
  except Exception as e:
    st.error(f"Impossible de charger les données MongoDB pour la carte : {e}")
    mongo_ok = False

  # --------------------------------------------------------------------------
  # 3.1 CARTE CHOROPLÈTHE PAR ÉTAT BRÉSILIEN (À PARTIR DES REQUÊTES EXCEL)
  # --------------------------------------------------------------------------
  st.subheader("1. Carte choroplèthe par État brésilien")
  if sheets:
    # Agrégation du CA par État et de la note moyenne par État à partir des feuilles Excel
    ca_etat = (
        df_ops.groupby("customer_state", as_index=False)["ca_item"]
        .sum()
        .rename(columns={"customer_state": "state", "ca_item": "CA_total"})
        if mongo_ok
        else pd.DataFrame(columns=["state", "CA_total"])
    )
    note_etat = (
        df_ops.groupby("customer_state", as_index=False)["note_moyenne_cmd"]
        .mean()
        .rename(
            columns={"customer_state": "state", "note_moyenne_cmd": "note_moyenne"}
        )
        if mongo_ok
        else pd.DataFrame(columns=["state", "note_moyenne"])
    )

    df_d = sheets["d"].rename(columns={"customer_state": "state"})
    df_choro = (
        df_d.merge(ca_etat, on="state", how="outer")
        .merge(note_etat, on="state", how="outer")
    )

    indicateurs_map = {
        "Délai moyen de livraison (jours)": "delai_moyen_jours",
        "Taux de retard (%)": "taux_retard_pourcent",
        "Chiffre d'affaires (R$)": "CA_total",
        "Note moyenne (/5)": "note_moyenne",
    }
    choix_ind = st.selectbox(
        "Choisir l'indicateur à afficher sur la carte :",
        list(indicateurs_map.keys()),
    )
    col_ind = indicateurs_map[choix_ind]


    geojson_br = get_brazil_geojson()
    m_choro = folium.Map(
        location=[-14.2350, -51.9253],
        zoom_start=4,
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="© OpenStreetMap contributors",
    )

    folium.Choropleth(
        geo_data=geojson_br,
        name="Choroplèthe",
        data=df_choro.dropna(subset=["state", col_ind]),
        columns=["state", col_ind],
        key_on="feature.properties.sigla",  # Propriété contenant SP, RJ, etc.
        fill_color="YlOrRd" if "Note" not in choix_ind else "YlGn",
        fill_opacity=0.75,
        line_opacity=0.3,
        legend_name=choix_ind,
    ).add_to(m_choro)

    st_folium(m_choro, width=1100, height=450, key="map_choro")

  st.divider()

  # --------------------------------------------------------------------------
  # 3.2 CARTE DES VENDEURS AVEC MARQUEURS ET FILTRES OBLIGATOIRES
  # --------------------------------------------------------------------------
  if mongo_ok:
    st.subheader("2. Performance géographique des vendeurs (Filtres obligatoires)")

    f1, f2, f3, f4 = st.columns(4)
    etats_dispo = ["Tous"] + sorted(
        df_ops["seller_state"].dropna().unique().tolist()
    )
    filtre_etat = f1.selectbox("État du vendeur", etats_dispo)

    cats_dispo = ["Toutes"] + sorted(
        df_ops["categorie"].dropna().unique().tolist()
    )
    filtre_cat = f2.selectbox("Catégorie de produit", cats_dispo)

    min_date = df_ops["order_purchase_timestamp"].min().date()
    max_date = df_ops["order_purchase_timestamp"].max().date()
    filtre_periode = f3.date_input(
        "Période d'achat", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )

    min_cmd = f4.slider("Nombre minimal de commandes", 1, 100, 10)

    critere_couleur = st.radio(
        "Colorer les vendeurs selon :",
        ["Note moyenne", "Taux de retard"],
        horizontal=True,
    )

    # Application des filtres
    df_filtre = df_ops.copy()
    if filtre_etat != "Tous":
      df_filtre = df_filtre[df_filtre["seller_state"] == filtre_etat]
    if filtre_cat != "Toutes":
      df_filtre = df_filtre[df_filtre["categorie"] == filtre_cat]
    if isinstance(filtre_periode, tuple) and len(filtre_periode) == 2:
      df_filtre = df_filtre[
          (df_filtre["order_purchase_timestamp"].dt.date >= filtre_periode[0])
          & (df_filtre["order_purchase_timestamp"].dt.date <= filtre_periode[1])
      ]

    # Agrégation par vendeur
    vendeurs_stats = (
        df_filtre.groupby(
            ["seller_id", "seller_city", "seller_state", "seller_lat", "seller_lng"],
            as_index=False,
        )
        .agg(
            nb_commandes=("order_id", "nunique"),
            chiffre_affaires=("ca_item", "sum"),
            note_moyenne=("note_moyenne_cmd", "mean"),
            delai_traitement=("delai_traitement_j", "mean"),
            taux_retard=("en_retard", "mean"),
        )
    )
    vendeurs_stats["taux_retard_pct"] = vendeurs_stats["taux_retard"] * 100
    vendeurs_stats = vendeurs_stats[
        vendeurs_stats["nb_commandes"] >= min_cmd
    ].dropna(subset=["seller_lat", "seller_lng"])

    m_sellers = folium.Map(
    location=[-15.7801, -47.9292],
    zoom_start=4,
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr="© OpenStreetMap contributors",
    )

    for _, v in vendeurs_stats.head(400).iterrows():
      if critere_couleur == "Note moyenne":
        color = (
            "green"
            if v["note_moyenne"] >= 4.0
            else ("orange" if v["note_moyenne"] >= 3.0 else "red")
        )
      else:
        color = (
            "green"
            if v["taux_retard_pct"] <= 5.0
            else ("orange" if v["taux_retard_pct"] <= 15.0 else "red")
        )

      popup_html = f"""
      <b>Vendeur :</b> {v['seller_id'][:8]}...<br>
      <b>Ville :</b> {v['seller_city']} ({v['seller_state']})<br>
      <b>Commandes :</b> {v['nb_commandes']}<br>
      <b>CA :</b> {v['chiffre_affaires']:.2f} R$<br>
      <b>Note moyenne :</b> {v['note_moyenne']:.2f}/5<br>
      <b>Délai moyen traitement :</b> {v['delai_traitement']:.2f} j
      """
      folium.CircleMarker(
          location=[v["seller_lat"], v["seller_lng"]],
          radius=6,
          color=color,
          fill=True,
          fill_opacity=0.8,
          popup=folium.Popup(popup_html, max_width=260),
      ).add_to(m_sellers)

    st_folium(m_sellers, width=1100, height=450, key="map_sellers")

    st.divider()

    # ------------------------------------------------------------------------
    # 3.3 SÉLECTION D'UN VENDEUR : COMMANDES, ZONES DE LIVRAISON & DISTANCE
    # ------------------------------------------------------------------------
    st.subheader("3. Zoom détaillé sur un vendeur et ses zones de livraison")

    if vendeurs_stats.empty:
      st.info("Aucun vendeur ne correspond aux filtres sélectionnés.")
    else:
      liste_vendeurs = vendeurs_stats.sort_values(
          "chiffre_affaires", ascending=False
      )["seller_id"].tolist()
      vendeur_choisi = st.selectbox(
          "Sélectionner un vendeur (triés par CA décroissant) :",
          liste_vendeurs,
      )

      cmd_vendeur = df_filtre[df_filtre["seller_id"] == vendeur_choisi]
      info_v = vendeurs_stats[
          vendeurs_stats["seller_id"] == vendeur_choisi
      ].iloc[0]

      # Indicateurs pertinents (distance moyenne, délai, retard, note)
      k1, k2, k3, k4 = st.columns(4)
      k1.metric(
          "Distance moyenne vendeur-client",
          f"{cmd_vendeur['distance_km'].mean():.0f} km",
      )
      k2.metric(
          "Délai moyen de livraison",
          f"{cmd_vendeur['delai_livraison_j'].mean():.1f} jours",
      )
      k3.metric(
          "Taux de retard",
          f"{(cmd_vendeur['en_retard'].mean() * 100):.1f} %",
      )
      k4.metric(
          "Note moyenne",
          f"{cmd_vendeur['note_moyenne_cmd'].mean():.2f} / 5",
      )

      col_v1, col_v2 = st.columns([1.2, 1])

      with col_v1:
        st.markdown("**Carte des zones de livraison de ce vendeur**")
        m_zone = folium.Map(
            location=[info_v["seller_lat"], info_v["seller_lng"]],
            zoom_start=4,
            tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attr="© OpenStreetMap contributors",
        )
        # Position du vendeur
        folium.Marker(
            location=[info_v["seller_lat"], info_v["seller_lng"]],
            popup=f"Entrepôt Vendeur ({info_v['seller_city']})",
            icon=folium.Icon(color="blue", icon="home"),
        ).add_to(m_zone)

        # Points de livraison clients
        clients_livres = cmd_vendeur.dropna(
            subset=["cust_lat", "cust_lng"]
        ).head(200)
        for _, c in clients_livres.iterrows():
          folium.CircleMarker(
              location=[c["cust_lat"], c["cust_lng"]],
              radius=4,
              color="purple",
              fill=True,
              fill_opacity=0.6,
              popup=(
                  f"Client : {c['customer_city']} ({c['customer_state']}) —"
                  f" Distance : {c['distance_km']:.0f} km"
              ),
          ).add_to(m_zone)

        st_folium(m_zone, width=600, height=400, key="map_zone_vendeur")

      with col_v2:
        st.markdown("**Tableau de ses commandes**")
        cols_affichage = [
            "order_id",
            "order_purchase_timestamp",
            "customer_state",
            "categorie",
            "ca_item",
            "distance_km",
            "delai_livraison_j",
            "note_moyenne_cmd",
        ]
        st.dataframe(
            cmd_vendeur[cols_affichage].head(100),
            use_container_width=True,
            height=400,
        )
# -*- coding: utf-8 -*-
# SAE Migration de donnees vers un environnement NoSQL
# Partie 1 : Requetes SQL sur la base relationnelle SQLite

import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "olist.sqlite"

# Creation de la connexion
conn = sqlite3.connect(DB_PATH)


#%% Requete a - Directeur general
# Question : Evolution mensuelle du chiffre d'affaires (price + freight_value des articles) et du nombre de commandes livrees
# Commentaire : Le CA et le nombre de commandes livrees augmentent fortement en 2017 avec un pic en novembre (1,15M R$ pour le Black Friday) avant de se stabiliser autour de 1M R$ par mois en 2018.

req_a = """
SELECT 
    strftime('%Y-%m', o.order_purchase_timestamp) AS mois,
    ROUND(SUM(oi.price + oi.freight_value), 2) AS chiffre_affaires,
    COUNT(DISTINCT o.order_id) AS nb_commandes_livrees
FROM orders o
INNER JOIN order_items oi USING (order_id)
WHERE o.order_status = 'delivered'
GROUP BY mois
ORDER BY mois ASC;
"""
df_a = pd.read_sql_query(req_a, conn)
#df_a.to_csv("requete_a.csv", index=False)
print("\n--- Requete a ---")
print(df_a)
print("Commentaire a : Le CA et le nombre de commandes livrees augmentent fortement en 2017 avec un pic en novembre (1,15M R$ pour le Black Friday) avant de se stabiliser autour de 1M R$ par mois en 2018.")

req_b = """
SELECT 
    c.customer_state,
    AVG(op_sum.total_payment) AS panier_moyen
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN (
    SELECT order_id, SUM(payment_value) AS total_payment
    FROM order_payments
    GROUP BY order_id
) op_sum ON o.order_id = op_sum.order_id
GROUP BY c.customer_state
ORDER BY panier_moyen DESC;
"""
df_b = pd.read_sql_query(req_b, conn)
#df_b.to_csv("req_b.csv", index=False)
print("\n--- Panier moyen ---")
print(df_b)

#%% Requete c - Directeur commercial
# Question : Top 10 des categories de produits (nom en anglais) par chiffre d'affaires, avec leur part dans le chiffre d'affaires total
# Commentaire : Les ventes sont concentrees sur quelques categories phares puisque le top 5 (health_beauty, watches_gifts, bed_bath_table, sports_leisure, computers_accessories) represente pres de 40 % du CA total.

req_c = """
SELECT 
    ct.product_category_name_english AS categorie,
    ROUND(SUM(oi.price + oi.freight_value), 2) AS chiffre_affaires,
    ROUND(SUM(oi.price + oi.freight_value) * 100.0 / (SELECT SUM(price + freight_value) FROM order_items), 2) AS part_ca_pct
FROM order_items oi
INNER JOIN products p USING (product_id)
INNER JOIN category_translation ct USING (product_category_name)
GROUP BY categorie
ORDER BY chiffre_affaires DESC
LIMIT 10;
"""
df_c = pd.read_sql_query(req_c, conn)
#df_c.to_csv("requete_c.csv", index=False)
print("\n--- Requete c ---")
print(df_c)
print("Commentaire c : Les ventes sont concentrees sur quelques categories phares puisque le top 5 represente pres de 40 % du CA total.")

req_d = """
SELECT 
    c.customer_state,
    ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp)), 2) AS delai_moyen_jours,
    ROUND(AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1.0 ELSE 0.0 END) * 100, 2) AS taux_retard_pourcent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY c.customer_state
ORDER BY delai_moyen_jours DESC;
"""
df_d = pd.read_sql_query(req_d, conn)
#df_d.to_csv("req_d.csv", index=False)
print("\n--- Délai moyen et taux de retard ---")
print(df_d)

#%% Requete e - Responsable marketplace
# Question : Top 10 des vendeurs par chiffre d'affaires, avec nombre de commandes et note moyenne
# Commentaire : Les 10 plus gros vendeurs depassent chacun 160 000 R$ de CA avec de bonnes notes (> 4/5), sauf le 2e vendeur (7c67e...) qui a une note moyenne faible de 3,35 malgre 241 374 R$ de ventes.

req_e = """
SELECT 
    oi.seller_id,
    ROUND(SUM(oi.price + oi.freight_value), 2) AS chiffre_affaires,
    COUNT(DISTINCT oi.order_id) AS nb_commandes,
    ROUND(AVG(r.review_score), 2) AS note_moyenne
FROM order_items oi
LEFT JOIN order_reviews r USING (order_id)
GROUP BY oi.seller_id
ORDER BY chiffre_affaires DESC
LIMIT 10;
"""
df_e = pd.read_sql_query(req_e, conn)
#df_e.to_csv("requete_e.csv", index=False)
print("\n--- Requete e ---")
print(df_e)
print("Commentaire e : Les 10 plus gros vendeurs depassent chacun 160 000 R$ de CA avec de bonnes notes (> 4/5), sauf le 2e vendeur (7c67e...) qui a une note moyenne faible de 3,35 malgre 241 374 R$ de ventes.")

req_f = """SELECT 
    s.seller_id,
    s.seller_city,
    s.seller_state,
    COUNT(oi.order_item_id) AS nb_articles,
    (
        SELECT AVG(r.review_score) 
        FROM order_reviews r 
        JOIN order_items oi2 ON r.order_id = oi2.order_id 
        WHERE oi2.seller_id = s.seller_id
    ) AS note_moyenne,
    (SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1.0 ELSE 0.0 END) * 100.0) / COUNT(o.order_id) AS pct_retard
FROM sellers s
JOIN order_items oi ON s.seller_id = oi.seller_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY s.seller_id, s.seller_city, s.seller_state
HAVING COUNT(oi.order_item_id) >= 30
   AND (
       SELECT AVG(r.review_score) 
       FROM order_reviews r 
       JOIN order_items oi2 ON r.order_id = oi2.order_id 
       WHERE oi2.seller_id = s.seller_id
   ) < 3.5
   AND (SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1.0 ELSE 0.0 END) * 100.0) / COUNT(o.order_id) < 5.0
ORDER BY s.seller_state, s.seller_city;"""

df_f = pd.read_sql_query(req_f, conn)
#df_f.to_csv("req_f.csv", index=False)


#%% Requete g - Directeur logistique
# Question : Taux de livraison a l'heure global (commandes livrees avant la date estimee / commandes livrees), puis par mois d'achat
# Commentaire : Le taux de livraison a l'heure est bon au global (91,9 %), mais chute fortement lors des pics d'activite comme en novembre 2017 (85,7 %) et en fevrier-mars 2018 (78,6 %).

req_g = """
SELECT 
    'Global' AS periode,
    COUNT(*) AS nb_commandes_livrees,
    ROUND(SUM(CASE WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(*), 2) AS taux_livraison_heure_pct
FROM orders
WHERE order_status = 'delivered' 
  AND order_delivered_customer_date IS NOT NULL
UNION ALL
SELECT 
    strftime('%Y-%m', order_purchase_timestamp) AS periode,
    COUNT(*) AS nb_commandes_livrees,
    ROUND(SUM(CASE WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(*), 2) AS taux_livraison_heure_pct
FROM orders
WHERE order_status = 'delivered' 
  AND order_delivered_customer_date IS NOT NULL
GROUP BY periode;
"""
df_g = pd.read_sql_query(req_g, conn)
#df_g.to_csv("requete_g.csv", index=False)
print("\n--- Requete g ---")
print(df_g)
print("Commentaire g : Le taux de livraison a l'heure est bon au global (91,9 %), mais chute fortement lors des pics d'activite comme en novembre 2017 (85,7 %) et en fevrier-mars 2018 (78,6 %).")

req_h = """
SELECT 
    t.state,
    (SELECT COUNT(c.customer_id) FROM customers c WHERE c.customer_state = t.state) AS nb_clients,
    (SELECT COUNT(s.seller_id) FROM sellers s WHERE s.seller_state = t.state) AS nb_vendeurs,
    (SELECT AVG(g.geolocation_lat) FROM geolocation g WHERE g.geolocation_state = t.state) AS lat_moyenne,
    (SELECT AVG(g.geolocation_lng) FROM geolocation g WHERE g.geolocation_state = t.state) AS lng_moyenne,
    CAST((SELECT COUNT(c.customer_id) FROM customers c WHERE c.customer_state = t.state) AS REAL) / 
    NULLIF((SELECT COUNT(s.seller_id) FROM sellers s WHERE s.seller_state = t.state), 0) AS ratio_clients_vendeur

FROM (
    SELECT customer_state AS state FROM customers WHERE customer_state IS NOT NULL
    UNION
    SELECT seller_state AS state FROM sellers WHERE seller_state IS NOT NULL
    UNION
    SELECT geolocation_state AS state FROM geolocation WHERE geolocation_state IS NOT NULL
) t
ORDER BY t.state;
"""
df_h = pd.read_sql_query(req_h, conn)
#df_h.to_csv("req_h.csv", index=False)
print("\n--- Clients et vendeurs par état ---")
print(df_h)


#%% Requete i - Responsable satisfaction
# Question : Note moyenne selon la tranche de retard, puis correlation entre jours de retard et note par Etat
# Commentaire : La note moyenne chute fortement des que le retard depasse 3 jours (de 4,29 a l'heure a 2,32 entre 4 et 7 jours, puis 1,73 au-dela), avec une correlation negative marquee dans presque tous les Etats (jusqu'a -0,47 en CE).

req_i1 = """
SELECT 
    CASE 
        WHEN (julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)) <= 0 THEN '1 - A l heure'
        WHEN (julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)) <= 3 THEN '2 - Retard 1 a 3 jours'
        WHEN (julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)) <= 7 THEN '3 - Retard 4 a 7 jours'
        ELSE '4 - Retard plus de 7 jours'
    END AS tranche_retard,
    COUNT(DISTINCT o.order_id) AS nb_commandes,
    ROUND(AVG(r.review_score), 2) AS note_moyenne
FROM orders o
INNER JOIN order_reviews r USING (order_id)
WHERE o.order_status = 'delivered' 
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY tranche_retard
ORDER BY tranche_retard ASC;
"""
df_i1 = pd.read_sql_query(req_i1, conn)
#df_i1.to_csv("requete_i_tranches.csv", index=False)
print("\n--- Requete i (Tranches de retard) ---")
print(df_i1)

req_i2 = """
SELECT 
    c.customer_state AS etat,
    o.order_id,
    (julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)) AS jours_retard,
    AVG(r.review_score) AS note_moyenne
FROM orders o
INNER JOIN customers c USING (customer_id)
INNER JOIN order_reviews r USING (order_id)
WHERE o.order_status = 'delivered' 
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY o.order_id, c.customer_state;
"""
df_i2_commandes = pd.read_sql_query(req_i2, conn)
df_i2 = df_i2_commandes.groupby("etat")["jours_retard"].corr(df_i2_commandes["note_moyenne"]).reset_index(name="correlation_retard_note")
df_i2["correlation_retard_note"] = df_i2["correlation_retard_note"].round(3)
df_i2 = df_i2.sort_values(by="correlation_retard_note", ascending=True)
#df_i2.to_csv("requete_i_correlation.csv", index=False)
print("\n--- Requete i (Correlation par Etat) ---")
print(df_i2)
print("Commentaire i : La note moyenne chute fortement des que le retard depasse 3 jours (de 4,29 a l'heure a 2,32 entre 4 et 7 jours, puis 1,73 au-dela), avec une correlation negative marquee dans presque tous les Etats.")


req_j = """
SELECT 
    payment_type AS moyen_paiement,
    COUNT(DISTINCT order_id) AS nb_commandes,
    (COUNT(DISTINCT order_id) * 100.0) / (SELECT COUNT(DISTINCT order_id) FROM order_payments) AS pct_commandes,
    SUM(payment_value) AS valeur_totale,
    (SUM(payment_value) * 100.0) / (SELECT SUM(payment_value) FROM order_payments) AS pct_valeur,
    AVG(payment_installments) AS nb_moyen_echeances

FROM order_payments
GROUP BY payment_type
ORDER BY pct_valeur DESC;
"""
df_j = pd.read_sql_query(req_j, conn)
#df_j.to_csv("req_j.csv", index=False)
print("\n--- repartition_moyenne_paiement  ---")
print(df_j)

#%% Requete k - Responsable vendeurs
# Question : Delai moyen de traitement par vendeur (achat -> remise au transporteur) pour les vendeurs ayant au moins 30 commandes : les 10 plus lents
# Commentaire : Les 10 vendeurs reguliers les plus lents mettent entre 11,4 et 18,1 jours rien que pour remettre le colis au transporteur (notamment le gros vendeur 7c67e... avec 980 commandes et 12,15 jours), ce qui penalise directement les delais de livraison.

req_k = """
SELECT 
    oi.seller_id,
    COUNT(DISTINCT o.order_id) AS nb_commandes,
    ROUND(AVG(julianday(o.order_delivered_carrier_date) - julianday(o.order_purchase_timestamp)), 2) AS delai_moyen_traitement_jours
FROM order_items oi
INNER JOIN orders o USING (order_id)
WHERE o.order_delivered_carrier_date IS NOT NULL
GROUP BY oi.seller_id
HAVING nb_commandes >= 30
ORDER BY delai_moyen_traitement_jours DESC
LIMIT 10;
"""
df_k = pd.read_sql_query(req_k, conn)
#df_k.to_csv("requete_k.csv", index=False)
print("\n--- Requete k ---")
print(df_k)
print("Commentaire k : Les 10 vendeurs reguliers les plus lents mettent entre 11,4 et 18,1 jours rien que pour remettre le colis au transporteur, ce qui penalise directement les delais de livraison.")


req_l = """
SELECT 
    c.customer_state AS state,
    COUNT(DISTINCT c.customer_unique_id) AS total_clients,
    SUM(CASE WHEN sub.nb_commandes >= 2 THEN 1 ELSE 0 END) AS nb_clients_recurrents,
    (SUM(CASE WHEN sub.nb_commandes >= 2 THEN 1.0 ELSE 0.0 END) * 100.0) / COUNT(DISTINCT c.customer_unique_id) AS taux_recurence_pct

FROM customers c
JOIN (
    SELECT customer_unique_id, COUNT(order_id) AS nb_commandes
    FROM customers c2
    JOIN orders o ON c2.customer_id = o.customer_id
    GROUP BY customer_unique_id
) sub ON c.customer_unique_id = sub.customer_unique_id

WHERE c.customer_state IS NOT NULL
GROUP BY c.customer_state
ORDER BY taux_recurence_pct DESC;
"""
df_l = pd.read_sql_query(req_l, conn)
#df_l.to_csv("req_l.csv", index=False)
print("\n--- Taux de clients récurrents par état ---")
print(df_l)

#%% Requete m - Directeur logistique
# Question : Requete CASE WHEN : classer chaque commande livree selon la rapidite de livraison (< 8j, 8 a 15j, > 15j), puis donner par Etat le nombre de commandes et la note moyenne de chaque classe
# Commentaire : Les livraisons rapides (< 8 jours) obtiennent de tres bonnes notes (> 4,3/5), mais dans la plupart des Etats hors Sao Paulo les livraisons lentes (> 15 jours) sont majoritaires et tirent la satisfaction vers le bas.

req_m = """
SELECT 
    c.customer_state AS etat,
    CASE 
        WHEN (julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp)) < 8 THEN '1 - Rapide (< 8j)'
        WHEN (julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp)) <= 15 THEN '2 - Normale (8 a 15j)'
        ELSE '3 - Lente (> 15j)'
    END AS rapidite_livraison,
    COUNT(DISTINCT o.order_id) AS nb_commandes,
    ROUND(AVG(r.review_score), 2) AS note_moyenne
FROM orders o
INNER JOIN customers c USING (customer_id)
LEFT JOIN order_reviews r USING (order_id)
WHERE o.order_status = 'delivered' 
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY c.customer_state, rapidite_livraison
ORDER BY c.customer_state ASC, rapidite_livraison ASC;
"""
df_m = pd.read_sql_query(req_m, conn)
#df_m.to_csv("requete_m.csv", index=False)
print("\n--- Requete m ---")
print(df_m)
print("Commentaire m : Les livraisons rapides (< 8 jours) obtiennent de tres bonnes notes (> 4,3/5), mais dans la plupart des Etats hors Sao Paulo les livraisons lentes (> 15 jours) sont majoritaires et tirent la satisfaction vers le bas.")

req_n = """
WITH depenses_clients AS (
    SELECT 
        c.customer_unique_id,
        SUM(p.payment_value) AS total_depense
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN order_payments p ON o.order_id = p.order_id
    GROUP BY c.customer_unique_id
)
SELECT 
    CASE 
        WHEN total_depense >= 500 THEN '1. VIP (> 500 R$)'
        WHEN total_depense >= 200 THEN '2. Standard (200 - 500 R$)'
        ELSE '3. Occasionnel (< 200 R$)'
    END AS segment_client,
    COUNT(customer_unique_id) AS nombre_clients,
    (COUNT(customer_unique_id) * 100.0) / (SELECT COUNT(*) FROM depenses_clients) AS pct_clients,
    SUM(total_depense) AS ca_total_segment,
    (SUM(total_depense) * 100.0) / (SELECT SUM(total_depense) FROM depenses_clients) AS pct_ca

FROM depenses_clients
GROUP BY segment_client
ORDER BY segment_client;
"""
df_n = pd.read_sql_query(req_n, conn)
#df_n.to_csv("req_n.csv", index=False)
print("\n--- Segmentation des clients ---")
print(df_n)

""""""


# 1. Regroupe tes DataFrames existants dans un dictionnaire : {"nom_de_feuille": dataframe}
resultats = {
    "a": df_a,
    "b": df_b,
    "c": df_c,
    "d": df_d,
    "e": df_e,
    "f": df_f,
    "g": df_g,
    "h": df_h,
    "i1": df_i1,
    "i2": df_i2,
    "j": df_j,
    "k": df_k,
    "l": df_l,
    "m": df_m,
    "n": df_n,
}



# Racine du projet 
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

# Crée le dossier output/ s'il n'existe pas encore
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# 2. Écrit toutes les feuilles dans un seul fichier .xlsx
nom_fichier = OUTPUT_DIR / "resultats_sql.xlsx"


with pd.ExcelWriter(nom_fichier, engine="openpyxl") as writer:
  for sheet_name, df in resultats.items():
    # Sécurité : s'assure que le nom de feuille fait max 31 caractères (limite Excel)
    df.to_excel(writer, sheet_name=str(sheet_name)[:31], index=False)

print(f"✅ Fichier {nom_fichier} généré avec {len(resultats)} feuilles.")

# Fermeture de la connexion
conn.close()

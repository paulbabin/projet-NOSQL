import sqlite3
import pandas as pd

# 1. Création de la connexion à la base SQLite
conn = sqlite3.connect("olist.sqlite")

# Écriture de la requête SQL 
panier_moyen = """
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
delai_moyen_taux_retard = """
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

liste_vendeur = """SELECT 
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

clients_vendeurs_par_etat = """
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

repartition_moyenne_paiement = """
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

taux_clients_recurrents = """
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

segmentation = """
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

# 3. Exécution de la requête et récupération dans un DataFrame pandas
df_b = pd.read_sql_query(panier_moyen, conn)
df_d = pd.read_sql_query(delai_moyen_taux_retard, conn)
df_f = pd.read_sql_query(liste_vendeur, conn)
df_h = pd.read_sql_query(clients_vendeurs_par_etat, conn)
df_j = pd.read_sql_query(repartition_moyenne_paiement, conn)
df_l = pd.read_sql_query(taux_clients_recurrents, conn)
df_n = pd.read_sql_query(segmentation  , conn)

# 4. Sauvegarde du résultat dans un fichier CSV (requis par la consigne)
df_b.to_csv("requete_b.csv", index=False)
df_d.to_csv("requete_d.csv", index=False)
df_f.to_csv("requete_f.csv", index=False)
df_h.to_csv("requete_h.csv", index=False)
df_j.to_csv("requete_j.csv", index=False)
df_l.to_csv("requete_l.csv", index=False)
df_n.to_csv("requete_n.csv", index=False)

# 5. Affichage des premiers résultats dans la console
print(df_b.head())
print(df_d.head())
print(df_f.head())
print(df_h.head())
print(df_j.head())
print(df_l.head())
print(df_n.head())

# Fermeture de la connexion
conn.close()
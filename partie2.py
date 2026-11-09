import pandas as pd
import pymongo
import sqlite3

# 1. Connexion à la base SQLite
conn = sqlite3.connect("olist.sqlite")

# 2. Connexion à MongoDB
client = pymongo.MongoClient("mongodb://127.0.0.1:27017/")
db = client["SAE"]  # Crée la base 'SAE' dans MongoDB

print("Début de la migration vers les 4 collections...")

# ==========================================
# COLLECTION 1 : products (avec traduction)
# ==========================================
print("Migration de la collection 'products'...")
products_df = pd.read_sql_query("SELECT * FROM products", conn)
trans_df = pd.read_sql_query("SELECT * FROM category_translation", conn)

# Ajout de la traduction anglaise de la catégorie
products_df = products_df.merge(
    trans_df, on="product_category_name", how="left"
)

db.products.drop()  # Nettoyage si la collection existe déjà
db.products.insert_many(products_df.to_dict(orient="records"))


# ==========================================
# COLLECTION 2 : sellers
# ==========================================
print("Migration de la collection 'sellers'...")
sellers_df = pd.read_sql_query("SELECT * FROM sellers", conn)
db.sellers.drop()
db.sellers.insert_many(sellers_df.to_dict(orient="records"))


# ==========================================
# COLLECTION 3 : customers
# ==========================================
print("Migration de la collection 'customers'...")
customers_df = pd.read_sql_query("SELECT * FROM customers", conn)
db.customers.drop()
db.customers.insert_many(customers_df.to_dict(orient="records"))


# ==========================================
# COLLECTION 4 : orders (Collection riche & imbriquée)
# ==========================================
print(
    "Préparation et imbrication de la collection centrale 'orders' (cela peut"
    " prendre quelques secondes)..."
)

orders_df = pd.read_sql_query("SELECT * FROM orders", conn)
items_df = pd.read_sql_query("SELECT * FROM order_items", conn)
payments_df = pd.read_sql_query("SELECT * FROM order_payments", conn)
reviews_df = pd.read_sql_query("SELECT * FROM order_reviews", conn)

# Groupby pour associer rapidement les sous-éléments par order_id
# On retire la colonne order_id des sous-documents pour éviter la redondance inutile
items_grouped = (
    items_df.drop(columns=["order_id"])
    .groupby(items_df["order_id"])
    .apply(lambda x: x.to_dict(orient="records"))
    .to_dict()
)

payments_grouped = (
    payments_df.drop(columns=["order_id"])
    .groupby(payments_df["order_id"])
    .apply(lambda x: x.to_dict(orient="records"))
    .to_dict()
)

reviews_grouped = (
    reviews_df.drop(columns=["order_id"])
    .groupby(reviews_df["order_id"])
    .apply(lambda x: x.to_dict(orient="records"))
    .to_dict()
)

# Construction de la liste des documents de commandes enrichis
orders_list = []
for _, row in orders_df.iterrows():
  o_id = row["order_id"]
  order_dict = row.to_dict()

  # Injection des tableaux imbriqués (gestion des cas vides avec .get)
  order_dict["items"] = items_grouped.get(o_id, [])
  order_dict["payments"] = payments_grouped.get(o_id, [])
  order_dict["reviews"] = reviews_grouped.get(o_id, [])

  orders_list.append(order_dict)

# Insertion dans MongoDB
db.orders.drop()
db.orders.insert_many(orders_list)

# Fermeture de la connexion SQLite
conn.close()

print(" Migration terminée avec succès !")
print(f"Nombre de produits insérés : {db.products.count_documents({})}")
print(f"Nombre de vendeurs insérés : {db.sellers.count_documents({})}")
print(f"Nombre de clients insérés : {db.customers.count_documents({})}")
print(f"Nombre de commandes insérées : {db.orders.count_documents({})}")
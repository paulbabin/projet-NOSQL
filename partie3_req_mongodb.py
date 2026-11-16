import pandas as pd
from pymongo import MongoClient

# Connexion à MongoDB
client = MongoClient("mongodb://127.0.0.1:27017/")
db = client["SAE"]

# Pipeline d'agrégation MongoDB (liste de blocs séparés)
pipeline = [
    # Étape 1 : Filtrer les commandes livrées (attention aux minuscules "delivered" dans Olist)
    {"$match": {"order_status": "delivered"}},
    
    # Étape 2 : Dérouler le tableau "items" pour accéder aux prix de chaque article
    {"$unwind": "$items"},
    
    # Étape 3 : Grouper pour calculer le CA total (price + freight_value) et compter les commandes uniques
    {
        "$group": {
            "_id": None,
            "total_revenue": {
                "$sum": {
                    "$add": ["$items.price", "$items.freight_value"]
                }
            },
            # On utilise un set pour compter les commandes uniques (car un order_id peut avoir plusieurs items)
            "unique_orders": {
                "$addToSet": "$order_id"
            }
        }
    },
    
    # Étape 4 : Transformer le set de commandes en un simple compteur numérique
    {
        "$project": {
            "_id": 0,
            "total_revenue": 1,
            "total_orders": {"$size": "$unique_orders"}
        }
    },
    
    # Étape 5 : Trier 
    {"$sort": {"total_revenue": -1}},
    
    # Étape 6 : Limiter le résultat
    {"$limit": 1}
]

# Exécution de la requête d'agrégation
result = db.orders.aggregate(pipeline)
revenue_and_orders = pd.DataFrame(result)

print(revenue_and_orders)

# Export en Excel
revenue_and_orders.to_excel("output.xlsx", index=False)


#########requete B
# 2. Pipeline d'agrégation simplifié
pipeline = [
    # Étape A : Joindre la collection "customers" pour récupérer le state via customer_id
    {
        "$lookup": {
            "from": "customers",
            "localField": "customer_id",
            "foreignField": "customer_id",
            "as": "client_info"
        }
    },
    # Étape B : Transformer le tableau client_info en objet unique
    {"$unwind": "$client_info"},
    
    # Étape C : Aplatir le tableau des paiements pour sommer la valeur payée par commande
    {"$unwind": {"path": "$payments", "preserveNullAndEmptyArrays": True}},
    
    # Étape D : Grouper par commande (pour sommer les paiements d'une même commande)
    {
        "$group": {
            "_id": {
                "order_id": "$order_id",
                "state": "$client_info.customer_state"
            },
            "order_total": {"$sum": "$payments.payment_value"}
        }
    },
    
    # Étape E : Grouper par État (state) pour calculer la moyenne du panier par État
    {
        "$group": {
            "_id": "$_id.state",
            "panier_moyen": {"$avg": "$order_total"},
            "nombre_commandes": {"$sum": 1}
        }
    },
    
    # Étape F : Mettre en forme propre pour Pandas
    {
        "$project": {
            "_id": 0,
            "customer_state": "$_id",
            "panier_moyen": 1,
            "nombre_commandes": 1
        }
    },
    
    # Étape G : Trier par panier moyen décroissant
    {"$sort": {"panier_moyen": -1}}
]

# 3. Exécution et export
result = list(db.orders.aggregate(pipeline))
df = pd.DataFrame(result)

print(df.head(10))
df.to_excel("panier_moyen_par_etat.xlsx", index=False)
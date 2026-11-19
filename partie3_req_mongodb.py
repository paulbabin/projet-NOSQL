import pandas as pd
from pymongo import MongoClient


def run_query_a(db):
    """Évolution mensuelle du chiffre d'affaires et des commandes livrées."""
    pipeline = [
        {"$match": {"order_status": "delivered"}},
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": {"$substrBytes": ["$order_purchase_timestamp", 0, 7]},
                "chiffre_affaires": {
                    "$sum": {
                        "$add": ["$items.price", "$items.freight_value"]
                    }
                },
                "commandes": {"$addToSet": "$order_id"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "mois": "$_id",
                "chiffre_affaires": 1,
                "nb_commandes_livrees": {"$size": "$commandes"},
            }
        },
        {"$sort": {"mois": 1}},
    ]

    rows = list(db.orders.aggregate(pipeline))
    result = pd.DataFrame(rows)
    print("\n--- Requête A : évolution mensuelle ---")
    print(result)
    #result.to_excel("output.xlsx", index=False)
    return result


def run_query_b(db):
    """Panier moyen par état."""
    # L'index accélère le $lookup et sa création est idempotente.
    db.customers.create_index("customer_id")

    pipeline = [
        # Le JOIN SQL exclut les commandes sans paiement.
        {"$match": {"payments.0": {"$exists": True}}},
        {"$project": {"customer_id": 1, "payments": 1}},
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "client",
            }
        },
        {"$unwind": "$client"},
        {"$addFields": {"total_commande": {"$sum": "$payments.payment_value"}}},
        {
            "$group": {
                "_id": "$client.customer_state",
                "panier_moyen": {"$avg": "$total_commande"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "customer_state": "$_id",
                "panier_moyen": 1,
            }
        },
        {"$sort": {"panier_moyen": -1}},
    ]

    rows = list(db.orders.aggregate(pipeline))
    result = pd.DataFrame(rows)
    print("\n--- Requête B : panier moyen par état ---")
    print(result.head(10))
    #result.to_excel("panier_moyen_par_etat.xlsx", index=False)
    return result


def run_query_c(db):
    """Top 10 des catégories anglaises par chiffre d'affaires et part du total."""
    # L'index accélère le $lookup des produits dans les articles de commande.
    db.products.create_index("product_id")

    # Le dénominateur SQL inclut aussi les articles sans catégorie traduite.
    total_revenue_pipeline = [
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": None,
                "total": {
                    "$sum": {
                        "$add": ["$items.price", "$items.freight_value"]
                    }
                },
            }
        },
    ]
    total_rows = list(db.orders.aggregate(total_revenue_pipeline))
    if not total_rows:
        raise ValueError("Aucun article trouvé pour calculer le chiffre d'affaires.")

    total_revenue = total_rows[0]["total"]
    if total_revenue <= 0:
        raise ValueError("Le chiffre d'affaires total doit être positif.")

    category_pipeline = [
        {"$unwind": "$items"},
        {
            "$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "product_id",
                "as": "product",
            }
        },
        {"$unwind": "$product"},
        {"$match": {"product.product_category_name_english": {"$type": "string"}}},
        {
            "$group": {
                "_id": "$product.product_category_name_english",
                "chiffre_affaires_brut": {
                    "$sum": {
                        "$add": ["$items.price", "$items.freight_value"]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "categorie": "$_id",
                "chiffre_affaires_brut": 1,
            }
        },
    ]

    category_rows = list(db.orders.aggregate(category_pipeline))
    categories = pd.DataFrame(category_rows)
    if categories.empty:
        raise ValueError("Aucune catégorie traduite n'a été trouvée.")

    # Calculer la part sur les valeurs non arrondies, puis trier comme la requête SQL.
    categories["chiffre_affaires"] = categories["chiffre_affaires_brut"].round(2)
    categories["part_ca_pct"] = (
        categories["chiffre_affaires_brut"] * 100 / total_revenue
    ).round(2)
    result = (
        categories.sort_values("chiffre_affaires", ascending=False)
        .head(10)[["categorie", "chiffre_affaires", "part_ca_pct"]]
        .reset_index(drop=True)
    )

    print("\n--- Requête C : top 10 des catégories ---")
    print(result)
    #result.to_excel("top_10_categories.xlsx", index=False)
    return result


def _parse_date(field):
    return {
        "$dateFromString": {
            "dateString": field,
            "format": "%Y-%m-%d %H:%M:%S",
            "onError": None,
            "onNull": None,
        }
    }


def _days_between(start_field, end_field):
    return {
        "$divide": [
            {"$subtract": [_parse_date(end_field), _parse_date(start_field)]},
            86_400_000,
        ]
    }


def _late_flag():
    return {
        "$cond": [
            {
                "$and": [
                    {
                        "$eq": [
                            {"$type": "$order_delivered_customer_date"},
                            "string",
                        ]
                    },
                    {
                        "$eq": [
                            {"$type": "$order_estimated_delivery_date"},
                            "string",
                        ]
                    },
                    {
                        "$gt": [
                            "$order_delivered_customer_date",
                            "$order_estimated_delivery_date",
                        ]
                    },
                ]
            },
            1,
            0,
        ]
    }


def _on_time_flag():
    return {
        "$cond": [
            {
                "$and": [
                    {
                        "$eq": [
                            {"$type": "$order_delivered_customer_date"},
                            "string",
                        ]
                    },
                    {
                        "$eq": [
                            {"$type": "$order_estimated_delivery_date"},
                            "string",
                        ]
                    },
                    {
                        "$lte": [
                            "$order_delivered_customer_date",
                            "$order_estimated_delivery_date",
                        ]
                    },
                ]
            },
            1,
            0,
        ]
    }


def run_query_d(db):
    """Délai moyen de livraison et taux de retard par état."""
    db.customers.create_index("customer_id")
    pipeline = [
        {
            "$match": {
                "order_status": "delivered",
                "order_delivered_customer_date": {"$type": "string"},
                "order_estimated_delivery_date": {"$type": "string"},
            }
        },
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer",
            }
        },
        {"$unwind": "$customer"},
        {
            "$addFields": {
                "delai_jours": _days_between(
                    "$order_purchase_timestamp", "$order_delivered_customer_date"
                ),
                "est_en_retard": _late_flag(),
            }
        },
        {
            "$group": {
                "_id": "$customer.customer_state",
                "delai_moyen_jours": {"$avg": "$delai_jours"},
                "taux_retard": {"$avg": "$est_en_retard"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "customer_state": "$_id",
                "delai_moyen_jours": {"$round": ["$delai_moyen_jours", 2]},
                "taux_retard_pourcent": {
                    "$round": [{"$multiply": ["$taux_retard", 100]}, 2]
                },
            }
        },
        {"$sort": {"delai_moyen_jours": -1}},
    ]

    result = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    print("\n--- Requête D : délais et retards par état ---")
    print(result)
    # result.to_excel("delai_moyen_taux_retard.xlsx", index=False)
    return result


def run_query_e(db):
    """Top 10 des vendeurs par chiffre d'affaires, commandes et notes."""
    pipeline = [
        {"$unwind": "$items"},
        {"$unwind": {"path": "$reviews", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": "$items.seller_id",
                "chiffre_affaires_brut": {
                    "$sum": {
                        "$add": ["$items.price", "$items.freight_value"]
                    }
                },
                "commandes": {"$addToSet": "$order_id"},
                "note_moyenne": {"$avg": "$reviews.review_score"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "seller_id": "$_id",
                "chiffre_affaires_brut": 1,
                "nb_commandes": {"$size": "$commandes"},
                "note_moyenne": {"$round": ["$note_moyenne", 2]},
            }
        },
    ]

    result = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    result["chiffre_affaires"] = result["chiffre_affaires_brut"].round(2)
    result = (
        result.sort_values("chiffre_affaires", ascending=False)
        .head(10)[["seller_id", "chiffre_affaires", "nb_commandes", "note_moyenne"]]
        .reset_index(drop=True)
    )
    print("\n--- Requête E : top 10 des vendeurs ---")
    print(result)
    # result.to_excel("top_10_vendeurs.xlsx", index=False)
    return result


def run_query_f(db):
    """Vendeurs réguliers à faible note et à faible taux de retard."""
    db.sellers.create_index("seller_id")
    delivery_pipeline = [
        {"$match": {"order_status": "delivered"}},
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.seller_id",
                "nb_articles": {"$sum": 1},
                "nb_retards": {"$sum": _late_flag()},
            }
        },
        {
            "$addFields": {
                "pct_retard": {
                    "$multiply": [
                        {"$divide": ["$nb_retards", "$nb_articles"]},
                        100,
                    ]
                }
            }
        },
        {
            "$lookup": {
                "from": "sellers",
                "localField": "_id",
                "foreignField": "seller_id",
                "as": "seller",
            }
        },
        {"$unwind": "$seller"},
        {
            "$project": {
                "_id": 0,
                "seller_id": "$_id",
                "seller_state": "$seller.seller_state",
                "seller_city": "$seller.seller_city",
                "nb_articles": 1,
                "pct_retard": 1,
            }
        },
    ]
    review_pipeline = [
        {"$unwind": "$items"},
        {"$unwind": "$reviews"},
        {
            "$group": {
                "_id": "$items.seller_id",
                "note_moyenne": {"$avg": "$reviews.review_score"},
            }
        },
        {"$project": {"_id": 0, "seller_id": "$_id", "note_moyenne": 1}},
    ]

    delivery_stats = pd.DataFrame(list(db.orders.aggregate(delivery_pipeline)))
    review_stats = pd.DataFrame(list(db.orders.aggregate(review_pipeline)))
    result = delivery_stats.merge(review_stats, on="seller_id", how="inner")
    result = result[
        (result["nb_articles"] >= 30)
        & (result["note_moyenne"] < 3.5)
        & (result["pct_retard"] < 5.0)
    ]
    result = (
        result.sort_values(["seller_state", "seller_city"])
        [["seller_id", "seller_city", "seller_state", "nb_articles",
          "note_moyenne", "pct_retard"]]
        .reset_index(drop=True)
    )
    print("\n--- Requête F : vendeurs à surveiller ---")
    print(result)
    # result.to_excel("vendeurs_a_surveiller.xlsx", index=False)
    return result


def run_query_g(db):
    """Taux de livraison à l'heure, global et par mois."""
    pipeline = [
        {
            "$match": {
                "order_status": "delivered",
                "order_delivered_customer_date": {"$type": "string"},
            }
        },
        {"$addFields": {"a_l_heure": _on_time_flag()}},
        {
            "$facet": {
                "global": [
                    {
                        "$group": {
                            "_id": "Global",
                            "nb_commandes_livrees": {"$sum": 1},
                            "commandes_a_l_heure": {"$sum": "$a_l_heure"},
                        }
                    }
                ],
                "mensuel": [
                    {
                        "$group": {
                            "_id": {
                                "$substrBytes": [
                                    "$order_purchase_timestamp",
                                    0,
                                    7,
                                ]
                            },
                            "nb_commandes_livrees": {"$sum": 1},
                            "commandes_a_l_heure": {"$sum": "$a_l_heure"},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ],
            }
        },
    ]

    facet_rows = list(db.orders.aggregate(pipeline))
    if not facet_rows:
        raise ValueError("Aucune commande livrée trouvée.")

    rows = facet_rows[0]["global"] + facet_rows[0]["mensuel"]
    result = pd.DataFrame(rows).rename(columns={"_id": "periode"})
    result["taux_livraison_heure_pct"] = (
        result["commandes_a_l_heure"] * 100 / result["nb_commandes_livrees"]
    ).round(2)
    result = result[
        ["periode", "nb_commandes_livrees", "taux_livraison_heure_pct"]
    ]
    print("\n--- Requête G : taux de livraison à l'heure ---")
    print(result)
    # result.to_excel("taux_livraison_heure.xlsx", index=False)
    return result


#def run_query_h(db):
    """Clients, vendeurs et coordonnées moyennes par état."""
    if "geolocation" not in db.list_collection_names():
        raise RuntimeError(
            "La collection geolocation est absente. Relancez la migration mise à jour."
        )

    customers = list(
        db.customers.aggregate(
            [
                {"$match": {"customer_state": {"$type": "string"}}},
                {"$group": {"_id": "$customer_state", "nb_clients": {"$sum": 1}}},
            ]
        )
    )
    sellers = list(
        db.sellers.aggregate(
            [
                {"$match": {"seller_state": {"$type": "string"}}},
                {"$group": {"_id": "$seller_state", "nb_vendeurs": {"$sum": 1}}},
            ]
        )
    )
    geolocation = list(
        db.geolocation.find(
            {},
            {
                "_id": 0,
                "geolocation_state": 1,
                "lat_moyenne": 1,
                "lng_moyenne": 1,
            },
        )
    )
    if not geolocation:
        raise ValueError("La collection geolocation ne contient aucune donnée.")

    customer_df = pd.DataFrame(customers).rename(columns={"_id": "state"})
    seller_df = pd.DataFrame(sellers).rename(columns={"_id": "state"})
    state_df = pd.DataFrame(
        {
            "state": sorted(
                set(customer_df["state"])
                | set(seller_df["state"])
                | {row["geolocation_state"] for row in geolocation}
            )
        }
    )
    geo_df = pd.DataFrame(geolocation).rename(
        columns={"geolocation_state": "state"}
    )
    result = (
        state_df.merge(customer_df, on="state", how="left")
        .merge(seller_df, on="state", how="left")
        .merge(geo_df, on="state", how="left")
    )
    result["nb_clients"] = result["nb_clients"].fillna(0).astype(int)
    result["nb_vendeurs"] = result["nb_vendeurs"].fillna(0).astype(int)
    result["ratio_clients_vendeur"] = result.apply(
        lambda row: (
            row["nb_clients"] / row["nb_vendeurs"]
            if row["nb_vendeurs"]
            else None
        ),
        axis=1,
    )
    result = result[
        [
            "state",
            "nb_clients",
            "nb_vendeurs",
            "lat_moyenne",
            "lng_moyenne",
            "ratio_clients_vendeur",
        ]
    ].sort_values("state")
    print("\n--- Requête H : clients et vendeurs par état ---")
    print(result)
    # result.to_excel("clients_vendeurs_par_etat.xlsx", index=False)
    return result


def run_query_i1(db):
    """Notes moyennes par tranche de retard de livraison."""
    pipeline = [
        {
            "$match": {
                "order_status": "delivered",
                "order_delivered_customer_date": {"$type": "string"},
            }
        },
        {"$unwind": "$reviews"},
        {
            "$addFields": {
                "jours_retard": _days_between(
                    "$order_estimated_delivery_date",
                    "$order_delivered_customer_date",
                )
            }
        },
        {
            "$addFields": {
                "tranche_retard": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$and": [
                                        {"$isNumber": "$jours_retard"},
                                        {"$lte": ["$jours_retard", 0]},
                                    ]
                                },
                                "then": "1 - A l heure",
                            },
                            {
                                "case": {
                                    "$and": [
                                        {"$isNumber": "$jours_retard"},
                                        {"$lte": ["$jours_retard", 3]},
                                    ]
                                },
                                "then": "2 - Retard 1 a 3 jours",
                            },
                            {
                                "case": {
                                    "$and": [
                                        {"$isNumber": "$jours_retard"},
                                        {"$lte": ["$jours_retard", 7]},
                                    ]
                                },
                                "then": "3 - Retard 4 a 7 jours",
                            },
                        ],
                        "default": "4 - Retard plus de 7 jours",
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$tranche_retard",
                "commandes": {"$addToSet": "$order_id"},
                "note_moyenne": {"$avg": "$reviews.review_score"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "tranche_retard": "$_id",
                "nb_commandes": {"$size": "$commandes"},
                "note_moyenne": {"$round": ["$note_moyenne", 2]},
            }
        },
        {"$sort": {"tranche_retard": 1}},
    ]

    result = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    print("\n--- Requête I1 : avis par tranche de retard ---")
    print(result)
    #result.to_excel("avis_par_tranche_retard.xlsx", index=False)
    return result


def run_query_i2(db):
    """Corrélation entre retard et note moyenne par état."""
    db.customers.create_index("customer_id")
    pipeline = [
        {
            "$match": {
                "order_status": "delivered",
                "order_delivered_customer_date": {"$type": "string"},
            }
        },
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer",
            }
        },
        {"$unwind": "$customer"},
        {"$unwind": "$reviews"},
        {
            "$addFields": {
                "jours_retard": _days_between(
                    "$order_estimated_delivery_date",
                    "$order_delivered_customer_date",
                )
            }
        },
        {
            "$group": {
                "_id": {
                    "etat": "$customer.customer_state",
                    "order_id": "$order_id",
                },
                "jours_retard": {"$first": "$jours_retard"},
                "note_moyenne": {"$avg": "$reviews.review_score"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "etat": "$_id.etat",
                "order_id": "$_id.order_id",
                "jours_retard": 1,
                "note_moyenne": 1,
            }
        },
    ]

    orders = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    correlation = (
        orders.groupby("etat")
        .apply(lambda group: group["jours_retard"].corr(group["note_moyenne"]))
        .rename("correlation_retard_note")
        .reset_index()
    )
    correlation["correlation_retard_note"] = correlation[
        "correlation_retard_note"
    ].round(3)
    result = correlation.sort_values(
        "correlation_retard_note", ascending=True
    ).reset_index(drop=True)
    print("\n--- Requête I2 : corrélation retard / note ---")
    print(result)
    #result.to_excel("correlation_retard_note.xlsx", index=False)
    return result


def run_query_j(db):
    """Répartition des commandes et des montants par moyen de paiement."""
    pipeline = [
        {
            "$facet": {
                "par_moyen": [
                    {"$unwind": "$payments"},
                    {
                        "$group": {
                            "_id": "$payments.payment_type",
                            "commandes": {"$addToSet": "$order_id"},
                            "valeur_totale": {
                                "$sum": "$payments.payment_value"
                            },
                            "nb_moyen_echeances": {
                                "$avg": "$payments.payment_installments"
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "moyen_paiement": "$_id",
                            "commandes": 1,
                            "nb_commandes": {"$size": "$commandes"},
                            "valeur_totale": 1,
                            "nb_moyen_echeances": 1,
                        }
                    },
                ],
                "totaux": [
                    {"$unwind": "$payments"},
                    {
                        "$group": {
                            "_id": None,
                            "commandes": {"$addToSet": "$order_id"},
                            "valeur_totale": {
                                "$sum": "$payments.payment_value"
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "nb_commandes_total": {"$size": "$commandes"},
                            "valeur_totale_total": "$valeur_totale",
                        }
                    },
                ],
            }
        }
    ]

    facet_rows = list(db.orders.aggregate(pipeline))
    if not facet_rows or not facet_rows[0]["totaux"]:
        raise ValueError("Aucun paiement trouvé.")

    result = pd.DataFrame(facet_rows[0]["par_moyen"])
    totals = facet_rows[0]["totaux"][0]
    result["pct_commandes"] = (
        result["nb_commandes"] * 100 / totals["nb_commandes_total"]
    )
    result["pct_valeur"] = (
        result["valeur_totale"] * 100 / totals["valeur_totale_total"]
    )
    result = result[
        [
            "moyen_paiement",
            "nb_commandes",
            "pct_commandes",
            "valeur_totale",
            "pct_valeur",
            "nb_moyen_echeances",
        ]
    ].sort_values("pct_valeur", ascending=False).reset_index(drop=True)
    print("\n--- Requête J : répartition des moyens de paiement ---")
    print(result)
    #result.to_excel("repartition_moyens_paiement.xlsx", index=False)
    return result


def run_query_k(db):
    """Top 10 des délais moyens de traitement les plus longs par vendeur."""
    pipeline = [
        {
            "$match": {
                "order_delivered_carrier_date": {"$type": "string"},
            }
        },
        {"$unwind": "$items"},
        {
            "$addFields": {
                "delai_traitement": _days_between(
                    "$order_purchase_timestamp",
                    "$order_delivered_carrier_date",
                )
            }
        },
        {
            "$group": {
                "_id": "$items.seller_id",
                "commandes": {"$addToSet": "$order_id"},
                "delai_moyen_brut": {"$avg": "$delai_traitement"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "seller_id": "$_id",
                "nb_commandes": {"$size": "$commandes"},
                "delai_moyen_brut": 1,
            }
        },
    ]

    result = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    result["delai_moyen_traitement_jours"] = result[
        "delai_moyen_brut"
    ].round(2)
    result = (
        result[result["nb_commandes"] >= 30]
        .sort_values("delai_moyen_traitement_jours", ascending=False)
        .head(10)[
            ["seller_id", "nb_commandes", "delai_moyen_traitement_jours"]
        ]
        .reset_index(drop=True)
    )
    print("\n--- Requête K : vendeurs aux délais de traitement les plus longs ---")
    print(result)
    #result.to_excel("delai_traitement_vendeurs.xlsx", index=False)
    return result


def run_query_l(db):
    """Taux de clients récurrents par état."""
    db.orders.create_index("customer_id")
    pipeline = [
        {
            "$lookup": {
                "from": "orders",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "orders",
            }
        },
        {
            "$group": {
                "_id": "$customer_unique_id",
                "nb_commandes": {"$sum": {"$size": "$orders"}},
                "clients": {
                    "$push": {
                        "state": "$customer_state",
                    }
                },
            }
        },
        {"$match": {"_id": {"$ne": None}, "nb_commandes": {"$gt": 0}}},
        {"$unwind": "$clients"},
        {"$match": {"clients.state": {"$type": "string"}}},
        {
            "$group": {
                "_id": "$clients.state",
                "clients_uniques": {"$addToSet": "$_id"},
                "nb_clients_recurrents": {
                    "$sum": {
                        "$cond": [{"$gte": ["$nb_commandes", 2]}, 1, 0]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "state": "$_id",
                "total_clients": {"$size": "$clients_uniques"},
                "nb_clients_recurrents": 1,
                "taux_recurence_pct": {
                    "$multiply": [
                        {
                            "$divide": [
                                "$nb_clients_recurrents",
                                {"$size": "$clients_uniques"},
                            ]
                        },
                        100,
                    ]
                },
            }
        },
        {"$sort": {"taux_recurence_pct": -1}},
    ]

    result = pd.DataFrame(list(db.customers.aggregate(pipeline)))
    result = result[
        [
            "state",
            "total_clients",
            "nb_clients_recurrents",
            "taux_recurence_pct",
        ]
    ]
    print("\n--- Requête L : clients récurrents par état ---")
    print(result)
    #result.to_excel("clients_recurrents_par_etat.xlsx", index=False)
    return result


def run_query_m(db):
    """Nombre de commandes et notes moyennes par rapidité et état."""
    db.customers.create_index("customer_id")
    pipeline = [
        {
            "$match": {
                "order_status": "delivered",
                "order_delivered_customer_date": {"$type": "string"},
            }
        },
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer",
            }
        },
        {"$unwind": "$customer"},
        {"$unwind": {"path": "$reviews", "preserveNullAndEmptyArrays": True}},
        {
            "$addFields": {
                "delai_livraison": _days_between(
                    "$order_purchase_timestamp",
                    "$order_delivered_customer_date",
                )
            }
        },
        {
            "$addFields": {
                "rapidite_livraison": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$and": [
                                        {"$isNumber": "$delai_livraison"},
                                        {"$lt": ["$delai_livraison", 8]},
                                    ]
                                },
                                "then": "1 - Rapide (< 8j)",
                            },
                            {
                                "case": {
                                    "$and": [
                                        {"$isNumber": "$delai_livraison"},
                                        {"$lte": ["$delai_livraison", 15]},
                                    ]
                                },
                                "then": "2 - Normale (8 a 15j)",
                            },
                        ],
                        "default": "3 - Lente (> 15j)",
                    }
                }
            }
        },
        {
            "$group": {
                "_id": {
                    "etat": "$customer.customer_state",
                    "rapidite": "$rapidite_livraison",
                },
                "commandes": {"$addToSet": "$order_id"},
                "note_moyenne": {"$avg": "$reviews.review_score"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "etat": "$_id.etat",
                "rapidite_livraison": "$_id.rapidite",
                "nb_commandes": {"$size": "$commandes"},
                "note_moyenne": {"$round": ["$note_moyenne", 2]},
            }
        },
        {"$sort": {"etat": 1, "rapidite_livraison": 1}},
    ]

    result = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    print("\n--- Requête M : rapidité de livraison par état ---")
    print(result)
    #result.to_excel("rapidite_livraison_par_etat.xlsx", index=False)
    return result


def run_query_n(db):
    """Segmentation des clients selon leurs dépenses totales."""
    db.customers.create_index("customer_id")
    pipeline = [
        {"$unwind": "$payments"},
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer",
            }
        },
        {"$unwind": "$customer"},
        {
            "$group": {
                "_id": "$customer.customer_unique_id",
                "total_depense": {"$sum": "$payments.payment_value"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "customer_unique_id": "$_id",
                "total_depense": 1,
            }
        },
    ]

    spending = pd.DataFrame(list(db.orders.aggregate(pipeline)))
    if spending.empty:
        raise ValueError("Aucun paiement trouvé pour segmenter les clients.")

    spending["segment_client"] = spending["total_depense"].map(
        lambda amount: (
            "1. VIP (> 500 R$)"
            if amount >= 500
            else "2. Standard (200 - 500 R$)"
            if amount >= 200
            else "3. Occasionnel (< 200 R$)"
        )
    )
    result = (
        spending.groupby("segment_client", as_index=False)
        .agg(
            nombre_clients=("customer_unique_id", "count"),
            ca_total_segment=("total_depense", "sum"),
        )
    )
    total_clients = len(spending)
    total_revenue = spending["total_depense"].sum()
    result["pct_clients"] = result["nombre_clients"] * 100 / total_clients
    result["pct_ca"] = result["ca_total_segment"] * 100 / total_revenue
    result = result[
        [
            "segment_client",
            "nombre_clients",
            "pct_clients",
            "ca_total_segment",
            "pct_ca",
        ]
    ]
    print("\n--- Requête N : segmentation des clients ---")
    print(result)
    #result.to_excel("segmentation_clients.xlsx", index=False)
    return result


def main():
    with MongoClient("mongodb://127.0.0.1:27017/") as client:
        db = client["SAE"]
        run_query_a(db)
        run_query_b(db)
        run_query_c(db)
        run_query_d(db)
        run_query_e(db)
        run_query_f(db)
        run_query_g(db)
        #run_query_h(db)
        run_query_i1(db)
        run_query_i2(db)
        run_query_j(db)
        run_query_k(db)
        run_query_l(db)
        run_query_m(db)
        run_query_n(db)


if __name__ == "__main__":
  client = MongoClient("mongodb://127.0.0.1:27017/")
  db = client["SAE"]

  resultats_mongo = {
      "a": run_query_a(db),
      "b": run_query_b(db),
      "c": run_query_c(db),
      "d": run_query_d(db),
      "e": run_query_e(db),
      "f": run_query_f(db),
      "g": run_query_g(db),
      #"h": run_query_h(db),
      "i1": run_query_i1(db),
      "i2": run_query_i2(db),
      "j": run_query_j(db),
      "k": run_query_k(db),
      "l": run_query_l(db),
      "m": run_query_m(db),
      "n": run_query_n(db), 
  }

  with pd.ExcelWriter("resultats_mongodb.xlsx", engine="openpyxl") as writer:
    for nom_feuille, df in resultats_mongo.items():
      df.to_excel(writer, sheet_name=nom_feuille[:31], index=False)

  client.close()

# Projet Migration de données vers un environnement NoSQL

## Objectif

La base relationnelle SQLite contient environ 100 000 commandes Olist, leurs articles,
paiements, avis et informations géographiques. Le travail consiste à :

1. analyser les données avec des requêtes SQLite ;
2. migrer les données vers MongoDB dans un modèle à documents ;
3. reproduire les analyses en MongoDB avec des pipelines d'agrégation ;
4. afficher les indicateurs dans une application Streamlit interactive ;
5. comparer les résultats SQL et MongoDB pour vérifier la migration.

L'application doit fournir des réponses compréhensibles pour les décideurs :
direction générale, commerce, logistique, satisfaction, expansion, finance, marketing
et responsable des vendeurs.

---

## Architecture du projet

```text
migration_noqsl_final/
├── app.py                         # Tableau de bord Streamlit
├── data/
│   └── olist.sqlite               # Base relationnelle source
├── scripts/
│   ├── partie1_req_SQL.py         # Requêtes SQLite : a à n
│   ├── partie2.py                 # Migration SQLite vers MongoDB
│   ├── partie3_req_mongodb.py     # Requêtes MongoDB : a à n
│   └── comparaison.py             # Comparaison des résultats SQL/MongoDB
├── output/
│   ├── resultats_sql.xlsx         # Résultats SQLite
│   └── resultats_mongodb.xlsx     # Résultats MongoDB
├── requirements.txt
├── setup.sh                       # Lanceur Linux/macOS
└── setup.bat                      # Lanceur Windows
```

---

## Collections MongoDB

La migration crée cinq collections dans la base `olist` :

| `orders` | Collection centrale : Pourquoi ce choix : Dans le schéma relationnel, une commande est liée à plusieurs tables enfants (order_items, order_payments, order_reviews). Le sujet précise qu'une commande est naturellement un objet riche et imbriqué, et que les avis contiennent souvent des textes libres manquants (données semi-structurées).|
| `products` | Catalogue produit enrichi avec la traduction anglaise des catégories |
| `customers` | Informations des clients, États et identifiants récurrents |
| `sellers` | Informations des vendeurs, villes et États |
| `geolocation` | Le sujet signale que geolocation contient plus d'un million de points liés par préfixe de code postal (sans clé étrangère déclarée) pour alimenter des cartes dynamiques et calculer des moyennes/centroïdes par État. L'isoler dans sa propre collection correspond à cet usage cartographique |



Ce modèle imbriqué évite de répéter les informations générales de la commande dans
plusieurs tables liées. Les référentiels `customers`, `sellers`, `products` et
`geolocation` restent séparés pour limiter les duplications et permettre les
`$lookup` lorsque nécessaire.

---

## Installation et lancement

### Prérequis

- Python **3.12 à 3.15**, version 64 bits sur Windows
- MongoDB accessible sur `mongodb://127.0.0.1:27017/`
- MongoDB Compass recommandé pour contrôler les bases et collections
- Le fichier `data/olist.sqlite`

MongoDB doit être démarré **avant** d'exécuter la migration ou le tableau de bord.

### Windows

```bat
setup.bat
```

### Linux / macOS

```bash
chmod +x setup.sh
./setup.sh
```

Ces lanceurs créent un environnement virtuel `.venv`, installent les dépendances,
puis ouvrent l'application Streamlit. Il faut se connecter depuis le terminal. Le premier chargement de streamlit peut etre un peu long (quelques secondes / minute).

### Lancement manuel

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Dans certains environnements, les dépendances doivent être installées avec
`python -m pip` au lieu de `pip` pour garantir leur installation dans le bon
interpréteur Python.

---

## Utilisation du tableau de bord

L'application comporte trois onglets :

1. **Exécution & Comparaison SQL / MongoDB**
   Lance successivement les parties 1, 2 et 3, puis compare les feuilles Excel.
2. **Graphiques décisionnels**
3. **Cartographie Folium**


---

## Résultats générés

Les scripts créent automatiquement deux fichiers Excel dans `output/` : `resultats_sql.xlsx` et `resultats_mongodb.xlsx`

Le script `comparaison.py` compare les données sans dépendre de l'ordre exact
des lignes ou des colonnes, avec une tolérance sur les nombres décimaux.


---

### Améliorations techniques possibles

- démarrer MongoDB depuis les lanceurs ou afficher une vérification explicite
  avant le pipeline ;
- créer les index MongoDB dès la migration ;
- remplacer les `groupby().apply()` de la partie 2 par un regroupement plus
  directement vectorisé ;
- insérer les documents par lots plus petits pour réduire l'utilisation mémoire ;

Nassim AOULAD-SAID, Rose CHAUVIN, Clara DECROS, Paul BABIN
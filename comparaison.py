import pandas as pd

sql_sheets = pd.read_excel("resultats_sql.xlsx", sheet_name=None)
mongo_sheets = pd.read_excel("resultats_mongodb.xlsx", sheet_name=None)

print("🔍 Début de la vérification de la migration...\n")

requetes_problematiques = []
erreurs_details = {}

# Vérifie aussi d'éventuels onglets présents uniquement dans MongoDB
tous_les_onglets = list(dict.fromkeys(list(sql_sheets.keys()) + list(mongo_sheets.keys())))

for sheet_name in tous_les_onglets:
    if sheet_name not in sql_sheets:
        msg = f"Onglet '{sheet_name}' absent de SQL mais présent dans MongoDB."
        print(f"❌ [ABSENT SQL] {msg}")
        requetes_problematiques.append(sheet_name)
        erreurs_details[sheet_name] = msg
        continue

    if sheet_name not in mongo_sheets:
        msg = f"Onglet '{sheet_name}' présent dans SQL mais absent de MongoDB."
        print(f"❌ [ABSENT MONGO] {msg}")
        requetes_problematiques.append(sheet_name)
        erreurs_details[sheet_name] = msg
        continue

    df_sql = sql_sheets[sheet_name]
    df_mongo = mongo_sheets[sheet_name]

    try:
        # check_like=True : ignore l'ordre des lignes/colonnes si tri différent
        # rtol / atol : tolérance légère sur les nombres décimaux (ex: 12.34 vs 12.3400001)
        pd.testing.assert_frame_equal(
            df_sql,
            df_mongo,
            check_like=True,
            rtol=1e-4,
            atol=1e-4,
        )
        print(f"✅ [SUCCÈS] L'onglet '{sheet_name}' est identique.")

    except AssertionError as e:
        print(f"❌ [DIFFÉRENCE] L'onglet '{sheet_name}' présente des écarts.")
        requetes_problematiques.append(sheet_name)
        erreurs_details[sheet_name] = str(e)

print("\n" + "=" * 50)
if not requetes_problematiques:
    print("🎉 Mission accomplie : 100% des résultats SQL et MongoDB concordent !")
else:
    print(f"⚠️ {len(requetes_problematiques)} requête(s) problématique(s) : {requetes_problematiques}")
    for req in requetes_problematiques:
        print(f"\n--- Détail pour '{req}' ---")
        print(erreurs_details[req])
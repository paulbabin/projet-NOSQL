import contextlib
import io
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pymongo import MongoClient


PROJECT_DIR = Path(__file__).resolve().parent
SQL_SCRIPT = PROJECT_DIR / "requete_SQL_rose.py"
OUTPUT_FILE = PROJECT_DIR / "comparatif_sql_mongodb.xlsx"

QUERY_FILES = {
    "A": "requete_a.csv",
    "B": "panier_moyen.csv",
    "C": "requete_c.csv",
    "D": "delai_moyen_taux_retard.csv",
    "E": "requete_e.csv",
    "F": "requete_f.csv",
    "G": "requete_g.csv",
    "H": "requete_clients_vendeurs.csv",
    "I1": "requete_i_tranches.csv",
    "I2": "requete_i_correlation.csv",
    "J": "requete_repartition_paiement.csv",
    "K": "requete_k.csv",
    "L": "requete_taux_clients_recurrents.csv",
    "M": "requete_m.csv",
    "N": "requete_segmentation_clients.csv",
}

def _capture_sql_outputs():
    outputs = {}

    def capture_csv(dataframe, path, *args, **kwargs):
        outputs[Path(path).name] = dataframe.copy()

    previous_directory = Path.cwd()
    try:
        os.chdir(PROJECT_DIR)
        with patch.object(pd.DataFrame, "to_csv", capture_csv):
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(SQL_SCRIPT), run_name="__main__")
    finally:
        os.chdir(previous_directory)

    missing = set(QUERY_FILES.values()) - outputs.keys()
    if missing:
        raise RuntimeError(
            "Les résultats SQL suivants n'ont pas été produits : "
            + ", ".join(sorted(missing))
        )
    return outputs


def _normalized_result(dataframe, columns):
    result = dataframe.loc[:, columns].copy()
    for column in columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            result[column] = pd.to_numeric(result[column]).astype("float64").round(8)
    return result.sort_values(
        columns, kind="mergesort", na_position="last"
    ).reset_index(drop=True)


def _results_match(sql_result, mongo_result):
    if set(sql_result.columns) != set(mongo_result.columns):
        return False
    columns = list(sql_result.columns)
    if len(sql_result) != len(mongo_result):
        return False
    return _normalized_result(sql_result, columns).equals(
        _normalized_result(mongo_result, columns)
    )


def create_comparison_workbook():
    sql_outputs = _capture_sql_outputs()

    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    from partie3_req_mongodb import (
        run_query_a,
        run_query_b,
        run_query_c,
        run_query_d,
        run_query_e,
        run_query_f,
        run_query_g,
        run_query_h,
        run_query_i1,
        run_query_i2,
        run_query_j,
        run_query_k,
        run_query_l,
        run_query_m,
        run_query_n,
    )

    query_functions = {
        "A": run_query_a,
        "B": run_query_b,
        "C": run_query_c,
        "D": run_query_d,
        "E": run_query_e,
        "F": run_query_f,
        "G": run_query_g,
        "H": run_query_h,
        "I1": run_query_i1,
        "I2": run_query_i2,
        "J": run_query_j,
        "K": run_query_k,
        "L": run_query_l,
        "M": run_query_m,
        "N": run_query_n,
    }

    mongo_outputs = {}
    with MongoClient("mongodb://127.0.0.1:27017/") as client:
        db = client["SAE"]
        with patch.object(pd.DataFrame, "to_excel", lambda *args, **kwargs: None):
            with contextlib.redirect_stdout(io.StringIO()):
                for query_name, query_function in query_functions.items():
                    mongo_outputs[query_name] = query_function(db)

    summary_rows = []
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        for query_name, csv_name in QUERY_FILES.items():
            sql_result = sql_outputs[csv_name]
            mongo_result = mongo_outputs[query_name]
            same_columns = set(sql_result.columns) == set(mongo_result.columns)
            matches = _results_match(sql_result, mongo_result)
            summary_rows.append(
                {
                    "Requête": query_name,
                    "Lignes SQL": len(sql_result),
                    "Lignes MongoDB": len(mongo_result),
                    "Colonnes identiques": same_columns,
                    "Résultats identiques": matches,
                }
            )

            sheet_name = query_name
            sql_result.to_excel(
                writer,
                sheet_name=sheet_name,
                startrow=2,
                startcol=0,
                index=False,
            )
            mongo_start_column = len(sql_result.columns) + 2
            mongo_result.to_excel(
                writer,
                sheet_name=sheet_name,
                startrow=2,
                startcol=mongo_start_column,
                index=False,
            )

            worksheet = writer.sheets[sheet_name]
            worksheet.cell(row=1, column=1, value="SQL")
            worksheet.cell(
                row=1, column=mongo_start_column + 1, value="MongoDB"
            )
            worksheet.freeze_panes = "A4"

        pd.DataFrame(summary_rows).to_excel(
            writer, sheet_name="Résumé", index=False
        )
        writer.sheets["Résumé"].freeze_panes = "A2"

    print(f"Comparatif créé : {OUTPUT_FILE}")
    print(pd.DataFrame(summary_rows).to_string(index=False))
    return OUTPUT_FILE


if __name__ == "__main__":
    create_comparison_workbook()

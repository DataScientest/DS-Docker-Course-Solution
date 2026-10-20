"""
Entraînement du modèle de détection de fraude : le programme du service train.

Vous n'avez pas besoin de modifier ce fichier : votre travail consiste à le
faire tourner dans un conteneur.

Ce que fait le script
---------------------
1. Il lit dans la base MariaDB le montant, l'heure et l'étiquette is_fraud
   (fraude ou non) de chaque transaction.
2. Il entraîne un modèle des k plus proches voisins (KNN, avec k = 5) : pour
   juger une nouvelle transaction, le modèle cherche les 5 transactions connues
   dont le montant et l'heure lui ressemblent le plus, et regarde combien
   d'entre elles étaient des fraudes.
3. Il enregistre le modèle dans le fichier indiqué par MODEL_PATH, puis il
   s'arrête : c'est un traitement ponctuel, pas un serveur.

Lancer le script
----------------
    python train.py

Configuration (variables d'environnement)
-----------------------------------------
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
                 la connexion à MariaDB, exactement comme pour l'API
    MODEL_PATH   chemin du fichier où enregistrer le modèle, par exemple
                 /models/knn.joblib (le dossier est créé s'il n'existe pas)

Si une variable manque ou si la base est injoignable, le script s'arrête avec
un message d'erreur et un code de sortie différent de 0.
"""

import os
import sys
from pathlib import Path

import joblib  # installé avec scikit-learn
import pymysql
import sklearn
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

NB_VOISINS = 5


def lire_transactions():
    """Renvoie, pour chaque transaction, le triplet (montant, heure, fraude)."""
    connexion = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        connect_timeout=5,
    )
    try:
        with connexion.cursor() as curseur:
            curseur.execute(
                "SELECT amount, HOUR(transaction_date), is_fraud FROM transactions ORDER BY transaction_id"
            )
            return curseur.fetchall()
    finally:
        connexion.close()


def main():
    chemin_modele = os.getenv("MODEL_PATH")
    if not chemin_modele:
        sys.exit("Erreur : la variable d'environnement MODEL_PATH n'est pas définie.")
    if not os.getenv("DB_HOST"):
        sys.exit("Erreur : la variable d'environnement DB_HOST n'est pas définie.")

    try:
        transactions = lire_transactions()
    except pymysql.MySQLError as erreur:
        sys.exit(f"Erreur : impossible de lire les transactions dans la base ({erreur}).")
    if not transactions:
        sys.exit("Erreur : la table transactions est vide.")

    # Les entrées du modèle (montant et heure) et la réponse attendue (fraude ou non)
    entrees = [[float(montant), heure] for montant, heure, _ in transactions]
    fraudes = [fraude for _, _, fraude in transactions]

    # Mise à l'échelle des entrées, puis KNN : sans mise à l'échelle, les montants
    # (jusqu'à 2 000 euros) écraseraient les heures (de 0 à 23) dans le calcul des distances.
    modele = make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=NB_VOISINS))
    modele.fit(entrees, fraudes)

    Path(chemin_modele).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modele, chemin_modele)

    print(f"Modèle KNN (k = {NB_VOISINS}) entraîné sur {len(transactions)} transactions, "
          f"dont {sum(fraudes)} fraudes.")
    print(f"Modèle enregistré dans {chemin_modele} (scikit-learn {sklearn.__version__}).")


if __name__ == "__main__":
    main()

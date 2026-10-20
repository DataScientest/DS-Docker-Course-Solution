"""
Training of the fraud detection model: the program of the train service.

You do not need to modify this file: your job is to run it in a container.

What the script does
--------------------
1. It reads from the MariaDB database the amount, the hour and the is_fraud
   label (fraud or not) of each transaction.
2. It trains a k-nearest neighbors model (KNN, with k = 5): to assess a new
   transaction, the model looks for the 5 known transactions whose amount and
   hour are the most similar, and checks how many of them were frauds.
3. It saves the model to the file given by MODEL_PATH, then stops: it is a
   one-off job, not a server.

Running the script
------------------
    python train.py

Configuration (environment variables)
-------------------------------------
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
                 the connection to MariaDB, exactly as for the API
    MODEL_PATH   path of the file where the model is saved, for example
                 /models/knn.joblib (the folder is created if it does not exist)

If a variable is missing or the database cannot be reached, the script stops
with an error message and an exit code other than 0.
"""

import os
import sys
from pathlib import Path

import joblib  # installed with scikit-learn
import pymysql
import sklearn
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

N_NEIGHBORS = 5


def read_transactions():
    """Returns, for each transaction, the triplet (amount, hour, fraud)."""
    connection = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        connect_timeout=5,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT amount, HOUR(transaction_date), is_fraud FROM transactions ORDER BY transaction_id"
            )
            return cursor.fetchall()
    finally:
        connection.close()


def main():
    model_path = os.getenv("MODEL_PATH")
    if not model_path:
        sys.exit("Error: the MODEL_PATH environment variable is not set.")
    if not os.getenv("DB_HOST"):
        sys.exit("Error: the DB_HOST environment variable is not set.")

    try:
        transactions = read_transactions()
    except pymysql.MySQLError as error:
        sys.exit(f"Error: cannot read the transactions from the database ({error}).")
    if not transactions:
        sys.exit("Error: the transactions table is empty.")

    # The model inputs (amount and hour) and the expected answer (fraud or not)
    inputs = [[float(amount), hour] for amount, hour, _ in transactions]
    frauds = [fraud for _, _, fraud in transactions]

    # Input scaling, then KNN: without scaling, the amounts (up to 2,000 euros)
    # would crush the hours (from 0 to 23) in the distance computation.
    model = make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=N_NEIGHBORS))
    model.fit(inputs, frauds)

    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)

    print(f"KNN model (k = {N_NEIGHBORS}) trained on {len(transactions)} transactions, "
          f"including {sum(frauds)} frauds.")
    print(f"Model saved to {model_path} (scikit-learn {sklearn.__version__}).")


if __name__ == "__main__":
    main()

"""
"Customer Transactions" API: the application of the Docker module's running project.

You do not need to modify this file: your job is to run this application
in Docker.

What the application does
-------------------------
It exposes, as a web API, customer transactions stored in a MariaDB
database, as well as a fraud detection model (the /predict route). FastAPI
automatically generates interactive documentation of the routes, available
at /docs.

Starting the application
------------------------
    uvicorn main:app --host 0.0.0.0 --port 8000

Configuration (environment variables)
-------------------------------------
    DB_HOST      host name of the MariaDB server
    DB_PORT      port of the MariaDB server (3306 by default)
    DB_USER      database user
    DB_PASSWORD  password of this user
    DB_NAME      name of the database
    MODEL_PATH   path of the trained model file, for example
                 /models/knn.joblib (see the train.py script of the train service)

If DB_HOST is not set, the API starts anyway, but without a database: the
routes that need the data respond with a 503 error.

If DB_HOST is set but the database cannot be reached at startup, the API
stops immediately with an error message ("fail fast" principle: better to
stop right away than to keep running in a broken state).

The /predict route needs a model: as long as MODEL_PATH is not set, the model
file does not exist or scikit-learn is not installed in the image, it
responds with a 503 error that explains what is missing. The model is loaded
at the first prediction, then reloaded if it has been retrained.
"""

import logging
import os
import platform
import socket
from contextlib import asynccontextmanager
from datetime import datetime

import pymysql
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# --- Configuration, read from environment variables ---------------------------
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "")
MODEL_PATH = os.getenv("MODEL_PATH")

# We write to uvicorn's logs: they are displayed by `docker logs`
logger = logging.getLogger("uvicorn.error")


# --- Database access ----------------------------------------------------------
def connect():
    """Opens a connection to MariaDB (raises pymysql.MySQLError on failure)."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def run_query(query, parameters=()):
    """Runs a read-only SQL query and returns the resulting rows."""
    if not DB_HOST:
        raise HTTPException(
            status_code=503,
            detail="No database configured: the DB_HOST environment variable "
                   "is not set.",
        )
    try:
        connection = connect()
    except pymysql.MySQLError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database unreachable ({DB_HOST}:{DB_PORT}): {error}",
        ) from error
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall()
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"SQL error: {error}") from error
    finally:
        connection.close()


# --- Model access -------------------------------------------------------------
_model_in_memory = {"file_date": None, "model": None}


def load_model():
    """Returns the model saved in MODEL_PATH, reloaded if it has been retrained."""
    if not MODEL_PATH:
        raise HTTPException(
            status_code=503,
            detail="No model configured: the MODEL_PATH environment variable "
                   "is not set.",
        )
    if not os.path.isfile(MODEL_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"No model found at {MODEL_PATH}: "
                   "the model has not been trained yet, or this file "
                   "is not accessible from the API container.",
        )
    try:
        import joblib  # installed with scikit-learn
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="scikit-learn is not installed in the API image: "
                   "cannot load the model.",
        ) from error
    file_date = os.path.getmtime(MODEL_PATH)
    if file_date != _model_in_memory["file_date"]:
        _model_in_memory["model"] = joblib.load(MODEL_PATH)
        _model_in_memory["file_date"] = file_date
        logger.info("Model loaded from %s.", MODEL_PATH)
    return _model_in_memory["model"]


# --- Application startup ------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Code run once, when the API starts."""
    if not DB_HOST:
        logger.warning(
            "DB_HOST is not set: the API is starting WITHOUT a database. "
            "Routes that read transactions will return a 503 error."
        )
    else:
        try:
            connect().close()
        except pymysql.MySQLError as error:
            logger.error(
                "Cannot connect to database '%s' on %s:%s: %s",
                DB_NAME, DB_HOST, DB_PORT, error,
            )
            raise RuntimeError("Database unreachable at startup: stopping the API.") from error
        logger.info("Connected to database '%s' on %s:%s.", DB_NAME, DB_HOST, DB_PORT)
    yield


app = FastAPI(
    title="Customer Transactions API",
    description="Running project of the Docker module: customer transactions stored in MariaDB.",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Response formats (displayed in /docs) ------------------------------------
class Transaction(BaseModel):
    transaction_id: int
    transaction_date: datetime
    customer_id: str
    amount: float
    category: str
    payment_method: str
    is_fraud: bool


class CustomerSummary(BaseModel):
    customer_id: str
    nb_transactions: int
    total_amount: float
    average_amount: float
    first_transaction: datetime
    last_transaction: datetime


class Stats(BaseModel):
    nb_transactions: int
    nb_customers: int
    total_amount: float
    average_amount: float
    nb_frauds: int
    transactions_by_category: dict[str, int]


class Prediction(BaseModel):
    is_fraud: bool
    fraud_probability: float


# --- Routes -------------------------------------------------------------------
@app.get("/", tags=["Home"])
def home():
    """Welcome message."""
    return {"message": "Welcome to the Customer Transactions API!", "documentation": "/docs"}


@app.get("/info", tags=["Home"])
def info():
    """Information about the environment the API runs in."""
    return {
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "database_configured": DB_HOST is not None,
        "db_host": DB_HOST,
    }


@app.get("/health", tags=["Health"])
def health():
    """Checks that the API responds, without querying the database."""
    return {"status": "ok"}


@app.get("/health/db", tags=["Health"])
def health_db():
    """Checks that the database is reachable and counts the transactions."""
    row = run_query("SELECT COUNT(*) AS nb FROM transactions")[0]
    return {"status": "ok", "database": DB_NAME, "nb_transactions": row["nb"]}


@app.get("/transactions", response_model=list[Transaction], tags=["Transactions"])
def list_transactions(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of transactions returned"),
    offset: int = Query(0, ge=0, description="Number of transactions to skip (pagination)"),
    customer_id: str | None = Query(None, description="Filter on a customer, for example C042"),
    category: str | None = Query(None, description="Filter on a category, for example health"),
):
    """Lists the transactions, from the oldest to the most recent."""
    conditions, parameters = [], []
    if customer_id:
        conditions.append("customer_id = %s")
        parameters.append(customer_id)
    if category:
        conditions.append("category = %s")
        parameters.append(category)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return run_query(
        f"SELECT * FROM transactions {where} ORDER BY transaction_id LIMIT %s OFFSET %s",
        (*parameters, limit, offset),
    )


@app.get("/transactions/{transaction_id}", response_model=Transaction, tags=["Transactions"])
def read_transaction(transaction_id: int):
    """Returns a transaction from its identifier."""
    rows = run_query("SELECT * FROM transactions WHERE transaction_id = %s", (transaction_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found.")
    return rows[0]


@app.get("/customers/{customer_id}/summary", response_model=CustomerSummary, tags=["Customers"])
def customer_summary(customer_id: str):
    """Summary of a customer's activity: number of transactions, amounts and dates."""
    rows = run_query(
        """
        SELECT customer_id,
               COUNT(*)              AS nb_transactions,
               SUM(amount)           AS total_amount,
               ROUND(AVG(amount), 2) AS average_amount,
               MIN(transaction_date) AS first_transaction,
               MAX(transaction_date) AS last_transaction
        FROM transactions
        WHERE customer_id = %s
        GROUP BY customer_id
        """,
        (customer_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    return rows[0]


@app.get("/stats", response_model=Stats, tags=["Statistics"])
def statistics():
    """Overall statistics on all transactions."""
    stats = run_query(
        """
        SELECT COUNT(*)                           AS nb_transactions,
               COUNT(DISTINCT customer_id)        AS nb_customers,
               COALESCE(SUM(amount), 0)           AS total_amount,
               COALESCE(ROUND(AVG(amount), 2), 0) AS average_amount,
               COALESCE(SUM(is_fraud), 0)         AS nb_frauds
        FROM transactions
        """
    )[0]
    categories = run_query(
        "SELECT category, COUNT(*) AS nb FROM transactions GROUP BY category ORDER BY nb DESC"
    )
    stats["transactions_by_category"] = {row["category"]: row["nb"] for row in categories}
    return stats


@app.get("/predict", response_model=Prediction, tags=["Model"])
def predict(
    amount: float = Query(..., gt=0, description="Transaction amount, in euros", examples=[450.0]),
    hour: int = Query(..., ge=0, le=23, description="Transaction hour, from 0 to 23", examples=[2]),
):
    """Predicts whether a transaction is fraudulent, from its amount and hour."""
    model = load_model()
    # Column 1: probability of class 1, i.e. "fraud"
    probability = float(model.predict_proba([[amount, hour]])[0][1])
    return {"is_fraud": probability >= 0.5, "fraud_probability": round(probability, 2)}

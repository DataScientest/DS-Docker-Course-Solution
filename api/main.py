"""
API « Transactions clients » : l'application du projet fil rouge du module Docker.

Vous n'avez pas besoin de modifier ce fichier : votre travail consiste à faire
tourner cette application dans Docker.

Ce que fait l'application
-------------------------
Elle expose, sous forme d'API web, des transactions clients stockées dans une
base de données MariaDB, ainsi qu'un modèle de détection de fraude (route
/predict). FastAPI génère automatiquement une documentation interactive des
routes, accessible à l'adresse /docs.

Lancer l'application
--------------------
    uvicorn main:app --host 0.0.0.0 --port 8000

Configuration (variables d'environnement)
-----------------------------------------
    DB_HOST      nom d'hôte du serveur MariaDB
    DB_PORT      port du serveur MariaDB (3306 par défaut)
    DB_USER      utilisateur de la base de données
    DB_PASSWORD  mot de passe de cet utilisateur
    DB_NAME      nom de la base de données
    MODEL_PATH   chemin du fichier du modèle entraîné, par exemple
                 /models/knn.joblib (voir le script train.py du service train)

Si DB_HOST n'est pas définie, l'API démarre quand même, mais sans base de
données : les routes qui ont besoin des données répondent par une erreur 503.

Si DB_HOST est définie mais que la base est injoignable au démarrage, l'API
s'arrête immédiatement avec un message d'erreur (principe du « fail fast » :
mieux vaut s'arrêter tout de suite que tourner dans un état bancal).

La route /predict a besoin d'un modèle : tant que MODEL_PATH n'est pas définie,
que le fichier du modèle n'existe pas ou que scikit-learn n'est pas installé
dans l'image, elle répond par une erreur 503 qui explique ce qui manque. Le
modèle est lu à la première prédiction, puis relu s'il a été réentraîné.
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

# --- Configuration, lue dans les variables d'environnement --------------------
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "")
MODEL_PATH = os.getenv("MODEL_PATH")

# On écrit dans les logs d'uvicorn : ils s'affichent avec `docker logs`
logger = logging.getLogger("uvicorn.error")


# --- Accès à la base de données -----------------------------------------------
def connecter():
    """Ouvre une connexion à MariaDB (lève pymysql.MySQLError en cas d'échec)."""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def executer(requete, parametres=()):
    """Exécute une requête SQL de lecture et renvoie les lignes obtenues."""
    if not DB_HOST:
        raise HTTPException(
            status_code=503,
            detail="Aucune base de données configurée : la variable d'environnement "
                   "DB_HOST n'est pas définie.",
        )
    try:
        connexion = connecter()
    except pymysql.MySQLError as erreur:
        raise HTTPException(
            status_code=503,
            detail=f"Base de données injoignable ({DB_HOST}:{DB_PORT}) : {erreur}",
        ) from erreur
    try:
        with connexion.cursor() as curseur:
            curseur.execute(requete, parametres)
            return curseur.fetchall()
    except pymysql.MySQLError as erreur:
        raise HTTPException(status_code=500, detail=f"Erreur SQL : {erreur}") from erreur
    finally:
        connexion.close()


# --- Accès au modèle ----------------------------------------------------------
_modele_en_memoire = {"date_du_fichier": None, "modele": None}


def charger_modele():
    """Renvoie le modèle enregistré dans MODEL_PATH, relu s'il a été réentraîné."""
    if not MODEL_PATH:
        raise HTTPException(
            status_code=503,
            detail="Aucun modèle configuré : la variable d'environnement "
                   "MODEL_PATH n'est pas définie.",
        )
    if not os.path.isfile(MODEL_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"Aucun modèle trouvé à l'emplacement {MODEL_PATH} : "
                   "le modèle n'a pas encore été entraîné, ou ce fichier "
                   "n'est pas accessible depuis le conteneur de l'API.",
        )
    try:
        import joblib  # installé avec scikit-learn
    except ImportError as erreur:
        raise HTTPException(
            status_code=503,
            detail="scikit-learn n'est pas installé dans l'image de l'API : "
                   "impossible de charger le modèle.",
        ) from erreur
    date_du_fichier = os.path.getmtime(MODEL_PATH)
    if date_du_fichier != _modele_en_memoire["date_du_fichier"]:
        _modele_en_memoire["modele"] = joblib.load(MODEL_PATH)
        _modele_en_memoire["date_du_fichier"] = date_du_fichier
        logger.info("Modèle chargé depuis %s.", MODEL_PATH)
    return _modele_en_memoire["modele"]


# --- Démarrage de l'application -----------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Code exécuté une fois, au démarrage de l'API."""
    if not DB_HOST:
        logger.warning(
            "DB_HOST n'est pas définie : l'API démarre SANS base de données. "
            "Les routes qui lisent les transactions renverront une erreur 503."
        )
    else:
        try:
            connecter().close()
        except pymysql.MySQLError as erreur:
            logger.error(
                "Impossible de se connecter à la base '%s' sur %s:%s : %s",
                DB_NAME, DB_HOST, DB_PORT, erreur,
            )
            raise RuntimeError("Base de données injoignable au démarrage : arrêt de l'API.") from erreur
        logger.info("Connexion à la base '%s' sur %s:%s réussie.", DB_NAME, DB_HOST, DB_PORT)
    yield


app = FastAPI(
    title="API Transactions clients",
    description="Projet fil rouge du module Docker : des transactions clients stockées dans MariaDB.",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Format des réponses (affiché dans /docs) ---------------------------------
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
@app.get("/", tags=["Accueil"])
def accueil():
    """Message d'accueil."""
    return {"message": "Bienvenue sur l'API Transactions clients !", "documentation": "/docs"}


@app.get("/info", tags=["Accueil"])
def informations():
    """Informations sur l'environnement dans lequel tourne l'API."""
    return {
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "database_configured": DB_HOST is not None,
        "db_host": DB_HOST,
    }


@app.get("/health", tags=["Santé"])
def sante():
    """Vérifie que l'API répond, sans interroger la base."""
    return {"status": "ok"}


@app.get("/health/db", tags=["Santé"])
def sante_base():
    """Vérifie que la base est joignable et compte les transactions."""
    ligne = executer("SELECT COUNT(*) AS nb FROM transactions")[0]
    return {"status": "ok", "database": DB_NAME, "nb_transactions": ligne["nb"]}


@app.get("/transactions", response_model=list[Transaction], tags=["Transactions"])
def lister_transactions(
    limit: int = Query(10, ge=1, le=100, description="Nombre maximum de transactions renvoyées"),
    offset: int = Query(0, ge=0, description="Nombre de transactions à sauter (pagination)"),
    customer_id: str | None = Query(None, description="Filtrer sur un client, par exemple C042"),
    category: str | None = Query(None, description="Filtrer sur une catégorie, par exemple sante"),
):
    """Liste les transactions, de la plus ancienne à la plus récente."""
    conditions, parametres = [], []
    if customer_id:
        conditions.append("customer_id = %s")
        parametres.append(customer_id)
    if category:
        conditions.append("category = %s")
        parametres.append(category)
    filtre = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return executer(
        f"SELECT * FROM transactions {filtre} ORDER BY transaction_id LIMIT %s OFFSET %s",
        (*parametres, limit, offset),
    )


@app.get("/transactions/{transaction_id}", response_model=Transaction, tags=["Transactions"])
def lire_transaction(transaction_id: int):
    """Renvoie une transaction à partir de son identifiant."""
    lignes = executer("SELECT * FROM transactions WHERE transaction_id = %s", (transaction_id,))
    if not lignes:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} introuvable.")
    return lignes[0]


@app.get("/customers/{customer_id}/summary", response_model=CustomerSummary, tags=["Clients"])
def resume_client(customer_id: str):
    """Résumé de l'activité d'un client : nombre de transactions, montants et dates."""
    lignes = executer(
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
    if not lignes:
        raise HTTPException(status_code=404, detail=f"Client {customer_id} introuvable.")
    return lignes[0]


@app.get("/stats", response_model=Stats, tags=["Statistiques"])
def statistiques():
    """Statistiques globales sur l'ensemble des transactions."""
    stats = executer(
        """
        SELECT COUNT(*)                           AS nb_transactions,
               COUNT(DISTINCT customer_id)        AS nb_customers,
               COALESCE(SUM(amount), 0)           AS total_amount,
               COALESCE(ROUND(AVG(amount), 2), 0) AS average_amount,
               COALESCE(SUM(is_fraud), 0)         AS nb_frauds
        FROM transactions
        """
    )[0]
    categories = executer(
        "SELECT category, COUNT(*) AS nb FROM transactions GROUP BY category ORDER BY nb DESC"
    )
    stats["transactions_by_category"] = {ligne["category"]: ligne["nb"] for ligne in categories}
    return stats


@app.get("/predict", response_model=Prediction, tags=["Modèle"])
def predire(
    amount: float = Query(..., gt=0, description="Montant de la transaction, en euros", examples=[450.0]),
    hour: int = Query(..., ge=0, le=23, description="Heure de la transaction, de 0 à 23", examples=[2]),
):
    """Prédit si une transaction est frauduleuse, à partir de son montant et de son heure."""
    modele = charger_modele()
    # Colonne 1 : probabilité de la classe 1, c'est-à-dire « fraude »
    probabilite = float(modele.predict_proba([[amount, hour]])[0][1])
    return {"is_fraud": probabilite >= 0.5, "fraud_probability": round(probabilite, 2)}

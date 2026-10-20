# Projet fil rouge Docker : solution

🇬🇧 *English version: branch [`main`](https://github.com/DataScientest/DS-Docker-Course-Solution/tree/main).*

Le projet final du module Docker : une API de transactions clients et de détection de fraude, découpée en trois conteneurs reliés par Docker Compose.

Le point de départ des apprenants se trouve dans le dépôt [DS-Docker-Course-Architecture](https://github.com/DataScientest/DS-Docker-Course-Architecture/tree/fr) (branche `fr`).

| Service | Rôle | Image |
|---|---|---|
| **`db`** | Base MariaDB, initialisée au premier démarrage avec 1 000 transactions clients fictives | Construite à partir de l'image officielle `mariadb:12.3` (`db/Dockerfile`) |
| **`train`** | Traitement ponctuel : lit les transactions, entraîne un modèle KNN de détection de fraude, l'enregistre, puis s'arrête | Construite à partir de `python:3.13-slim` (`train/Dockerfile`) |
| **`api`** | API FastAPI : transactions, statistiques et prédictions du modèle | Construite à partir de `python:3.13-slim` (`api/Dockerfile`) |

```
navigateur ──port 8000──▶ api ─────── SQL ───────▶ db ──▶ volume db_data
                           ▲                       ▲
                           │ lit le modèle         │ lit les transactions
                           │                       │
                     volume models ◀── écrit ─── train
```

## Lancer le projet

Il suffit d'avoir Docker. Depuis la racine du dépôt :

**1. Créez le fichier `.env`**, qui contient les mots de passe, à partir du modèle fourni :

```bash
cp .env.example .env              # PowerShell : Copy-Item .env.example .env
```

Les valeurs du modèle conviennent pour un essai local.

**2. Construisez les images et démarrez le projet** :

```bash
docker compose up -d --build
```

Au premier lancement, Compose démarre la base, qui crée la table et y charge le CSV. Une fois la base prête (`healthy`), il lance l'entraînement du modèle, puis l'API une fois l'entraînement terminé avec succès. Comptez quelques dizaines de secondes. Ensuite :

- http://localhost:8000/docs affiche la documentation interactive de l'API ;
- http://localhost:8000/stats indique `"nb_transactions": 1000` ;
- http://localhost:8000/predict?amount=450&hour=2 renvoie `{"is_fraud":true,"fraud_probability":1.0}`.

**3. Pour arrêter le projet** : `docker compose down`. Les données et le modèle sont conservés dans leurs volumes. Pour tout supprimer, volumes compris : `docker compose down -v`.

## Architecture

```
DS-Docker-Course-Solution/
├── api/                          service api
│   ├── main.py                   l'application FastAPI
│   ├── requirements.txt          ses dépendances, dont scikit-learn pour lire le modèle
│   ├── Dockerfile
│   └── .dockerignore
├── db/                           service db
│   ├── Dockerfile                image officielle de MariaDB + scripts + données initiales
│   ├── init/
│   │   └── 01_transactions.sql   exécuté au premier démarrage : crée la table, charge le CSV
│   └── data/
│       └── transactions.csv      les données initiales
├── train/                        service train
│   ├── train.py                  l'entraînement du modèle KNN
│   ├── requirements.txt          ses dépendances, avec la même version de scikit-learn que l'API
│   ├── Dockerfile
│   └── .dockerignore
├── compose.yaml                  les trois services, leurs volumes et leur ordre de démarrage
├── .env.example                  modèle du fichier .env (mots de passe)
├── .gitignore
└── .gitattributes
```

Cette organisation suit six principes :

1. **Un dossier par service**, qui porte le nom du service et regroupe son code, ses dépendances et son Dockerfile. Ce dossier est le contexte de construction de l'image : seul son contenu peut y être copié.
2. **Chaque service a son image, même la base.** `db/Dockerfile` part de l'image officielle de MariaDB et y ajoute ce qui est propre au projet : les scripts d'initialisation (`init/`) et les données initiales (`data/`). L'image se suffit à elle-même : elle fonctionne sur n'importe quelle machine, sans dépendre de fichiers extérieurs.
3. **Les images contiennent le code, les volumes contiennent l'état.** La base vivante est dans le volume `db_data`, le modèle entraîné dans le volume `models`. Supprimer ou recréer un conteneur ne fait rien perdre.
4. **La configuration passe par des variables d'environnement**, définies dans `compose.yaml` : la même image fonctionne avec une autre base ou un autre emplacement de modèle, sans reconstruction.
5. **Les secrets ne vont ni dans les images, ni dans Git.** Les mots de passe sont dans `.env`, exclu de Git par `.gitignore`, et chaque contexte de construction a son `.dockerignore`.
6. **Les versions sont figées partout** : images de base (`python:3.13-slim`, `mariadb:12.3`) et librairies (`requirements.txt`). En particulier, `train` et `api` utilisent exactement la même version de scikit-learn : un modèle enregistré avec une version et relu avec une autre peut donner des résultats faux.

## Les fichiers Docker en détail

### `db/Dockerfile`

- `FROM mariadb:12.3` : l'image hérite de tout ce que définit l'image officielle, dont sa commande de démarrage (d'où l'absence de `CMD`), son port 3306 et son volume `/var/lib/mysql`.
- `COPY init/ /docker-entrypoint-initdb.d/` : l'image officielle exécute les scripts de ce dossier au premier démarrage, uniquement si la base n'existe pas encore (volume vide), par ordre alphabétique.
- `COPY data/ /data/` : le CSV, lu par `01_transactions.sql` avec `LOAD DATA INFILE '/data/transactions.csv'`.

### `api/Dockerfile` et `train/Dockerfile`

- Les dépendances sont copiées et installées **avant** le code : tant que `requirements.txt` ne change pas, cette couche reste en cache, et une modification du code ne réinstalle pas les librairies.
- `COPY . .` copie tout le dossier du service, sauf ce qu'exclut son `.dockerignore` (secrets, environnements virtuels, fichiers générés par Python).
- API : `EXPOSE 8000` documente le port, que `ports:` publie réellement. `--host 0.0.0.0` est indispensable : sur `127.0.0.1`, uvicorn n'accepterait que les connexions venues de l'intérieur du conteneur.
- Entraînement : pas de port. Le conteneur exécute `python train.py`, puis s'arrête avec le code 0 : c'est le comportement attendu d'un traitement ponctuel.

### `compose.yaml`

- **`name: fil-rouge`** fixe le nom du projet : les conteneurs s'appellent `fil-rouge-db-1`, `fil-rouge-train-1` et `fil-rouge-api-1`, les volumes `fil-rouge_db_data` et `fil-rouge_models`, le réseau `fil-rouge_default`.
- **`build`** : chaque service est construit à partir de son dossier ; Compose nomme les images d'après le projet et le service (`fil-rouge-db`, `fil-rouge-train`, `fil-rouge-api`).
- **Réseau** : chaque service est joignable par son nom. `DB_HOST` vaut donc `db` (dans un conteneur, `localhost` désignerait le conteneur lui-même). Le port 3306 de la base n'est pas publié : seuls les conteneurs du projet y accèdent.
- **Volumes** : `db_data` conserve la base ; `models` est partagé entre `train`, qui y écrit le modèle, et `api`, qui le lit en lecture seule (`:ro`). `MODEL_PATH` indique aux deux programmes le chemin du fichier dans ce volume.
- **Ordre de démarrage** : le `healthcheck` de la base utilise le script `healthcheck.sh`, fourni par l'image MariaDB, qui ne la déclare en bonne santé que lorsqu'elle accepte les connexions. `train` attend cette condition (`service_healthy`), et `api` attend en plus que `train` se soit terminé avec succès (`service_completed_successfully`).
- **Variables `${…}`** : Compose les remplace par les valeurs du fichier `.env`. Une seule variable, `DB_PASSWORD`, alimente la base et les deux programmes : les mots de passe ne peuvent pas diverger. `docker compose config` affiche le résultat.

## Vérifier que tout fonctionne

```bash
docker compose ps -a                 # db « (healthy) », api « Up », train « Exited (0) »
docker compose logs train            # « Modèle KNN (k = 5) entraîné sur 1000 transactions, dont 77 fraudes. »
curl http://localhost:8000/health/db # {"status":"ok","database":"fil_rouge","nb_transactions":1000}
curl "http://localhost:8000/predict?amount=42.5&hour=14"   # {"is_fraud":false,"fraud_probability":0.0}
docker compose exec db mariadb -u api -papipass fil_rouge -e "SELECT COUNT(*) FROM transactions;"
```

Sous Windows PowerShell, remplacez `curl` par `curl.exe`.

## Les routes de l'API

| Route | Rôle |
|---|---|
| `GET /` | Message d'accueil |
| `GET /info` | Environnement d'exécution : nom du conteneur, version de Python, base configurée ou non |
| `GET /health` | L'API répond-elle ? (sans interroger la base) |
| `GET /health/db` | La base est-elle joignable ? Nombre de transactions |
| `GET /transactions` | Liste des transactions, paginée (`limit`, `offset`) et filtrable (`customer_id`, `category`) |
| `GET /transactions/{transaction_id}` | Une transaction |
| `GET /customers/{customer_id}/summary` | Résumé de l'activité d'un client |
| `GET /stats` | Statistiques globales |
| `GET /predict?amount=…&hour=…` | Prédiction du modèle : la transaction est-elle frauduleuse ? |

Le modèle est un KNN (k = 5) entraîné sur le montant et l'heure des transactions : `fraud_probability` est la part de fraudes parmi les 5 transactions connues les plus proches. Dans ces données fictives, la fraude se concentre la nuit et sur les gros montants.

## Correspondance avec le cours

| Fichier | Étape du cours |
|---|---|
| `api/Dockerfile`, `api/.dockerignore` | 4 : conteneuriser l'API |
| `db/Dockerfile` | 5 : ajouter une base MariaDB et un volume |
| `compose.yaml` (services `db` et `api`) | 6 : tout relier avec Docker Compose |
| `.env.example` et variables `${…}` | 6 : bonus, sortir les mots de passe du fichier Compose |
| `train/Dockerfile`, `train/.dockerignore`, service `train`, volume `models`, `api/requirements.txt` | 8 : servir un modèle |

La solution de l'exercice de l'étape 2 (le premier Dockerfile) se trouve dans le cours.

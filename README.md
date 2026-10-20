# Docker running project: solution

🇫🇷 *Version française : branche [`fr`](https://github.com/DataScientest/DS-Docker-Course-Solution/tree/fr).*

The final project of the Docker module: a customer transactions and fraud detection API, split into three containers connected by Docker Compose.

The learners' starting point is in the [DS-Docker-Course-Architecture](https://github.com/DataScientest/DS-Docker-Course-Architecture) repository.

| Service | Role | Image |
|---|---|---|
| **`db`** | MariaDB database, initialized on first startup with 1,000 fictitious customer transactions | Built from the official `mariadb:12.3` image (`db/Dockerfile`) |
| **`train`** | One-off job: reads the transactions, trains a KNN fraud detection model, saves it, then stops | Built from `python:3.13-slim` (`train/Dockerfile`) |
| **`api`** | FastAPI API: transactions, statistics and model predictions | Built from `python:3.13-slim` (`api/Dockerfile`) |

```
browser ──port 8000──▶ api ─────── SQL ───────▶ db ──▶ volume db_data
                        ▲                       ▲
                        │ reads the model       │ reads the transactions
                        │                       │
                  volume models ◀── writes ── train
```

## Running the project

All you need is Docker. From the root of the repository:

**1. Create the `.env` file**, which holds the passwords, from the provided template:

```bash
cp .env.example .env              # PowerShell: Copy-Item .env.example .env
```

The template's values are fine for a local test.

**2. Build the images and start the project**:

```bash
docker compose up -d --build
```

On first start, Compose starts the database, which creates the table and loads the CSV into it. Once the database is ready (`healthy`), it runs the model training, then the API once the training has completed successfully. Allow a few dozen seconds. Then:

- http://localhost:8000/docs displays the interactive documentation of the API;
- http://localhost:8000/stats shows `"nb_transactions": 1000`;
- http://localhost:8000/predict?amount=450&hour=2 returns `{"is_fraud":true,"fraud_probability":1.0}`.

**3. To stop the project**: `docker compose down`. The data and the model are kept in their volumes. To delete everything, volumes included: `docker compose down -v`.

## Architecture

```
DS-Docker-Course-Solution/
├── api/                          api service
│   ├── main.py                   the FastAPI application
│   ├── requirements.txt          its dependencies, including scikit-learn to read the model
│   ├── Dockerfile
│   └── .dockerignore
├── db/                           db service
│   ├── Dockerfile                official MariaDB image + scripts + initial data
│   ├── init/
│   │   └── 01_transactions.sql   run on first startup: creates the table, loads the CSV
│   └── data/
│       └── transactions.csv      the initial data
├── train/                        train service
│   ├── train.py                  the KNN model training
│   ├── requirements.txt          its dependencies, with the same scikit-learn version as the API
│   ├── Dockerfile
│   └── .dockerignore
├── compose.yaml                  the three services, their volumes and their startup order
├── .env.example                  template for the .env file (passwords)
├── .gitignore
└── .gitattributes
```

This structure follows six principles:

1. **One folder per service**, named after the service, which groups its code, its dependencies and its Dockerfile. This folder is the image's build context: only its contents can be copied into the image.
2. **Each service has its own image, even the database.** `db/Dockerfile` starts from the official MariaDB image and adds what is specific to the project: the initialization scripts (`init/`) and the initial data (`data/`). The image is self-contained: it works on any machine, without depending on external files.
3. **Images hold the code, volumes hold the state.** The live database is in the `db_data` volume, the trained model in the `models` volume. Deleting or recreating a container loses nothing.
4. **Configuration goes through environment variables**, defined in `compose.yaml`: the same image works with another database or another model location, without rebuilding.
5. **Secrets go neither into images nor into Git.** The passwords are in `.env`, excluded from Git by `.gitignore`, and each build context has its `.dockerignore`.
6. **Versions are pinned everywhere**: base images (`python:3.13-slim`, `mariadb:12.3`) and libraries (`requirements.txt`). In particular, `train` and `api` use exactly the same scikit-learn version: a model saved with one version and loaded with another can give wrong results.

## The Docker files in detail

### `db/Dockerfile`

- `FROM mariadb:12.3`: the image inherits everything the official image defines, including its startup command (hence no `CMD`), its port 3306 and its `/var/lib/mysql` volume.
- `COPY init/ /docker-entrypoint-initdb.d/`: the official image runs the scripts in this folder on first startup, only if the database does not exist yet (empty volume), in alphabetical order.
- `COPY data/ /data/`: the CSV, read by `01_transactions.sql` with `LOAD DATA INFILE '/data/transactions.csv'`.

### `api/Dockerfile` and `train/Dockerfile`

- The dependencies are copied and installed **before** the code: as long as `requirements.txt` does not change, this layer stays cached, and a code change does not reinstall the libraries.
- `COPY . .` copies the whole service folder, except what its `.dockerignore` excludes (secrets, virtual environments, files generated by Python).
- API: `EXPOSE 8000` documents the port, which `ports:` actually publishes. `--host 0.0.0.0` is essential: on `127.0.0.1`, uvicorn would only accept connections coming from inside the container.
- Training: no port. The container runs `python train.py`, then stops with code 0: this is the expected behavior of a one-off job.

### `compose.yaml`

- **`name: ds-project`** sets the project name: the containers are called `ds-project-db-1`, `ds-project-train-1` and `ds-project-api-1`, the volumes `ds-project_db_data` and `ds-project_models`, the network `ds-project_default`.
- **`build`**: each service is built from its folder; Compose names the images after the project and the service (`ds-project-db`, `ds-project-train`, `ds-project-api`).
- **Network**: each service can be reached by its name. `DB_HOST` is therefore `db` (inside a container, `localhost` would mean the container itself). The database's port 3306 is not published: only the project's containers access it.
- **Volumes**: `db_data` keeps the database; `models` is shared between `train`, which writes the model to it, and `api`, which reads it in read-only mode (`:ro`). `MODEL_PATH` tells both programs the path of the file in this volume.
- **Startup order**: the database `healthcheck` uses the `healthcheck.sh` script, provided by the MariaDB image, which only reports it healthy once it accepts connections. `train` waits for this condition (`service_healthy`), and `api` additionally waits for `train` to complete successfully (`service_completed_successfully`).
- **`${…}` variables**: Compose replaces them with the values from the `.env` file. A single variable, `DB_PASSWORD`, feeds the database and both programs: the passwords cannot diverge. `docker compose config` displays the result.

## Checking that everything works

```bash
docker compose ps -a                 # db "(healthy)", api "Up", train "Exited (0)"
docker compose logs train            # "KNN model (k = 5) trained on 1000 transactions, including 77 frauds."
curl http://localhost:8000/health/db # {"status":"ok","database":"ds_project","nb_transactions":1000}
curl "http://localhost:8000/predict?amount=42.5&hour=14"   # {"is_fraud":false,"fraud_probability":0.0}
docker compose exec db mariadb -u api -papipass ds_project -e "SELECT COUNT(*) FROM transactions;"
```

On Windows PowerShell, replace `curl` with `curl.exe`.

## The API routes

| Route | Role |
|---|---|
| `GET /` | Welcome message |
| `GET /info` | Runtime environment: container name, Python version, database configured or not |
| `GET /health` | Does the API respond? (without querying the database) |
| `GET /health/db` | Is the database reachable? Number of transactions |
| `GET /transactions` | List of transactions, paginated (`limit`, `offset`) and filterable (`customer_id`, `category`) |
| `GET /transactions/{transaction_id}` | One transaction |
| `GET /customers/{customer_id}/summary` | Summary of a customer's activity |
| `GET /stats` | Overall statistics |
| `GET /predict?amount=…&hour=…` | Model prediction: is the transaction fraudulent? |

The model is a KNN (k = 5) trained on the amount and hour of the transactions: `fraud_probability` is the share of frauds among the 5 closest known transactions. In this fictitious data, fraud is concentrated at night and on large amounts.

## Mapping to the course

| File | Course step |
|---|---|
| `api/Dockerfile`, `api/.dockerignore` | 4: containerize the API |
| `db/Dockerfile` | 5: add a MariaDB database and a volume |
| `compose.yaml` (`db` and `api` services) | 6: connect everything with Docker Compose |
| `.env.example` and `${…}` variables | 6: bonus, move the passwords out of the Compose file |
| `train/Dockerfile`, `train/.dockerignore`, `train` service, `models` volume, `api/requirements.txt` | 8: serve a model |

The solution to the step 2 exercise (the first Dockerfile) is in the course.

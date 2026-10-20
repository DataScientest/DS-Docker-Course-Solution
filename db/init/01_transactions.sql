-- ============================================================================
-- Initialisation de la base du projet fil rouge
--
-- Ce script crée la table `transactions`, puis y charge le fichier
-- transactions.csv. L'image officielle MariaDB l'exécute automatiquement au
-- premier démarrage du conteneur (quand la base n'existe pas encore), à
-- condition que :
--   - ce script se trouve dans le dossier /docker-entrypoint-initdb.d du conteneur ;
--   - le fichier de données se trouve dans /data/transactions.csv.
-- Les scripts de /docker-entrypoint-initdb.d sont exécutés par ordre
-- alphabétique : le préfixe 01_ fixe leur ordre.
-- ============================================================================

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id   INT           NOT NULL PRIMARY KEY,
    transaction_date DATETIME      NOT NULL,
    customer_id      VARCHAR(10)   NOT NULL,
    amount           DECIMAL(10,2) NOT NULL,
    category         VARCHAR(30)   NOT NULL,
    payment_method   VARCHAR(20)   NOT NULL,
    is_fraud         TINYINT(1)    NOT NULL DEFAULT 0,
    INDEX idx_customer (customer_id)
) DEFAULT CHARSET = utf8mb4;

-- Chargement du CSV : séparateur virgule, une transaction par ligne,
-- la première ligne (les noms de colonnes) est ignorée.
LOAD DATA INFILE '/data/transactions.csv'
INTO TABLE transactions
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(transaction_id, transaction_date, customer_id, amount, category, payment_method, @is_fraud)
-- Retire un éventuel retour chariot Windows (\r) en fin de ligne
SET is_fraud = TRIM(TRAILING '\r' FROM @is_fraud);

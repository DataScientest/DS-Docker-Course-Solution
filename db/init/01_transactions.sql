-- ============================================================================
-- Initialization of the running project's database
--
-- This script creates the `transactions` table, then loads the
-- transactions.csv file into it. The official MariaDB image runs it
-- automatically the first time the container starts (when the database does
-- not exist yet), provided that:
--   - this script is in the container's /docker-entrypoint-initdb.d folder;
--   - the data file is at /data/transactions.csv.
-- The scripts in /docker-entrypoint-initdb.d are run in alphabetical
-- order: the 01_ prefix sets their order.
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

-- Loading the CSV: comma separator, one transaction per line,
-- the first line (the column names) is skipped.
LOAD DATA INFILE '/data/transactions.csv'
INTO TABLE transactions
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(transaction_id, transaction_date, customer_id, amount, category, payment_method, @is_fraud)
-- Removes a possible Windows carriage return (\r) at the end of the line
SET is_fraud = TRIM(TRAILING '\r' FROM @is_fraud);

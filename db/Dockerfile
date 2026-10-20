# Base image: the official MariaDB image.
# Our image inherits everything from it: the server, its startup command (no need for CMD),
# its port 3306 and its /var/lib/mysql volume.
FROM mariadb:12.3

# Scripts run automatically on first startup, when the database is empty
COPY init/ /docker-entrypoint-initdb.d/

# Initial data, loaded by the initialization script
COPY data/ /data/

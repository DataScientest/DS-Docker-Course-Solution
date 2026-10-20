# Image de base : l'image officielle de MariaDB.
# Notre image en hérite tout : le serveur, sa commande de démarrage (pas besoin de CMD),
# son port 3306 et son volume /var/lib/mysql.
FROM mariadb:12.3

# Scripts exécutés automatiquement au premier démarrage, quand la base est vide
COPY init/ /docker-entrypoint-initdb.d/

# Données initiales, chargées par le script d'initialisation
COPY data/ /data/

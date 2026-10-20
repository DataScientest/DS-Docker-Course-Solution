# Image de base : la même que celle de l'API
FROM python:3.13-slim

# Dossier de travail dans l'image
WORKDIR /app

# Les dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Puis le code
COPY . .

# Un traitement ponctuel, pas un serveur : pas de port à documenter.
# Le conteneur s'arrête (code 0) une fois le modèle enregistré.
CMD ["python", "train.py"]

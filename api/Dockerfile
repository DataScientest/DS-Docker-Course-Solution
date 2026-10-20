# Image de base : Python 3.13 en version allégée
FROM python:3.13-slim

# Dossier de travail dans l'image
WORKDIR /app

# Les dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Puis le code de l'application
COPY . .

# Port sur lequel l'API écoute (simple documentation, ne publie rien)
EXPOSE 8000

# Lancement de l'API. --host 0.0.0.0 : accepter les connexions venant de l'extérieur du conteneur
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

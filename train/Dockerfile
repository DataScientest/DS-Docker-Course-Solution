# Base image: the same as the API's
FROM python:3.13-slim

# Working directory in the image
WORKDIR /app

# Dependencies first: this layer stays cached as long as requirements.txt does not change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the code
COPY . .

# A one-off job, not a server: no port to document.
# The container stops (code 0) once the model is saved.
CMD ["python", "train.py"]

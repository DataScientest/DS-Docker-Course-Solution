# Base image: Python 3.13, lightweight version
FROM python:3.13-slim

# Working directory in the image
WORKDIR /app

# Dependencies first: this layer stays cached as long as requirements.txt does not change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the application code
COPY . .

# Port the API listens on (documentation only, publishes nothing)
EXPOSE 8000

# Start the API. --host 0.0.0.0: accept connections coming from outside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

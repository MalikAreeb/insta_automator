# Dockerfile
FROM python:3.11-slim

# Install poppler-utils for pdftotext
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT environment variable
CMD ["python", "app.py"]
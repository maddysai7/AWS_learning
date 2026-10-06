FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# DevSecOps Best Practice: Create non-root user and drop privileges
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

# Run with Gunicorn production WSGI server
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]

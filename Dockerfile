FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project code
COPY . /app/

# Make entrypoint executable
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT [/app/docker/entrypoint.sh]
CMD [gunicorn, --bind, 0.0.0.0:8000, --workers, 3, --timeout, 120, config.wsgi:application]

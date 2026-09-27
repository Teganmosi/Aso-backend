#!/bin/sh
set -e

if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
  echo "Waiting for PostgreSQL database at ${DB_HOST}:${DB_PORT}..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
  done
  echo "PostgreSQL is ready!"
fi

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Seeding/updating marketplace categories..."
python manage.py seed_categories || true

echo "Collecting static files..."
python manage.py collectstatic --noinput || true

exec "$@"

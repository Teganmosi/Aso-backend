#!/bin/sh
set -e

echo Waiting for PostgreSQL database to be ready...
while ! nc -z  ; do
  sleep 1
done
echo PostgreSQL is ready!

echo Applying database migrations...
python manage.py migrate --noinput

echo Collecting static files...
python manage.py collectstatic --noinput || true

exec $@

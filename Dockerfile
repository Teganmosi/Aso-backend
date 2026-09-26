FROM postgres:16-alpine

# Set default locale & time zone to Nigerian/Lagos
ENV TZ=Africa/Lagos
ENV LANG=en_US.utf8

# Copy custom initialization scripts for extensions and permissions
COPY docker/01-init.sql /docker-entrypoint-initdb.d/01-init.sql

# Expose standard PostgreSQL port
EXPOSE 5432

# Health check to ensure PostgreSQL is ready to accept connections
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD pg_isready -U "${POSTGRES_USER:-aso_user}" -d "${POSTGRES_DB:-aso_db}" || exit 1

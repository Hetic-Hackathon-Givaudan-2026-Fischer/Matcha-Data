# API Data FlavorTrends (FastAPI) + pipeline de collecte, dans une image Python légère.
# Construction : docker compose build      Lancement : docker compose up api
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1. Dépendances d'abord (couche mise en cache tant que pyproject.toml ne change pas)
COPY pyproject.toml ./
COPY src/flavortrends/__init__.py src/flavortrends/__init__.py
RUN pip install -e ".[spike]"

# 2. Code et données publiables (jamais .env : voir .dockerignore)
#    Installation « éditable » obligatoire : le code retrouve data/ et taxonomy/ à partir de /app.
COPY src ./src
COPY taxonomy ./taxonomy
COPY config ./config
COPY migrations ./migrations
COPY data/sample ./data/sample
RUN pip install -e ".[spike]" --no-deps

# Utilisateur sans droits root
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["flavortrends"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]

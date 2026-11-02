ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Utilisateur sans droits : le conteneur ne tourne pas en root
RUN useradd --create-home --uid 10001 appuser

# Les dépendances d'abord, pour profiter du cache quand seul le code change
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=appuser:appuser . .

USER appuser

# Cloud Run fournit la variable PORT (8080 par défaut)
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
# ---- Etapa base ----
FROM python:3.11-slim

# Evita archivos .pyc y activa salida sin buffer (logs en tiempo real en Cloud Run)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero (capa cacheada mientras requirements no cambie)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Cloud Run inyecta la variable PORT; gunicorn escucha en ella (8080 por defecto)
EXPOSE 8080

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120 app:app"]

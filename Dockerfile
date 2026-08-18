# CivicLens Ethiopia — API + built frontend in one image (worker uses same image)
FROM node:20-alpine AS webbuild
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]"
COPY backend/ ./
COPY --from=webbuild /web/dist ../frontend/dist
RUN useradd -r -u 10001 civiclens && mkdir -p /data/storage && chown -R civiclens /app /data/storage
USER civiclens
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import httpx;httpx.get('http://127.0.0.1:8000/api/health',timeout=4).raise_for_status()"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

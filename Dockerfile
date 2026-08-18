# CivicLens Ethiopia — API + built frontend in one image (worker uses same image)
#
# Runs anywhere Docker runs: docker compose, Render, Railway, Fly.io, a VPS…
# Honors the platform-injected $PORT (defaults to 8000) via docker-entrypoint.sh.
FROM node:20-alpine AS webbuild
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# VITE_API_BASE is only needed for SPLIT deployments (SPA on another origin);
# for this all-in-one image the SPA talks to the same origin, so leave empty.
ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]" boto3
COPY backend/ ./
COPY --from=webbuild /web/dist ../frontend/dist
RUN chmod +x docker-entrypoint.sh && \
    useradd -r -u 10001 civiclens && mkdir -p /data/storage && chown -R civiclens /app /data/storage
USER civiclens
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import httpx,os;httpx.get(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/api/health',timeout=4).raise_for_status()"
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["api"]

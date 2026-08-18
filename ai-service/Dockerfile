FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./
RUN useradd -r -u 10002 civiclens-ai
USER civiclens-ai
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import httpx,os;httpx.get(f'http://127.0.0.1:{os.environ.get(\"PORT\",8090)}/health',timeout=4).raise_for_status()"
EXPOSE 8090
# Honors platform-injected $PORT (Render/Railway/Fly), defaults to 8090.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8090}"]

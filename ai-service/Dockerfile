FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./
RUN useradd -r -u 10002 civiclens-ai
USER civiclens-ai
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import httpx;httpx.get('http://127.0.0.1:8090/health',timeout=4).raise_for_status()"
EXPOSE 8090
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]

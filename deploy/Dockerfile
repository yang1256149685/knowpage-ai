FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt && useradd --create-home appuser && mkdir /app/data && chown appuser:appuser /app/data
COPY --chown=appuser:appuser server server
COPY --chown=appuser:appuser web web
USER appuser
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=3)"
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]

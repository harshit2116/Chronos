FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHRONOS_RUNS_DIR=/data/runs
WORKDIR /app
RUN groupadd --gid 10001 chronos \
    && useradd --uid 10001 --gid chronos --no-create-home chronos \
    && mkdir -p /data/runs && chown -R chronos:chronos /data
COPY --chown=chronos:chronos chronos/ ./chronos/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "chronos.web", "--host", "0.0.0.0", "--port", "8000"]

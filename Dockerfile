# API image: FastAPI + agent. Multi-stage; models are baked in so containers start without downloads.

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .
# Pre-download the embedding and rerank models into the image.
COPY corpus/processed ./corpus/processed
RUN FASTEMBED_CACHE=/opt/models python -c "\
from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; \
TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/models'); \
TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2', cache_dir='/opt/models')"

FROM python:3.12-slim AS runtime
ARG GIT_SHA=dev
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=prod APP_RELEASE=${GIT_SHA} \
    CACHE_DIR=/data/cache DATABASE_URL=sqlite:////data/app.db \
    HF_HUB_OFFLINE=1
RUN useradd --create-home --uid 10001 app && mkdir -p /data/cache && chown -R app /data
COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=app /opt/models /data/cache/fastembed
WORKDIR /srv
COPY --chown=app app ./app
COPY --chown=app corpus/processed ./corpus/processed
COPY --chown=app corpus/sources.yaml ./corpus/sources.yaml
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]

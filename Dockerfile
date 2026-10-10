FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58
ENV PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /workspace
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    tesseract-ocr=5.3.0-2 tesseract-ocr-heb=1:4.1.0-2 poppler-utils=22.12.0-2+deb12u3 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --group dev
RUN useradd --uid 10001 --create-home pinui && mkdir -p /runtime /data/raw \
    && chown -R pinui:pinui /workspace /runtime /data
COPY --chown=pinui:pinui config ./config
COPY --chown=pinui:pinui app ./app
COPY --chown=pinui:pinui ui ./ui
COPY --chown=pinui:pinui scripts ./scripts
COPY --chown=pinui:pinui tests ./tests
COPY --chown=pinui:pinui benchmarks ./benchmarks
COPY --chown=pinui:pinui migrations ./migrations
COPY --chown=pinui:pinui alembic.ini ./alembic.ini
USER pinui
ENV PATH="/workspace/.venv/bin:$PATH"
CMD ["uvicorn", "app.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

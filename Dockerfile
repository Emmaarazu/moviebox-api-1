FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MOVIEBOX_DOWNLOAD_DIR=/downloads \
    MOVIEBOX_DOWNLOAD_ROOT=/downloads

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install ".[cli]" fastapi uvicorn \
    && mkdir -p /downloads

COPY docker/moviebox_service.py /app/moviebox_service.py
COPY docker/entrypoint.sh /usr/local/bin/moviebox-entrypoint

RUN chmod +x /usr/local/bin/moviebox-entrypoint

WORKDIR /downloads

EXPOSE 8095

ENTRYPOINT ["moviebox-entrypoint"]
CMD ["api"]

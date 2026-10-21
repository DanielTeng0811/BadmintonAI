FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58
RUN uv pip install --system --no-cache "aiohttp==3.14.5"
WORKDIR /app
COPY . /app/local_auth
RUN useradd -m -u 1000 app && mkdir -p /data && chown app:app /data
USER app
CMD ["python3", "-m", "local_auth.server"]

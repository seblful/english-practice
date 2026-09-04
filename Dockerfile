FROM python:3.13-slim

# uv installs from uv.lock, so the image cannot drift from the manifests.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependencies alone, for one package, so source edits do not rebuild them.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml ./packages/core/
COPY packages/runtime/pyproject.toml ./packages/runtime/
COPY packages/bot/pyproject.toml ./packages/bot/
COPY packages/extraction/pyproject.toml ./packages/extraction/
RUN uv sync --frozen --no-dev --package english-practice-bot --no-install-workspace

# Then the source, and the local packages on top of it.
COPY . .
RUN uv sync --frozen --no-dev --package english-practice-bot

# Into /app/.venv as a real distribution, which metadata.version() needs.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# The console script, so the container runs a developer's entry point.
CMD ["english-practice", "bot"]

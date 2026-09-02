FROM python:3.13-slim

# uv installs from uv.lock, so the image can never drift from the manifests the
# way a hand-written pip list did.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# The repository is a uv workspace, and this image is one package of it.
# `--package english-practice-bot` resolves that package's dependencies only,
# which is why nothing here installs OpenCV, PyMuPDF or an OCR client: those
# belong to the offline content pipeline, and the bot never calls them.
#
# Dependency layer first, from the manifests alone — `--no-install-workspace`
# builds none of the local packages, so editing their source does not
# invalidate the slow third-party install below it.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml ./packages/core/
COPY packages/runtime/pyproject.toml ./packages/runtime/
COPY packages/bot/pyproject.toml ./packages/bot/
COPY packages/extraction/pyproject.toml ./packages/extraction/
RUN uv sync --frozen --no-dev --package english-practice-bot --no-install-workspace

# Then the source, and the local packages on top of it.
COPY . .
RUN uv sync --frozen --no-dev --package english-practice-bot

# The project is installed into /app/.venv, which puts `practice_bot` on the
# path as a real distribution — importlib.metadata.version() needs that.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# The console script from packages/bot/pyproject.toml, so the container runs
# the same entry point a developer does.
CMD ["english-practice", "bot"]

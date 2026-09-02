FROM python:3.13-slim

# uv installs the project and its dependencies straight from uv.lock, so the
# image can never drift from pyproject.toml the way a hand-written pip list did.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency layer: only the files that affect resolution, so source edits
# don't invalidate the (slow) dependency install.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

COPY . .

# The project is installed into /app/.venv, which puts `english_practice` on the
# path as a real distribution — importlib.metadata.version() needs that.
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# The console script from pyproject.toml, so the container runs the same
# entry point a developer does.
CMD ["english-practice", "bot"]

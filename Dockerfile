FROM python:3.14-slim-bookworm@sha256:55e465cb7e50cd1d7217fcb5386aa87d0356ca2cd790872142ef68d9ef6812b4

COPY --from=ghcr.io/astral-sh/uv:latest@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 /uv /uvx /bin/

RUN useradd -m -s /bin/bash pwuser

WORKDIR /app
RUN chown pwuser:pwuser /app

COPY --chown=pwuser:pwuser . /app

# Install git (needed for git-based dependencies in pyproject.toml)
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (no browser — all API-based)
RUN uv sync --frozen

RUN chown -R pwuser:pwuser /app

USER pwuser

ENTRYPOINT ["uv", "run", "-m", "instagram_mcp_server"]
CMD []

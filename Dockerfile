FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --system --uid 10001 --create-home homelabpilot
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001

EXPOSE 8000
CMD ["homelabpilot-mcp"]

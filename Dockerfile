FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Copenhagen

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 1000 hygge

COPY messages.example ./messages.example
COPY config.example.yaml ./
RUN mkdir -p /app/data && chown -R hygge /app
USER hygge

# config.yaml, private/ et data/ sont montés par docker-compose
ENTRYPOINT ["hygge", "--config", "/app/config.yaml"]
CMD ["run"]

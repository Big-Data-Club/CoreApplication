ARG PG_MAJOR=18
FROM postgres:${PG_MAJOR}-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-psycopg2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY kube.py server.py runner.py replication.py endpoints.py ./
COPY static ./static
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
ENTRYPOINT []
CMD ["python3", "/app/server.py"]

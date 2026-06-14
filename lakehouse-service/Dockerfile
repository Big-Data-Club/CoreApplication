FROM python:3.12-slim

# Install system dependencies (build tools for packages if necessary)
RUN apk_add_if_needed="build-essential libgomp" && \
    apt-get update && apt-get install -y --no-install-recommends $apk_add_if_needed wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download DuckDB extensions to avoid runtime network download latency
RUN python -c "import duckdb; con = duckdb.connect(':memory:'); con.execute('INSTALL httpfs; INSTALL iceberg;')"

# Copy source code
COPY . .

# Run the processor
ENTRYPOINT ["python", "duckdb_processor.py"]

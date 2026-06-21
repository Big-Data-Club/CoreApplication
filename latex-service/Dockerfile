# --- Build stage ---
FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod ./
# Copy go.sum if it exists, otherwise go mod download will still work
COPY go.mod go.su[m] ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o api ./cmd/api

# --- Runtime stage ---
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Install TeX Live Full (~4.5GB) and basic utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-full \
    latexmk \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/api .
COPY --from=builder /app/migrations ./migrations
COPY --from=builder /app/templates ./templates

EXPOSE 8084
CMD ["./api"]

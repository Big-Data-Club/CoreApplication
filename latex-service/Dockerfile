ARG BASE_IMAGE=ubuntu:24.04

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
# To optimize build speed and support sub-second rebuilds, you can pre-build the latex-base image:
#   docker build -f Dockerfile.base -t bdc-latex-base:latest .
# And build this Dockerfile with:
#   docker build --build-arg BASE_IMAGE=bdc-latex-base:latest -t bdc-latex:latest .
FROM ${BASE_IMAGE}

# Redeclare the arg inside the stage to make it available in the RUN command
ARG BASE_IMAGE
ENV DEBIAN_FRONTEND=noninteractive

# Install TeX Live packages and basic utilities only if building from clean ubuntu:24.04
RUN if [ "${BASE_IMAGE}" = "ubuntu:24.04" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-science \
        texlive-xetex \
        texlive-luatex \
        latexmk \
        ca-certificates \
        tzdata \
        wget \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY --from=builder /app/api .
COPY --from=builder /app/migrations ./migrations
COPY --from=builder /app/templates ./templates

EXPOSE 8084
CMD ["./api"]

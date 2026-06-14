# Build stage
FROM golang:1.25-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git gcc musl-dev

# Set working directory
WORKDIR /build

# Copy go mod files
COPY go.mod ./
# Note: we do not copy go.sum initially as go mod init / tidy will generate it or we write a local tidy later.

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s" \
    -o streaming-server \
    .

# Runtime stage
FROM alpine:latest

# Install runtime dependencies
RUN apk --no-cache add ca-certificates tzdata wget

# Create app user
RUN addgroup -g 1000 app && \
    adduser -D -u 1000 -G app app

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/streaming-server .

# Create logs directory
RUN mkdir -p /app/logs && \
    chown -R app:app /app

# Switch to non-root user
USER app

# Expose port
EXPOSE 8085

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8085/health || exit 1

# Run the application
CMD ["./streaming-server"]

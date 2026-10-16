FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /farm ./cmd/api
FROM alpine:3.22
RUN apk add --no-cache ca-certificates && adduser -D -u 1001 farm
USER 1001
COPY --from=build /farm /usr/local/bin/farm
EXPOSE 8087
ENTRYPOINT ["farm"]

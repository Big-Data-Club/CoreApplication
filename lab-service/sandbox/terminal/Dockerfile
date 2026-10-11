# Build and publish under an immutable tag, then configure LAB_TERMINAL_SANDBOX_IMAGE.
FROM alpine:3.22
RUN apk add --no-cache bash git coreutils findutils grep sed gawk python3 jq \
    && addgroup -g 1000 student && adduser -D -u 1000 -G student student \
    && mkdir /workspace && chown 1000:1000 /workspace
USER 1000:1000
ENV HOME=/workspace TERM=xterm-256color
WORKDIR /workspace
CMD ["/bin/sh", "-c", "sleep 86400"]

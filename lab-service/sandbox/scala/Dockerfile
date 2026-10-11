FROM alpine:3.23 AS scala-dist

ARG SCALA_VERSION=2.13.16
ARG SCALA_SHA256=937f743be315302caad15be99ab1ca425ff7e63f15ef5790db6c81bb49543256

# Fetch the official release asset from GitHub: the legacy Lightbend download
# endpoint can reject CI requests with HTTP 403. Verify the pinned archive before
# it can enter a learner runtime; never download dependencies during execution.
RUN apk add --no-cache ca-certificates curl tar \
    && curl -fsSL --retry 3 --connect-timeout 15 --max-time 180 "https://github.com/scala/scala/releases/download/v${SCALA_VERSION}/scala-${SCALA_VERSION}.tgz" -o /tmp/scala.tgz \
    && echo "${SCALA_SHA256}  /tmp/scala.tgz" | sha256sum -c - \
    && tar -xzf /tmp/scala.tgz -C /opt \
    && mv "/opt/scala-${SCALA_VERSION}" /opt/scala

FROM eclipse-temurin:21-jdk-alpine-3.23

# Scala launchers require bash even though the base JDK image only has sh.
RUN apk add --no-cache bash

COPY --from=scala-dist /opt/scala /opt/scala
ENV PATH="/opt/scala/bin:${PATH}"

USER 1000:1000

FROM alpine:3.23 AS scala-dist

ARG SCALA_VERSION=2.13.16
ARG SCALA_SHA256=937f743be315302caad15be99ab1ca425ff7e63f15ef5790db6c81bb49543256

# Alpine no longer packages Scala. Fetch the official Scala distribution once
# at image-build time and verify it before it can enter a learner runtime.
RUN apk add --no-cache ca-certificates curl tar \
    && curl -fsSL "https://downloads.lightbend.com/scala/${SCALA_VERSION}/scala-${SCALA_VERSION}.tgz" -o /tmp/scala.tgz \
    && echo "${SCALA_SHA256}  /tmp/scala.tgz" | sha256sum -c - \
    && tar -xzf /tmp/scala.tgz -C /opt \
    && mv "/opt/scala-${SCALA_VERSION}" /opt/scala

FROM eclipse-temurin:21-jdk-alpine-3.23

COPY --from=scala-dist /opt/scala /opt/scala
ENV PATH="/opt/scala/bin:${PATH}"

USER 1000:1000

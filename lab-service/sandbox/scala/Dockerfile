FROM eclipse-temurin:21-jdk-alpine-3.23

# The compiler is baked into a platform-owned image at CI time. Learner Jobs
# never install packages or fetch dependencies, and the runtime invocation is
# still overridden by the controller's fixed command.
RUN apk add --no-cache scala

USER 1000:1000

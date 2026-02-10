FROM maven:3.9.4-eclipse-temurin-21-alpine AS builder
WORKDIR /build

COPY pom.xml .
RUN mvn dependency:go-offline -B

COPY src ./src
RUN mvn clean package -DskipTests -B && \
    java -Djarmode=layertools -jar target/*.jar extract

FROM eclipse-temurin:21-jdk-alpine AS jre-builder

COPY --from=builder /build/application/ /tmp/app/
COPY --from=builder /build/dependencies/ /tmp/app/
COPY --from=builder /build/spring-boot-loader/ /tmp/app/
COPY --from=builder /build/snapshot-dependencies/ /tmp/app/

RUN jdeps \
    --ignore-missing-deps \
    --print-module-deps \
    --multi-release 21 \
    --recursive \
    --class-path '/tmp/app/BOOT-INF/lib/*' \
    /tmp/app/BOOT-INF/classes > /tmp/modules.txt

RUN jlink \
    --add-modules $(cat /tmp/modules.txt),jdk.crypto.ec,jdk.localedata \
    --strip-debug \
    --no-man-pages \
    --no-header-files \
    --compress=2 \
    --output /javaruntime

FROM alpine:3.19
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

COPY --from=jre-builder /javaruntime $JAVA_HOME

RUN apk add --no-cache curl gcompat && \
    rm -rf /var/cache/apk/*

RUN addgroup -S spring && adduser -S spring -G spring
USER spring:spring
WORKDIR /app

COPY --from=builder --chown=spring:spring /build/dependencies/ ./
COPY --from=builder --chown=spring:spring /build/spring-boot-loader/ ./
COPY --from=builder --chown=spring:spring /build/snapshot-dependencies/ ./
COPY --from=builder --chown=spring:spring /build/application/ ./

ENV JAVA_OPTS="-XX:+UseContainerSupport \
    -XX:MaxRAMPercentage=75.0 \
    -XX:+UseSerialGC \
    -XX:MinHeapFreeRatio=20 \
    -XX:MaxHeapFreeRatio=40 \
    -Djava.security.egd=file:/dev/./urandom \
    -Dfile.encoding=UTF-8"

EXPOSE 8080

HEALTHCHECK --interval=600s --timeout=3s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS org.springframework.boot.loader.launch.JarLauncher"]
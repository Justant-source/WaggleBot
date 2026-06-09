FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /build
COPY . .
RUN chmod +x gradlew && ./gradlew --no-daemon bootJar -x test

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache nodejs npm && npm install -g @anthropic-ai/claude-code
COPY --from=build /build/build/libs/*.jar /app/app.jar
EXPOSE 8090
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

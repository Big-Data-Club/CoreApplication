FROM node:22-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
FROM node:22-alpine
ENV NODE_ENV=production PORT=8088
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY --chown=node:node src ./src
COPY --chown=node:node migrations ./migrations
USER node
EXPOSE 8088
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s CMD node -e "fetch('http://127.0.0.1:8088/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/main.mjs"]

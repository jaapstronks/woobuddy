# Stage 1: Build
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Run
FROM node:22-alpine

WORKDIR /app

COPY --from=build /app/build ./build
COPY --from=build /app/package.json ./package-lock.json ./
RUN npm ci --omit=dev

ENV NODE_ENV=production
ENV PORT=3000

USER node
EXPOSE 3000

CMD ["node", "build"]

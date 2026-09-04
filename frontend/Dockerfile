# Stage 1: Build
FROM node:26-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Self-hosted tesseract.js assets for in-browser OCR. `static/tesseract/` is
# gitignored (derivable, ~32 MB) and .dockerignore keeps it out of the build
# context, so the image has to produce it here or ship without an OCR worker,
# wasm core and Dutch model — OCR then fails at runtime with "taalmodule niet
# geinstalleerd". Copied ahead of the rest of the source so the layer is only
# invalidated by the script or the lockfile, not by every frontend edit.
#
# This step needs network access: the Dutch traineddata is fetched from the
# tesseract-ocr project's GitHub repo. Everything else comes from node_modules.
COPY scripts/download-tesseract-data.mjs ./scripts/
RUN npm run setup:tesseract

COPY . .

ARG PUBLIC_API_URL=http://localhost:8000
ENV PUBLIC_API_URL=$PUBLIC_API_URL

RUN npm run build

# Stage 2: Run
FROM node:26-alpine

WORKDIR /app

COPY --from=build /app/build ./build
COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev

ENV NODE_ENV=production
ENV PORT=3000

USER node
EXPOSE 3000

CMD ["node", "build"]

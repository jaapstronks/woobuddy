# Pinned to 3.12 on purpose. CI (.github/workflows/test.yml), mypy
# (pyproject.toml) and the site-packages path in the chown below all
# target 3.12. Dependabot bumped this to 3.14 in #64; back then nothing
# built the image in CI, so it merged green and the api image was
# unbuildable for four months -- `regex` ships no cp314 wheel and this
# slim image has no gcc to build one. The `Images build` job now catches
# that, but the chown below still hardcodes the version: move all four
# together, or not at all.
FROM python:3.12-slim

WORKDIR /app

# System dependencies for PyMuPDF
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmupdf-dev \
        && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY app/ ./app/

# Non-root user
RUN useradd --create-home appuser && \
    chown -R appuser /usr/local/lib/python3.12/site-packages/deduce/data/lookup/cache
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

#!/bin/sh
# Initialize MinIO: create the "documents" bucket if it doesn't exist.

set -e

# Configure the MinIO client alias
mc alias set woobuddy http://minio:9000 "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

# Create bucket if it doesn't already exist
if ! mc ls woobuddy/documents > /dev/null 2>&1; then
  mc mb woobuddy/documents
  echo "Bucket 'documents' created."
else
  echo "Bucket 'documents' already exists, skipping."
fi

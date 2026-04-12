# Third-Party Licenses

WOO Buddy is licensed under the MIT License. This file documents the licenses of key dependencies.

## Backend (Python)

| Package | License | Note |
|---------|---------|------|
| FastAPI | MIT | |
| Uvicorn | BSD-3-Clause | |
| PyMuPDF | AGPL-3.0 | Used as a pip dependency (not modified/redistributed as source). See [PyMuPDF licensing](https://pymupdf.readthedocs.io/en/latest/about.html#license). Commercial license available. |
| **Deduce** | **LGPL-3.0** | Used as a pip dependency. LGPL permits use in MIT-licensed projects when linked dynamically (standard pip install). The library is not modified. |
| SQLAlchemy | MIT | |
| Pydantic | MIT | |
| Alembic | MIT | |
| httpx | BSD-3-Clause | |
| Anthropic SDK | MIT | |

## Frontend (JavaScript/TypeScript)

| Package | License | Note |
|---------|---------|------|
| SvelteKit | MIT | |
| Svelte | MIT | |
| Tailwind CSS | MIT | |
| Shoelace | MIT | |
| Lucide | ISC | |
| pdf.js (pdfjs-dist) | Apache-2.0 | |

## Infrastructure

| Component | License | Note |
|-----------|---------|------|
| PostgreSQL | PostgreSQL License (BSD-like) | |
| MinIO | AGPL-3.0 | Used as a standalone service (not embedded). Network use does not trigger AGPL copyleft for WOO Buddy's code. |

## LLM Models

| Model | License | Note |
|-------|---------|------|
| Gemma 4 | Apache-2.0 | Fully open, no restrictions on use |

## Important notes

- **PyMuPDF (AGPL-3.0)**: WOO Buddy uses PyMuPDF as an unmodified pip dependency. If you modify PyMuPDF source code or distribute WOO Buddy as a combined work, AGPL-3.0 terms apply. A commercial license is available from Artifex Software for organizations that cannot comply with AGPL.
- **Deduce (LGPL-3.0)**: Compatible with MIT when used as a standard pip dependency. The LGPL requires that users can re-link against a different version of Deduce, which pip install satisfies by default.
- **MinIO (AGPL-3.0)**: Runs as a separate network service. WOO Buddy communicates with it via the S3 API. This does not create a combined/derivative work under AGPL.

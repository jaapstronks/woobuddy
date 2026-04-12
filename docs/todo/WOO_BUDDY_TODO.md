# WOO Buddy — Personal Todo List

Everything you need to do yourself. This assumes Claude Code handles the actual coding from the briefing, and the domain registration is already on your radar.

---

## 1. Local Development Environment Setup

### Install Ollama

```bash
brew install ollama
```

After install, verify it's running:

```bash
ollama --version
```

### Pull Gemma 4 26B

This is an ~18GB download, so do it on a good connection and don't start it right before you need it.

```bash
ollama pull gemma4:26b
```

Verify the model is available:

```bash
ollama list
```

You should see `gemma4:26b` in the output.

### Configure Ollama for Development

Ollama's defaults are conservative. For your 48GB MBP, you want full GPU offload and persistent model loading. Set these environment variables **before** starting `ollama serve`:

```bash
# Offload all layers to Apple Silicon GPU (unified memory)
export OLLAMA_NUM_GPU=99

# Keep model loaded indefinitely (prevents 15-30s reload delays)
# Use -1 or 0 — both work, docs vary
export OLLAMA_KEEP_ALIVE=-1

# Optional: bind to all interfaces if you want other devices to reach it
# export OLLAMA_HOST=0.0.0.0:11434
```

To make these persistent across reboots, either add them to your `~/.zshrc` or set them via `launchctl`:

```bash
launchctl setenv OLLAMA_NUM_GPU 99
launchctl setenv OLLAMA_KEEP_ALIVE -1
```

Then restart Ollama (quit the menu bar app and reopen, or `brew services restart ollama`).

### Verify Ollama is Working

Start the server:

```bash
ollama serve
```

In another terminal, test the API:

```bash
curl http://localhost:11434/api/chat -s -d '{
  "model": "gemma4:26b",
  "messages": [{"role": "user", "content": "Wat is de Wet open overheid?"}],
  "stream": false
}' | python3 -m json.tool
```

You should get a coherent Dutch response. Note the response time — on Apple Silicon with full GPU offload, expect ~1-3 seconds for the first token and then ~20-30 tokens/second.

### Test Function Calling

This is critical for the WOO Buddy pipeline. Verify Gemma 4 handles tool calls correctly:

```bash
curl -s http://localhost:11434/api/chat -d '{
  "model": "gemma4:26b",
  "messages": [
    {"role": "system", "content": "Je bent een juridisch assistent voor Woo-verzoeken."},
    {"role": "user", "content": "Beoordeel of de naam Jan Jansen gelakt moet worden. Context: ...het besluit van Jan Jansen, bewoner van de Kerkstraat 12 te Utrecht..."}
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "classify_woo_entity",
      "description": "Classify whether a detected entity should be redacted under the Dutch Woo",
      "parameters": {
        "type": "object",
        "properties": {
          "should_redact": {"type": "boolean"},
          "confidence": {"type": "number"},
          "woo_article": {"type": "string"},
          "reason_nl": {"type": "string"}
        },
        "required": ["should_redact", "confidence", "reason_nl"]
      }
    }
  }],
  "stream": false
}' | python3 -m json.tool
```

Check the response for a `tool_calls` array with structured output. If Gemma 4 returns plain text instead of a tool call, you may need to adjust the prompt or try the `gemma4:26b-a4b-it-q4_K_M` tag explicitly.

### Tune Context Window (Optional)

Ollama defaults to a 2048 token context window, which is way too small for processing full document pages. Create a custom Modelfile to increase it:

```bash
cat << 'EOF' > ~/Modelfile-gemma4-woo
FROM gemma4:26b
PARAMETER num_ctx 16384
PARAMETER temperature 0.3
EOF

ollama create gemma4-woo -f ~/Modelfile-gemma4-woo
```

On 48GB you can safely push to 16384 or even 32768. Monitor memory pressure in Activity Monitor while testing — if it goes yellow, dial back. Use `gemma4-woo` as the model name in your `.env` instead of `gemma4:26b`.

**Note:** Higher context windows improve function calling reliability according to the Ollama team. For the Woo classification task, 8192-16384 should be plenty since you're sending ~400-500 chars of context per entity.

### Monitor Performance

While Ollama is running and processing requests:

```bash
# Check GPU utilization on Apple Silicon
sudo powermetrics --samplers gpu_power -i 1000 -n 1

# Watch memory pressure
vm_stat 1
```

If `powermetrics` shows near-zero GPU activity during generation, something is wrong with GPU offloading.

---

## 2. Docker & Infrastructure Prerequisites

### Ensure Docker Desktop is Running

You need Docker Desktop for Mac with enough memory allocated. Go to Docker Desktop → Settings → Resources and set memory to at least 8GB (the heavy lifting is done by Ollama outside Docker, so the containers themselves are light).

### Create the `.env` File

Before the first `docker-compose up`, create `.env` from the example:

```bash
cp .env.example .env
```

Edit it to set:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=gemma4:26b
```

The `host.docker.internal` address is how Docker containers on macOS reach services running on the host. This is how the FastAPI container will talk to your locally-running Ollama.

### Initialize MinIO Bucket

After the first `docker-compose up`, MinIO will be running but the `documents` bucket won't exist yet. Either:

- Visit the MinIO console at `http://localhost:9001` (login: `woobuddy` / `woobuddy-secret`) and create a bucket called `documents` manually, or
- Have Claude Code add a startup script that creates it via the MinIO client

---

## 3. Test Data: Create Sample Woo Documents

You need realistic test PDFs for development. Create 3-5 sample documents that cover the detection scenarios:

### Document 1: Simple letter with private person names
A fake "besluit" letter mentioning private citizens by name, with a home address, phone number, and BSN. This tests the core detection pipeline.

### Document 2: Official decision with public officials
A document signed by a "wethouder" or "gemeentesecretaris" acting in official capacity. The system should detect their names but recommend NOT redacting them.

### Document 3: Mixed entities
An email thread or memo containing IBAN numbers, email addresses, license plates, dates of birth, and a mix of private and public persons.

### Document 4: Health/sensitive data
A document referencing someone's medical condition or religious affiliation — testing Art. 5.1.1d absolute grounds.

### Document 5: Edge cases
A document with publicly available KvK data (should not redact), a function title without a name (should not redact), and names that are also common Dutch words.

**Tip:** Use fictional data but make it structurally realistic. Include common Dutch name patterns (van der, de, van den), properly formatted BSN numbers that pass the 11-proef, and real-looking but fake IBANs (NL + 2 digits + 4 letters + 10 digits).

---

## 4. Licensing Consideration

The briefing says MIT license, but **Deduce is LGPL-3.0**. This is compatible — you can use an LGPL library in an MIT-licensed project as long as:

- Deduce is used as a dependency (pip install), not modified and bundled
- Users can replace the Deduce version (which they can, since it's a Python package)
- You include Deduce's license notice in your project

In practice, since WOO Buddy is a self-hosted web app and Deduce is a Python dependency, this is fine. Just make sure your `LICENSE` file or `NOTICES` file acknowledges Deduce and its LGPL-3.0 license. Have Claude Code add a `THIRD_PARTY_LICENSES.md` file.

---

## 5. GitHub Repository Setup

Before Claude Code starts writing code:

- Create the `woobuddy` repository on GitHub (public, MIT license)
- Initialize with README, `.gitignore` (Python + Node), and LICENSE
- Set up branch protection on `main` (require PR reviews — even if it's just you for now, it's good practice for an open-source project)
- Add relevant topics: `woo`, `privacy`, `redaction`, `dutch-government`, `open-source`, `pdf`, `de-identification`

---

## 6. Deduce Validation

Before building the full pipeline, independently test Deduce on realistic Woo document text. This tells you what Deduce catches out of the box and what you'll need custom regex for.

```bash
pip install deduce
```

```python
from deduce import Deduce

deduce = Deduce()  # ~2s first load

text = """
Betreft: besluit op Woo-verzoek van dhr. Jan van der Berg,
BSN 123456782, wonend aan de Kerkstraat 42, 3511 LX Utrecht.

Het college van burgemeester en wethouders heeft besloten
het verzoek gedeeltelijk toe te wijzen. Wethouder P.M. de Vries
heeft het besluit ondertekend op 15 maart 2024.

Voor vragen kunt u contact opnemen met j.vanderberg@gmail.com
of bellen naar 06-12345678. Het IBAN-nummer NL91ABNA0417164300
is gebruikt voor de terugbetaling.
"""

doc = deduce.deidentify(text)
for ann in doc.annotations:
    print(f"{ann.tag:20s} | {ann.text}")
```

**What to look for:**
- Does it catch the BSN? (It should — Deduce has built-in BSN detection)
- Does it catch the phone number? Email? Names?
- Does it flag "Wethouder P.M. de Vries" as a person? (It probably will — your LLM layer needs to then determine this is an official acting in capacity)
- Does it catch the IBAN? (It might not — this is where you'll need custom regex)
- Does it catch the address? Date of birth formats?

Document what Deduce catches and misses. This directly informs which custom regex patterns you need to write.

---

## 7. Sample Woo Document Research

Look at real published Woo documents to understand how they actually look. Many municipalities publish their Woo decisions online:

- Search for "woo-besluit" or "wob-besluit" on municipal websites
- Look at how redactions are currently done (manually, with black bars)
- Note common document types: besluiten, e-mails, nota's, brieven, bijlagen
- Note which Woo articles are most commonly cited

This will inform your test data and help you validate that the tool's output matches real-world practice.

---

## 8. Prompt Engineering & Evaluation

Once the LLM layer is wired up, you need to evaluate classification quality. Create an evaluation set:

- 50-100 entity examples with known correct classifications
- Cover all entity types and all Woo articles
- Include tricky edge cases (official acting in capacity, publicly available business data, consent situations)
- Run them through the LLM and measure precision/recall

This is a manual effort — Claude Code can build the harness, but you need to define the ground truth and review the results. Pay special attention to:

- **False negatives** (missed redactions) — these are the dangerous ones legally
- **Confidence calibration** — does confidence=0.90 actually mean 90% correct?
- **Dutch language quality** — are the `reason_nl` explanations clear and legally accurate?

---

## 9. Future Decisions (Park These for Now)

Things you don't need to decide yet but should keep in mind:

- **Authentication**: Not needed for prototype, but for production deployment at a municipality, you'll want something. OIDC with the organization's identity provider is the most likely path.
- **Hosting for demo**: If you want woobuddy.nl to show a live demo, you'll need hosting. A single VPS with Docker Compose works, but you'd need a GPU for Ollama — or switch to the Anthropic fallback for the demo instance.
- **CI/CD**: GitHub Actions for testing and building Docker images. Not needed for phase 1.
- **Branding**: The ShieldCheck placeholder works for now. Consider commissioning a proper logo once the product is functional.
- **Community**: If this gains traction with municipalities, you'll want a contribution guide, issue templates, and potentially a discussion forum or Discord.

---

## Quick Reference: Startup Commands

Once everything is set up, your daily dev workflow:

```bash
# Terminal 1: Ollama (if not running as a service)
ollama serve

# Terminal 2: Docker stack
cd woobuddy
docker-compose up

# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
# MinIO console: http://localhost:9001
# Ollama: http://localhost:11434
```

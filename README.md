# DocuVerity AI

Professional multi-document investigation platform for ALGOTHON'26 — ALG-AI-02.

## What it does

- Upload multiple PDF, DOCX and TXT documents
- Extract and chunk text while preserving PDF page / DOCX section metadata
- Create local embeddings with Ollama `nomic-embed-text`
- Retrieve semantically relevant evidence
- Ask natural-language questions
- Return grounded answers with source references
- Detect and surface material document conflicts
- Handle insufficient evidence instead of guessing
- Show confidence and investigation history
- Professional responsive dashboard with a CSS 3D evidence visual

## Architecture

Browser → FastAPI → Extraction → Embeddings → Semantic Retrieval → Conflict Signals → Llama 3 Investigation → Sources / Verdict / Confidence

## Requirements

- Python 3.11+ recommended (the current environment may also work with newer Python versions)
- Ollama installed and running
- Ollama models:
  - `llama3:latest`
  - `nomic-embed-text:latest`

## First-time setup on Windows

Open this project folder in VS Code. In the integrated terminal run:

```powershell
python -m pip install -r requirements.txt
ollama list
```

If the embedding model is missing:

```powershell
ollama pull nomic-embed-text
```

## Run

From the project root:

```powershell
python -m uvicorn backend.main:app --reload --port 8010
```

Then open **http://127.0.0.1:8010** in the browser.

Do not use VS Code Live Preview / Live Server for this app. FastAPI serves both the API and the frontend.

## Demo scenario for conflict detection

1. Upload two documents that intentionally disagree.
2. Example question: `What is the annual income limit?`
3. The system should identify evidence from both documents.
4. If the LLM confirms the disagreement refers to the same fact, the verdict becomes `CONFLICT`.
5. If the documents do not provide enough evidence, the verdict becomes `INSUFFICIENT`.

## Important design principle

A statement such as “the applicant is seeking an internship” is not treated as proof of eligibility. The system requires the relevant eligibility criteria and evidence before making a decision.

## Limitations

- Workspace data is held in memory and is reset when the server restarts.
- Scanned image-only PDFs are not OCR'd in this MVP.
- Conflict detection uses candidate heuristics plus LLM verification; it intentionally avoids treating unrelated numeric differences as definitive conflicts.

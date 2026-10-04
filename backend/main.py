from pathlib import Path
import shutil
import uuid
from typing import Dict, List

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.schemas import QuestionRequest
from backend.services.conflict import detect_possible_conflicts
from backend.services.embeddings import create_embeddings
from backend.services.extractor import extract_pages, chunk_records
from backend.services.investigator import investigate_documents
from backend.services.retriever import retrieve_relevant_chunks


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="DocuVerity AI",
    description="Evidence-grounded multi-document investigation platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOCUMENTS: Dict[str, Dict] = {}
HISTORY: List[Dict] = []


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "application": "DocuVerity AI",
        "documents": len(DOCUMENTS),
        "llm_model": "llama3:latest",
        "embedding_model": "nomic-embed-text:latest",
    }


@app.get("/api/documents")
def list_documents():
    return [
        {
            "id": doc_id,
            "name": doc["name"],
            "format": doc["format"],
            "chunks": len(doc["chunks"]),
            "characters": doc["characters"],
        }
        for doc_id, doc in DOCUMENTS.items()
    ]


@app.post("/api/upload")
def upload_document(file: UploadFile = File(...)):
    original_name = file.filename or "document"
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail="Supported formats: PDF, DOCX and TXT.")

    document_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{document_id}{suffix}"

    try:
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        records = extract_pages(str(saved_path), original_name)
        if not records:
            raise HTTPException(status_code=400, detail="No readable text was found in this document.")

        chunks = chunk_records(records)
        if not chunks:
            raise HTTPException(status_code=400, detail="The document could not be split into searchable evidence.")

        embeddings = create_embeddings([chunk["text"] for chunk in chunks])
        if len(embeddings) != len(chunks):
            raise RuntimeError("Embedding count does not match chunk count.")

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding

        DOCUMENTS[document_id] = {
            "id": document_id,
            "name": original_name,
            "format": suffix.removeprefix(".").upper(),
            "chunks": chunks,
            "characters": sum(len(chunk["text"]) for chunk in chunks),
            "path": str(saved_path),
        }

        return {
            "success": True,
            "document_id": document_id,
            "name": original_name,
            "format": suffix.removeprefix(".").upper(),
            "chunks": len(chunks),
            "characters": sum(len(chunk["text"]) for chunk in chunks),
        }

    except HTTPException:
        saved_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {exc}") from exc


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str):
    document = DOCUMENTS.pop(document_id, None)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    Path(document["path"]).unlink(missing_ok=True)
    return {"success": True, "message": "Document removed."}


@app.delete("/api/documents")
def clear_workspace():
    DOCUMENTS.clear()
    HISTORY.clear()
    for file in UPLOAD_DIR.iterdir():
        if file.is_file() and file.name != ".gitkeep":
            file.unlink(missing_ok=True)
    return {"success": True, "message": "Workspace cleared."}


@app.get("/api/history")
def get_history():
    return HISTORY[-25:][::-1]


@app.post("/api/ask")
def investigate(payload: QuestionRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if not DOCUMENTS:
        raise HTTPException(status_code=400, detail="Upload at least one document first.")

    selected_ids = payload.document_ids or list(DOCUMENTS.keys())
    selected_ids = [doc_id for doc_id in selected_ids if doc_id in DOCUMENTS]
    if not selected_ids:
        raise HTTPException(status_code=400, detail="Select at least one document.")

    all_chunks: List[Dict] = []
    for doc_id in selected_ids:
        for chunk in DOCUMENTS[doc_id]["chunks"]:
            all_chunks.append({
                **chunk,
                "document_id": doc_id,
                "document": DOCUMENTS[doc_id]["name"],
            })

    try:
        matches = retrieve_relevant_chunks(question, all_chunks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evidence retrieval failed: {exc}") from exc

    if not matches:
        result = {
            "answer": "The selected documents do not contain enough relevant evidence to answer this question reliably.",
            "verdict": "INSUFFICIENT",
            "confidence": 10,
            "confidence_label": "Low",
            "key_findings": [],
            "conflicts": [],
            "sources": [],
            "possible_conflicts": [],
        }
    else:
        possible_conflict, candidates = detect_possible_conflicts(matches)
        try:
            result = investigate_documents(question, matches, candidates if possible_conflict else None)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Investigation failed: {exc}") from exc

        result["sources"] = [
            {
                "document": match.get("document", "Unknown"),
                "page": match.get("page"),
                "section": match.get("section"),
                "score": match.get("score", 0),
                "snippet": match.get("text", "")[:650],
            }
            for match in matches
        ]
        result["possible_conflicts"] = candidates if possible_conflict else []

    HISTORY.append({
        "id": str(uuid.uuid4()),
        "question": question,
        "verdict": result["verdict"],
        "confidence": result["confidence"],
        "documents": [DOCUMENTS[doc_id]["name"] for doc_id in selected_ids],
    })

    return result


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

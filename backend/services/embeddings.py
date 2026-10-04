from typing import List

import ollama


EMBEDDING_MODEL = "nomic-embed-text:latest"


def create_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    response = ollama.embed(model=EMBEDDING_MODEL, input=texts)
    return response.embeddings


def create_query_embedding(question: str) -> List[float]:
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")
    response = ollama.embed(model=EMBEDDING_MODEL, input=[question])
    return response.embeddings[0]

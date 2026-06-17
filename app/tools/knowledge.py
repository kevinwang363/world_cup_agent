import json

from langchain_core.tools import tool

from app.rag.store import search_knowledge


@tool
def query_vector_knowledge(query: str, k: int = 4) -> str:
    """Search the local FAISS knowledge base for World Cup reports, rules, team notes, and project guidance."""
    results = search_knowledge(query=query, k=k)
    return json.dumps(
        {
            "source": "local_faiss_knowledge_base",
            "query": query,
            "results": results,
            "note": "Scores are FAISS inner-product similarities over local lightweight embeddings.",
        },
        ensure_ascii=False,
    )

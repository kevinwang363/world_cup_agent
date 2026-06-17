import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import faiss
import numpy as np

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"
FAISS_DIR = Path(__file__).resolve().parents[2] / "data" / "faiss"
INDEX_PATH = FAISS_DIR / "index.faiss"
CHUNKS_PATH = FAISS_DIR / "chunks.json"
META_PATH = FAISS_DIR / "meta.json"
VECTOR_DIM = 384

_cached_index: Optional[faiss.IndexFlatIP] = None
_cached_chunks: Optional[List["KnowledgeChunk"]] = None
_cached_hash: Optional[str] = None


@dataclass(frozen=True)
class KnowledgeChunk:
    content: str
    metadata: Dict[str, str]


def _hash_token(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % VECTOR_DIM


def _tokens(text: str) -> List[str]:
    normalized = text.lower()
    words = []
    current = []

    for char in normalized:
        if char.isalnum():
            current.append(char)
        else:
            if current:
                words.append("".join(current))
                current = []
            if "\u4e00" <= char <= "\u9fff":
                words.append(char)

    if current:
        words.append("".join(current))

    char_bigrams = [
        normalized[index : index + 2]
        for index in range(max(len(normalized) - 1, 0))
        if normalized[index : index + 2].strip()
    ]
    return words + char_bigrams


def embed_text(text: str) -> np.ndarray:
    vector = np.zeros(VECTOR_DIM, dtype="float32")
    for token in _tokens(text):
        vector[_hash_token(token)] += 1.0

    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


def _chunk_text(text: str, source: str, chunk_size: int = 700, overlap: int = 120) -> List[KnowledgeChunk]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: List[KnowledgeChunk] = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue

        if current:
            chunks.append(
                KnowledgeChunk(
                    content=current,
                    metadata={"source": source, "chunk": str(len(chunks))},
                )
            )
            current = current[-overlap:] if overlap else ""

        current = f"{current}\n\n{paragraph}".strip()

    if current:
        chunks.append(
            KnowledgeChunk(
                content=current,
                metadata={"source": source, "chunk": str(len(chunks))},
            )
        )

    return chunks


def load_knowledge_chunks() -> List[KnowledgeChunk]:
    chunks: List[KnowledgeChunk] = []
    if not KNOWLEDGE_DIR.exists():
        return chunks

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        chunks.extend(_chunk_text(text, source=str(path.relative_to(KNOWLEDGE_DIR.parent))))
    return chunks


def knowledge_hash() -> str:
    hasher = hashlib.sha256()
    if not KNOWLEDGE_DIR.exists():
        return hasher.hexdigest()

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def build_faiss_index() -> Dict[str, object]:
    chunks = load_knowledge_chunks()
    if not chunks:
        raise ValueError(f"No markdown files found in {KNOWLEDGE_DIR}")

    vectors = np.vstack([embed_text(chunk.content) for chunk in chunks]).astype("float32")
    index = faiss.IndexFlatIP(VECTOR_DIM)
    index.add(vectors)

    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))

    with CHUNKS_PATH.open("w", encoding="utf-8") as file:
        json.dump([asdict(chunk) for chunk in chunks], file, ensure_ascii=False, indent=2)

    meta = {
        "knowledge_hash": knowledge_hash(),
        "chunk_count": len(chunks),
        "vector_dim": VECTOR_DIM,
        "index_path": str(INDEX_PATH.relative_to(FAISS_DIR.parent)),
        "chunks_path": str(CHUNKS_PATH.relative_to(FAISS_DIR.parent)),
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    with META_PATH.open("w", encoding="utf-8") as file:
        json.dump(meta, file, ensure_ascii=False, indent=2)

    global _cached_index, _cached_chunks, _cached_hash
    _cached_index = index
    _cached_chunks = chunks
    _cached_hash = meta["knowledge_hash"]

    return meta


def _load_chunks_from_disk() -> List[KnowledgeChunk]:
    with CHUNKS_PATH.open("r", encoding="utf-8") as file:
        raw_chunks = json.load(file)
    return [KnowledgeChunk(content=item["content"], metadata=item["metadata"]) for item in raw_chunks]


def _index_is_stale() -> bool:
    if not INDEX_PATH.exists() or not CHUNKS_PATH.exists() or not META_PATH.exists():
        return True

    with META_PATH.open("r", encoding="utf-8") as file:
        meta = json.load(file)
    return meta.get("knowledge_hash") != knowledge_hash()


def _load_persisted_index() -> Tuple[faiss.IndexFlatIP, List[KnowledgeChunk]]:
    global _cached_index, _cached_chunks, _cached_hash

    current_hash = knowledge_hash()
    if _cached_index is not None and _cached_chunks is not None and _cached_hash == current_hash:
        return _cached_index, _cached_chunks

    if _index_is_stale():
        build_faiss_index()

    index = faiss.read_index(str(INDEX_PATH))
    chunks = _load_chunks_from_disk()

    _cached_index = index
    _cached_chunks = chunks
    _cached_hash = current_hash
    return index, chunks


def search_knowledge(query: str, k: int = 4) -> List[Dict[str, object]]:
    index, chunks = _load_persisted_index()
    if not chunks:
        return []

    query_vector = embed_text(query).reshape(1, -1).astype("float32")
    scores, indices = index.search(query_vector, min(k, len(chunks)))

    results: List[Dict[str, object]] = []
    for score, index_id in zip(scores[0], indices[0]):
        if index_id < 0:
            continue

        chunk = chunks[int(index_id)]
        results.append(
            {
                "score": round(float(score), 4),
                "content": chunk.content,
                "metadata": chunk.metadata,
            }
        )
    return results

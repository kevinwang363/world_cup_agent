"""Build or rebuild the persisted FAISS index from data/knowledge/*.md."""

from app.rag.store import FAISS_DIR, build_faiss_index, knowledge_hash, load_knowledge_chunks


def main() -> None:
    chunks = load_knowledge_chunks()
    if not chunks:
        raise SystemExit("No knowledge documents found. Add markdown files under data/knowledge/.")

    meta = build_faiss_index()
    print("FAISS index built successfully.")
    print(f"  knowledge_hash: {knowledge_hash()}")
    print(f"  chunk_count: {meta['chunk_count']}")
    print(f"  index_path: {FAISS_DIR / 'index.faiss'}")
    print(f"  chunks_path: {FAISS_DIR / 'chunks.json'}")


if __name__ == "__main__":
    main()

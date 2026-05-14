"""
Semantic chunking for documentation pages.
Uses recursive character splitting with overlap.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents(
    documents: list[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict]:
    """
    Split documents into overlapping chunks.
    Returns list of {"text": str, "url": str, "title": str, "source": str, "chunk_index": int}
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in documents:
        doc_chunks = splitter.split_text(doc["text"])
        for i, chunk_text in enumerate(doc_chunks):
            chunks.append({
                "text": chunk_text,
                "url": doc["url"],
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "chunk_index": i,
            })

    return chunks

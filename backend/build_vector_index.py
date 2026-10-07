"""Embed the unstructured documents (tickets, call notes, QBR notes, NPS comments) into a local Chroma index.

Run:  python build_vector_index.py
The first run downloads the small embedding model (all-MiniLM-L6-v2) if it is not cached.
"""
import sqlite3
import sys

import chromadb
from chromadb.utils import embedding_functions

from db import ROOT, q

CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION = "documents"
FTS_DB = ROOT / "data" / "search.db"


def get_collection():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(COLLECTION, embedding_function=ef, metadata={"hnsw:space": "cosine"})


def main():
    docs = q("SELECT doc_id, customer_id, doc_type, doc_date, title, text FROM documents")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = get_collection()
    B = 200
    for i in range(0, len(docs), B):
        b = docs[i:i + B]
        col.add(ids=[d["doc_id"] for d in b], documents=[f"{d['title']}\n{d['text']}" for d in b],
                metadatas=[{"customer_id": d["customer_id"], "doc_type": d["doc_type"], "doc_date": d["doc_date"], "title": d["title"]} for d in b])
        print(f"indexed {min(i + B, len(docs))}/{len(docs)}")
    print("done:", col.count(), "documents in", CHROMA_DIR)
    # keyword index (BM25 via SQLite FTS5) for hybrid search
    con = sqlite3.connect(FTS_DB)
    con.execute("DROP TABLE IF EXISTS docs_fts")
    con.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(doc_id UNINDEXED, customer_id UNINDEXED, doc_type UNINDEXED, doc_date UNINDEXED, title, text)")
    con.executemany("INSERT INTO docs_fts VALUES (?,?,?,?,?,?)", [(d["doc_id"], d["customer_id"], d["doc_type"], d["doc_date"], d["title"], d["text"]) for d in docs])
    con.commit()
    con.close()
    print("keyword index written:", FTS_DB)


if __name__ == "__main__":
    sys.exit(main())

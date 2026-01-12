import os
import chromadb

def main():
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", "8000"))
    name = os.getenv("AUDIO_COLLECTION_NAME", "audio_base")

    client = chromadb.HttpClient(host=host, port=port)

    try:
        client.delete_collection(name=name)
        print(f"[OK] deleted collection: {name}")
    except Exception as e:
        print(f"[INFO] delete skipped (maybe not exist): {e}")

    col = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"[OK] recreated collection: {name}, count={col.count()}")


if __name__ == "__main__":
    main()
from app.ingestion.loader import split_docs, load_docs
from app.deps import get_vs

def main():
    """
    将文档（语料）转换为向量并存储到向量数据库中
    :return:
    """
    docs = split_docs(load_docs("../../data/docs"))
    vs = get_vs()
    vs.add_documents(docs)
    print(f"Indexed {len(docs)} chunks into Chroma.")

if __name__ == "__main__":
    main()
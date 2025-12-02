from typing import List
from langchain_core.documents import Document
from pathlib import Path
from pypdf import PdfReader
import docx
from app.config import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_pdf(path: Path) -> List[Document]:
    """
    分页加载 pdf 文件
    :param path: pdf文件的路径
    :return:
    """
    reader = PdfReader(str(path))
    docs = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            docs.append(Document(
                page_content=text,
                metadata={"source": str(path), "page": i + 1}
            ))
    return docs

def load_docx(path: Path) -> List[Document]:
    """
    读取 docx 文件
    :param path: word文件的路径
    :return:
    """
    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs if p.text.strip())
    return [Document(page_content=text, metadata={"source": str(path)})] if text else []

def load_docs(dir_path: str) -> List[Document]:
    """
    读取某个目录下的文件，包括docx/doc, pdf, md, txt
    :param dir_path: 目录路径
    :return:
    """
    p = Path(dir_path)
    docs: List[Document] = []
    for f in p.rglob("*"):                  # 全局递归匹配
        if f.suffix.lower() == ".pdf":
            docs.extend(load_pdf(f))
        elif f.suffix.lower() in [".docx", ".doc"]:
            docs.extend(load_docx(f))
        elif f.suffix.lower() in [".md", ".txt"]:
            docs.append(Document(page_content=f.read_text(encoding="utf-8"),
                                 metadata={"source": str(f)}))
    return docs

def split_docs(docs: List[Document]) -> List[Document]:
    """
    分割文档
    :param docs: 准备要分块的文档
    :return:
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap
    )
    return splitter.split_documents(docs)

if __name__ == "__main__":
    docs = split_docs(load_docs("/home/supercao/PycharmProjects/kb_assistant/data/docs"))
    for _ in docs[:10]:
        print(_)
from typing import List
from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader
import docx
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def load_pdf(path: Path) -> List[Document]:
    """
    分页加载 pdf 文件，将其存储为带有 source 和 page 元数据的 Document 对象列表
    :param path: pdf文件的路径
    :return: langchain_core.documents下的 Document 对象的列表
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
    读取 docx 文件, 将其转换为带有 source 元数据的 Document 对象列表
    :param path: word文件的路径
    :return: langchain_core.documents下的 Document 对象的列表
    """
    d = docx.Document(str(path))
    text = "\n".join(p.text for p in d.paragraphs if p.text.strip())
    return [Document(page_content=text, metadata={"source": str(path)})] if text else []


def load_docs(dir_path: str) -> List[Document]:
    """
    读取 dir_path 下的文件，文件类型支持 docx/doc, pdf, md, txt
    :param dir_path: 目录路径
    :return: langchain_core.documents下的 Document 对象的列表
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
    将 docs 切割成块
    :param docs: 准备要分块的文档
    :return: langchain_core.documents下的 Document 对象的列表
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap
    )
    return splitter.split_documents(docs)


def load_single_file(path: Path) -> List[Document]:
    """
    读取单个文件，将其处理为 langchain_core.documents 下的 Document 对象的列表
    :param path: 文件路径
    :return: langchain_core.document 的 Document 对象的列表
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix in [".docx", ".doc"]:
        return load_docx(path)
    if suffix in [".md", ".txt"]:
        text = path.read_text(encoding="utf-8")
        return [Document(page_content=text, metadata={"source": str(path)})] if text.strip() else []
    return []


def split_and_enrich_metadata(docs: List[Document],
                          visibility: str,
                          doc_id: str | None = None,
                          extra_meta: dict | None = None) -> List[Document]:
    """
    将传入的 docs 分块，并给每个分块加入 visibility 、doc_id 和 extra_meta 元数据
    :param docs: Document 列表
    :param visibility: 可见性
    :param doc_id: 文档id
    :param extra_meta: 额外的元数据
    :return: 添加了元数据的文件块（chunks）
    """
    chunks = split_docs(docs)
    extra_metadata = dict(extra_meta or {})
    for c in chunks:
        c.metadata = dict(c.metadata or {})
        c.metadata["visibility"] = visibility
        if doc_id:
            c.metadata["doc_id"] = doc_id
        for k, v in extra_metadata.items():
            if v:
                c.metadata[k] = v
    return chunks


def batch_chunks(docs, batch_size):
    """
    分块添加文件
    """
    for i in range(0, len(docs), batch_size):
        yield docs[i:i + batch_size]


if __name__ == "__main__":
    docs = split_docs(load_docs("/home/supercao/PycharmProjects/kb_assistant/data/docs"))
    for _ in docs[:10]:
        print(_)
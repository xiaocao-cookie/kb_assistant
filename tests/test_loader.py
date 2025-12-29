import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from langchain_core.documents import Document

# 导入你的模块
from app.ingestion.doc_loader import (
    load_pdf,
    load_docx,
    load_docs,
    split_docs,
    load_single_file,
    split_and_enrich_metadata,
    batch_chunks
)


class TestFileLoaders(unittest.TestCase):

    def setUp(self):
        """临时目录用于模拟文件结构"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ----------------------- load_pdf -----------------------
    @patch("app.ingestion.loader.PdfReader")
    def test_load_pdf(self, mock_reader_cls):
        """测试 PDF 加载逻辑"""
        mock_reader = MagicMock()
        mock_reader.pages = [MagicMock(), MagicMock()]

        # 模拟提取文本
        mock_reader.pages[0].extract_text.return_value = "PDF page 1"
        mock_reader.pages[1].extract_text.return_value = "PDF page 2"
        mock_reader_cls.return_value = mock_reader

        pdf_file = self.base / "tests.pdf"
        pdf_file.write_text("fake pdf")

        docs = load_pdf(pdf_file)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].metadata["page"], 1)

    # ----------------------- load_docx -----------------------
    @patch("app.ingestion.loader.docx.Document")
    def test_load_docx(self, mock_docx_cls):
        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="Hello"),
            MagicMock(text=""),
            MagicMock(text="World")
        ]
        mock_docx_cls.return_value = mock_doc

        docx_file = self.base / "tests.docx"
        docx_file.write_text("fake docx")

        docs = load_docx(docx_file)
        self.assertEqual(len(docs), 1)
        self.assertIn("Hello", docs[0].page_content)
        self.assertIn("World", docs[0].page_content)

    # ----------------------- load_docs -----------------------
    def test_load_docs_txt_md(self):
        txt = self.base / "a.txt"
        md = self.base / "b.md"
        txt.write_text("TXT file")
        md.write_text("MD file")

        docs = load_docs(self.base)
        contents = [d.page_content for d in docs]

        self.assertIn("TXT file", contents)
        self.assertIn("MD file", contents)

    # ----------------------- load_single_file -----------------------
    def test_load_single_txt(self):
        f = self.base / "t.txt"
        f.write_text("hello")

        docs = load_single_file(f)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "hello")

    @patch("app.ingestion.loader.load_pdf")
    def test_load_single_pdf(self, mock_load_pdf):
        f = self.base / "a.pdf"
        f.write_text("fake pdf")
        mock_load_pdf.return_value = [Document(page_content="PDF")]

        docs = load_single_file(f)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "PDF")

    # ----------------------- split_docs -----------------------
    @patch("app.ingestion.loader.RecursiveCharacterTextSplitter")
    def test_split_docs(self, mock_splitter_cls):
        splitter = MagicMock()
        splitter.split_documents.return_value = ["chunk1", "chunk2"]
        mock_splitter_cls.return_value = splitter

        docs = [Document(page_content="tests")]
        chunks = split_docs(docs)

        self.assertEqual(len(chunks), 2)
        splitter.split_documents.assert_called_once()

    # ----------------------- split_with_visibility -----------------------
    @patch("app.ingestion.loader.split_docs")
    def test_split_and_enrich_metadata(self, mock_split_docs):
        mock_split_docs.return_value = [
            Document("chunk1", **{"source": "A"}),
            Document("chunk2", **{"source": "B"}),
        ]

        docs = [Document("tests")]
        results = split_and_enrich_metadata(docs, visibility="private", doc_id="123")

        self.assertEqual(len(results), 2)
        for c in results:
            self.assertEqual(c.metadata["visibility"], "private")
            self.assertEqual(c.metadata["doc_id"], "123")

    # ----------------------- batch_chunks -----------------------
    def test_batch_chunks(self):
        docs = ["a", "b", "c", "d"]
        batches = list(batch_chunks(docs, batch_size=2))

        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], ["a", "b"])
        self.assertEqual(batches[1], ["c", "d"])


if __name__ == "__main__":
    unittest.main()

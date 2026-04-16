import hashlib
import logging
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.matching.embedder import TicketEmbedder
from app.sop.sop_store import SOPStore

log = logging.getLogger(__name__)

_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


class SOPLoader:
    def __init__(self, embedder: TicketEmbedder, sop_store: SOPStore):
        self._embedder = embedder
        self._store = sop_store

    def _extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in (".md", ".txt"):
            return path.read_text(encoding="utf-8")
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        raise ValueError(f"Unsupported SOP file type: {ext}")

    def _infer_title(self, path: Path, content: str) -> str:
        # Try first non-empty line
        for line in content.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line[:120]
        return path.stem.replace("-", " ").replace("_", " ").title()

    async def load_file(self, path: Path, category: str | None = None) -> int:
        content = self._extract_text(path)
        title = self._infer_title(path, content)
        sop_id = hashlib.md5(str(path).encode()).hexdigest()[:12]
        chunks = _splitter.split_text(content)

        embeddings = await self._embedder.embed_batch(chunks)

        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{sop_id}_chunk_{i}"
            await self._store.upsert_chunk(
                chunk_id=chunk_id,
                embedding=embedding,
                content=chunk,
                sop_id=sop_id,
                title=title,
                chunk_index=i,
                doc_path=str(path),
                category=category,
            )

        log.info("Loaded SOP '%s' (%d chunks) from %s", title, len(chunks), path)
        return len(chunks)

    async def load_directory(self, directory: Path, category: str | None = None) -> int:
        total = 0
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() in (".md", ".txt", ".pdf"):
                total += await self.load_file(path, category=category)
        return total

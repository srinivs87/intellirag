"""
Ingestion Service — parses, chunks, embeds and stores documents.

Key improvement: Table-aware Excel chunking.
Instead of dumping entire sheets as one block, each row in a data table
is chunked with its column headers, making individual rows searchable.

Example — Client Analytics sheet:
  Old: One chunk containing all 20 clients → can't find "NurseConnect"
  New: Each client gets its own chunk with headers → instantly findable

Also registers every document in document_registry for Layer 3 retrieval.
"""
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple

from qdrant_client.models import PointStruct
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.vector_store import get_qdrant, ensure_collection
from app.services.embedding import get_embeddings
from app.services.storage import upload_to_minio

log = logging.getLogger("intellirag.ingestion")


async def ingest_document(
    file_bytes: bytes,
    filename: str,
    tenant_slug: str,
    document_id: str,
    uploaded_by: str = "system",
    extra_metadata: dict = None,
    collection_name: str = None,
) -> Dict[str, Any]:
    """
    Full ingestion pipeline:
    1. Save to MinIO
    2. Parse text from document (table-aware for Excel)
    3. Split into chunks
    4. Embed each chunk
    5. Store in Qdrant with metadata
    6. Register in document_registry (Layer 3)
    """

    # 1. Store raw file in MinIO
    object_key = f"{tenant_slug}/{document_id}/{filename}"
    await upload_to_minio(file_bytes, object_key, filename)

    # 2. Parse — Excel gets special table-aware treatment
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xls"):
        chunks = await _parse_and_chunk_xlsx(file_bytes, extra_metadata)
        text = "\n\n".join(chunks)  # For registry sample
    else:
        text = await parse_document(file_bytes, filename)
        if not text.strip():
            raise ValueError(f"Could not extract text from {filename}")
        # Prepend file date so embeddings encode the date context
        if extra_metadata and extra_metadata.get("file_date"):
            fd = extra_metadata["file_date"][:10]
            text = f"[Document Date: {fd}]\n\n{text}"
        # Standard chunking for non-Excel
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_text(text)

    if not chunks:
        raise ValueError(f"No content extracted from {filename}")

    # 3. Embed all chunks
    embeddings = await get_embeddings(chunks)

    # 4. Upsert into Qdrant
    target_collection = collection_name or await ensure_collection(tenant_slug)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "document_id": document_id,
                "tenant_slug": tenant_slug,
                "filename": filename,
                "chunk_index": i,
                "chunk_total": len(chunks),
                "text": chunk,
                "uploaded_by": uploaded_by,
                **(extra_metadata or {}),
            },
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    client = get_qdrant()
    await client.upsert(collection_name=target_collection, points=points)

    # 5. Register in document_registry (Layer 3)
    try:
        from app.services.registry import upsert_registry_entry
        file_ext = Path(filename).suffix.lower().lstrip(".")
        file_path = (extra_metadata or {}).get("file_path", filename)
        await upsert_registry_entry(
            document_id=document_id,
            filename=filename,
            collection=target_collection,
            file_type=file_ext,
            file_path=file_path,
            chunk_count=len(chunks),
            text_sample=text[:3000],
        )
    except Exception as e:
        log.warning(f"[Ingestion] Registry update failed for {filename}: {e}")

    return {
        "document_id": document_id,
        "filename": filename,
        "chunks_created": len(chunks),
        "collection": target_collection,
    }


# ── Table-Aware Excel Chunking ────────────────────────────────────────────────

async def _parse_and_chunk_xlsx(
    file_bytes: bytes,
    extra_metadata: dict = None,
) -> List[str]:
    """
    Table-aware Excel parsing. Each sheet is analyzed:
    - If it has a header row + data rows → each row becomes its own chunk
      with headers repeated, making individual rows searchable
    - If it's a summary/config sheet → treat as regular text block

    This ensures queries like "which client had highest growth" can find
    the specific row for NurseConnect in the Client Analytics sheet.
    """
    import io
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    date_prefix = ""
    if extra_metadata and extra_metadata.get("file_date"):
        date_prefix = f"[Document Date: {extra_metadata['file_date'][:10]}]\n\n"

    all_chunks = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        # Read all non-empty rows
        rows = []
        for row in ws.iter_rows(values_only=True):
            values = [str(v).strip() if v is not None else "" for v in row]
            if any(v for v in values):
                rows.append(values)

        if not rows:
            continue

        # Detect if this is a data table (has header + multiple data rows)
        is_data_table, header_idx = _is_data_table(rows)

        if is_data_table and len(rows) > header_idx + 2:
            # Table-aware chunking: header + each row = one chunk
            headers = rows[header_idx]
            data_rows = rows[header_idx + 1:]
            chunks = _chunk_table_rows(sheet_name, headers, data_rows, date_prefix)
            all_chunks.extend(chunks)
            log.info(f"[Ingestion] Sheet '{sheet_name}': {len(rows)-1} rows → {len(chunks)} row-chunks")
        else:
            # Regular text block for summary/config sheets
            text_rows = ["  |  ".join(row) for row in rows]
            block = f"{date_prefix}Sheet: {sheet_name}\n" + "\n".join(text_rows)

            # Split large blocks further
            if len(block) > settings.CHUNK_SIZE * 2:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=settings.CHUNK_SIZE,
                    chunk_overlap=settings.CHUNK_OVERLAP,
                )
                sub_chunks = splitter.split_text(block)
                all_chunks.extend(sub_chunks)
            else:
                all_chunks.append(block)

    return all_chunks


def _find_header_row(rows: List[List[str]]) -> int:
    """
    Find the actual header row index. Skips title rows (single cell with long text).
    Returns index of header row, or -1 if not found.
    """
    for i, row in enumerate(rows[:5]):  # Check first 5 rows only
        non_empty = [v for v in row if v and v != "None"]
        if len(non_empty) < 2:
            continue  # Skip title rows (single cell)
        # Check if this looks like headers (mostly short text values)
        numeric_count = sum(1 for v in non_empty if _is_numeric(v))
        text_ratio = 1 - (numeric_count / len(non_empty))
        if text_ratio > 0.5:
            return i
    return -1


def _is_data_table(rows: List[List[str]]) -> Tuple[bool, int]:
    """
    Determine if rows represent a data table with headers.
    Returns (is_table, header_row_index).
    """
    if len(rows) < 3:
        return False, 0

    header_idx = _find_header_row(rows)
    if header_idx == -1:
        return False, 0

    # Need at least 2 data rows after header
    data_rows = rows[header_idx + 1:]
    if len(data_rows) < 2:
        return False, 0

    return True, header_idx


def _is_numeric(value: str) -> bool:
    """Check if a string value is numeric."""
    try:
        float(value.replace(",", "").replace("%", "").replace("$", "").replace("(", "-").replace(")", ""))
        return True
    except ValueError:
        return False


def _chunk_table_rows(
    sheet_name: str,
    headers: List[str],
    data_rows: List[List[str]],
    date_prefix: str = "",
) -> List[str]:
    """
    Create one chunk per data row, with headers included for context.

    Format:
    Sheet: Client Analytics | Row: MedCore Health Systems
    Client Name: MedCore Health Systems
    Segment: Healthcare AI
    Region: North America
    Q1 ($K): 285
    Q2 ($K): 310
    ...
    """
    chunks = []
    clean_headers = [h for h in headers if h and h != "None"]

    for row in data_rows:
        # Skip empty rows
        non_empty_values = [v for v in row if v and v != "None"]
        if not non_empty_values:
            continue

        # Build row identifier from first non-empty value
        row_id = row[0] if row[0] and row[0] != "None" else "Row"

        # Build key-value pairs: header → value
        pairs = []
        for i, header in enumerate(clean_headers):
            if i < len(row):
                val = row[i]
                if val and val != "None":
                    pairs.append(f"{header}: {val}")

        if not pairs:
            continue

        # Format chunk
        chunk = (
            f"{date_prefix}Sheet: {sheet_name} | Entry: {row_id}\n"
            + "\n".join(pairs)
        )
        chunks.append(chunk)

    # If no row chunks created, fall back to full sheet text
    if not chunks:
        all_rows = ["  |  ".join(h for h in headers if h)] + \
                   ["  |  ".join(v for v in row) for row in data_rows]
        chunks = [f"{date_prefix}Sheet: {sheet_name}\n" + "\n".join(all_rows)]

    return chunks


# ── Standard Document Parsers ─────────────────────────────────────────────────

async def parse_document(file_bytes: bytes, filename: str) -> str:
    """Parse text from various file types."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return await _parse_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        return await _parse_docx(file_bytes)
    elif ext in (".xlsx", ".xls"):
        # Fallback for when called directly — use table-aware
        chunks = await _parse_and_chunk_xlsx(file_bytes)
        return "\n\n".join(chunks)
    elif ext in (".pptx", ".ppt"):
        return await _parse_pptx(file_bytes)
    elif ext in (".txt", ".md", ".csv"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        return file_bytes.decode("utf-8", errors="ignore")


async def _parse_pdf(file_bytes: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            pages.append(t)
    return "\n\n".join(pages)


async def _parse_docx(file_bytes: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


async def _parse_pptx(file_bytes: bytes) -> str:
    """Parse PowerPoint — each slide becomes a named section."""
    import io
    from pptx import Presentation
    prs = Presentation(io.BytesIO(file_bytes))
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text.strip())
        if texts:
            slides.append(f"Slide {i}:\n" + "\n".join(texts))
    return "\n\n".join(slides)


# ── Deletion ──────────────────────────────────────────────────────────────────

async def delete_document_chunks(document_id: str, tenant_slug: str):
    """Remove all Qdrant points and registry entry for a document."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = get_qdrant()
    collection_name = f"intellirag_{tenant_slug}"
    await client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        ),
    )
    try:
        from app.services.registry import remove_registry_entry
        await remove_registry_entry(document_id, collection_name)
    except Exception as e:
        log.warning(f"[Ingestion] Registry removal failed: {e}")

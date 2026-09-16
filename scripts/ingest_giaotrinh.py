"""Ingest all markdown files from copus/hoctap/ into ChromaDB as GIAOTRINH.

This script directly indexes markdown curriculum files into the RAG system
without creating Document records in PostgreSQL. It's useful for quickly
populating the knowledge base for testing.

Usage: python scripts/ingest_giaotrinh.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add server to path so we can import from app
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from app.rag_container import get_rag_container


async def main():
    print("=== INGEST GIAO TRINH ===")
    print()

    # Initialize RAG container
    print("Initializing RAG container...")
    container = get_rag_container()
    indexer = container.indexing

    # Find all markdown files in copus/hoctap/
    corpus_dir = Path(__file__).parent.parent / "copus" / "hoctap"
    if not corpus_dir.exists():
        print(f"ERROR: Directory not found: {corpus_dir}")
        return

    md_files = sorted(corpus_dir.glob("*.md"))
    print(f"Found {len(md_files)} markdown files in {corpus_dir}")
    print()

    if not md_files:
        print("No markdown files to ingest!")
        return

    # Ingest each file
    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(md_files, 1):
        # Extract title from filename (remove number prefix and extension)
        title = file_path.stem
        # Remove leading numbers like "1.", "2.", etc
        if "." in title and title.split(".")[0].isdigit():
            title = ".".join(title.split(".")[1:]).strip()
        title = title.replace("_", " ").title()

        # Generate a deterministic UUID based on filename
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"giaotrinh:{file_path.name}"))

        print(f"[{i}/{len(md_files)}] {file_path.name}")
        print(f"  Title: {title}")
        print(f"  ID: {doc_id}")

        try:
            report = await indexer.ingest(
                file_path=str(file_path),
                document_id=doc_id,
                document_type="giaotrinh",
                title=title,
                course_id=None,  # No specific course
            )

            print(f"  [OK] Indexed: {report.chunks} chunks, {report.points_upserted} points")
            print(f"    {report.pages} pages, {report.chars} chars, {report.seconds:.1f}s")
            if report.warnings:
                for w in report.warnings:
                    print(f"    WARNING: {w}")
            success_count += 1

        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            fail_count += 1

        print()

    print("=== SUMMARY ===")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Total: {len(md_files)}")


if __name__ == "__main__":
    asyncio.run(main())

"""Fusiona el PDF de declaración con el PDF del albarán del ERP."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter

from config.settings import settings


def fusionar_pdfs(declaration_pdf: Path, albaran_pdf: Path | None, num_albaran: str) -> Path:
    """
    Combina declaración + albarán del ERP en un único PDF.
    Si albaran_pdf es None, devuelve solo el PDF de declaración.
    """
    out_dir = settings.output_dir / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)
    merged_path = out_dir / f"completo_{num_albaran}.pdf"

    writer = PdfWriter()

    # Primero la declaración
    writer.append(str(declaration_pdf))

    # Luego el albarán del ERP si existe
    if albaran_pdf and albaran_pdf.exists():
        writer.append(str(albaran_pdf))

    with open(merged_path, "wb") as f:
        writer.write(f)

    return merged_path

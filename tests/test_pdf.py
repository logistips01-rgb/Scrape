"""Tests de generación y fusión de PDFs."""
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from core.models import Albaran, DeclaracionResult, DeclarationStatus, EnvaseLinea, Portal


@pytest.fixture
def albaran_ejemplo():
    return Albaran(
        num_albaran="ALB-TEST-001",
        fecha_entrega=date(2024, 6, 15),
        num_pedido="PED-TEST-001",
        cliente_codigo="CLI001",
        cliente_nombre="Frutas García S.L.",
        portal=Portal.EUROPOOL,
        lineas=[
            EnvaseLinea("RPC6410", 50),
            EnvaseLinea("RPC4415", 30),
        ],
    )


def test_generar_declaracion_pdf(albaran_ejemplo, tmp_path):
    with patch("documents.declaration.settings") as mock_settings:
        mock_settings.output_dir = tmp_path

        from documents.declaration import generar_declaracion_pdf

        result = DeclaracionResult(
            albaran=albaran_ejemplo,
            status=DeclarationStatus.SUBMITTED,
            confirmation_number="CONF-12345",
        )
        pdf_path = generar_declaracion_pdf(albaran_ejemplo, result)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
        assert pdf_path.suffix == ".pdf"


def test_fusionar_sin_albaran_erp(albaran_ejemplo, tmp_path):
    try:
        import pypdf  # noqa: F401
    except BaseException:
        pytest.skip("pypdf/cryptography no disponible en este entorno")

    with patch("documents.merger.settings") as mock_settings:
        mock_settings.output_dir = tmp_path

        from documents.declaration import generar_declaracion_pdf
        from documents.merger import fusionar_pdfs

        with patch("documents.declaration.settings") as mock_decl_settings:
            mock_decl_settings.output_dir = tmp_path
            result = DeclaracionResult(
                albaran=albaran_ejemplo,
                status=DeclarationStatus.SUBMITTED,
                confirmation_number="CONF-12345",
            )
            decl_pdf = generar_declaracion_pdf(albaran_ejemplo, result)

        merged = fusionar_pdfs(decl_pdf, None, albaran_ejemplo.num_albaran)
        assert merged.exists()
        assert merged.stat().st_size > 0

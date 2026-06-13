"""Tests del flujo del watcher sin ejecutar scraping real."""
import csv
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.models import (
    Albaran,
    DeclaracionResult,
    DeclarationStatus,
    EnvaseLinea,
    Portal,
)


def _make_csv(path: Path, portal: str = "europool") -> None:
    fieldnames = [
        "num_albaran", "fecha_entrega", "num_pedido",
        "cliente_codigo", "cliente_nombre", "portal",
        "tipo_envase", "cantidad", "pdf_albaran",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow({
            "num_albaran": "ALB-WATCH-001",
            "fecha_entrega": "2024-06-15",
            "num_pedido": "PED-001",
            "cliente_codigo": "CLI001",
            "cliente_nombre": "Test Cliente",
            "portal": portal,
            "tipo_envase": "RPC6410",
            "cantidad": "50",
            "pdf_albaran": "",
        })


def test_procesar_csv_exito(tmp_path):
    """El flujo completo debe mover el CSV a procesados y generar un PDF."""
    # Parchear carpetas del watcher con tmp_path
    import watcher as w_module

    dir_pendientes = tmp_path / "pendientes"
    dir_procesando = tmp_path / "procesando"
    dir_procesados = tmp_path / "procesados"
    dir_errores    = tmp_path / "errores"
    dir_completados = tmp_path / "completados"
    for d in (dir_pendientes, dir_procesando, dir_procesados, dir_errores, dir_completados):
        d.mkdir()

    csv_file = dir_pendientes / "ALB-WATCH-001.csv"
    _make_csv(csv_file)

    albaran = Albaran(
        num_albaran="ALB-WATCH-001",
        fecha_entrega=date(2024, 6, 15),
        num_pedido="PED-001",
        cliente_codigo="CLI001",
        cliente_nombre="Test Cliente",
        portal=Portal.EUROPOOL,
        lineas=[EnvaseLinea("RPC6410", 50)],
    )
    mock_result = DeclaracionResult(
        albaran=albaran,
        status=DeclarationStatus.SUBMITTED,
        confirmation_number="CONF-999",
    )

    fake_decl_pdf = tmp_path / "declaracion.pdf"
    fake_decl_pdf.write_bytes(b"%PDF-1.4 fake")
    fake_merged_pdf = tmp_path / "completo.pdf"
    fake_merged_pdf.write_bytes(b"%PDF-1.4 fake merged")

    with (
        patch.object(w_module, "DIR_PENDIENTES", dir_pendientes),
        patch.object(w_module, "DIR_PROCESANDO", dir_procesando),
        patch.object(w_module, "DIR_PROCESADOS", dir_procesados),
        patch.object(w_module, "DIR_ERRORES",    dir_errores),
        patch.object(w_module, "DIR_COMPLETADOS", dir_completados),
        patch("watcher.init_db"),
        patch("watcher.ya_declarado", return_value=False),
        patch("watcher.get_scraper") as mock_factory,
        patch("watcher.generar_declaracion_pdf", return_value=fake_decl_pdf),
        patch("watcher.fusionar_pdfs", return_value=fake_merged_pdf),
        patch("watcher.imprimir_pdf", return_value=True),
        patch("watcher.guardar_declaracion"),
        patch("watcher.settings") as mock_settings,
    ):
        mock_settings.auto_print = False
        mock_settings.printer_name = ""
        scraper = MagicMock()
        scraper.declarar.return_value = mock_result
        mock_factory.return_value = scraper

        w_module.procesar_csv(csv_file)

    assert not csv_file.exists(), "CSV original debe haberse movido"
    assert (dir_procesados / "ALB-WATCH-001.csv").exists(), "CSV debe estar en procesados"


def test_procesar_csv_error(tmp_path):
    """Si el scraper falla, el CSV debe ir a errores."""
    import watcher as w_module

    dir_pendientes  = tmp_path / "pendientes"
    dir_procesando  = tmp_path / "procesando"
    dir_procesados  = tmp_path / "procesados"
    dir_errores     = tmp_path / "errores"
    dir_completados = tmp_path / "completados"
    for d in (dir_pendientes, dir_procesando, dir_procesados, dir_errores, dir_completados):
        d.mkdir()

    csv_file = dir_pendientes / "ALB-ERR-001.csv"
    _make_csv(csv_file)

    albaran = Albaran(
        num_albaran="ALB-ERR-001",
        fecha_entrega=date(2024, 6, 15),
        num_pedido="PED-ERR",
        cliente_codigo="CLI001",
        cliente_nombre="Test",
        portal=Portal.EUROPOOL,
        lineas=[EnvaseLinea("RPC6410", 10)],
    )
    error_result = DeclaracionResult(
        albaran=albaran,
        status=DeclarationStatus.ERROR,
        error_message="Timeout en portal",
    )

    with (
        patch.object(w_module, "DIR_PENDIENTES",  dir_pendientes),
        patch.object(w_module, "DIR_PROCESANDO",  dir_procesando),
        patch.object(w_module, "DIR_PROCESADOS",  dir_procesados),
        patch.object(w_module, "DIR_ERRORES",     dir_errores),
        patch.object(w_module, "DIR_COMPLETADOS", dir_completados),
        patch("watcher.init_db"),
        patch("watcher.ya_declarado", return_value=False),
        patch("watcher.get_scraper") as mock_factory,
        patch("watcher.guardar_declaracion"),
        patch("watcher.settings") as mock_settings,
    ):
        mock_settings.auto_print = False
        scraper = MagicMock()
        scraper.declarar.return_value = error_result
        mock_factory.return_value = scraper

        w_module.procesar_csv(csv_file)

    assert (dir_errores / "ALB-ERR-001.csv").exists(), "CSV debe estar en errores"
    assert not (dir_procesados / "ALB-ERR-001.csv").exists()

"""Tests básicos de carga de modelos y CSV."""
import csv
import tempfile
from datetime import date
from pathlib import Path

from core.models import Albaran, DeclarationStatus, EnvaseLinea, Portal, albaranes_from_csv


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "num_albaran", "fecha_entrega", "num_pedido",
        "cliente_codigo", "cliente_nombre", "portal",
        "tipo_envase", "cantidad", "pdf_albaran",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def test_albaran_creation():
    a = Albaran(
        num_albaran="ALB-001",
        fecha_entrega=date(2024, 6, 15),
        num_pedido="PED-001",
        cliente_codigo="CLI001",
        cliente_nombre="Test Cliente",
        portal=Portal.EUROPOOL,
        lineas=[EnvaseLinea("RPC6410", 50), EnvaseLinea("RPC4415", 30)],
    )
    assert a.total_envases == 80
    assert a.portal == Portal.EUROPOOL


def test_csv_loading():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp = Path(f.name)

    _write_csv([
        {
            "num_albaran": "ALB-001", "fecha_entrega": "2024-06-15",
            "num_pedido": "PED-001", "cliente_codigo": "CLI001",
            "cliente_nombre": "Cliente A", "portal": "europool",
            "tipo_envase": "RPC6410", "cantidad": "50",
        },
        {
            "num_albaran": "ALB-001", "fecha_entrega": "2024-06-15",
            "num_pedido": "PED-001", "cliente_codigo": "CLI001",
            "cliente_nombre": "Cliente A", "portal": "europool",
            "tipo_envase": "RPC4415", "cantidad": "30",
        },
        {
            "num_albaran": "ALB-002", "fecha_entrega": "2024-06-16",
            "num_pedido": "PED-002", "cliente_codigo": "CLI002",
            "cliente_nombre": "Cliente B", "portal": "ifco",
            "tipo_envase": "IFCO2310", "cantidad": "100",
        },
    ], tmp)

    albaranes = albaranes_from_csv(tmp)
    assert len(albaranes) == 2
    assert albaranes[0].num_albaran == "ALB-001"
    assert len(albaranes[0].lineas) == 2
    assert albaranes[0].total_envases == 80
    assert albaranes[1].portal == Portal.IFCO

    tmp.unlink()


def test_portal_enum():
    assert Portal("europool") == Portal.EUROPOOL
    assert Portal("ifco") == Portal.IFCO
    assert Portal("chep") == Portal.CHEP


def test_declaration_status():
    assert DeclarationStatus.PENDING.value == "pending"
    assert DeclarationStatus.CONFIRMED.value == "confirmed"

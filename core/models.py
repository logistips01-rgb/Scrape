from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional


class Portal(str, Enum):
    EUROPOOL = "europool"
    IFCO = "ifco"
    CHEP = "chep"


class DeclarationStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    ERROR = "error"


@dataclass
class EnvaseLinea:
    tipo: str        # Código de envase, p.ej. "RPC6410", "PALET_CHEP"
    cantidad: int

    def __str__(self) -> str:
        return f"{self.tipo} x{self.cantidad}"


@dataclass
class Albaran:
    num_albaran: str
    fecha_entrega: date
    num_pedido: str
    cliente_codigo: str
    cliente_nombre: str
    portal: Portal
    lineas: list[EnvaseLinea] = field(default_factory=list)
    pdf_path: Optional[Path] = None  # PDF generado por el ERP

    @property
    def total_envases(self) -> int:
        return sum(l.cantidad for l in self.lineas)


@dataclass
class DeclaracionResult:
    albaran: Albaran
    status: DeclarationStatus
    confirmation_number: Optional[str] = None
    declaration_pdf_path: Optional[Path] = None
    merged_pdf_path: Optional[Path] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Carga desde CSV
# ---------------------------------------------------------------------------

CSV_FIELDNAMES = [
    "num_albaran",
    "fecha_entrega",   # formato YYYY-MM-DD
    "num_pedido",
    "cliente_codigo",
    "cliente_nombre",
    "portal",          # europool | ifco | chep
    "tipo_envase",
    "cantidad",
    "pdf_albaran",     # ruta al PDF del ERP (opcional)
]


def albaranes_from_csv(csv_path: Path) -> list[Albaran]:
    """Agrupa las líneas del CSV por num_albaran y devuelve lista de Albaran."""
    rows: dict[str, Albaran] = {}
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row["num_albaran"]
            if key not in rows:
                pdf = Path(row["pdf_albaran"]) if row.get("pdf_albaran") else None
                rows[key] = Albaran(
                    num_albaran=row["num_albaran"],
                    fecha_entrega=date.fromisoformat(row["fecha_entrega"]),
                    num_pedido=row["num_pedido"],
                    cliente_codigo=row["cliente_codigo"],
                    cliente_nombre=row["cliente_nombre"],
                    portal=Portal(row["portal"].lower()),
                    pdf_path=pdf,
                )
            rows[key].lineas.append(
                EnvaseLinea(
                    tipo=row["tipo_envase"],
                    cantidad=int(row["cantidad"]),
                )
            )
    return list(rows.values())

"""
Punto de entrada CLI para procesar declaraciones de envases.

Uso:
    python main.py declarar input/albaranes.csv
    python main.py listar
    python main.py demo-csv

El flujo completo:
    1. Lee el CSV exportado por el ERP
    2. Para cada albarán, llama al scraper del portal correspondiente
    3. Genera el PDF de declaración
    4. Fusiona declaración + PDF albarán del ERP
    5. Guarda el resultado en output/pdfs/ y registra en BD
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from config.settings import settings
from core.database import guardar_declaracion, init_db, listar_declaraciones, ya_declarado
from core.models import DeclarationStatus, albaranes_from_csv
from documents.declaration import generar_declaracion_pdf
from documents.merger import fusionar_pdfs
from scrapers.factory import get_scraper

app = typer.Typer(help="Declarador automático de envases IFCO / Europool / CHEP")
console = Console()

# Configurar logger
logger.remove()
settings.output_dir.mkdir(parents=True, exist_ok=True)
logger.add(settings.output_dir / "logs" / "declaraciones.log", rotation="10 MB", level="DEBUG")
logger.add(sys.stderr, level="INFO")


@app.command()
def declarar(
    csv_path: Path = typer.Argument(..., help="Ruta al CSV exportado por el ERP"),
    forzar: bool = typer.Option(False, "--forzar", help="Re-declarar aunque ya esté confirmado"),
) -> None:
    """Procesa un CSV de albaranes y declara los envases en el portal correspondiente."""
    if not csv_path.exists():
        console.print(f"[red]Archivo no encontrado: {csv_path}[/red]")
        raise typer.Exit(1)

    init_db()
    albaranes = albaranes_from_csv(csv_path)
    console.print(f"\n[bold]Procesando {len(albaranes)} albarán(es)...[/bold]\n")

    for albaran in albaranes:
        console.print(f"[cyan]→ {albaran.num_albaran}[/cyan] [{albaran.portal.value}] "
                      f"{albaran.cliente_nombre} | {albaran.total_envases} envases")

        if not forzar and ya_declarado(albaran.num_albaran, albaran.portal.value):
            console.print("  [yellow]Ya declarado previamente. Omitiendo.[/yellow]")
            continue

        scraper = get_scraper(albaran.portal)
        result = scraper.declarar(albaran)

        if result.status != DeclarationStatus.ERROR:
            # Usar PDF oficial del portal si fue descargado, o generar uno propio
            if albaran.pdf_declaracion_oficial and albaran.pdf_declaracion_oficial.exists():
                result.declaration_pdf_path = albaran.pdf_declaracion_oficial
                console.print("  [blue]PDF oficial descargado del portal[/blue]")
            else:
                result.declaration_pdf_path = generar_declaracion_pdf(albaran, result)

            # Fusionar con albarán del ERP
            result.merged_pdf_path = fusionar_pdfs(
                result.declaration_pdf_path,
                albaran.pdf_path,
                albaran.num_albaran,
            )
            console.print(f"  [green]OK[/green] → {result.merged_pdf_path}")
        else:
            console.print(f"  [red]ERROR[/red]: {result.error_message}")
            if result.screenshot_path:
                console.print(f"  Captura: {result.screenshot_path}")

        guardar_declaracion(
            num_albaran=albaran.num_albaran,
            portal=albaran.portal.value,
            status=result.status.value,
            confirmation_num=result.confirmation_number,
            declaration_pdf=str(result.declaration_pdf_path) if result.declaration_pdf_path else None,
            merged_pdf=str(result.merged_pdf_path) if result.merged_pdf_path else None,
            error_message=result.error_message,
        )

    console.print("\n[bold green]Proceso completado.[/bold green]")


@app.command()
def listar() -> None:
    """Muestra el historial de declaraciones enviadas."""
    init_db()
    rows = listar_declaraciones()
    if not rows:
        console.print("No hay declaraciones registradas.")
        return

    table = Table(title="Declaraciones registradas")
    for col in ("ID", "Albarán", "Portal", "Fecha", "Estado", "Confirmación"):
        table.add_column(col)

    for r in rows:
        color = {"confirmed": "green", "submitted": "cyan", "error": "red", "pending": "yellow"}.get(r["status"], "white")
        table.add_row(
            str(r["id"]),
            r["num_albaran"],
            r["portal"],
            r["fecha_declaracion"][:16],
            f"[{color}]{r['status']}[/{color}]",
            r["confirmation_num"] or "—",
        )
    console.print(table)


@app.command(name="demo-csv")
def demo_csv() -> None:
    """Genera un CSV de ejemplo para probar el sistema."""
    demo_path = settings.input_dir / "ejemplo.csv"
    settings.input_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "num_albaran", "fecha_entrega", "num_pedido",
        "cliente_codigo", "cliente_nombre", "portal",
        "tipo_envase", "cantidad", "pdf_albaran",
    ]
    rows = [
        {
            "num_albaran": "ALB-2024-001",
            "fecha_entrega": "2024-06-15",
            "num_pedido": "PED-2024-100",
            "cliente_codigo": "CLI001",
            "cliente_nombre": "Frutas García S.L.",
            "portal": "europool",
            "tipo_envase": "RPC6410",
            "cantidad": "50",
            "pdf_albaran": "",
        },
        {
            "num_albaran": "ALB-2024-001",
            "fecha_entrega": "2024-06-15",
            "num_pedido": "PED-2024-100",
            "cliente_codigo": "CLI001",
            "cliente_nombre": "Frutas García S.L.",
            "portal": "europool",
            "tipo_envase": "RPC4415",
            "cantidad": "30",
            "pdf_albaran": "",
        },
        {
            "num_albaran": "ALB-2024-002",
            "fecha_entrega": "2024-06-16",
            "num_pedido": "PED-2024-101",
            "cliente_codigo": "CLI002",
            "cliente_nombre": "Verduras López S.A.",
            "portal": "ifco",
            "tipo_envase": "IFCO2310",
            "cantidad": "100",
            "pdf_albaran": "",
        },
    ]

    with open(demo_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    console.print(f"[green]CSV de ejemplo creado:[/green] {demo_path}")


if __name__ == "__main__":
    app()

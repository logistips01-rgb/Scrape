"""
Herramienta para declarar en Euro Pool llamando directamente a su API (sin formulario).

Uso:
    python europool_api.py explorar
        → Login (navegador, solo si no hay token válido) y guarda en
          output/europool_api/*.json los catálogos: destinos, tipos de envase...
          Muestra un resumen de destinos y envases con sus IDs.

    python europool_api.py probar input/prueba_uno.csv
        → Monta el JSON de cada albarán y valida la fecha con Euro Pool,
          SIN crear nada. Sirve para comprobar el mapeo.

    python europool_api.py probar input/prueba_uno.csv --enviar
        → Crea de verdad el movimiento en Euro Pool.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from core.erp_parser import albaranes_from_xls
from core.models import albaranes_from_csv
from scrapers.europool_api import EuropoolApi

app = typer.Typer(help="Euro Pool: declaración directa por API")
console = Console()


@app.command()
def explorar(nuevo_token: bool = typer.Option(False, "--nuevo-token", help="Forzar login")) -> None:
    """Descarga los catálogos de la API y muestra destinos y tipos de envase."""
    api = EuropoolApi(forzar_token=nuevo_token)
    console.print(f"CustomerId activo: [bold]{api.customer_id or '(ninguno)'}[/bold]")
    carpeta = api.volcar_catalogos()
    console.print(f"Catálogos guardados en [cyan]{carpeta}[/cyan]\n")

    try:
        api.resolver_ruta("__listar__")
    except RuntimeError as exc:
        console.print(f"[bold]Destinos:[/bold] {str(exc).split('Disponibles:')[-1]}\n")
    try:
        api.resolver_envase("__listar__")
    except RuntimeError as exc:
        console.print(f"[bold]Envases:[/bold] {str(exc).split('Disponibles:')[-1]}")


@app.command()
def probar(
    fichero: Path = typer.Argument(..., help="XLS o CSV del ERP"),
    enviar: bool = typer.Option(False, "--enviar", help="Crear de verdad el movimiento"),
) -> None:
    """Monta y valida (o envía con --enviar) los movimientos del fichero."""
    if fichero.suffix.lower() in (".xls", ".xlsx"):
        albaranes = albaranes_from_xls(fichero)
    else:
        albaranes = albaranes_from_csv(fichero)
    albaranes = [a for a in albaranes if a.portal.value == "europool"]

    api = EuropoolApi()
    for albaran in albaranes:
        console.print(f"\n[cyan]→ {albaran.num_albaran}[/cyan] {albaran.cliente_nombre}")
        try:
            flow = api.construir_flow(albaran)
            console.print_json(json.dumps(flow, ensure_ascii=False))
            console.print(f"  checkFlowDate: {api.validar_fecha(flow)}")
            if enviar:
                console.print(f"  [green]Creado:[/green] {api.crear_flow(flow)}")
        except Exception as exc:
            console.print(f"  [red]Error:[/red] {exc}")


if __name__ == "__main__":
    app()

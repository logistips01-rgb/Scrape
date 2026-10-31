"""
Punto de entrada para que la app de almacén declare albaranes en Euro Pool por API.

La app envía los datos ya extraídos del albarán en JSON:

    {
      "num_albaran":    "AV26/031825",
      "fecha_entrega":  "2026-06-13",
      "num_pedido":     "4500123456",
      "cliente_nombre": "Consum Barcelona Carne.",     ← nombre del destino en Euro Pool
      "lineas": [
        {"tipo": "216-Caja Verde", "cantidad": 65}
      ],
      "enviar": false                                  ← false = simulación (no crea nada)
    }

y recibe:

    {"ok": true, "estado": "simulado" | "declarado" | "ya_declarado" | "error",
     "confirmacion": "...", "pdf": "...", "flow": {...}, "error": "..."}

Dos formas de llamarlo:

  1) Línea de comandos (JSON por fichero o por stdin con "-"):
       python europool_servicio.py declarar albaran.json
       type albaran.json | python europool_servicio.py declarar -
     Imprime el JSON de respuesta. Código de salida 0 = ok, 1 = error.

  2) Servidor HTTP local (la app hace POST):
       python europool_servicio.py servidor --puerto 8765
       POST http://127.0.0.1:8765/europool/declarar   (cuerpo: el JSON de arriba)
     Atiende las peticiones de una en una para no hacer dos logins a la vez.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import typer
from loguru import logger

from config.settings import settings
from core.database import guardar_declaracion, init_db, ya_declarado
from core.models import Albaran, EnvaseLinea, Portal
from scrapers.europool_api import EuropoolApi, EuropoolApiDeclarer

app = typer.Typer(help="Servicio de declaración Euro Pool por API para la app de almacén")

logger.remove()
settings.output_dir.mkdir(parents=True, exist_ok=True)
logger.add(settings.output_dir / "logs" / "europool_servicio.log", rotation="10 MB", level="DEBUG")
logger.add(sys.stderr, level="INFO")


def _albaran_desde_json(data: dict) -> Albaran:
    faltan = [c for c in ("num_albaran", "fecha_entrega", "cliente_nombre", "lineas") if not data.get(c)]
    if faltan:
        raise ValueError(f"Faltan campos obligatorios: {faltan}")
    lineas = [EnvaseLinea(tipo=str(l["tipo"]), cantidad=int(l["cantidad"])) for l in data["lineas"]]
    if any(l.cantidad <= 0 for l in lineas):
        raise ValueError("Todas las cantidades deben ser mayores que 0")
    return Albaran(
        num_albaran=str(data["num_albaran"]),
        fecha_entrega=date.fromisoformat(str(data["fecha_entrega"])[:10]),
        num_pedido=str(data.get("num_pedido") or ""),
        cliente_codigo=str(data.get("cliente_codigo") or ""),
        cliente_nombre=str(data["cliente_nombre"]),
        portal=Portal.EUROPOOL,
        lineas=lineas,
    )


def procesar(data: dict) -> dict:
    """Valida, simula o declara un albarán. Nunca lanza excepción: devuelve el error en el dict."""
    init_db()
    enviar = bool(data.get("enviar"))
    try:
        albaran = _albaran_desde_json(data)

        if ya_declarado(albaran.num_albaran, Portal.EUROPOOL.value) and not data.get("forzar"):
            return {"ok": True, "estado": "ya_declarado", "num_albaran": albaran.num_albaran}

        if not enviar:
            api = EuropoolApi()
            flow = api.construir_flow(albaran)
            api.validar_fecha(flow)
            return {"ok": True, "estado": "simulado", "num_albaran": albaran.num_albaran, "flow": flow}

        result = EuropoolApiDeclarer().declarar(albaran)
        pdf = str(albaran.pdf_declaracion_oficial) if albaran.pdf_declaracion_oficial else None
        guardar_declaracion(
            num_albaran=albaran.num_albaran,
            portal=Portal.EUROPOOL.value,
            status=result.status.value,
            confirmation_num=result.confirmation_number,
            declaration_pdf=pdf,
            error_message=result.error_message,
        )
        if result.status.value == "error":
            return {"ok": False, "estado": "error", "num_albaran": albaran.num_albaran,
                    "error": result.error_message}
        return {"ok": True, "estado": "declarado", "num_albaran": albaran.num_albaran,
                "confirmacion": result.confirmation_number, "pdf": pdf}

    except Exception as exc:
        logger.exception(f"[europool-servicio] Error procesando {data.get('num_albaran')}")
        return {"ok": False, "estado": "error", "num_albaran": data.get("num_albaran"), "error": str(exc)}


@app.command()
def declarar(
    fichero: str = typer.Argument(..., help="Fichero JSON del albarán, o '-' para leer de stdin"),
    enviar: bool = typer.Option(False, "--enviar", help="Crear de verdad el movimiento"),
) -> None:
    """Procesa un albarán en JSON e imprime el resultado en JSON."""
    texto = sys.stdin.read() if fichero == "-" else Path(fichero).read_text(encoding="utf-8-sig")
    data = json.loads(texto)
    if enviar:
        data["enviar"] = True
    respuesta = procesar(data)
    print(json.dumps(respuesta, ensure_ascii=False))
    raise typer.Exit(0 if respuesta["ok"] else 1)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/europool/declarar":
            self._responder(404, {"ok": False, "error": "Ruta no encontrada"})
            return
        try:
            largo = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(largo).decode("utf-8-sig"))
        except Exception as exc:
            self._responder(400, {"ok": False, "estado": "error", "error": f"JSON no válido: {exc}"})
            return
        respuesta = procesar(data)
        self._responder(200 if respuesta["ok"] else 422, respuesta)

    def _responder(self, codigo: int, cuerpo: dict) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, fmt: str, *args) -> None:
        logger.info(f"[europool-servicio] {self.address_string()} {fmt % args}")


@app.command()
def servidor(
    host: str = typer.Option("127.0.0.1", help="Interfaz de escucha (127.0.0.1 = solo este PC)"),
    puerto: int = typer.Option(8765, help="Puerto HTTP"),
) -> None:
    """Arranca el servidor HTTP local para la app de almacén."""
    logger.info(f"[europool-servicio] Escuchando en http://{host}:{puerto}/europool/declarar")
    HTTPServer((host, puerto), _Handler).serve_forever()


if __name__ == "__main__":
    app()

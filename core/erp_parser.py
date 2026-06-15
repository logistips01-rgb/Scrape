"""
Parser del fichero XLS exportado por el ERP Prisma 4.

Formato del fichero:
  COD_CLI | DIRECCION | NOMBRE | SERIE | NUM_ALBARAN | FECHA(DD-MM-YYYY)
  CODIG   | DESCRIPCION | UNIDADES | CANTIDAD | PRECIO | DESCUENTO | LOTE | PEDIDO

Las líneas de envase se identifican por PRECIO='0' y LOTE='' (vacío).
Se agrupan por NUM_ALBARAN + portal y se devuelven como lista de Albaran.

Requiere los ficheros de configuración:
  config/envases_mapping.json  → código ERP → (portal, nombre en portal)
  config/clientes_mapping.json → nombre ERP → nombre exacto en portal
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import xlrd
from loguru import logger

from core.models import Albaran, EnvaseLinea, Portal

# Portales ignorados (no implementados)
_PORTALES_IGNORADOS = {"lpr"}

# Rutas por defecto a los ficheros de mapeo
_DIR = Path(__file__).parent.parent / "config"
_ENVASES_MAP_FILE  = _DIR / "envases_mapping.json"
_CLIENTES_MAP_FILE = _DIR / "clientes_mapping.json"


def _cargar_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def albaranes_from_xls(
    xls_path: Path,
    envases_map: dict | None = None,
    clientes_map: dict | None = None,
) -> list[Albaran]:
    """
    Lee el XLS del ERP y devuelve los albaranes con líneas de envase.

    Solo incluye los albaranes que tienen al menos un tipo de envase
    configurado en envases_mapping.json para un portal soportado.

    Args:
        xls_path:     Ruta al fichero .xls exportado por el ERP
        envases_map:  Mapeo código ERP → [portal, nombre_portal].
                      Si None, carga config/envases_mapping.json
        clientes_map: Mapeo nombre ERP → nombre en portal.
                      Si None, carga config/clientes_mapping.json
    """
    if envases_map is None:
        envases_map = _cargar_json(_ENVASES_MAP_FILE)
    if clientes_map is None:
        clientes_map = _cargar_json(_CLIENTES_MAP_FILE)

    wb = xlrd.open_workbook(str(xls_path))
    sheet = wb.sheets()[0]

    # ── Primera pasada: recopilar metadatos de cada albarán ──────────
    meta: dict[str, dict] = {}  # num_albaran → {nombre, fecha, pedido, cod_cli}

    for r in range(1, sheet.nrows):
        num_alb = str(sheet.cell_value(r, 4)).strip()
        if not num_alb:
            continue

        nombre  = str(sheet.cell_value(r, 2)).strip()
        fecha_s = str(sheet.cell_value(r, 5)).strip()
        pedido  = str(sheet.cell_value(r, 13)).strip()
        cod_cli = str(sheet.cell_value(r, 0)).strip()

        if num_alb not in meta:
            meta[num_alb] = {"nombre": "", "fecha_s": fecha_s,
                              "pedido": pedido, "cod_cli": cod_cli}

        # Actualizar nombre: la primera fila del albarán puede estar vacía
        if nombre and not meta[num_alb]["nombre"]:
            meta[num_alb]["nombre"] = nombre
        if pedido and not meta[num_alb]["pedido"]:
            meta[num_alb]["pedido"] = pedido

    # ── Segunda pasada: recopilar líneas de envase ───────────────────
    # Clave: "num_albaran|portal"
    lineas_por_alb: dict[str, list[EnvaseLinea]] = {}
    portal_por_alb: dict[str, Portal] = {}

    for r in range(1, sheet.nrows):
        precio  = str(sheet.cell_value(r, 10)).strip().replace(",", ".")
        lote    = str(sheet.cell_value(r, 12)).strip()
        codig   = str(sheet.cell_value(r, 6)).strip()
        unidades = sheet.cell_value(r, 8)
        num_alb = str(sheet.cell_value(r, 4)).strip()

        # Filtrar líneas de envase: precio=0 y lote vacío
        try:
            if float(precio) != 0.0 or lote != "":
                continue
        except ValueError:
            continue

        # Buscar el código en el mapeo
        if codig not in envases_map:
            logger.debug(f"Código {codig} no configurado en envases_mapping.json, ignorado")
            continue

        portal_nombre, tipo_portal = envases_map[codig]

        # Ignorar portales no implementados
        if portal_nombre in _PORTALES_IGNORADOS:
            logger.debug(f"Portal '{portal_nombre}' no implementado, ignorando {codig}")
            continue

        try:
            portal = Portal(portal_nombre)
        except ValueError:
            logger.warning(f"Portal desconocido '{portal_nombre}' en mapeo para código {codig}")
            continue

        cantidad = int(float(str(unidades).replace(",", ".")))
        if cantidad <= 0:
            continue

        key = f"{num_alb}|{portal_nombre}"
        if key not in lineas_por_alb:
            lineas_por_alb[key] = []
            portal_por_alb[key] = portal

        lineas_por_alb[key].append(EnvaseLinea(tipo=tipo_portal, cantidad=cantidad))
        logger.debug(f"  [{num_alb}] {tipo_portal} x {cantidad} → {portal_nombre}")

    # ── Construir objetos Albaran ────────────────────────────────────
    albaranes: list[Albaran] = []

    for key, lineas in lineas_por_alb.items():
        num_alb, _ = key.split("|", 1)
        m = meta.get(num_alb, {})
        portal = portal_por_alb[key]

        nombre_erp = m.get("nombre", "")
        # Mapear nombre ERP → nombre en portal (si está configurado)
        nombre_portal = clientes_map.get(nombre_erp, nombre_erp)
        if nombre_portal == nombre_erp and nombre_erp:
            logger.warning(
                f"Cliente '{nombre_erp}' no encontrado en clientes_mapping.json. "
                f"Se usará tal cual — verifique que coincida con el portal."
            )

        try:
            fecha = datetime.strptime(m.get("fecha_s", ""), "%d-%m-%Y").date()
        except ValueError:
            logger.error(f"Fecha inválida para albarán {num_alb}: {m.get('fecha_s')}")
            continue

        albaranes.append(Albaran(
            num_albaran=num_alb,
            fecha_entrega=fecha,
            num_pedido=m.get("pedido", ""),
            cliente_codigo=m.get("cod_cli", ""),
            cliente_nombre=nombre_portal,
            portal=portal,
            lineas=lineas,
        ))

    logger.info(
        f"XLS procesado: {len(albaranes)} albarán(es) con envases "
        f"({sum(len(a.lineas) for a in albaranes)} líneas)"
    )
    return albaranes

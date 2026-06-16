"""
Parser del fichero XLS exportado por el ERP.

Soporta dos formatos:

  FORMATO NUEVO (columnas nombradas, exportación personalizada):
    Cabecera fija en fila 0:
      CLIENTE | SPEDIDO | ALBARAN | DESCRIPCION | CANTIDAD | FECHAENTREGA
    Cada fila = una línea de envase. Se detecta automáticamente si la
    primera fila contiene "ALBARAN" y "CLIENTE".

  FORMATO ANTIGUO (Prisma 4, columnas por posición):
    COD_CLI | DIRECCION | NOMBRE | SERIE | NUM_ALBARAN | FECHA | CODIG |
    DESCRIPCION | UNIDADES | CANTIDAD | PRECIO | DESCUENTO | LOTE | PEDIDO
    Las líneas de envase se identifican por PRECIO=0 y LOTE vacío.

En ambos casos se usan:
  config/envases_mapping.json  → código/texto ERP → (portal, nombre en portal)
  config/clientes_mapping.json → nombre ERP       → nombre exacto en portal
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import xlrd
from loguru import logger

from core.models import Albaran, EnvaseLinea, Portal

_PORTALES_IGNORADOS = {"lpr"}

_DIR = Path(__file__).parent.parent / "config"
_ENVASES_MAP_FILE  = _DIR / "envases_mapping.json"
_CLIENTES_MAP_FILE = _DIR / "clientes_mapping.json"


def _cargar_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Punto de entrada único — auto-detecta el formato
# ---------------------------------------------------------------------------

def albaranes_from_xls(
    xls_path: Path,
    envases_map: dict | None = None,
    clientes_map: dict | None = None,
) -> list[Albaran]:
    """Lee un XLS del ERP y devuelve los albaranes con líneas de envase.

    Detecta automáticamente el formato (nombrado vs. posicional antiguo).
    """
    if envases_map is None:
        envases_map = _cargar_json(_ENVASES_MAP_FILE)
    if clientes_map is None:
        clientes_map = _cargar_json(_CLIENTES_MAP_FILE)

    wb = xlrd.open_workbook(str(xls_path))
    sheet = wb.sheets()[0]

    if sheet.nrows == 0:
        return []

    # Auto-detección: si la primera fila tiene "ALBARAN" y "CLIENTE" → nuevo formato
    headers_row0 = [str(sheet.cell_value(0, c)).strip().upper() for c in range(sheet.ncols)]
    if "ALBARAN" in headers_row0 and "CLIENTE" in headers_row0:
        logger.info("XLS con columnas nombradas detectado")
        return _from_named(sheet, envases_map, clientes_map)

    logger.info("XLS en formato posicional (Prisma 4) detectado")
    return _from_positional(sheet, envases_map, clientes_map)


# ---------------------------------------------------------------------------
# Formato nuevo: columnas nombradas
# ---------------------------------------------------------------------------

def _from_named(
    sheet: xlrd.sheet.Sheet,
    envases_map: dict,
    clientes_map: dict,
) -> list[Albaran]:
    """
    Lee el XLS con cabecera nombrada:
      CLIENTE | SPEDIDO | ALBARAN | DESCRIPCION | CANTIDAD | FECHAENTREGA
    Cada fila = una línea de envase.
    """
    headers = [str(sheet.cell_value(0, c)).strip().upper() for c in range(sheet.ncols)]

    def _idx(name: str) -> int:
        try:
            return headers.index(name)
        except ValueError:
            raise ValueError(f"Columna '{name}' no encontrada. Cabeceras: {headers}")

    idx_cli   = _idx("CLIENTE")
    idx_sped  = _idx("SPEDIDO")
    idx_alb   = _idx("ALBARAN")
    idx_desc  = _idx("DESCRIPCION")
    idx_cant  = _idx("CANTIDAD")
    idx_fecha = _idx("FECHAENTREGA")

    agrupado: dict[str, dict] = {}  # "ALBARAN|portal" → datos

    for r in range(1, sheet.nrows):
        num_alb = str(sheet.cell_value(r, idx_alb)).strip()
        if not num_alb:
            continue

        desc    = str(sheet.cell_value(r, idx_desc)).strip()
        cliente = str(sheet.cell_value(r, idx_cli)).strip()
        spedido = str(sheet.cell_value(r, idx_sped)).strip()
        cant_v  = sheet.cell_value(r, idx_cant)
        fecha_v = sheet.cell_value(r, idx_fecha)

        # Resolver portal y nombre de envase
        portal_nombre, tipo_portal = _resolver_envase(desc, envases_map)
        if portal_nombre is None:
            logger.debug(f"[{num_alb}] DESCRIPCION '{desc}' sin mapeo, ignorada")
            continue
        if portal_nombre in _PORTALES_IGNORADOS:
            continue

        try:
            portal = Portal(portal_nombre)
        except ValueError:
            logger.warning(f"Portal desconocido '{portal_nombre}' en mapeo para '{desc}'")
            continue

        try:
            cantidad = int(float(str(cant_v).replace(",", ".")))
        except (ValueError, TypeError):
            continue
        if cantidad <= 0:
            continue

        fecha = _parsear_fecha(fecha_v, sheet.book.datemode, num_alb)
        if fecha is None:
            continue

        nombre_portal = clientes_map.get(cliente, cliente)
        if nombre_portal == cliente and cliente:
            logger.warning(
                f"Cliente '{cliente}' no en clientes_mapping.json — "
                f"se usará tal cual"
            )

        key = f"{num_alb}|{portal_nombre}"
        if key not in agrupado:
            agrupado[key] = {
                "num_albaran":   num_alb,
                "fecha":         fecha,
                "num_pedido":    spedido,
                "cliente_nombre": nombre_portal,
                "portal":        portal,
                "lineas":        [],
            }
        agrupado[key]["lineas"].append(EnvaseLinea(tipo=tipo_portal, cantidad=cantidad))
        logger.debug(f"  [{num_alb}] {tipo_portal} × {cantidad} → {portal_nombre}")

    albaranes = [
        Albaran(
            num_albaran=v["num_albaran"],
            fecha_entrega=v["fecha"],
            num_pedido=v["num_pedido"],
            cliente_codigo="",
            cliente_nombre=v["cliente_nombre"],
            portal=v["portal"],
            lineas=v["lineas"],
        )
        for v in agrupado.values()
    ]

    logger.info(
        f"XLS procesado: {len(albaranes)} albarán(es) con envases "
        f"({sum(len(a.lineas) for a in albaranes)} líneas)"
    )
    return albaranes


# ---------------------------------------------------------------------------
# Formato antiguo: columnas por posición (Prisma 4)
# ---------------------------------------------------------------------------

def _from_positional(
    sheet: xlrd.sheet.Sheet,
    envases_map: dict,
    clientes_map: dict,
) -> list[Albaran]:
    """Lee el XLS de Prisma 4 con columnas en posición fija."""
    # ── Primera pasada: metadatos de cada albarán ────────────────────
    meta: dict[str, dict] = {}

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
        if nombre and not meta[num_alb]["nombre"]:
            meta[num_alb]["nombre"] = nombre
        if pedido and not meta[num_alb]["pedido"]:
            meta[num_alb]["pedido"] = pedido

    # ── Segunda pasada: líneas de envase ────────────────────────────
    lineas_por_alb: dict[str, list[EnvaseLinea]] = {}
    portal_por_alb: dict[str, Portal] = {}

    for r in range(1, sheet.nrows):
        precio  = str(sheet.cell_value(r, 10)).strip().replace(",", ".")
        lote    = str(sheet.cell_value(r, 12)).strip()
        codig   = str(sheet.cell_value(r, 6)).strip()
        unidades = sheet.cell_value(r, 8)
        num_alb = str(sheet.cell_value(r, 4)).strip()

        try:
            if float(precio) != 0.0 or lote != "":
                continue
        except ValueError:
            continue

        if codig not in envases_map:
            logger.debug(f"Código {codig} no configurado en envases_mapping.json, ignorado")
            continue

        portal_nombre, tipo_portal = envases_map[codig]

        if portal_nombre in _PORTALES_IGNORADOS:
            continue

        try:
            portal = Portal(portal_nombre)
        except ValueError:
            logger.warning(f"Portal desconocido '{portal_nombre}'")
            continue

        cantidad = int(float(str(unidades).replace(",", ".")))
        if cantidad <= 0:
            continue

        key = f"{num_alb}|{portal_nombre}"
        if key not in lineas_por_alb:
            lineas_por_alb[key] = []
            portal_por_alb[key] = portal

        lineas_por_alb[key].append(EnvaseLinea(tipo=tipo_portal, cantidad=cantidad))
        logger.debug(f"  [{num_alb}] {tipo_portal} × {cantidad} → {portal_nombre}")

    # ── Construir Albaran ────────────────────────────────────────────
    albaranes: list[Albaran] = []

    for key, lineas in lineas_por_alb.items():
        num_alb, _ = key.split("|", 1)
        m = meta.get(num_alb, {})
        portal = portal_por_alb[key]

        nombre_erp = m.get("nombre", "")
        nombre_portal = clientes_map.get(nombre_erp, nombre_erp)
        if nombre_portal == nombre_erp and nombre_erp:
            logger.warning(
                f"Cliente '{nombre_erp}' no en clientes_mapping.json — "
                f"se usará tal cual"
            )

        fecha = _parsear_fecha(m.get("fecha_s", ""), 0, num_alb)
        if fecha is None:
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


# ---------------------------------------------------------------------------
# Helpers comunes
# ---------------------------------------------------------------------------

def _resolver_envase(desc: str, envases_map: dict) -> tuple[str | None, str | None]:
    """Mapea código o texto ERP → (portal, tipo_en_portal).

    Primero busca por código exacto, luego por texto parcial en los valores.
    """
    if desc in envases_map:
        v = envases_map[desc]
        return v[0], v[1]

    desc_u = desc.upper()
    for _code, (portal, tipo) in envases_map.items():
        if desc_u in tipo.upper() or tipo.upper() in desc_u:
            return portal, tipo

    return None, None


def _parsear_fecha(value, datemode: int, num_alb: str) -> date | None:
    """Parsea valor de celda Excel (número nativo o texto) como date."""
    if isinstance(value, float) and value > 0:
        try:
            t = xlrd.xldate_as_tuple(value, datemode)
            return date(t[0], t[1], t[2])
        except Exception:
            pass

    s = str(value).strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    if s:
        logger.error(f"Fecha inválida para albarán {num_alb}: {value!r}")
    return None

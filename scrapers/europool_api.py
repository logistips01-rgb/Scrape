"""
Declaración de envases en Euro Pool System llamando DIRECTAMENTE a su API REST,
sin rellenar el formulario web.

El webportal (Angular) usa por debajo estos endpoints (extraídos de su JS):
  GET  /api/User/context                                   → contexto del usuario
  GET  /api/Customer/getFlowTypes?date=YYYY-MM-DD&CustomerId=X
                                                           → tipos de movimiento, orígenes y destinos
  GET  /api/Definition/get?language=es                     → catálogo (tipos de envase, etc.)
  POST /api/Flow/checkFlowDate                             → valida la fecha del movimiento
  POST /api/Flow/create                                    → CREA EL MOVIMIENTO (lo que hace "ENVIAR")
  GET  /api/Flow/getFlowDocument?EtmOrderNumber=X          → PDF oficial

Autenticación: token Bearer de Microsoft Azure AD (MSAL). No hay usuario/contraseña
de API, así que el token se obtiene UNA vez abriendo el portal con el navegador
(mismo perfil persistente y mismo login que el scraper) y capturando la cabecera
Authorization de las peticiones que hace la propia web. Se guarda en
output/europool_token.json y se reutiliza mientras no caduque (~1 h).
Todas las peticiones llevan además la cabecera CustomerId del cliente activo.
"""
from __future__ import annotations

import base64
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from config.settings import settings
from core.models import Albaran, DeclarationStatus, DeclaracionResult

API_URL       = "https://webportal.europoolsystem.com/api"
DASHBOARD_URL = "https://webportal.europoolsystem.com/#/dashboard"

_TOKEN_FILE = settings.output_dir / "europool_token.json"
_DUMP_DIR   = settings.output_dir / "europool_api"


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

def _jwt_exp(token: str) -> float:
    """Devuelve el 'exp' (epoch) de un JWT sin validar la firma."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return 0.0


def _leer_token_cache() -> dict | None:
    try:
        data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        # Margen de 5 min para no usar un token a punto de caducar
        if _jwt_exp(data["token"]) - time.time() > 300:
            return data
    except Exception:
        pass
    return None


def _capturar_token_con_navegador() -> dict:
    """
    Abre el portal con el navegador (perfil persistente), hace login si hace falta
    y captura el Bearer token + CustomerId de las llamadas que hace la web a /api.
    """
    from scrapers.europool import EuropoolScraper

    capturado: dict[str, str] = {}

    def _on_request(req) -> None:
        if "/api/" not in req.url:
            return
        headers = req.headers
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer ") and "token" not in capturado:
            capturado["token"] = auth[7:]
        if headers.get("customerid") and "customer_id" not in capturado:
            capturado["customer_id"] = headers["customerid"]

    scraper = EuropoolScraper()
    try:
        scraper._start_browser()
        page = scraper._page
        page.on("request", _on_request)
        scraper._login()

        # Cargar el dashboard fuerza a la web a llamar a la API (y a renovar el token)
        if "token" not in capturado:
            page.goto(DASHBOARD_URL)
        for _ in range(40):
            if "token" in capturado and "customer_id" in capturado:
                break
            page.wait_for_timeout(500)
    finally:
        scraper._stop_browser()

    if "token" not in capturado:
        raise RuntimeError("No se pudo capturar el token de Euro Pool (¿login correcto?)")

    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(json.dumps(capturado), encoding="utf-8")
    logger.info("[europool-api] Token capturado y guardado")
    return capturado


def obtener_token(forzar: bool = False) -> dict:
    """Devuelve {'token': ..., 'customer_id': ...} usando la caché si es válida."""
    if not forzar:
        cache = _leer_token_cache()
        if cache:
            return cache
    return _capturar_token_con_navegador()


# ---------------------------------------------------------------------------
# Utilidades de búsqueda en las respuestas JSON
# ---------------------------------------------------------------------------

def _norm(texto: Any) -> str:
    """Minúsculas, sin acentos, sin signos: 'Consum Barcelona Carne.' → 'consumbarcelonacarne'."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t.lower())


def _buscar_listas(obj: Any, clave: str) -> list:
    """Busca recursivamente todas las listas/dicts bajo una clave (insensible a mayúsculas)."""
    encontrados: list = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == clave.lower():
                encontrados.append(v)
            encontrados.extend(_buscar_listas(v, clave))
    elif isinstance(obj, list):
        for v in obj:
            encontrados.extend(_buscar_listas(v, clave))
    return encontrados


# ---------------------------------------------------------------------------
# Cliente API
# ---------------------------------------------------------------------------

class EuropoolApi:
    def __init__(self, forzar_token: bool = False) -> None:
        auth = obtener_token(forzar=forzar_token)
        self.token: str = auth["token"]
        self.customer_id: str = settings.europool_customer_id or auth.get("customer_id", "")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept":        "application/json",
        })
        self._flow_types: dict | None = None
        self._definitions: dict | None = None

    # -- HTTP ----------------------------------------------------------------

    def _headers(self) -> dict:
        return {"CustomerId": self.customer_id} if self.customer_id else {}

    def get(self, path: str, **params) -> Any:
        r = self._session.get(f"{API_URL}{path}", params=params or None,
                              headers=self._headers(), timeout=60)
        self._check(r, path)
        return r.json() if r.content else None

    def post(self, path: str, body: Any) -> Any:
        r = self._session.post(f"{API_URL}{path}", json=body,
                               headers=self._headers(), timeout=60)
        self._check(r, path)
        return r.json() if r.content else None

    def get_blob(self, path: str, **params) -> bytes:
        r = self._session.get(f"{API_URL}{path}", params=params or None,
                              headers=self._headers(), timeout=120)
        self._check(r, path)
        return r.content

    @staticmethod
    def _check(r: requests.Response, path: str) -> None:
        if r.status_code == 401:
            # Token caducado o revocado: borrar caché para que el próximo intento renueve
            _TOKEN_FILE.unlink(missing_ok=True)
        if r.status_code >= 400:
            raise RuntimeError(f"Euro Pool API {path} → HTTP {r.status_code}: {r.text[:500]}")

    # -- Catálogos -----------------------------------------------------------

    def user_context(self) -> Any:
        return self.get("/User/context")

    def flow_types(self) -> dict:
        if self._flow_types is None:
            self._flow_types = self.get(
                "/Customer/getFlowTypes",
                date=date.today().isoformat(),
                CustomerId=self.customer_id,
            )
        return self._flow_types

    def definitions(self) -> dict:
        if self._definitions is None:
            self._definitions = self.get("/Definition/get", language="es")
        return self._definitions

    def volcar_catalogos(self) -> Path:
        """Guarda en output/europool_api/*.json todo lo necesario para mapear datos."""
        _DUMP_DIR.mkdir(parents=True, exist_ok=True)
        hoy = date.today().isoformat()
        consultas = {
            "user_context":  lambda: self.user_context(),
            "flow_types":    lambda: self.flow_types(),
            "definitions":   lambda: self.definitions(),
            "customer_info": lambda: self.get("/Customer/getCustomerInfo",
                                              date=hoy, CustomerId=self.customer_id),
            "filter_values": lambda: self.post("/Flow/getFilterValues",
                                               {"customerId": [self.customer_id]}),
            "ultimos_flows": lambda: self.get("/Flow/Latest", CustomerId=self.customer_id),
        }
        for nombre, fn in consultas.items():
            try:
                data = fn()
            except Exception as exc:
                data = {"_error": str(exc)}
            (_DUMP_DIR / f"{nombre}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return _DUMP_DIR

    # -- Resolución de IDs ---------------------------------------------------

    def _tipos_movimiento(self) -> list[dict]:
        data = self.flow_types()
        if isinstance(data, list):
            return data
        for clave in ("flowTypes", "orderTypes", "items"):
            if isinstance(data.get(clave), list):
                return data[clave]
        return []

    def _nombres_ubicaciones(self) -> dict[str, str]:
        """id → nombre de todas las ubicaciones que aparezcan en getFlowTypes."""
        nombres: dict[str, str] = {}
        for locs in _buscar_listas(self.flow_types(), "locations"):
            items = locs.values() if isinstance(locs, dict) else locs
            for loc in items:
                if isinstance(loc, dict) and loc.get("id"):
                    nombres[str(loc["id"])] = loc.get("name") or ""
        return nombres

    def resolver_ruta(self, cliente_nombre: str) -> dict:
        """
        Devuelve {flowType, fromId, toId, frequency} para el destino indicado.
        Tipo de movimiento y origen: el configurado en .env o el único/primero disponible.
        Destino: el 'to' cuyo nombre coincide con el nombre del cliente en el portal.
        """
        tipos = self._tipos_movimiento()
        if settings.europool_flow_type:
            tipos = [t for t in tipos if t.get("id") == settings.europool_flow_type]
        if not tipos:
            raise RuntimeError("No hay tipos de movimiento disponibles (revisa flow_types.json)")

        nombres = self._nombres_ubicaciones()
        objetivo = _norm(cliente_nombre)
        candidatos = []
        for tipo in tipos:
            for cond in tipo.get("shippingConditions") or []:
                for origen in cond.get("froms") or []:
                    if settings.europool_from_id and origen.get("id") != settings.europool_from_id:
                        continue
                    for destino in origen.get("tos") or []:
                        nombre = destino.get("name") or nombres.get(str(destino.get("id")), "")
                        candidatos.append((tipo, origen, destino, nombre))

        for exacto in (True, False):
            for tipo, origen, destino, nombre in candidatos:
                n = _norm(nombre)
                if (n == objetivo) if exacto else (n and (objetivo in n or n in objetivo)):
                    return {
                        "flowType":  tipo.get("id"),
                        "fromId":    origen.get("id"),
                        "toId":      destino.get("id"),
                        "frequency": destino.get("frequency"),
                        "toName":    nombre,
                    }

        disponibles = sorted({c[3] for c in candidatos if c[3]})
        raise RuntimeError(
            f"Destino '{cliente_nombre}' no encontrado en Euro Pool. "
            f"Disponibles: {disponibles[:40]}"
        )

    def resolver_envase(self, tipo: str) -> str:
        """'216-Caja Verde' → packingId (p.ej. '000000000021000002')."""
        envases: list[dict] = []
        for packing in _buscar_listas(self.definitions(), "packing"):
            if isinstance(packing, dict):
                envases.extend(packing.get("type") or [])
            elif isinstance(packing, list):
                envases.extend(packing)
        envases = [e for e in envases if isinstance(e, dict) and e.get("id")]

        objetivo = _norm(tipo)
        codigo = tipo.split("-")[0].strip()
        for e in envases:
            if _norm(e.get("name")) == objetivo:
                return e["id"]
        for e in envases:
            nombre = str(e.get("name") or "")
            if nombre.split("-")[0].strip() == codigo or nombre.startswith(codigo + " "):
                return e["id"]

        raise RuntimeError(
            f"Tipo de envase '{tipo}' no encontrado. "
            f"Disponibles: {[e.get('name') for e in envases][:40]}"
        )

    # -- Declaración ---------------------------------------------------------

    def construir_flow(self, albaran: Albaran) -> dict:
        """Mismo JSON que monta la web en createFlowDataCreator()."""
        ruta = self.resolver_ruta(albaran.cliente_nombre)
        return {
            "frequency":               ruta["frequency"],
            "flowDate":                albaran.fecha_entrega.isoformat(),
            "flowType":                ruta["flowType"],
            "fromId":                  ruta["fromId"],
            "toId":                    ruta["toId"],
            "clearing":                None,
            "transporter":             None,
            "licensePlate":            None,
            "customerRefNumber":       albaran.num_pedido,     # Referencia destinatario
            "originalReferenceNumber": None,
            "senderRefNumber":         albaran.num_albaran,    # Referencia expedidor
            "comments":                None,
            "etmOrderNumber":          None,
            "salesOrderNumber":        None,
            "wholesalerId":            None,
            "lineItem": [
                {
                    "itemNumber":      0,
                    "packingId":       self.resolver_envase(linea.tipo),
                    "quantity":        linea.cantidad,
                    "contentId":       None,
                    "lineReferenceId": None,
                }
                for linea in albaran.lineas
            ],
        }

    def validar_fecha(self, flow: dict) -> Any:
        f = date.fromisoformat(flow["flowDate"])
        return self.post("/Flow/checkFlowDate", {
            "frequency": flow["frequency"],
            "flowDate":  flow["flowDate"],
            "flowWeek":  {"weekNumber": f.isocalendar()[1], "year": f.year},
            "fromId":    flow["fromId"],
            "toId":      flow["toId"],
        })

    def crear_flow(self, flow: dict) -> dict:
        return self.post("/Flow/create", flow) or {}

    def descargar_documento(self, etm_order_number: str, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(self.get_blob("/Flow/getFlowDocument", EtmOrderNumber=etm_order_number))
        return destino


# ---------------------------------------------------------------------------
# Adaptador con la misma interfaz que los scrapers (declarar → DeclaracionResult)
# ---------------------------------------------------------------------------

class EuropoolApiDeclarer:
    portal_name = "europool"

    def declarar(self, albaran: Albaran) -> DeclaracionResult:
        result = DeclaracionResult(albaran=albaran, status=DeclarationStatus.PENDING)
        for attempt in range(1, settings.retry_attempts + 1):
            try:
                api = EuropoolApi(forzar_token=attempt > 1)
                flow = api.construir_flow(albaran)
                logger.debug(f"[europool-api] Flow: {json.dumps(flow, ensure_ascii=False)}")
                api.validar_fecha(flow)
                respuesta = api.crear_flow(flow)
                logger.debug(f"[europool-api] Respuesta: {respuesta}")

                etm = str(respuesta.get("etmOrderNumber") or "")
                sales = str(respuesta.get("salesOrderNumber") or "")
                result.confirmation_number = sales or etm or f"EPS-{albaran.num_albaran}"
                result.status = DeclarationStatus.SUBMITTED

                if etm:
                    try:
                        safe = albaran.num_albaran.replace("/", "_").replace("\\", "_")
                        pdf = api.descargar_documento(
                            etm, settings.output_dir / "pdfs" / f"europool_oficial_{safe}.pdf")
                        albaran.pdf_declaracion_oficial = pdf
                    except Exception as exc:
                        logger.warning(f"[europool-api] No se pudo descargar el PDF oficial: {exc}")

                logger.success(f"[europool-api] Albarán {albaran.num_albaran} declarado: "
                               f"{result.confirmation_number}")
                break
            except Exception as exc:
                logger.warning(f"[europool-api] Intento {attempt}/{settings.retry_attempts} "
                               f"fallido para {albaran.num_albaran}: {exc}")
                result.error_message = str(exc)
                if attempt == settings.retry_attempts:
                    result.status = DeclarationStatus.ERROR
                else:
                    time.sleep(2 ** attempt)
        return result

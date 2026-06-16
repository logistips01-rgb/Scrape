"""
Scraper para MyIFCO (www.ifco-online.com).

Auth   : login propio con IFCO-N° + usuario + contraseña
Login  : https://sso.ifco-online.com/login  (CAS con formulario propio)
Portal : https://www.ifco-online.com/myifco-core-fe
Forma  : React + Headless UI

Flujo del formulario (página de transacciones):
  URL : /clearing/navi.transactions/transaction-overview?poolId=3
  1. Seleccionar Remitente  (headless UI popover, suele estar preseleccionado)
  2. Seleccionar Envíos hacia  (headless UI popover → nombre del cliente)
  3. Seleccionar Pool + Número de material (tipo de envase, headless UI)
  4. Rellenar Fecha de entrega  (#deliveryDate, formato dd.MM.yyyy)
  5. Rellenar Albarán           (#deliveryNoteNumber)
  6. Pulsar "Nuevo registro de salida"
"""
from __future__ import annotations

from loguru import logger

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
PORTAL_URL       = "https://www.ifco-online.com/myifco-core-fe"
SSO_URL          = "https://sso.ifco-online.com/login"
TRANSACTIONS_URL = (
    "https://www.ifco-online.com/myifco-core-fe"
    "/clearing/navi.transactions/transaction-overview?poolId=3"
)

# ---------------------------------------------------------------------------
# Selectores login
# ---------------------------------------------------------------------------
SEL_LOGIN_BTN = "button:has-text('INICIAR SESIÓN'), button[type='submit']"
SEL_PASSWORD  = "input[type='password']"

# ---------------------------------------------------------------------------
# Selectores formulario
# ---------------------------------------------------------------------------
SEL_DELIVERY_DATE    = "#deliveryDate"
SEL_ALBARAN          = "#deliveryNoteNumber"
SEL_LICENSE_PLATE    = "#licenseNumber"
BTN_NUEVO_REGISTRO   = "button:has-text('Nuevo registro de salida')"
BTN_GUARDAR          = "button:has-text('Guardar y salir')"


class IfcoScraper(BaseScraper):
    portal_name = "ifco"

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(self) -> None:
        page = self._page

        page.goto(PORTAL_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)

        if self._ya_autenticado():
            logger.info("[ifco] Sesión activa")
            return

        logger.info("[ifco] Iniciando login...")

        # La app React muestra el formulario inline; si redirigió al SSO,
        # también lo manejamos
        if "sso.ifco-online.com" in page.url:
            pass  # ya estamos en el SSO
        # Si la pantalla de login está en la propia app (sin redirect)
        # navegar al SSO no es necesario; rellenamos lo que hay visible

        self._rellenar_login(page)

        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)

        if not self._ya_autenticado():
            self._screenshot("login_fallido")
            raise RuntimeError(
                "Login en IFCO fallido. Verifica IFCO_NUMBER, IFCO_USER e "
                "IFCO_PASSWORD en el fichero .env"
            )
        logger.info("[ifco] Login OK")

    def _rellenar_login(self, page) -> None:
        """Rellena los campos de login en el formulario SSO de IFCO."""
        page.wait_for_timeout(1_000)

        # ── IFCO-N° ─────────────────────────────────────────────────
        # El campo muestra un popup informativo al hacer click — hay que
        # cerrarlo con Escape antes de poder escribir
        # Selectores confirmados por diagnóstico:
        # IFCO-N°  = input[name='domainname']
        # usuario  = input[name='username']
        # password = input[name='password']
        page.locator("input[name='domainname']").first.fill(settings.ifco_number)
        page.locator("input[name='username']").first.fill(settings.ifco_user)
        page.locator("input[name='password']").first.fill(settings.ifco_password)
        page.wait_for_timeout(300)
        page.locator(SEL_LOGIN_BTN).first.click()

    def _ya_autenticado(self) -> bool:
        if not self._page:
            return False
        url = self._page.url
        if "sso.ifco-online.com" in url:
            return False
        # Si hay botón de login visible, NO estamos autenticados
        try:
            if self._page.locator("button:has-text('INICIAR SESIÓN')").count() > 0:
                return False
        except Exception:
            pass
        # Si hay contenido del portal (menú de navegación), estamos dentro
        try:
            if self._page.locator("text=Clearing").count() > 0:
                return True
        except Exception:
            pass
        return "ifco-online.com" in url

    # ------------------------------------------------------------------
    # Declaración
    # ------------------------------------------------------------------

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page
        logger.info(f"[ifco] Declarando {albaran.num_albaran}...")

        page.goto(TRANSACTIONS_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)

        # Abrir el panel "Nueva salida"
        page.locator(BTN_NUEVO_REGISTRO).first.click()
        page.wait_for_timeout(2_000)
        page.wait_for_selector("text=Nueva salida", timeout=10_000)

        self._screenshot(f"ifco_panel_nuevo_{albaran.num_albaran}")

        # ── Envíos hacia (cliente destinatario) ──────────────────────
        # Remitente ya está pre-seleccionado con nuestra empresa
        self._seleccionar_popover("Envíos hacia", albaran.cliente_nombre)
        page.wait_for_timeout(1_500)  # esperar a que aparezca el panel Transacciones

        # ── Fecha de entrega (dd.MM.yyyy) ─────────────────────────────
        # Borrar el valor por defecto (hoy) y poner la fecha del albarán
        fecha = albaran.fecha_entrega.strftime("%d.%m.%Y")
        page.locator(SEL_DELIVERY_DATE).first.triple_click()
        page.locator(SEL_DELIVERY_DATE).first.fill(fecha)
        page.wait_for_timeout(300)

        # ── Nº albarán ────────────────────────────────────────────────
        page.locator(SEL_ALBARAN).first.fill(albaran.num_albaran)
        page.wait_for_timeout(300)

        # ── Líneas de envase (panel Transacciones) ────────────────────
        for idx, linea in enumerate(albaran.lineas):
            if idx > 0:
                # Añadir fila nueva antes de rellenar
                page.locator("button:has-text('Añadir nueva línea')").first.click()
                page.wait_for_timeout(800)
            self._añadir_transaccion(linea.tipo, linea.cantidad, idx)

        self._screenshot(f"ifco_form_relleno_{albaran.num_albaran}")

        # ── Guardar ───────────────────────────────────────────────────
        page.locator(BTN_GUARDAR).first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2_000)

        return self._extraer_confirmacion(albaran)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _seleccionar_popover(self, label_text: str, valor: str, nth: int = 0) -> None:
        """
        Abre el headless UI combobox asociado a la etiqueta dada (nth-ésimo)
        y selecciona la opción cuyo texto contiene `valor`.
        """
        page = self._page
        try:
            # Encontrar el contenedor nth que tiene la etiqueta dada
            container = page.locator(
                f"div:has(label:has-text('{label_text}')), "
                f"td:has(label:has-text('{label_text}')), "
                f"fieldset:has(legend:has-text('{label_text}'))"
            ).nth(nth)
            btn = container.locator("button[id^='headlessui']").first
            btn.click()
            page.wait_for_timeout(600)

            # Buscar input de búsqueda dentro del panel abierto
            search_input = page.locator(
                "[id^='headlessui-popover-panel'] input, "
                "[data-headlessui-state='open'] input, "
                "[role='listbox'] input"
            ).first
            try:
                if search_input.is_visible(timeout=2_000):
                    search_input.fill(valor)
                    page.wait_for_timeout(600)
            except Exception:
                pass

            # Seleccionar la opción
            option = page.locator(
                f"[role='option']:has-text('{valor}'), "
                f"li:has-text('{valor}'):visible"
            ).first
            option.click()
            page.wait_for_timeout(400)
            logger.debug(f"[ifco] {label_text}[{nth}] → {valor}")

        except Exception as exc:
            logger.warning(f"[ifco] No se pudo seleccionar '{label_text}'[{nth}]: {exc}")

    def _añadir_transaccion(self, tipo: str, cantidad: int, idx: int = 0) -> None:
        """
        Rellena la fila idx del panel Transacciones.
        IDs confirmados por diagnóstico: transactions.{idx}.myAmount
        Material* es headless UI combobox (nth=idx dentro del panel).
        """
        page = self._page
        try:
            # Material* — headless UI combobox, nth=idx (una por fila)
            self._seleccionar_popover("Material", tipo, nth=idx)
            page.wait_for_timeout(400)

            # Mis cantidades* — ID estable
            qty = page.locator(f"[id='transactions.{idx}.myAmount']").first
            qty.triple_click()
            qty.fill(str(cantidad))
            page.wait_for_timeout(300)

            logger.debug(f"[ifco] Fila {idx}: {tipo} x {cantidad}")
        except Exception as exc:
            logger.warning(f"[ifco] Error fila {idx}: {exc}")

    def _extraer_confirmacion(self, albaran: Albaran) -> str:
        page = self._page
        self._screenshot(f"ifco_confirmacion_{albaran.num_albaran}")
        # El portal IFCO muestra un número de transacción tras el envío
        # Intentar leer cualquier referencia visible
        try:
            for sel in ["[class*='transaction']", "[class*='confirm']",
                        "strong", "b"]:
                for el in page.locator(sel).all():
                    t = (el.text_content() or "").strip()
                    if t and len(t) < 30 and any(c.isdigit() for c in t):
                        logger.info(f"[ifco] Confirmación: {t}")
                        return t
        except Exception:
            pass
        return f"IFCO-{albaran.num_albaran}"

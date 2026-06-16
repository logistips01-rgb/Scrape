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
        filled_ifco = False
        for sel in [
            "input[placeholder='IFCO-N°']",
            "input[placeholder*='IFCO']",
            "input[name='ifcoNumber']", "input[id='ifcoNumber']",
            "input[name='ifco-number']", "input[name='tenantId']",
        ]:
            try:
                f = page.locator(sel).first
                if f.is_visible(timeout=1_000):
                    f.click()
                    page.wait_for_timeout(600)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    f.fill(settings.ifco_number)
                    filled_ifco = True
                    logger.debug(f"[ifco] IFCO-N° rellenado ({sel})")
                    break
            except Exception:
                pass

        if not filled_ifco:
            # Fallback: el primer input visible que no sea username ni password
            try:
                inputs = page.locator(
                    "input:visible:not([type='password']):not([name='username'])"
                ).all()
                if inputs:
                    inputs[0].click()
                    page.wait_for_timeout(600)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    inputs[0].fill(settings.ifco_number)
                    logger.debug("[ifco] IFCO-N° rellenado (fallback: primer input)")
                    filled_ifco = True
            except Exception:
                pass

        if not filled_ifco:
            logger.warning("[ifco] No se pudo rellenar IFCO-N°")

        # ── Identificación de usuario ────────────────────────────────
        try:
            page.locator("input[name='username']").first.fill(settings.ifco_user)
        except Exception:
            try:
                page.get_by_label("Identificación", exact=False).first.fill(settings.ifco_user)
            except Exception:
                logger.warning("[ifco] No se pudo rellenar usuario")

        # ── Contraseña ───────────────────────────────────────────────
        page.locator(SEL_PASSWORD).first.fill(settings.ifco_password)
        page.wait_for_timeout(300)

        # ── Submit ───────────────────────────────────────────────────
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
        for linea in albaran.lineas:
            self._añadir_transaccion(linea.tipo, linea.cantidad)

        self._screenshot(f"ifco_form_relleno_{albaran.num_albaran}")

        # ── Guardar ───────────────────────────────────────────────────
        page.locator(BTN_GUARDAR).first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2_000)

        return self._extraer_confirmacion(albaran)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _seleccionar_popover(self, label_text: str, valor: str) -> None:
        """
        Abre el headless UI popover asociado a la etiqueta dada y
        selecciona la opción cuyo texto coincide con `valor`.
        """
        page = self._page
        try:
            # Buscar contenedor que tenga la etiqueta de texto
            container = page.locator(
                f"div:has(label:has-text('{label_text}')), "
                f"fieldset:has(legend:has-text('{label_text}'))"
            ).first
            btn = container.locator("button").first
            btn.click()
            page.wait_for_timeout(600)

            # Escribir en el input de búsqueda del popover si existe
            search_input = page.locator(
                "[role='listbox'] input, [data-headlessui-state] input"
            ).first
            try:
                if search_input.is_visible(timeout=2_000):
                    search_input.fill(valor)
                    page.wait_for_timeout(500)
            except Exception:
                pass

            # Clic en la opción
            option = page.locator(
                f"[role='option']:has-text('{valor}'), "
                f"li:has-text('{valor}')"
            ).first
            option.click()
            page.wait_for_timeout(400)
            logger.debug(f"[ifco] {label_text} → {valor}")

        except Exception as exc:
            logger.warning(f"[ifco] No se pudo seleccionar '{label_text}': {exc}")

    def _añadir_transaccion(self, tipo: str, cantidad: int) -> None:
        """
        Añade una línea de envase en el panel 'Transacciones' (derecha).
        Se activa después de seleccionar Remitente + Envíos hacia.
        TODO: ajustar selectores cuando se vea el panel real con ifco_diagnostico.py
        """
        page = self._page
        try:
            # Seleccionar tipo de material/envase
            self._seleccionar_popover("Número de material", tipo)
            page.wait_for_timeout(400)

            # Rellenar cantidad — buscar el input de cantidad visible
            qty_input = page.locator("input[id*='quantity'], input[name*='quantity'], "
                                     "input[placeholder*='antidad']").first
            if qty_input.is_visible(timeout=3_000):
                qty_input.triple_click()
                qty_input.fill(str(cantidad))
                page.wait_for_timeout(300)

            # Botón para añadir la línea ("+", "Añadir", "Add")
            add_btn = page.locator(
                "button:has-text('Añadir'), button:has-text('Add'), "
                "button[aria-label*='ñadir'], button[aria-label*='add']"
            ).first
            if add_btn.is_visible(timeout=2_000):
                add_btn.click()
                page.wait_for_timeout(600)

            logger.debug(f"[ifco] Transacción añadida: {tipo} x {cantidad}")
        except Exception as exc:
            logger.warning(f"[ifco] No se pudo añadir transacción {tipo}: {exc}")

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

"""
Scraper para Euro Pool System (EPS).

Portal : https://webportal.europoolsystem.com
Auth   : Microsoft Azure AD (SSO)
Form   : https://webportal.europoolsystem.com/#/flows/new

Flujo del formulario (3 secciones):
  1. ENCABEZAMIENTO
       - DESTINO            ← dropdown con nombre del cliente
       - REFERENCIA DEST.   ← nº de pedido del destinatario
       - REFERENCIA EXPED.  ← nº de albarán nuestro
       → Botón "IR A LAS LÍNEAS DEL MOVIMIENTO"

  2. LÍNEAS PEDIDO
       Por cada tipo de envase:
         - TIPO DE ENVASE   ← dropdown (p.ej. "156-Caja Verde")
         - CANTIDAD         ← número de unidades
         → Botón "+ AÑADIR MODELO"
       → Botón "ACCEDER A LA FECHA DE TRANSACCIÓN"

  3. FECHA TRANSACCIÓN
       - FECHA DEL MOVIMIENTO ← fecha de entrega
       → Botón "SIGUIENTE"  (envía el formulario)

Sesión persistida en output/europool_session.json para evitar
re-login en cada ejecución.
"""
from __future__ import annotations

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper
from loguru import logger

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
HUB_URL    = "https://my.europoolsystem.com"
PORTAL_URL     = "https://webportal.europoolsystem.com"
DASHBOARD_URL  = "https://webportal.europoolsystem.com/#/dashboard"
FLOWS_NEW_URL  = "https://webportal.europoolsystem.com/#/flows/new"

# ---------------------------------------------------------------------------
# Selectores Microsoft login (IDs oficiales, muy estables)
# ---------------------------------------------------------------------------
MS_EMAIL_INPUT    = "input[name='loginfmt']"
MS_NEXT_BTN       = "#idSIButton9"
MS_PASSWORD_INPUT = "input[name='passwd']"
MS_SIGNIN_BTN     = "#idSIButton9"
MS_KEEP_YES_BTN   = "#idSIButton9"

# ---------------------------------------------------------------------------
# Selectores del formulario Euro Pool (usa ng-select, no Angular Material)
# ---------------------------------------------------------------------------

# Sección 1 — Encabezamiento
# ng-select nth(0) = ORIGEN (pre-fijado), nth(1) = DESTINO
SEL_NG_OPTION         = ".ng-option"           # opciones del desplegable ng-select
BTN_IR_LINEAS         = "button:has-text('IR A LAS LÍNEAS')"

# Sección 2 — Líneas
BTN_AÑADIR_MODELO     = "button:has-text('AÑADIR MODELO')"
BTN_ACCEDER_FECHA     = "button:has-text('ACCEDER A LA FECHA')"

# Sección 3 — Fecha + envío final
BTN_SIGUIENTE         = "button:has-text('SIGUIENTE')"
BTN_ENVIAR            = "button:has-text('ENVIAR')"

# Modal de confirmación
SEL_MODAL_OK          = "text=guardado correctamente"
SEL_TRANSACTION_NUM   = "strong"
BTN_DESCARGAR_DOC     = "button:has-text('DESCARGAR DOCUMENTO')"


class EuropoolScraper(BaseScraper):
    portal_name  = "europool"
    _session_file = settings.output_dir / "europool_session.json"

    # ------------------------------------------------------------------
    # Login vía Microsoft SSO
    # ------------------------------------------------------------------

    def _login(self) -> None:
        page = self._page

        page.goto(PORTAL_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3_000)

        # Caso 1: hub "YOUR PORTALS" en my.europoolsystem.com → click MY EPS
        if "my.europoolsystem.com" in page.url or page.locator("text=MY EPS").count() > 0:
            logger.debug("[europool] Hub detectado, haciendo click en MY EPS")
            page.locator("text=MY EPS").first.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2_000)
            logger.info("[europool] Sesión activa (via hub MY EPS)")
            return

        # Caso 2: ya dentro del portal webportal sin necesitar login
        if self._ya_autenticado():
            logger.info("[europool] Sesión activa, sin necesidad de login")
            return

        logger.info("[europool] Iniciando login Microsoft SSO...")

        # El portal muestra "You need to be logged in!" con botón "Log in"
        # Hay que hacer click en él para que redirija a Microsoft
        try:
            login_btn = page.locator("a:has-text('Log in'), button:has-text('Log in')")
            if login_btn.first.is_visible(timeout=8_000):
                logger.debug("[europool] Haciendo click en botón Log in")
                login_btn.first.click()
                page.wait_for_load_state("networkidle")
        except Exception:
            pass

        # Esperar redirección a Microsoft
        page.wait_for_url("**/login.microsoftonline.com/**", timeout=15_000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1_000)

        # Selector de cuenta (aparece cuando hay múltiples cuentas guardadas)
        # La cuenta objetivo es 0001006572-4@epswebportal.onmicrosoft.com
        try:
            tile = page.locator(
                f"[data-test-id='{settings.europool_user}'], "
                f"div[role='button']:has-text('{settings.europool_user}')"
            )
            if tile.first.is_visible(timeout=5_000):
                logger.debug(f"[europool] Seleccionando cuenta: {settings.europool_user}")
                tile.first.click()
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2_000)
                # Si la cuenta tiene sesión activa redirige directo al portal
                if self._ya_autenticado():
                    self._save_session()
                    logger.info("[europool] Login OK (cuenta con sesión activa)")
                    return
        except Exception:
            pass

        # Campo email (si no viene pre-rellenado)
        try:
            email_field = page.locator(MS_EMAIL_INPUT)
            if email_field.is_visible(timeout=5_000):
                email_field.fill(settings.europool_user)
                page.wait_for_timeout(800)
                email_field.press("Enter")
                page.wait_for_load_state("networkidle")
        except Exception:
            pass

        # Contraseña
        page.wait_for_selector(MS_PASSWORD_INPUT, timeout=30_000)
        page.fill(MS_PASSWORD_INPUT, settings.europool_password)
        page.wait_for_timeout(500)
        page.locator(MS_PASSWORD_INPUT).press("Enter")
        page.wait_for_load_state("networkidle")

        # "¿Mantener sesión?" → Sí
        try:
            if page.locator(MS_KEEP_YES_BTN).is_visible(timeout=5_000):
                page.click(MS_KEEP_YES_BTN)
                page.wait_for_load_state("networkidle")
        except Exception:
            pass

        page.wait_for_load_state("networkidle")

        if not self._ya_autenticado():
            self._screenshot("login_fallido")
            raise RuntimeError(
                "Login en Euro Pool System fallido. Verifica EUROPOOL_USER y "
                "EUROPOOL_PASSWORD en el fichero .env"
            )

        self._save_session()
        logger.info("[europool] Login OK")

    def _ya_autenticado(self) -> bool:
        url = self._page.url if self._page else ""
        return "europoolsystem.com" in url and "microsoftonline" not in url

    # ------------------------------------------------------------------
    # Declaración de envases — formulario /#/flows/new
    # ------------------------------------------------------------------

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page

        page.goto(FLOWS_NEW_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2_000)

        # Cerrar aviso de cookies si aparece
        try:
            cookie_btn = page.locator("button:has-text('Got it'), button:has-text('Aceptar'), button:has-text('Accept')")
            if cookie_btn.first.is_visible(timeout=3_000):
                cookie_btn.first.click()
                page.wait_for_timeout(500)
        except Exception:
            pass

        # Esperar a que el formulario cargue (texto ENCABEZAMIENTO siempre presente)
        page.wait_for_selector("text=ENCABEZAMIENTO", timeout=30_000)
        page.wait_for_timeout(1_000)

        self._screenshot(f"form_inicio_{albaran.num_albaran}")

        # ── Sección 1: ENCABEZAMIENTO ────────────────────────────────
        self._seleccionar_destino(albaran.cliente_nombre)
        self._rellenar_por_label("REFERENCIA DESTINATARIO", albaran.num_pedido)
        self._rellenar_por_label("REFERENCIA EXPEDIDOR",    albaran.num_albaran)

        self._screenshot(f"encabezamiento_{albaran.num_albaran}")
        page.click(BTN_IR_LINEAS)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)  # Angular re-render

        # ── Sección 2: LÍNEAS PEDIDO ─────────────────────────────────
        for linea in albaran.lineas:
            self._añadir_linea_envase(linea.tipo, linea.cantidad)

        self._screenshot(f"lineas_{albaran.num_albaran}")
        page.click(BTN_ACCEDER_FECHA)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)

        # ── Sección 3: FECHA TRANSACCIÓN ─────────────────────────────
        self._rellenar_fecha(albaran.fecha_entrega.strftime("%d/%m/%Y"))

        self._screenshot(f"fecha_{albaran.num_albaran}")

        # "SIGUIENTE" lleva a la pantalla de resumen, luego "ENVIAR" confirma
        page.click(BTN_SIGUIENTE)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(600)

        # En el resumen pulsamos ENVIAR para registrar el movimiento
        try:
            page.wait_for_selector(BTN_ENVIAR, timeout=8_000)
            self._screenshot(f"resumen_{albaran.num_albaran}")
            page.click(BTN_ENVIAR)
            page.wait_for_load_state("networkidle")
        except Exception:
            # Si no hay pantalla de resumen intermedia, el botón ya era ENVIAR
            pass

        return self._extraer_confirmacion(albaran)

    # ------------------------------------------------------------------
    # Helpers del formulario
    # ------------------------------------------------------------------

    def _seleccionar_ng_select(self, nth: int, valor: str) -> None:
        """Abre el ng-select en posición nth y selecciona la opción por texto."""
        page = self._page
        select = page.locator("ng-select").nth(nth)
        select.click()
        page.wait_for_selector(SEL_NG_OPTION, state="visible", timeout=8_000)

        option = page.locator(SEL_NG_OPTION).filter(has_text=valor)
        if option.count() == 0:
            # Búsqueda parcial por primer token
            option = page.locator(SEL_NG_OPTION).filter(has_text=valor.split()[0])

        option.first.click()
        page.wait_for_timeout(400)

    def _seleccionar_destino(self, cliente_nombre: str) -> None:
        """ORIGEN = ng-select nth(0) pre-fijado. DESTINO = ng-select nth(1)."""
        self._seleccionar_ng_select(1, cliente_nombre)
        logger.debug(f"[europool] DESTINO seleccionado: {cliente_nombre}")

    def _añadir_linea_envase(self, tipo: str, cantidad: int) -> None:
        """Rellena TIPO DE ENVASE + CANTIDAD y pulsa '+ AÑADIR MODELO'."""
        page = self._page

        # En sección 2, el primer ng-select visible es TIPO DE ENVASE
        select = page.locator("ng-select").first
        select.click()
        page.wait_for_selector(SEL_NG_OPTION, state="visible", timeout=8_000)

        option = page.locator(SEL_NG_OPTION).filter(has_text=tipo)
        if option.count() == 0:
            codigo = tipo.split("-")[0].strip()
            option = page.locator(SEL_NG_OPTION).filter(has_text=codigo)
        option.first.click()
        page.wait_for_timeout(400)

        self._rellenar_por_label("CANTIDAD", str(cantidad))
        page.locator(BTN_AÑADIR_MODELO).click()
        page.wait_for_timeout(600)
        logger.debug(f"[europool] Línea añadida: {tipo} x {cantidad}")

    def _rellenar_por_label(self, label_text: str, value: str) -> None:
        """
        Localiza el input asociado a una etiqueta de texto y lo rellena.
        Funciona con Angular Material mat-form-field / mat-label.
        """
        page = self._page
        try:
            # Estrategia 1: getByLabel (funciona si el label está correctamente vinculado)
            field = page.get_by_label(label_text, exact=False)
            if field.first.is_visible(timeout=2_000):
                field.first.fill(value)
                return
        except Exception:
            pass

        try:
            # Estrategia 2: mat-form-field que contiene la label con ese texto
            container = page.locator(
                f"mat-form-field:has(mat-label:has-text('{label_text}'))"
            )
            inp = container.locator("input").first
            if inp.is_visible(timeout=2_000):
                inp.fill(value)
                return
        except Exception:
            pass

        logger.warning(f"[europool] No se encontró el campo '{label_text}'")

    def _rellenar_fecha(self, fecha_str: str) -> None:
        """Rellena el campo FECHA DEL MOVIMIENTO (formato dd/mm/yyyy)."""
        page = self._page
        try:
            # El campo de fecha puede ser un mat-datepicker
            self._rellenar_por_label("FECHA DEL MOVIMIENTO", fecha_str)
            page.wait_for_timeout(300)
            # Cerrar el datepicker si se abrió
            page.keyboard.press("Escape")
        except Exception as exc:
            logger.warning(f"[europool] Error al rellenar fecha: {exc}")

    def _extraer_confirmacion(self, albaran: Albaran) -> str:
        """
        Lee el número de transacción del modal de confirmación (N.XXXXXXXXXX)
        y descarga el PDF oficial de Europool si está disponible.

        El modal muestra:
          "su registro ha sido guardado correctamente en nuestro sistema."
          "haga referencia a su número de transacción N.0133060456"
        """
        import re
        page = self._page

        # Esperar el modal de éxito (fondo verde)
        try:
            page.wait_for_selector(SEL_MODAL_OK, timeout=15_000)
            self._screenshot(f"confirmacion_{albaran.num_albaran}")
            logger.info("[europool] Modal de confirmación detectado")
        except Exception:
            self._screenshot(f"sin_modal_{albaran.num_albaran}")
            logger.warning("[europool] No apareció el modal de confirmación")

        # Extraer número de transacción de los elementos <strong> del modal
        transaction_num = ""
        try:
            for strong in page.locator(SEL_TRANSACTION_NUM).all():
                texto = (strong.text_content() or "").strip()
                if re.match(r"N\.\d+", texto):
                    transaction_num = texto
                    logger.info(f"[europool] Nº transacción: {transaction_num}")
                    break
        except Exception:
            pass

        # Fallback: buscar patrón N.XXXXXXXXXX en todo el texto de la página
        if not transaction_num:
            try:
                contenido = page.content()
                match = re.search(r"N\.(\d+)", contenido)
                if match:
                    transaction_num = f"N.{match.group(1)}"
            except Exception:
                pass

        if not transaction_num:
            transaction_num = f"EPS-{albaran.num_albaran}"

        # Descargar el PDF oficial de Europool (mejor que generar uno propio)
        self._descargar_documento_oficial(albaran, transaction_num)

        return transaction_num

    def _descargar_documento_oficial(self, albaran: Albaran, transaction_num: str) -> None:
        """
        Pulsa 'DESCARGAR DOCUMENTO' en el modal y guarda el PDF oficial
        de Europool en output/pdfs/europool_{num_albaran}.pdf
        """
        page = self._page
        try:
            btn = page.locator(BTN_DESCARGAR_DOC)
            if not btn.is_visible(timeout=5_000):
                return

            out_dir = settings.output_dir / "pdfs"
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / f"europool_oficial_{albaran.num_albaran}.pdf"

            with page.expect_download(timeout=30_000) as dl_info:
                btn.click()

            download = dl_info.value
            download.save_as(str(dest))
            # Guardar ruta en el albaran para que el merger la use
            albaran.pdf_declaracion_oficial = dest  # atributo dinámico
            logger.info(f"[europool] PDF oficial descargado: {dest.name}")

        except Exception as exc:
            logger.warning(f"[europool] No se pudo descargar el documento oficial: {exc}")

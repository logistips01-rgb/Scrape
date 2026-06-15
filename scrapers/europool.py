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
# Selectores del formulario Euro Pool (Angular Material)
# ---------------------------------------------------------------------------

# Sección 1 — Encabezamiento
SEL_DESTINO_SELECT    = "mat-select"          # primer select libre (ORIGEN está pre-fijado)
SEL_REF_DEST_INPUT    = "input"               # se localiza por label REFERENCIA DESTINATARIO
SEL_REF_EXPED_INPUT   = "input"               # se localiza por label REFERENCIA EXPEDIDOR
BTN_IR_LINEAS         = "button:has-text('IR A LAS LÍNEAS')"

# Sección 2 — Líneas
SEL_TIPO_ENVASE_SEL   = "mat-select"          # dropdown TIPO DE ENVASE (primer mat-select en sección 2)
SEL_CANTIDAD_INPUT    = "input"               # campo CANTIDAD
BTN_AÑADIR_MODELO     = "button:has-text('AÑADIR MODELO')"
BTN_ACCEDER_FECHA     = "button:has-text('ACCEDER A LA FECHA')"

# Sección 3 — Fecha + envío final
SEL_FECHA_INPUT       = "input"               # FECHA DEL MOVIMIENTO
BTN_SIGUIENTE         = "button:has-text('SIGUIENTE')"   # avanza a resumen
BTN_ENVIAR            = "button:has-text('ENVIAR')"      # envía el formulario

# Modal de confirmación (aparece tras ENVIAR)
SEL_MODAL_OK          = "text=guardado correctamente"    # texto del modal verde
SEL_TRANSACTION_NUM   = "strong"                          # N.XXXXXXXXXX en negrita
BTN_DESCARGAR_DOC     = "button:has-text('DESCARGAR DOCUMENTO')"

# Panel de opciones Angular Material (fuera del DOM del formulario)
SEL_MAT_OPTION        = "mat-option"


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

        # Sesión guardada válida → ya estamos en el portal
        if self._ya_autenticado():
            logger.info("[europool] Sesión activa, sin necesidad de login")
            return

        logger.info("[europool] Iniciando login Microsoft SSO...")

        # Esperar redirección a Microsoft
        page.wait_for_url("**/login.microsoftonline.com/**", timeout=15_000)
        page.wait_for_load_state("domcontentloaded")

        # Selector de cuenta (si aparece con múltiples cuentas guardadas)
        try:
            tile = page.locator(
                f"[data-test-id='{settings.europool_user}'], "
                f"div[role='button']:has-text('{settings.europool_user}')"
            )
            if tile.first.is_visible(timeout=3_000):
                tile.first.click()
                page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

        # Campo email (si no viene pre-rellenado)
        try:
            email_field = page.locator(MS_EMAIL_INPUT)
            if email_field.is_visible(timeout=3_000):
                email_field.fill(settings.europool_user)
                page.locator(MS_NEXT_BTN).click()
                page.wait_for_load_state("domcontentloaded")
        except Exception:
            pass

        # Contraseña
        page.wait_for_selector(MS_PASSWORD_INPUT, timeout=15_000)
        page.fill(MS_PASSWORD_INPUT, settings.europool_password)
        page.click(MS_SIGNIN_BTN)
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
        page.wait_for_selector("mat-select", timeout=15_000)  # esperar Angular

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

    def _seleccionar_destino(self, cliente_nombre: str) -> None:
        """
        Abre el dropdown DESTINO y selecciona el cliente por nombre.
        ORIGEN está pre-fijado con nuestra empresa → DESTINO es el segundo mat-select.
        """
        page = self._page
        selects = page.locator("mat-select")
        # ORIGEN es el primero (disabled/pre-filled). DESTINO es el segundo.
        destino_select = selects.nth(1)
        destino_select.click()
        page.wait_for_selector(SEL_MAT_OPTION, state="visible", timeout=8_000)

        # Buscar la opción que contenga el nombre del cliente
        option = page.locator(SEL_MAT_OPTION).filter(has_text=cliente_nombre)
        if option.count() == 0:
            # Intento de búsqueda parcial por las primeras palabras
            primer_token = cliente_nombre.split()[0]
            option = page.locator(SEL_MAT_OPTION).filter(has_text=primer_token)

        option.first.click()
        page.wait_for_timeout(400)
        logger.debug(f"[europool] DESTINO seleccionado: {cliente_nombre}")

    def _añadir_linea_envase(self, tipo: str, cantidad: int) -> None:
        """
        Rellena TIPO DE ENVASE + CANTIDAD y pulsa '+ AÑADIR MODELO'.
        En la sección 2 el primer mat-select visible es el TIPO DE ENVASE.
        """
        page = self._page

        # TIPO DE ENVASE — dropdown
        tipo_select = page.locator("mat-select").filter(
            has=page.locator("mat-label:has-text('TIPO DE ENVASE'), mat-label:has-text('Tipo de envase')")
        ).first
        # Fallback: primer mat-select visible en la sección de líneas
        if not tipo_select.is_visible(timeout=2_000):
            tipo_select = page.locator("mat-select").first

        tipo_select.click()
        page.wait_for_selector(SEL_MAT_OPTION, state="visible", timeout=8_000)
        option = page.locator(SEL_MAT_OPTION).filter(has_text=tipo)
        if option.count() == 0:
            # Búsqueda por código (parte antes del guión, p.ej. "156" de "156-Caja Verde")
            codigo = tipo.split("-")[0].strip()
            option = page.locator(SEL_MAT_OPTION).filter(has_text=codigo)
        option.first.click()
        page.wait_for_timeout(400)

        # CANTIDAD — input asociado a la label "CANTIDAD"
        self._rellenar_por_label("CANTIDAD", str(cantidad))

        # Añadir la línea
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

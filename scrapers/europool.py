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
BTN_IR_LINEAS         = "button:has-text('Ir a las líneas del movimiento')"

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

        # Ir al hub directamente — goto al webportal redirige aquí de todas formas
        page.goto(HUB_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)

        # ── Click en MY EPS (misma pestaña, confirmado por diagnóstico) ──────
        logger.debug("[europool] Haciendo click en MY EPS via JS...")
        try:
            tile = page.locator("text=MY EPS").first
            tile.wait_for(state="attached", timeout=15_000)
            # JS click: bypassa todos los checks de Playwright (visibilidad, scroll, estabilidad)
            tile.evaluate("el => (el.closest('a,[role=button],[tabindex],button') || el.parentElement || el).click()")
            page.wait_for_url("**/webportal.europoolsystem.com/**", timeout=20_000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2_000)
            logger.info(f"[europool] MY EPS OK, URL: {page.url}")
        except Exception as exc:
            logger.warning(f"[europool] Error al navegar via MY EPS: {exc}")
            if "webportal.europoolsystem.com" not in page.url:
                raise RuntimeError(f"No se pudo acceder al webportal via MY EPS: {exc}")

        # ── Si aterrizamos en #/login, completar el OAuth de Microsoft ──────
        if "#/login" in page.url:
            self._manejar_login_page()

        if not self._ya_autenticado():
            self._screenshot("login_fallido")
            raise RuntimeError(
                "Login en Euro Pool System fallido. Verifica EUROPOOL_USER en el fichero .env"
            )

        logger.info("[europool] Login OK")

    def _manejar_login_page(self) -> None:
        """
        Maneja la página #/login completando el OAuth de Microsoft.

        La app Angular usa MSAL y puede abrir el login de Microsoft en:
          - Un popup (loginPopup) → escuchamos el evento 'popup'
          - La misma pestaña (loginRedirect) → wait_for_url
        Fallback: navegar a #/login sin token para forzar redirección OAuth.
        """
        page = self._page
        logger.info("[europool] Página de login detectada, iniciando OAuth...")

        # Localizar "Log in" con selector amplio (puede ser cualquier elemento Angular)
        login_btn = page.locator("text=Log in").first
        try:
            login_btn.wait_for(state="visible", timeout=8_000)
        except Exception:
            logger.debug("[europool] Botón 'Log in' no visible — intentando igualmente")

        # ── Intento 1: popup (MSAL loginPopup abre nueva ventana) ────────────
        popup_handled = False
        popup_ref: list = []

        def _on_popup(p) -> None:
            popup_ref.append(p)

        page.on("popup", _on_popup)
        try:
            login_btn.click(force=True, timeout=5_000)
        except Exception as exc:
            logger.debug(f"[europool] Click en 'Log in': {exc}")

        # Esperar hasta 6 s para que aparezca el popup
        for _ in range(12):
            if popup_ref:
                break
            page.wait_for_timeout(500)
        page.remove_listener("popup", _on_popup)

        if popup_ref:
            popup = popup_ref[0]
            logger.info(f"[europool] Popup OAuth detectado: {popup.url[:80]}")
            try:
                popup.wait_for_load_state("domcontentloaded")
                self._completar_microsoft_oauth(popup)
                # Esperar a que el popup cierre (MSAL cierra el popup al terminar)
                popup.wait_for_event("close", timeout=40_000)
                logger.info("[europool] Popup OAuth cerrado — esperando callback...")
                page.wait_for_timeout(4_000)
                popup_handled = True
            except Exception as exc:
                logger.warning(f"[europool] Error procesando popup OAuth: {exc}")

        # ── Intento 2: navegación en misma página (loginRedirect) ────────────
        if not popup_handled:
            if "microsoftonline" in page.url:
                logger.info("[europool] Misma pestaña → Microsoft OAuth")
                self._completar_microsoft_oauth(page)
                try:
                    page.wait_for_url("**/webportal.europoolsystem.com/**", timeout=30_000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(3_000)
                    popup_handled = True
                except Exception as exc:
                    logger.warning(f"[europool] No volvió al webportal: {exc}")
            else:
                # No popup y no navegó a Microsoft: esperar un poco más
                try:
                    page.wait_for_url("**/login.microsoftonline.com/**", timeout=10_000)
                    logger.info("[europool] Navegación retrasada a Microsoft detectada")
                    self._completar_microsoft_oauth(page)
                    page.wait_for_url("**/webportal.europoolsystem.com/**", timeout=30_000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(3_000)
                    popup_handled = True
                except Exception:
                    pass

        # ── Intento 3: goto #/login sin token para re-trigger el OAuth ───────
        if not popup_handled and "#/login" in page.url:
            logger.info("[europool] Fallback: navegando a #/login sin token...")
            page.goto("https://webportal.europoolsystem.com/#/login")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3_000)
            if "microsoftonline" in page.url:
                self._completar_microsoft_oauth(page)
                try:
                    page.wait_for_url("**/webportal.europoolsystem.com/**", timeout=30_000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(3_000)
                except Exception as exc:
                    logger.warning(f"[europool] Fallback sin token falló: {exc}")

    def _completar_microsoft_oauth(self, p) -> None:
        """
        Completa el OAuth de Microsoft en la página (o popup) dada.
        Maneja:
          - Selector de cuenta (sesión ya activa, el más habitual)
          - Formulario email + contraseña (sesión nueva)
          - Prompt "Mantener sesión iniciada"
        """
        # Esperar a que la página de Microsoft esté lista
        try:
            p.wait_for_url("**/login.microsoftonline.com/**", timeout=12_000)
        except Exception:
            pass
        p.wait_for_load_state("domcontentloaded")
        p.wait_for_timeout(1_000)
        logger.info(f"[europool] Microsoft OAuth: {p.url[:60]}")

        # ── Caso A: selector de cuenta (sesión SSO activa) ────────────────
        account_clicked = False
        for sel in [
            f"[aria-label*='0001006572']",
            f"[aria-label*='{settings.europool_user}']",
            f"div[role='option']:has-text('0001006572')",
            "div[role='option']:visible",
            "div.account-button:visible",
            "[tabindex='0'][role='option']:visible",
        ]:
            try:
                el = p.locator(sel).first
                if el.is_visible(timeout=2_000):
                    logger.info(f"[europool] Cuenta seleccionada ({sel})")
                    el.click()
                    p.wait_for_load_state("domcontentloaded")
                    p.wait_for_timeout(2_000)
                    account_clicked = True
                    break
            except Exception:
                continue

        # ── Caso B: formulario email + contraseña (sin sesión SSO) ───────
        if not account_clicked:
            try:
                email_input = p.locator(MS_EMAIL_INPUT)
                if email_input.is_visible(timeout=4_000):
                    logger.info("[europool] Introduciendo credenciales Microsoft...")
                    email_input.fill(settings.europool_user)
                    p.locator(MS_NEXT_BTN).click()
                    p.wait_for_load_state("domcontentloaded")
                    p.wait_for_timeout(1_000)
                    pw = p.locator(MS_PASSWORD_INPUT)
                    if pw.is_visible(timeout=5_000):
                        pw.fill(settings.europool_password)
                        p.locator(MS_SIGNIN_BTN).click()
                        p.wait_for_load_state("domcontentloaded")
                        p.wait_for_timeout(2_000)
            except Exception as exc:
                logger.debug(f"[europool] Flujo email/contraseña: {exc}")

        # ── "Mantener sesión iniciada?" → Sí ────────────────────────────
        try:
            btn = p.locator(MS_KEEP_YES_BTN)
            if btn.is_visible(timeout=5_000):
                logger.info("[europool] Confirmando 'Mantener sesión'")
                btn.click()
                p.wait_for_load_state("domcontentloaded")
                p.wait_for_timeout(2_000)
        except Exception:
            pass

    def _ya_autenticado(self) -> bool:
        url = self._page.url if self._page else ""
        if "microsoftonline" in url or "europoolsystem.com" not in url:
            return False
        # Todavía en la página de login
        if "#/login" in url:
            return False
        return True

    # ------------------------------------------------------------------
    # Declaración de envases — formulario /#/flows/new
    # ------------------------------------------------------------------

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page

        page.goto(FLOWS_NEW_URL)
        page.wait_for_load_state("domcontentloaded")
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

        # Diagnóstico: registrar los labels exactos del formulario para ajuste futuro
        try:
            labels = [l.strip() for l in page.locator("mat-label").all_text_contents() if l.strip()]
            logger.info(f"[europool] Labels del formulario: {labels}")
        except Exception:
            pass

        # ── Sección 1: ENCABEZAMIENTO ────────────────────────────────
        self._seleccionar_destino(albaran.cliente_nombre)
        page.wait_for_timeout(1_000)  # Angular actualiza validación tras cambio
        self._rellenar_por_label("Referencia destinatario", albaran.num_pedido)
        self._rellenar_por_label("Referencia expedidor",    albaran.num_albaran)

        self._screenshot(f"encabezamiento_{albaran.num_albaran}")

        # Esperar a que el botón se habilite (máx 5 s) antes de hacer click
        try:
            page.locator(BTN_IR_LINEAS).wait_for(state="enabled", timeout=5_000)
        except Exception:
            pass

        page.click(BTN_IR_LINEAS)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)  # Angular re-render

        # ── Sección 2: LÍNEAS PEDIDO ─────────────────────────────────
        for linea in albaran.lineas:
            self._añadir_linea_envase(linea.tipo, linea.cantidad)

        self._screenshot(f"lineas_{albaran.num_albaran}")
        page.click(BTN_ACCEDER_FECHA)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(800)

        # ── Sección 3: FECHA TRANSACCIÓN ─────────────────────────────
        self._rellenar_fecha(albaran.fecha_entrega.strftime("%d/%m/%Y"))

        self._screenshot(f"fecha_{albaran.num_albaran}")

        # "SIGUIENTE" lleva a la pantalla de resumen, luego "ENVIAR" confirma
        page.click(BTN_SIGUIENTE)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(600)

        # En el resumen pulsamos ENVIAR para registrar el movimiento
        try:
            page.wait_for_selector(BTN_ENVIAR, timeout=8_000)
            self._screenshot(f"resumen_{albaran.num_albaran}")
            page.click(BTN_ENVIAR)
            page.wait_for_load_state("domcontentloaded")
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
        page.wait_for_timeout(400)

        # Escribir para filtrar opciones (más fiable que desplazarse por toda la lista)
        try:
            search_input = select.locator("input")
            if search_input.count() > 0 and search_input.first.is_visible(timeout=1_000):
                search_input.first.type(valor[:15], delay=40)
                page.wait_for_timeout(400)
        except Exception:
            pass

        # Esperar al panel desplegable visible
        page.wait_for_selector(".ng-dropdown-panel:visible", timeout=8_000)

        # Buscar opción en el panel abierto (no en toda la página)
        panel = page.locator(".ng-dropdown-panel:visible")
        option = panel.locator(SEL_NG_OPTION).filter(has_text=valor)
        if option.count() == 0:
            option = panel.locator(SEL_NG_OPTION).filter(has_text=valor.split()[0])
        if option.count() == 0:
            # Fallback: primera opción visible del panel
            option = panel.locator(SEL_NG_OPTION)

        option.first.click()
        page.wait_for_timeout(600)

    def _seleccionar_destino(self, cliente_nombre: str) -> None:
        """Selecciona el cliente en el campo 'Destino' del formulario."""
        page = self._page
        # Intentar por contexto de label (más robusto que por índice)
        try:
            container = page.locator(
                "mat-form-field:has(mat-label:has-text('Destino'))"
            )
            if container.count() > 0:
                select = container.locator("ng-select").first
                select.click()
                page.wait_for_timeout(400)
                try:
                    search_input = select.locator("input")
                    if search_input.count() > 0 and search_input.first.is_visible(timeout=1_000):
                        search_input.first.type(cliente_nombre[:15], delay=40)
                        page.wait_for_timeout(400)
                except Exception:
                    pass
                page.wait_for_selector(".ng-dropdown-panel:visible", timeout=8_000)
                panel = page.locator(".ng-dropdown-panel:visible")
                option = panel.locator(SEL_NG_OPTION).filter(has_text=cliente_nombre)
                if option.count() == 0:
                    option = panel.locator(SEL_NG_OPTION).filter(has_text=cliente_nombre.split()[0])
                option.first.click()
                page.wait_for_timeout(600)
                logger.debug(f"[europool] Destino seleccionado (por label): {cliente_nombre}")
                return
        except Exception as exc:
            logger.debug(f"[europool] Destino por label falló, usando nth(1): {exc}")
        # Fallback: posición nth(1)
        self._seleccionar_ng_select(1, cliente_nombre)
        logger.debug(f"[europool] Destino seleccionado (nth 1): {cliente_nombre}")

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

        self._rellenar_por_label("Cantidad", str(cantidad))
        page.locator(BTN_AÑADIR_MODELO).click()
        page.wait_for_timeout(600)
        logger.debug(f"[europool] Línea añadida: {tipo} x {cantidad}")

    # Mapeo de alias: nombres exactos del portal EPS + variantes por si cambia
    _LABEL_ALIASES: dict[str, list[str]] = {
        "Referencia destinatario": [
            "Referencia destinatario", "REFERENCIA DESTINATARIO",
            "REF. DEST.", "REF DEST", "REFERENCIA DEST",
        ],
        "Referencia expedidor": [
            "Referencia expedidor", "REFERENCIA EXPEDIDOR",
            "REF. EXPED.", "REF EXPED", "REFERENCIA EXPED",
        ],
        "Cantidad": ["Cantidad", "CANTIDAD", "UNITS", "QTY"],
        "Fecha del movimiento": [
            "Fecha del movimiento", "FECHA DEL MOVIMIENTO",
            "FECHA MOVIMIENTO", "FECHA",
        ],
    }

    def _rellenar_por_label(self, label_text: str, value: str) -> None:
        """
        Localiza el input asociado a una etiqueta de texto y lo rellena.
        Prueba múltiples alias y estrategias de búsqueda.
        """
        page = self._page
        candidates = self._LABEL_ALIASES.get(label_text, [label_text])

        for candidate in candidates:
            # Estrategia 1: getByLabel
            try:
                field = page.get_by_label(candidate, exact=False)
                if field.first.is_visible(timeout=1_000):
                    field.first.triple_click()
                    field.first.fill(value)
                    logger.debug(f"[europool] Campo '{candidate}' rellenado (getByLabel)")
                    return
            except Exception:
                pass

            # Estrategia 2: mat-form-field con mat-label
            try:
                container = page.locator(f"mat-form-field:has(mat-label:has-text('{candidate}'))")
                inp = container.locator("input").first
                if inp.is_visible(timeout=1_000):
                    inp.triple_click()
                    inp.fill(value)
                    logger.debug(f"[europool] Campo '{candidate}' rellenado (mat-label)")
                    return
            except Exception:
                pass

            # Estrategia 3: placeholder
            try:
                inp = page.get_by_placeholder(candidate, exact=False)
                if inp.first.is_visible(timeout=1_000):
                    inp.first.triple_click()
                    inp.first.fill(value)
                    logger.debug(f"[europool] Campo '{candidate}' rellenado (placeholder)")
                    return
            except Exception:
                pass

        logger.warning(f"[europool] No se encontró el campo '{label_text}'")

    def _rellenar_fecha(self, fecha_str: str) -> None:
        """Rellena el campo FECHA DEL MOVIMIENTO (formato dd/mm/yyyy)."""
        page = self._page
        try:
            # El campo de fecha puede ser un mat-datepicker
            self._rellenar_por_label("Fecha del movimiento", fecha_str)
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

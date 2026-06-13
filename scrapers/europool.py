"""
Scraper para el portal de declaraciones de Europool.

CONFIGURACIÓN INICIAL NECESARIA:
  Antes de usar este scraper es necesario inspeccionar el portal de Europool
  con las herramientas de desarrollador del navegador (F12) e identificar:

  1. URL de login              → EUROPOOL_LOGIN_URL
  2. Selector del campo usuario → "#username" o similar
  3. Selector del campo password → "#password" o similar
  4. Botón de login             → "button[type=submit]"
  5. URL/menú de nueva declaración
  6. Campos del formulario de declaración

  Los selectores marcados con TODO deben actualizarse según el portal real.
"""
from __future__ import annotations

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper

# ---------------------------------------------------------------------------
# Selectores CSS — actualizar tras inspeccionar el portal real
# ---------------------------------------------------------------------------
SEL_USERNAME = "#username"          # TODO: ajustar
SEL_PASSWORD = "#password"          # TODO: ajustar
SEL_LOGIN_BTN = "button[type=submit]"  # TODO: ajustar
SEL_NEW_DECL_LINK = "a[href*='declaration']"  # TODO: ajustar
SEL_DATE_FIELD = "#delivery_date"    # TODO: ajustar
SEL_ORDER_FIELD = "#order_number"    # TODO: ajustar
SEL_REF_FIELD = "#reference"        # TODO: ajustar
SEL_CONFIRM_BTN = "#confirm"         # TODO: ajustar
SEL_CONFIRMATION_NUM = ".confirmation-number"  # TODO: ajustar

EUROPOOL_LOGIN_URL = f"{settings.europool_url}/login"  # TODO: ajustar ruta


class EuropoolScraper(BaseScraper):
    portal_name = "europool"

    def _login(self) -> None:
        page = self._page
        page.goto(EUROPOOL_LOGIN_URL)
        page.wait_for_load_state("networkidle")

        page.fill(SEL_USERNAME, settings.europool_user)
        page.fill(SEL_PASSWORD, settings.europool_password)
        page.click(SEL_LOGIN_BTN)
        page.wait_for_load_state("networkidle")

        # Verificar login exitoso: el portal redirige al dashboard o muestra error
        if "login" in page.url.lower() or "error" in page.content().lower():
            raise RuntimeError("Login en Europool fallido. Verifica credenciales.")

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page

        # Navegar a nueva declaración
        page.click(SEL_NEW_DECL_LINK)
        page.wait_for_load_state("networkidle")

        # Rellenar fecha de entrega
        page.fill(SEL_DATE_FIELD, albaran.fecha_entrega.strftime("%d/%m/%Y"))

        # Rellenar número de pedido
        page.fill(SEL_ORDER_FIELD, albaran.num_pedido)

        # Rellenar referencia (nº albarán)
        page.fill(SEL_REF_FIELD, albaran.num_albaran)

        # Rellenar líneas de envases
        self._fill_container_lines(albaran)

        # Captura antes de confirmar
        self._screenshot(f"preconfirm_{albaran.num_albaran}")

        # Confirmar envío
        page.click(SEL_CONFIRM_BTN)
        page.wait_for_load_state("networkidle")

        # Extraer número de confirmación
        try:
            confirmation = page.text_content(SEL_CONFIRMATION_NUM, timeout=10_000)
            return (confirmation or "").strip()
        except Exception:
            # Si no hay selector claro, capturar pantalla y devolver timestamp
            self._screenshot(f"confirmed_{albaran.num_albaran}")
            return f"OK-{albaran.num_albaran}"

    def _fill_container_lines(self, albaran: Albaran) -> None:
        """
        Rellena las líneas de envases en el formulario.
        La lógica exacta depende de cómo el portal presente el formulario:
          - Tabla dinámica donde se añaden filas
          - Selector de tipo + campo cantidad repetido
          - Lista desplegable de tipos de envase

        TODO: implementar tras inspeccionar el formulario real.
        """
        page = self._page
        for i, linea in enumerate(albaran.lineas):
            # Ejemplo genérico: añadir fila y rellenar tipo + cantidad
            # page.click("#add-line-btn")
            # page.fill(f"#container_type_{i}", linea.tipo)
            # page.fill(f"#container_qty_{i}", str(linea.cantidad))
            pass  # TODO: implementar con selectores reales

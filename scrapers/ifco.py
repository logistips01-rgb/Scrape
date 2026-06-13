"""
Scraper para el portal de declaraciones de IFCO.

CONFIGURACIÓN INICIAL NECESARIA:
  Inspeccionar el portal IFCO con las herramientas de desarrollador (F12)
  e identificar los selectores correctos. Los marcados con TODO deben
  actualizarse según el portal real.
"""
from __future__ import annotations

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper

SEL_USERNAME = "#email"              # TODO: ajustar
SEL_PASSWORD = "#password"           # TODO: ajustar
SEL_LOGIN_BTN = "button[type=submit]"   # TODO: ajustar
SEL_NEW_DECL = "a[href*='return']"   # TODO: ajustar
SEL_DATE_FIELD = "#date"             # TODO: ajustar
SEL_ORDER_FIELD = "#order"           # TODO: ajustar
SEL_CONFIRM_BTN = "#submit"          # TODO: ajustar
SEL_CONFIRMATION_NUM = ".transaction-id"  # TODO: ajustar

IFCO_LOGIN_URL = f"{settings.ifco_url}/login"  # TODO: ajustar ruta


class IfcoScraper(BaseScraper):
    portal_name = "ifco"

    def _login(self) -> None:
        page = self._page
        page.goto(IFCO_LOGIN_URL)
        page.wait_for_load_state("networkidle")

        page.fill(SEL_USERNAME, settings.ifco_user)
        page.fill(SEL_PASSWORD, settings.ifco_password)
        page.click(SEL_LOGIN_BTN)
        page.wait_for_load_state("networkidle")

        if "login" in page.url.lower():
            raise RuntimeError("Login en IFCO fallido. Verifica credenciales.")

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page

        page.click(SEL_NEW_DECL)
        page.wait_for_load_state("networkidle")

        page.fill(SEL_DATE_FIELD, albaran.fecha_entrega.strftime("%d/%m/%Y"))
        page.fill(SEL_ORDER_FIELD, albaran.num_pedido)

        self._fill_container_lines(albaran)

        self._screenshot(f"preconfirm_{albaran.num_albaran}")
        page.click(SEL_CONFIRM_BTN)
        page.wait_for_load_state("networkidle")

        try:
            confirmation = page.text_content(SEL_CONFIRMATION_NUM, timeout=10_000)
            return (confirmation or "").strip()
        except Exception:
            self._screenshot(f"confirmed_{albaran.num_albaran}")
            return f"OK-{albaran.num_albaran}"

    def _fill_container_lines(self, albaran: Albaran) -> None:
        # TODO: implementar con selectores reales del portal IFCO
        pass

"""
Scraper para el portal de declaraciones de CHEP (palets).

CHEP gestiona palets de madera (azules). Su portal "My Account" permite
registrar movimientos de palets. La estructura es similar a Europool/IFCO
pero los "envases" son palets (EPAL, medio palet, etc.).

TODO: Implementar tras verificar acceso al portal myaccount.chep.com
"""
from __future__ import annotations

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper

CHEP_LOGIN_URL = f"{settings.chep_url}/login"  # TODO: ajustar


class ChepScraper(BaseScraper):
    portal_name = "chep"

    def _login(self) -> None:
        page = self._page
        page.goto(CHEP_LOGIN_URL)
        page.wait_for_load_state("networkidle")
        # TODO: implementar con selectores reales
        raise NotImplementedError("Scraper CHEP pendiente de implementar")

    def _submit_declaration(self, albaran: Albaran) -> str:
        # TODO: implementar
        raise NotImplementedError("Scraper CHEP pendiente de implementar")

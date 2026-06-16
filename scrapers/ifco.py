"""
Scraper para MyIFCO (www.ifco-online.com).

Auth : login propio con IFCO-N° + usuario + contraseña (sin SSO)
Login: https://sso.ifco-online.com/login
Portal: https://www.ifco-online.com/myifco-core-fe
"""
from __future__ import annotations

from loguru import logger

from config.settings import settings
from core.models import Albaran
from scrapers.base import BaseScraper

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
SSO_URL    = "https://sso.ifco-online.com/login"
PORTAL_URL = "https://www.ifco-online.com/myifco-core-fe"

# ---------------------------------------------------------------------------
# Selectores login  (CAS login page de sso.ifco-online.com)
# ---------------------------------------------------------------------------
SEL_IFCO_NUMBER = "input[name='ifcoNumber'], input[id='ifcoNumber']"
SEL_USERNAME    = "input[name='username'], input[id='username']"
SEL_PASSWORD    = "input[type='password']"
SEL_LOGIN_BTN   = "button:has-text('INICIAR SESIÓN'), button[type='submit']"


class IfcoScraper(BaseScraper):
    portal_name = "ifco"

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _login(self) -> None:
        page = self._page

        page.goto(PORTAL_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2_000)

        # Si ya estamos logueados, no hace falta volver a entrar
        if self._ya_autenticado():
            logger.info("[ifco] Sesión activa")
            return

        logger.info("[ifco] Iniciando login...")

        # La redirección puede llevar a sso.ifco-online.com/login
        # o podemos ir directamente si la app no redirige sola
        if "sso.ifco-online.com" not in page.url:
            page.goto(SSO_URL)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1_500)

        # ── IFCO-N° ─────────────────────────────────────────────────
        try:
            field = page.get_by_label("IFCO-N", exact=False)
            if not field.first.is_visible(timeout=3_000):
                raise ValueError("no visible")
            field.first.fill(settings.ifco_number)
        except Exception:
            try:
                page.locator(SEL_IFCO_NUMBER).first.fill(settings.ifco_number)
            except Exception:
                logger.warning("[ifco] No se encontró campo IFCO-N°")

        # ── Identificación de usuario ────────────────────────────────
        try:
            field = page.get_by_label("Identificación de usuario", exact=False)
            if not field.first.is_visible(timeout=2_000):
                raise ValueError("no visible")
            field.first.fill(settings.ifco_user)
        except Exception:
            page.locator(SEL_USERNAME).first.fill(settings.ifco_user)

        # ── Contraseña ───────────────────────────────────────────────
        page.locator(SEL_PASSWORD).first.fill(settings.ifco_password)

        # ── Enviar ───────────────────────────────────────────────────
        page.locator(SEL_LOGIN_BTN).first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)

        if not self._ya_autenticado():
            self._screenshot("login_fallido")
            raise RuntimeError(
                "Login en IFCO fallido. Verifica IFCO_NUMBER, IFCO_USER e IFCO_PASSWORD en .env"
            )

        logger.info("[ifco] Login OK")

    def _ya_autenticado(self) -> bool:
        url = self._page.url if self._page else ""
        # Estamos autenticados si la URL es del portal (no del SSO/login)
        if "sso.ifco-online.com" in url:
            return False
        if "ifco-online.com" not in url and "ifco.com" not in url:
            return False
        return True

    # ------------------------------------------------------------------
    # Declaración — se implementa tras explorar el formulario con
    # ifco_diagnostico.py
    # ------------------------------------------------------------------

    def _submit_declaration(self, albaran: Albaran) -> str:
        page = self._page
        logger.info(f"[ifco] Declarando albarán {albaran.num_albaran}...")

        # TODO: navegar al formulario de nueva declaración
        # TODO: rellenar campos según la estructura real del portal

        raise NotImplementedError(
            "Formulario IFCO pendiente de implementar. "
            "Ejecuta ifco_diagnostico.py para capturar la estructura."
        )

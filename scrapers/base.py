"""Clase base para todos los scrapers. Gestiona login, reintentos y capturas en error."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from config.settings import settings
from core.models import Albaran, DeclarationStatus, DeclaracionResult


class BaseScraper(ABC):
    portal_name: str = "base"
    _session_file: Path | None = None  # cada scraper puede definir su propia ruta

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida del navegador
    # ------------------------------------------------------------------

    def _start_browser(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=settings.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # Reutilizar sesión guardada si existe (evita re-login)
        session_path = self._session_file
        ctx_kwargs: dict = {"viewport": {"width": 1440, "height": 900}, "locale": "es-ES"}
        if session_path and session_path.exists():
            ctx_kwargs["storage_state"] = str(session_path)
            logger.debug(f"[{self.portal_name}] Cargando sesión guardada: {session_path}")

        self._context = self._browser.new_context(**ctx_kwargs)
        self._page = self._context.new_page()
        self._page.set_default_timeout(settings.browser_timeout_ms)

    def _save_session(self) -> None:
        """Persiste cookies y localStorage para evitar re-login en la siguiente ejecución."""
        if self._session_file and self._context:
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            self._context.storage_state(path=str(self._session_file))
            logger.debug(f"[{self.portal_name}] Sesión guardada en {self._session_file}")

    def _stop_browser(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _screenshot(self, name: str) -> Path:
        settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = settings.screenshots_dir / f"{self.portal_name}_{name}_{int(time.time())}.png"
        if self._page:
            self._page.screenshot(path=str(path), full_page=True)
        return path

    # ------------------------------------------------------------------
    # Método principal público
    # ------------------------------------------------------------------

    def declarar(self, albaran: Albaran) -> DeclaracionResult:
        result = DeclaracionResult(albaran=albaran, status=DeclarationStatus.PENDING)
        for attempt in range(1, settings.retry_attempts + 1):
            try:
                self._start_browser()
                self._login()
                confirmation = self._submit_declaration(albaran)
                result.status = DeclarationStatus.SUBMITTED
                result.confirmation_number = confirmation
                logger.success(
                    f"[{self.portal_name}] Albarán {albaran.num_albaran} "
                    f"declarado. Confirmación: {confirmation}"
                )
                break
            except Exception as exc:
                logger.warning(
                    f"[{self.portal_name}] Intento {attempt}/{settings.retry_attempts} "
                    f"fallido para {albaran.num_albaran}: {exc}"
                )
                result.screenshot_path = self._screenshot(
                    f"error_{albaran.num_albaran}_intento{attempt}"
                )
                result.error_message = str(exc)
                if attempt == settings.retry_attempts:
                    result.status = DeclarationStatus.ERROR
                    # Borrar sesión corrupta para forzar re-login la próxima vez
                    if self._session_file and self._session_file.exists():
                        self._session_file.unlink(missing_ok=True)
                else:
                    time.sleep(2 ** attempt)
            finally:
                self._stop_browser()
        return result

    # ------------------------------------------------------------------
    # Métodos a implementar por cada scraper concreto
    # ------------------------------------------------------------------

    @abstractmethod
    def _login(self) -> None:
        """Autenticar en el portal."""

    @abstractmethod
    def _submit_declaration(self, albaran: Albaran) -> str:
        """Rellenar y enviar el formulario de declaración. Devuelve nº de confirmación."""

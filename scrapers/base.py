"""Clase base para todos los scrapers. Gestiona login, reintentos y capturas en error."""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

from loguru import logger
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from config.settings import settings
from core.models import Albaran, DeclarationStatus, DeclaracionResult

# Perfil de Edge siempre junto al proyecto, independiente de OUTPUT_DIR
_ROOT = Path(__file__).resolve().parent.parent
_EDGE_PROFILE_DIR = _ROOT / "output" / "edge_profile"


class BaseScraper(ABC):
    portal_name: str = "base"
    _session_file: Path | None = None  # ya no se usa con perfil persistente

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida del navegador
    # ------------------------------------------------------------------

    def _start_browser(self) -> None:
        self._playwright = sync_playwright().start()
        _EDGE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # Usar Microsoft Edge real (tiene Windows Hello / SSO integrado)
        # Si Edge no está instalado, intenta Chrome; si tampoco, Chromium puro
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(_EDGE_PROFILE_DIR),
                    headless=settings.headless,
                    slow_mo=settings.browser_slow_mo,
                    viewport={"width": 1440, "height": 900},
                    locale="es-ES",
                )
                # Grabar vídeo de la sesión si está activado en .env
                if settings.record_video:
                    video_dir = settings.output_dir / "videos"
                    video_dir.mkdir(parents=True, exist_ok=True)
                    kwargs["record_video_dir"] = str(video_dir)
                    kwargs["record_video_size"] = {"width": 1440, "height": 900}
                if channel:
                    kwargs["channel"] = channel

                self._context = self._playwright.chromium.launch_persistent_context(**kwargs)
                logger.debug(f"[{self.portal_name}] Navegador: {channel or 'chromium'}")
                break
            except Exception as exc:
                logger.debug(f"[{self.portal_name}] Canal {channel} no disponible: {exc}")
                self._context = None

        if self._context is None:
            raise RuntimeError("No se pudo iniciar ningún navegador (Edge, Chrome o Chromium).")

        self._page = self._context.new_page()
        self._page.set_default_timeout(settings.browser_timeout_ms)

    def _save_session(self) -> None:
        """Con perfil persistente la sesión se guarda sola — no hace nada."""
        pass

    def _stop_browser(self) -> None:
        # Capturar la ruta del vídeo antes de cerrar (se finaliza al cerrar el context)
        video_path = None
        if settings.record_video and self._page:
            try:
                video_path = self._page.video.path() if self._page.video else None
            except Exception:
                video_path = None

        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._playwright:
            self._playwright.stop()

        if video_path:
            logger.info(f"[{self.portal_name}] Vídeo de la sesión guardado: {video_path}")

    def _screenshot(self, name: str) -> Path:
        settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize: num_albaran may contain '/' which breaks Windows paths
        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        path = settings.screenshots_dir / f"{self.portal_name}_{safe_name}_{int(time.time())}.png"
        if self._page:
            try:
                self._page.screenshot(path=str(path), full_page=True)
            except Exception:
                pass
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

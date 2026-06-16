from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Carga siempre el .env desde la raíz del proyecto (junto a watcher.py)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _bool(key: str, default: bool) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


class _Settings:
    # Europool
    europool_url:      str  = os.getenv("EUROPOOL_URL",      "https://webportal.europoolsystem.com")
    europool_user:     str  = os.getenv("EUROPOOL_USER",     "")
    europool_password: str  = os.getenv("EUROPOOL_PASSWORD", "")

    # IFCO
    ifco_url:      str = os.getenv("IFCO_URL",      "https://www.ifco-online.com")
    ifco_number:   str = os.getenv("IFCO_NUMBER",   "")   # IFCO-N° (ej: 612029)
    ifco_user:     str = os.getenv("IFCO_USER",     "")
    ifco_password: str = os.getenv("IFCO_PASSWORD", "")

    # CHEP
    chep_url:      str = os.getenv("CHEP_URL",      "https://myaccount.chep.com")
    chep_user:     str = os.getenv("CHEP_USER",     "")
    chep_password: str = os.getenv("CHEP_PASSWORD", "")

    # Rutas
    input_dir:       Path = Path(os.getenv("INPUT_DIR",       "./input"))
    output_dir:      Path = Path(os.getenv("OUTPUT_DIR",      "./output"))
    screenshots_dir: Path = Path(os.getenv("SCREENSHOTS_DIR", "./screenshots"))

    # Navegador
    headless:          bool = _bool("HEADLESS", True)
    browser_timeout_ms: int = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
    browser_slow_mo:    int = int(os.getenv("BROWSER_SLOW_MO", "0"))
    retry_attempts:     int = int(os.getenv("RETRY_ATTEMPTS", "3"))

    # Impresión
    auto_print:   bool = _bool("AUTO_PRINT", True)
    printer_name: str  = os.getenv("PRINTER_NAME", "")


settings = _Settings()

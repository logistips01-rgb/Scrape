from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Europool
    europool_url: str = "https://portal.europool.com"
    europool_user: str = ""
    europool_password: str = ""

    # IFCO
    ifco_url: str = "https://portal.ifco.com"
    ifco_user: str = ""
    ifco_password: str = ""

    # CHEP
    chep_url: str = "https://myaccount.chep.com"
    chep_user: str = ""
    chep_password: str = ""

    # Rutas
    input_dir: Path = Path("./input")
    output_dir: Path = Path("./output")
    screenshots_dir: Path = Path("./screenshots")

    # Comportamiento del navegador
    headless: bool = True
    browser_timeout_ms: int = 30_000
    retry_attempts: int = 3


settings = Settings()

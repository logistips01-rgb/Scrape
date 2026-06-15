"""
Login manual de Europool — ejecutar UNA VEZ para guardar la sesión.

Uso:
    python login_manual.py

Abre Chrome, inicia sesión manualmente en el portal y pulsa ENTER.
La sesión queda guardada y el watcher la reutilizará automáticamente
sin volver a pedir credenciales.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

from config.settings import settings

PORTAL_URL   = "https://webportal.europoolsystem.com"
SESSION_FILE = settings.output_dir / "europool_session.json"


def main() -> None:
    print()
    print("=" * 60)
    print("  LOGIN MANUAL - EUROPOOL")
    print("=" * 60)
    print()
    print("Se abrira el navegador con el portal de Europool.")
    print("Inicia sesion normalmente (con tu cuenta Microsoft).")
    print()
    print("Cuando estes dentro del portal (veas el dashboard),")
    print("vuelve aqui y pulsa ENTER para guardar la sesion.")
    print()
    input("Pulsa ENTER para abrir el navegador...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(
            viewport=None,
            locale="es-ES",
            no_viewport=True,
        )
        page = context.new_page()
        page.goto(PORTAL_URL)

        print()
        print("Navegador abierto. Inicia sesion en el portal.")
        print("Cuando estes dentro, vuelve aqui y pulsa ENTER.")
        print()
        input("Pulsa ENTER para guardar la sesion y cerrar el navegador...")

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        browser.close()

    print()
    print(f"Sesion guardada en: {SESSION_FILE}")
    print()
    print("Ya puedes arrancar el watcher con: python watcher.py")
    print("No necesitaras volver a hacer login hasta que caduque la sesion.")
    print()


if __name__ == "__main__":
    main()

"""
Login manual de Europool — ejecutar UNA VEZ para guardar la sesion.

Uso:
    python login_manual.py

Abre Chrome, inicia sesion manualmente en el portal y pulsa ENTER.
La sesion queda guardada y el watcher la reutilizara automaticamente.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_FILE = Path("output") / "europool_session.json"
PORTAL_URL   = "https://webportal.europoolsystem.com"


def main() -> None:
    print()
    print("=" * 60)
    print("  LOGIN MANUAL - EUROPOOL")
    print("=" * 60)
    print()
    print("Abriendo el navegador...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        print("Navegando al portal...")
        page.goto(PORTAL_URL)

        print()
        print("El navegador esta abierto.")
        print("  1. Haz click en Log in")
        print("  2. Elige la cuenta 0001006572-4@epswebportal.onmicrosoft.com")
        print("  3. Autenticate con PIN o Windows Hello")
        print("  4. Haz click en MY EPS si es necesario")
        print("  5. Cuando veas el dashboard, vuelve aqui")
        print()
        input("Pulsa ENTER cuando estes en el dashboard del portal...")

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        print(f"Sesion guardada en: {SESSION_FILE}")
        browser.close()

    print()
    print("Listo! Ahora arranca el watcher con: python watcher.py")
    print()


if __name__ == "__main__":
    main()

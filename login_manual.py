"""
Login manual de Europool — ejecutar UNA VEZ para guardar la sesion.

Uso:
    python login_manual.py
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

    # Borrar sesion anterior invalida si existe
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        print("Sesion anterior borrada.")

    print("Abriendo el navegador en pantalla completa...")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--window-position=0,0",
                "--window-size=1280,900",
                "--foreground",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.bring_to_front()
        page.goto(PORTAL_URL)
        page.bring_to_front()

        print("El navegador esta abierto (busca la ventana de Chrome en la barra de tareas).")
        print()
        print("Pasos a seguir en el navegador:")
        print("  1. Haz click en 'Log in'")
        print("  2. Elige la cuenta 0001006572-4@epswebportal.onmicrosoft.com")
        print("  3. Usa PIN o Windows Hello para autenticarte")
        print("  4. Si aparece 'MY EPS', haz click en ese tile")
        print("  5. Cuando veas el dashboard con PEDIDOS/MOVIMIENTOS")
        print("     vuelve AQUI y pulsa ENTER")
        print()
        print("IMPORTANTE: pulsa ENTER solo cuando veas el dashboard del portal,")
        print("NO cuando estes en la pantalla de Microsoft.")
        print()
        input("Pulsa ENTER cuando estes en el dashboard de Europool...")

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        print(f"Sesion guardada en: {SESSION_FILE}")
        browser.close()

    print()
    print("Listo! Ahora arranca el watcher con: python watcher.py")
    print()


if __name__ == "__main__":
    main()

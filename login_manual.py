"""
Login manual de Europool — ejecutar UNA VEZ para guardar la sesion.

Abre Microsoft Edge con un perfil dedicado al watcher. Como es Edge real,
Windows Hello funciona automaticamente igual que en tu navegador habitual.

Uso:
    python login_manual.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

PORTAL_URL   = "https://webportal.europoolsystem.com"
PROFILE_DIR  = Path("output") / "edge_profile"


def main() -> None:
    print()
    print("=" * 60)
    print("  LOGIN MANUAL - EUROPOOL")
    print("=" * 60)
    print()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        print("Abriendo Edge... (puede tardar unos segundos)")

        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    args=["--no-sandbox"],
                    viewport={"width": 1280, "height": 900},
                )
                if channel:
                    kwargs["channel"] = channel
                context = p.chromium.launch_persistent_context(**kwargs)
                print(f"Navegador abierto ({channel or 'chromium'}).")
                break
            except Exception as e:
                print(f"  {channel or 'chromium'} no disponible: {e}")
                context = None

        if context is None:
            print("ERROR: No se pudo abrir ningun navegador.")
            return

        page = context.new_page()
        page.goto(PORTAL_URL)

        print()
        print("El navegador esta abierto. Sigue estos pasos:")
        print("  1. Haz click en 'Log in'")
        print("  2. Elige la cuenta 0001006572-4@epswebportal.onmicrosoft.com")
        print("     (Windows Hello deberia autenticarte automaticamente)")
        print("  3. Si aparece selector 'MY EPS', haz click en el")
        print("  4. Cuando veas el dashboard con PEDIDOS/MOVIMIENTOS...")
        print()
        print("IMPORTANTE: pulsa ENTER aqui solo cuando estes en el dashboard,")
        print("NO desde la pantalla de Microsoft.")
        print()
        input("Pulsa ENTER cuando estes en el dashboard de Europool...")

        # Con perfil persistente la sesion se guarda automaticamente al cerrar
        context.close()

    print()
    print("Sesion guardada en:", PROFILE_DIR)
    print("Ya puedes arrancar el watcher con: python watcher.py")
    print()


if __name__ == "__main__":
    main()

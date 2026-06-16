"""
Script de DIAGNOSTICO / LOGIN - abre el navegador VISIBLE.

1. Abre Edge con el perfil que usa el watcher (output/edge_profile).
2. Si NO estas logueado, te deja iniciar sesion manualmente.
   Como el perfil es persistente, la sesion se guarda para siempre.
3. Luego recorre el portal e imprime que encuentra en cada paso,
   para localizar el formulario real.

Uso:
    python probar.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

PORTAL_URL  = "https://webportal.europoolsystem.com"
PROFILE_DIR = Path("output") / "edge_profile"


def info(page, etiqueta):
    print()
    print(f"--- {etiqueta} ---")
    print(f"  URL actual : {page.url}")
    for desc, sel in [
        ("Boton 'Log in'",     "a:has-text('Log in'), button:has-text('Log in')"),
        ("Tile 'MY EPS'",      "text=MY EPS"),
        ("Boton 'Log out'",    "text=Log out"),
        ("mat-select (form)",  "mat-select"),
        ("Menu PEDIDOS",       "text=PEDIDOS"),
        ("Menu MOVIMIENTOS",   "text=MOVIMIENTOS"),
        ("ALBARAN MANUAL",     "text=ALBARÁN MANUAL"),
    ]:
        try:
            n = page.locator(sel).count()
            print(f"  [{'SI' if n else 'no'}] {desc}  (encontrados: {n})")
        except Exception as e:
            print(f"  [??] {desc}: {e}")


def esta_logueado(page) -> bool:
    try:
        if page.locator("text=Log out").count() > 0:
            return True
        if page.locator("a:has-text('Log in'), button:has-text('Log in')").count() > 0:
            return False
    except Exception:
        pass
    return False


def main():
    print("=" * 60)
    print("  DIAGNOSTICO / LOGIN EUROPOOL")
    print("=" * 60)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = None
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    slow_mo=500,
                    viewport={"width": 1440, "height": 900},
                )
                if channel:
                    kwargs["channel"] = channel
                context = p.chromium.launch_persistent_context(**kwargs)
                print(f"\nNavegador abierto: {channel or 'chromium'}")
                break
            except Exception as e:
                print(f"  {channel or 'chromium'} no disponible: {e}")

        if context is None:
            print("ERROR: ningun navegador disponible.")
            return

        page = context.pages[0] if context.pages else context.new_page()

        # PASO 1: abrir el portal
        print("\n[PASO 1] Abriendo el portal...")
        page.goto(PORTAL_URL)
        page.wait_for_timeout(4000)
        info(page, "PASO 1: portal raiz")

        # PASO 2: comprobar login
        if not esta_logueado(page):
            print()
            print("*" * 60)
            print("  NO estas logueado en este perfil.")
            print("  En la ventana del navegador que se ha abierto:")
            print("    1. Haz click en 'Log in'")
            print("    2. Elige la cuenta y autenticate (PIN / Windows Hello)")
            print("    3. Cuando veas 'YOUR PORTALS' con el tile MY EPS, PARA AHI")
            print("  La sesion se guardara en el perfil automaticamente.")
            print("*" * 60)
            input("\nPulsa ENTER aqui cuando veas 'YOUR PORTALS' / MY EPS...")
            page.wait_for_timeout(1000)
            info(page, "Despues del login manual")
        else:
            print("\n[OK] Ya estabas logueado en este perfil.")

        # PASO 3: click en MY EPS
        tile = page.locator("text=MY EPS")
        if tile.count() > 0:
            print("\n[PASO 3] Haciendo click en 'MY EPS'...")
            try:
                with context.expect_page(timeout=8000) as nueva:
                    tile.first.click()
                page = nueva.value
                print("  -> Se abrio una PESTANA NUEVA")
            except Exception:
                print("  -> Navego en la MISMA pestana")
            page.wait_for_timeout(5000)
            info(page, "PASO 3: despues de click en MY EPS")
        else:
            print("\n[PASO 3] No se encontro el tile MY EPS")

        # PASO 4: intentar abrir el formulario
        print("\n[PASO 4] Intentando abrir /#/flows/new ...")
        try:
            base_url = page.url.split("#")[0]
            page.goto(base_url + "#/flows/new")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  Error: {e}")
        info(page, "PASO 4: formulario flows/new")

        print()
        print("=" * 60)
        print("  Navegador ABIERTO. Mira la pantalla y dime que ves.")
        print("  Copia y pegame TODO este texto de la consola.")
        print("=" * 60)
        input("\nPulsa ENTER para cerrar...")
        context.close()


if __name__ == "__main__":
    main()

"""
Script de DIAGNOSTICO - abre el navegador VISIBLE y a camara lenta.

Recorre el portal paso a paso imprimiendo en consola que encuentra en
cada momento, para ver donde esta el problema. El navegador se queda
ABIERTO al final para poder inspeccionar.

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
    try:
        print(f"  Titulo     : {page.title()}")
    except Exception:
        pass
    # Que elementos clave hay en la pagina
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
            marca = "SI" if n > 0 else "no"
            print(f"  [{marca}] {desc}  (encontrados: {n})")
        except Exception as e:
            print(f"  [??] {desc}: {e}")


def main():
    print("=" * 60)
    print("  DIAGNOSTICO EUROPOOL - navegador visible")
    print("=" * 60)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = None
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,        # SIEMPRE visible
                    slow_mo=700,           # camara lenta
                    args=["--no-sandbox"],
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

        # PASO 1: abrir el portal raiz
        print("\n[PASO 1] Abriendo el portal...")
        page.goto(PORTAL_URL)
        page.wait_for_timeout(4000)
        info(page, "PASO 1: portal raiz")

        # PASO 2: si hay tile MY EPS, ver su enlace y hacer click
        tile = page.locator("text=MY EPS")
        if tile.count() > 0:
            print("\n[PASO 2] Encontrado 'MY EPS'. Inspeccionando enlace...")
            # buscar el <a> contenedor para ver a donde apunta
            try:
                enlace = page.locator("a:has(img[alt*='EPS']), a:has-text('MY EPS')")
                if enlace.count() > 0:
                    href = enlace.first.get_attribute("href")
                    print(f"  href del tile: {href}")
            except Exception as e:
                print(f"  No se pudo leer href: {e}")

            print("  Haciendo click en MY EPS...")
            # el click puede abrir una pestana nueva
            try:
                with context.expect_page(timeout=8000) as nueva:
                    tile.first.click()
                page = nueva.value
                print("  -> Se abrio una PESTANA NUEVA")
            except Exception:
                print("  -> Navego en la MISMA pestana (sin pestana nueva)")
            page.wait_for_timeout(5000)
            info(page, "PASO 2: despues de click en MY EPS")
        else:
            print("\n[PASO 2] No hay tile 'MY EPS' (quiza ya estamos dentro o hay que hacer Log in)")

        # PASO 3: intentar ir al formulario de nuevo movimiento
        print("\n[PASO 3] Intentando abrir el formulario /#/flows/new ...")
        try:
            base_url = page.url.split("#")[0]
            page.goto(base_url + "#/flows/new")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  Error al navegar: {e}")
        info(page, "PASO 3: formulario flows/new")

        print()
        print("=" * 60)
        print("  El navegador se queda ABIERTO para que inspecciones.")
        print("  Mira la pantalla y dime que ves.")
        print("=" * 60)
        input("\nPulsa ENTER aqui cuando quieras cerrar el navegador...")
        context.close()


if __name__ == "__main__":
    main()

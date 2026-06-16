"""
diagnostico.py — Captura completa del portal Europool para análisis.

Qué hace:
  1. Abre Edge con el perfil persistente (headless=False)
  2. Si no hay sesión, te pide login manual UNA vez
  3. Navega a webportal.europoolsystem.com/#/dashboard
  4. Navega a /#/flows/new (formulario de declaración)
  5. Guarda screenshots + HTML en la carpeta  diagnostico/

Uso:
    python diagnostico.py

Al terminar, comparte la carpeta  diagnostico/  (o un zip).
"""

import json
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── Configuración ──────────────────────────────────────────────────────────
PORTAL_URL    = "https://webportal.europoolsystem.com"
DASHBOARD_URL = "https://webportal.europoolsystem.com/#/dashboard"
FLOWS_NEW_URL = "https://webportal.europoolsystem.com/#/flows/new"

_ROOT        = Path(__file__).resolve().parent
PROFILE_DIR  = _ROOT / "output" / "edge_profile"
OUT_DIR      = _ROOT / "diagnostico"


# ── Helpers ────────────────────────────────────────────────────────────────

def guardar(page, nombre: str, out: Path) -> None:
    """Guarda screenshot + HTML con el nombre dado."""
    ts = datetime.now().strftime("%H%M%S")
    slug = f"{ts}_{nombre}"

    # Screenshot
    img = out / f"{slug}.png"
    try:
        page.screenshot(path=str(img), full_page=True)
        print(f"  [IMG] {img.name}")
    except Exception as e:
        print(f"  [IMG] ERROR: {e}")

    # HTML
    html = out / f"{slug}.html"
    try:
        html.write_text(page.content(), encoding="utf-8")
        print(f"  [HTML] {html.name}")
    except Exception as e:
        print(f"  [HTML] ERROR: {e}")


def volcar_elementos(page, out: Path, nombre: str) -> dict:
    """Extrae información de todos los elementos de formulario de la página."""
    data = {
        "url": page.url,
        "ng_select": [],
        "inputs": [],
        "buttons": [],
        "labels": [],
        "text_visible": [],
    }

    # ng-select
    try:
        for i, el in enumerate(page.locator("ng-select").all()):
            try:
                data["ng_select"].append({
                    "nth": i,
                    "class": el.get_attribute("class") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "aria_label": el.get_attribute("aria-label") or "",
                    "text": (el.text_content() or "").strip()[:100],
                })
            except Exception:
                pass
    except Exception:
        pass

    # inputs
    try:
        for i, el in enumerate(page.locator("input:visible").all()):
            try:
                data["inputs"].append({
                    "nth": i,
                    "type": el.get_attribute("type") or "",
                    "name": el.get_attribute("name") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "id": el.get_attribute("id") or "",
                    "aria_label": el.get_attribute("aria-label") or "",
                })
            except Exception:
                pass
    except Exception:
        pass

    # buttons
    try:
        for i, el in enumerate(page.locator("button:visible").all()):
            try:
                texto = (el.text_content() or "").strip()[:80]
                if texto:
                    data["buttons"].append({"nth": i, "text": texto})
            except Exception:
                pass
    except Exception:
        pass

    # labels / mat-label / .ng-label
    try:
        for sel in ["label", "mat-label", ".ng-placeholder", ".form-label", "span.label"]:
            for el in page.locator(sel).all():
                try:
                    t = (el.text_content() or "").strip()
                    if t and t not in data["labels"]:
                        data["labels"].append(t)
                except Exception:
                    pass
    except Exception:
        pass

    # texto visible en pantalla (primeros 30 elementos de texto)
    try:
        texts = page.evaluate("""() => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            const result = [];
            let node;
            while ((node = walker.nextNode()) && result.length < 40) {
                const t = node.textContent.trim();
                if (t.length > 3 && t.length < 120) result.push(t);
            }
            return result;
        }""")
        data["text_visible"] = texts
    except Exception:
        pass

    # Guardar JSON
    json_path = out / f"{nombre}.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [JSON] {json_path.name}")
    return data


def esta_logueado(page) -> bool:
    try:
        if page.locator("a:has-text('Log in'), button:has-text('Log in')").count() > 0:
            return False
        if "login.microsoftonline.com" in page.url:
            return False
        if "my.europoolsystem.com" not in page.url and "webportal.europoolsystem.com" not in page.url:
            return False
    except Exception:
        return False
    return True


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    log("=" * 60)
    log("  DIAGNOSTICO EUROPOOL")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    log(f"  Perfil   : {PROFILE_DIR}")
    log(f"  Salida   : {OUT_DIR}")
    log("")

    with sync_playwright() as p:
        context = None
        canal_usado = None
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    slow_mo=600,
                    viewport={"width": 1440, "height": 900},
                    locale="es-ES",
                )
                if channel:
                    kwargs["channel"] = channel
                context = p.chromium.launch_persistent_context(**kwargs)
                canal_usado = channel or "chromium"
                log(f"  Navegador: {canal_usado}")
                break
            except Exception as e:
                log(f"  {channel or 'chromium'} no disponible: {e}")

        if context is None:
            log("ERROR: no se pudo abrir ningún navegador.")
            return

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)

        # ── PASO 1: abrir portal ──────────────────────────────────────
        log("\n[PASO 1] Abriendo portal...")
        page.goto(PORTAL_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3_000)
        log(f"  URL: {page.url}")
        guardar(page, "paso1_portal", OUT_DIR)

        # ── PASO 2: login manual si hace falta ───────────────────────
        if not esta_logueado(page):
            log("")
            log("*" * 60)
            log("  NO hay sesión guardada en este perfil.")
            log("")
            log("  En la ventana del navegador:")
            log("    1. Haz click en 'Log in'")
            log("    2. Elige tu cuenta y autentica con PIN / Windows Hello")
            log("    3. Cuando veas el dashboard o 'YOUR PORTALS', para")
            log("*" * 60)
            input("\n  Pulsa ENTER cuando hayas terminado el login...")
            page.wait_for_timeout(2_000)
            log(f"  URL tras login: {page.url}")
            guardar(page, "paso2_tras_login", OUT_DIR)
        else:
            log("  Sesión activa, no hace falta login.")

        # ── PASO 3: acceder al webportal via MY EPS ──────────────────
        log("\n[PASO 3] Buscando tile MY EPS para abrir webportal...")
        guardar(page, "paso3_hub_antes", OUT_DIR)

        # MY EPS abre webportal.europoolsystem.com en NUEVA PESTAÑA
        # page.goto() no funciona porque la sesión es de my.europoolsystem.com
        portal_page = None
        try:
            tile = page.locator("text=MY EPS").first
            if tile.is_visible(timeout=5_000):
                log("  Tile MY EPS encontrado. Haciendo click y esperando nueva pestaña...")
                with context.expect_page(timeout=15_000) as new_page_info:
                    tile.click()
                portal_page = new_page_info.value
                portal_page.wait_for_load_state("networkidle")
                portal_page.wait_for_timeout(3_000)
                log(f"  Nueva pestaña URL: {portal_page.url}")
                guardar(portal_page, "paso3_nueva_pestana_webportal", OUT_DIR)
            else:
                log("  Tile MY EPS NO encontrado.")
        except Exception as e:
            log(f"  ERROR al click MY EPS / nueva pestaña: {e}")

        # Si MY EPS no abrió nueva pestaña, comprobar si hay otras pestañas abiertas
        if portal_page is None:
            log("  Comprobando otras pestañas abiertas...")
            for p in context.pages:
                log(f"    Pestaña: {p.url}")
                if "webportal.europoolsystem.com" in p.url:
                    portal_page = p
                    log(f"  Webportal encontrado en pestaña existente: {p.url}")
                    break

        if portal_page is None:
            log("  NO se pudo abrir webportal via MY EPS.")
            log("  Intentando goto directo como fallback...")
            page.goto(DASHBOARD_URL)
            page.wait_for_timeout(4_000)
            log(f"  URL tras goto directo: {page.url}")
            portal_page = page

        # A partir de aquí usar portal_page
        page = portal_page
        log(f"\n  URL webportal: {page.url}")

        # ── PASO 4: navegar al formulario ────────────────────────────
        log("\n[PASO 4] Navegando al formulario flows/new...")
        page.goto(FLOWS_NEW_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4_000)
        log(f"  URL: {page.url}")
        guardar(page, "paso4_formulario", OUT_DIR)

        # Cerrar cookies si aparecen
        try:
            btn = page.locator("button:has-text('Got it'), button:has-text('Aceptar'), button:has-text('Accept')")
            if btn.first.is_visible(timeout=3_000):
                btn.first.click()
                page.wait_for_timeout(1_000)
                log("  Cookie banner cerrado.")
        except Exception:
            pass

        # Esperar a que cargue algo del formulario
        log("  Esperando formulario (hasta 30s)...")
        encontrado = False
        for selector in ["text=ENCABEZAMIENTO", "ng-select", "mat-select", "form", "input"]:
            try:
                page.wait_for_selector(selector, timeout=8_000)
                log(f"  Formulario detectado con: {selector}")
                encontrado = True
                break
            except Exception:
                pass

        if not encontrado:
            log("  AVISO: no se detectó formulario en 30s.")

        page.wait_for_timeout(2_000)
        guardar(page, "paso4b_formulario_cargado", OUT_DIR)

        # ── PASO 5: volcar elementos del formulario ──────────────────
        log("\n[PASO 5] Extrayendo elementos del formulario...")
        datos = volcar_elementos(page, OUT_DIR, "elementos_formulario")

        log(f"\n  ng-select encontrados  : {len(datos['ng_select'])}")
        for s in datos["ng_select"]:
            log(f"    [{s['nth']}] placeholder='{s['placeholder']}' aria-label='{s['aria_label']}'")
            log(f"         texto='{s['text']}'")

        log(f"\n  inputs visibles        : {len(datos['inputs'])}")
        for inp in datos["inputs"]:
            log(f"    [{inp['nth']}] type={inp['type']} name='{inp['name']}' placeholder='{inp['placeholder']}' id='{inp['id']}'")

        log(f"\n  botones visibles       : {len(datos['buttons'])}")
        for b in datos["buttons"]:
            log(f"    [{b['nth']}] '{b['text']}'")

        log(f"\n  labels                 : {datos['labels']}")
        log(f"\n  texto visible (muestra): {datos['text_visible'][:15]}")

        # ── PASO 6: screenshot final con scroll ──────────────────────
        log("\n[PASO 6] Screenshot final...")
        guardar(page, "paso6_final", OUT_DIR)

        # ── Guardar log ──────────────────────────────────────────────
        log_path = OUT_DIR / "log.txt"
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

        log("")
        log("=" * 60)
        log("  DIAGNOSTICO COMPLETADO")
        log(f"  Archivos guardados en: {OUT_DIR}")
        log("  Comparte esa carpeta (o un zip) para el análisis.")
        log("=" * 60)

        input("\nPulsa ENTER para cerrar el navegador...")
        context.close()


if __name__ == "__main__":
    main()

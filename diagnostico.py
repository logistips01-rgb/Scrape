"""
diagnostico.py — Captura completa del portal Europool para análisis.

Qué hace:
  1. Abre Edge con el perfil persistente (headless=False)
  2. Si no hay sesión, te pide login manual
  3. Te pide que hagas click en MY EPS manualmente (para evitar el problema
     de la nueva pestaña que no se detecta automáticamente)
  4. Una vez en el webportal, navega al formulario y vuelca todo
  5. Guarda screenshots + HTML + JSON en la carpeta  diagnostico/

Uso:
    python diagnostico.py

Al terminar, comparte la carpeta  diagnostico/  (o un zip).
"""

import json
import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── Configuración ──────────────────────────────────────────────────────────
HUB_URL        = "https://my.europoolsystem.com"
PORTAL_URL     = "https://webportal.europoolsystem.com"
FLOWS_NEW_URL  = "https://webportal.europoolsystem.com/#/flows/new"
EUROPOOL_USER  = "0001006572-4@epswebportal.onmicrosoft.com"

_ROOT        = Path(__file__).resolve().parent
PROFILE_DIR  = _ROOT / "output" / "edge_profile"
OUT_DIR      = _ROOT / "diagnostico"


# ── Helpers ────────────────────────────────────────────────────────────────

def guardar(page, nombre: str, out: Path) -> None:
    ts = datetime.now().strftime("%H%M%S")
    slug = f"{ts}_{nombre}"
    img = out / f"{slug}.png"
    html = out / f"{slug}.html"
    try:
        page.screenshot(path=str(img), full_page=True)
        print(f"  [IMG]  {img.name}")
    except Exception as e:
        print(f"  [IMG]  ERROR: {e}")
    try:
        html.write_text(page.content(), encoding="utf-8")
        print(f"  [HTML] {html.name}")
    except Exception as e:
        print(f"  [HTML] ERROR: {e}")


def perfil_info(label: str) -> None:
    """Muestra cuántos archivos y el tamaño total del perfil."""
    try:
        archivos = list(PROFILE_DIR.rglob("*"))
        total = sum(f.stat().st_size for f in archivos if f.is_file())
        print(f"  [{label}] Perfil: {len(archivos)} archivos, {total // 1024} KB")
    except Exception as e:
        print(f"  [{label}] Perfil: no se pudo leer ({e})")


def listar_pestanas(context) -> None:
    print(f"  Pestañas abiertas: {len(context.pages)}")
    for i, p in enumerate(context.pages):
        print(f"    [{i}] {p.url}")


def volcar_elementos(page, out: Path) -> dict:
    data = {
        "url": page.url,
        "ng_select": [],
        "inputs": [],
        "buttons": [],
        "labels": [],
        "text_visible": [],
    }

    try:
        for i, el in enumerate(page.locator("ng-select").all()):
            try:
                data["ng_select"].append({
                    "nth": i,
                    "class": el.get_attribute("class") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "aria_label": el.get_attribute("aria-label") or "",
                    "text": (el.text_content() or "").strip()[:120],
                })
            except Exception:
                pass
    except Exception:
        pass

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
                    "formcontrolname": el.get_attribute("formcontrolname") or "",
                })
            except Exception:
                pass
    except Exception:
        pass

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

    try:
        for sel in ["label", "mat-label", ".ng-placeholder", "span.label",
                    ".form-label", "[class*='label']"]:
            for el in page.locator(sel).all():
                try:
                    t = (el.text_content() or "").strip()
                    if t and len(t) < 80 and t not in data["labels"]:
                        data["labels"].append(t)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        texts = page.evaluate("""() => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null, false
            );
            const result = [];
            let node;
            while ((node = walker.nextNode()) && result.length < 50) {
                const t = node.textContent.trim();
                if (t.length > 2 && t.length < 150) result.push(t);
            }
            return result;
        }""")
        data["text_visible"] = texts
    except Exception:
        pass

    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "elementos_formulario.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [JSON] {json_path.name}")
    return data


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
    perfil_info("INICIO")

    with sync_playwright() as p:
        context = None
        canal_usado = None
        for channel in ("msedge", "chrome", None):
            try:
                kwargs = dict(
                    user_data_dir=str(PROFILE_DIR),
                    headless=False,
                    slow_mo=400,
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

        # Usar primera página existente (tiene las cookies del perfil)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)

        # ── PASO 1: ir al HUB ────────────────────────────────────────
        log("\n[PASO 1] Abriendo hub my.europoolsystem.com...")
        page.goto(HUB_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)
        log(f"  URL: {page.url}")
        listar_pestanas(context)
        guardar(page, "paso1_hub", OUT_DIR)

        # ── PASO 2: login manual si hace falta ───────────────────────
        hub_logueado = False
        try:
            hub_logueado = (
                page.locator("text=MY EPS").count() > 0
                or page.locator("text=Log out").count() > 0
            )
        except Exception:
            pass

        if not hub_logueado:
            log("")
            log("*" * 60)
            log("  NO hay sesión en el hub.")
            log("")
            log("  En la ventana del navegador:")
            log("    1. Haz click en 'Log in'")
            log("    2. Elige tu cuenta y autentica con PIN / Windows Hello")
            log("    3. Cuando veas 'YOUR PORTALS' con el tile MY EPS, PARA")
            log("*" * 60)
            input("\n  Pulsa ENTER cuando veas el tile MY EPS...")
            page.wait_for_timeout(2_000)
            log(f"  URL tras login: {page.url}")
            guardar(page, "paso2_tras_login", OUT_DIR)
        else:
            log("  Sesión activa en el hub.")

        perfil_info("TRAS LOGIN")

        # ── PASO 3: MY EPS → webportal (misma pestaña, confirmado) ──
        log("\n[PASO 3] Haciendo click en MY EPS...")
        portal_page = None

        # Intentar automáticamente via JS click (bypassa todos los checks de Playwright)
        try:
            tile = page.locator("text=MY EPS").first
            tile.wait_for(state="attached", timeout=10_000)
            # JS click: bypassa visibilidad, scroll y estabilidad
            tile.evaluate("el => (el.closest('a,[role=button],[tabindex],button') || el.parentElement || el).click()")
            page.wait_for_url("**/webportal.europoolsystem.com/**", timeout=20_000)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2_000)
            log(f"  Click automático OK. URL: {page.url}")
            portal_page = page
        except Exception as e:
            log(f"  Click automático falló: {e}")

        # Fallback manual
        if portal_page is None or "webportal.europoolsystem.com" not in portal_page.url:
            log("")
            log("*" * 60)
            log("  PASO 3 — ACCION MANUAL:")
            log("  En el navegador, haz CLICK en el tile 'MY EPS'")
            log("  Espera a que cargue (verás PEDIDOS / MOVIMIENTOS)")
            log("*" * 60)
            input("\n  Pulsa ENTER cuando el webportal haya cargado...")
            page.wait_for_timeout(2_000)
            log(f"\n  Pestañas abiertas: {len(context.pages)}")
            listar_pestanas(context)
            for pg in context.pages:
                if "webportal.europoolsystem.com" in pg.url:
                    portal_page = pg
                    break
            if portal_page is None:
                portal_page = page

        guardar(portal_page, "paso3_webportal", OUT_DIR)

        # ── PASO 3.5: manejar página de login del webportal ──────────
        if "webportal.europoolsystem.com" in portal_page.url:
            try:
                login_btns = portal_page.locator("a:has-text('Log in'), button:has-text('Log in')")
                cnt = login_btns.count()
                log(f"  Botones 'Log in' en página: {cnt}")

                if cnt > 0:
                    log("\n[PASO 3.5] Obteniendo URL OAuth del enlace 'Log in'...")

                    # Esperar a que Angular asigne el href dinámicamente
                    try:
                        portal_page.wait_for_function("""() => {
                            const a = Array.from(document.querySelectorAll('a'))
                                .find(el => el.textContent.trim() === 'Log in' && el.href && el.href.length > 10);
                            return !!a;
                        }""", timeout=10_000)
                    except Exception:
                        pass

                    # Volcar info del enlace para diagnóstico
                    info = portal_page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('a, button'))
                            .filter(el => el.textContent.trim() === 'Log in')
                            .map(el => ({ tag: el.tagName, href: el.href || '', cls: el.className.substring(0,60) }));
                    }""")
                    log(f"  Info botones Log in: {info}")
                    guardar(portal_page, "paso35_pre_login", OUT_DIR)

                    # Extraer href del enlace (Angular lo rellena con URL OAuth de Microsoft)
                    oauth_url = portal_page.evaluate("""() => {
                        const link = Array.from(document.querySelectorAll('a'))
                            .find(el => el.textContent.trim() === 'Log in' && el.href);
                        return link ? link.href : null;
                    }""")
                    log(f"  href 'Log in': {(oauth_url or 'ninguno')[:120]}")

                    if oauth_url and "microsoftonline" in oauth_url:
                        log("  Navegando directamente a Microsoft OAuth...")
                        portal_page.goto(oauth_url)
                    else:
                        log("  Sin href directo a Microsoft. Haciendo click...")
                        login_btns.first.click()

                    # Esperar Microsoft
                    try:
                        portal_page.wait_for_url("**/login.microsoftonline.com/**", timeout=15_000)
                        portal_page.wait_for_load_state("domcontentloaded")
                        portal_page.wait_for_timeout(1_000)
                        log(f"  Microsoft cargado: {portal_page.url[:100]}")
                        guardar(portal_page, "paso35_microsoft", OUT_DIR)

                        # Seleccionar cuenta — múltiples fallbacks
                        cuenta_ok = False
                        for sel in [
                            f"[aria-label*='0001006572']",
                            f"[aria-label*='{EUROPOOL_USER}']",
                            f"div[role='option']:has-text('0001006572')",
                            "div[role='option']:visible",
                            "div.account-button:visible",
                            "[tabindex='0'][role='option']:visible",
                        ]:
                            try:
                                el = portal_page.locator(sel).first
                                if el.is_visible(timeout=3_000):
                                    log(f"  Cuenta: {sel}")
                                    el.click()
                                    portal_page.wait_for_load_state("domcontentloaded")
                                    portal_page.wait_for_timeout(3_000)
                                    log(f"  URL: {portal_page.url[:100]}")
                                    guardar(portal_page, "paso35_tras_cuenta", OUT_DIR)
                                    cuenta_ok = True
                                    break
                            except Exception:
                                continue

                        if not cuenta_ok:
                            log("  Cuenta no seleccionada automáticamente.")
                            guardar(portal_page, "paso35_sin_cuenta", OUT_DIR)
                            input("\n  Selecciona la cuenta Microsoft y pulsa ENTER...")
                            portal_page.wait_for_timeout(2_000)

                    except Exception as e:
                        log(f"  No redirigió a Microsoft: {e}")
                        log(f"  URL: {portal_page.url[:100]}")
                        guardar(portal_page, "paso35_no_ms", OUT_DIR)
                        input("\n  Autentícate manualmente y pulsa ENTER...")
                        portal_page.wait_for_timeout(2_000)
            except Exception as e:
                log(f"  PASO 3.5 falló: {e}")

        # ── PASO 4: formulario flows/new ─────────────────────────────
        log("\n[PASO 4] Navegando al formulario flows/new...")
        portal_page.goto(FLOWS_NEW_URL)
        portal_page.wait_for_load_state("domcontentloaded")
        portal_page.wait_for_timeout(4_000)
        log(f"  URL: {portal_page.url}")
        guardar(portal_page, "paso4_formulario_goto", OUT_DIR)

        # Cerrar banner de cookies si aparece
        try:
            btn = portal_page.locator(
                "button:has-text('Got it'), button:has-text('Aceptar'), button:has-text('Accept')"
            )
            if btn.first.is_visible(timeout=3_000):
                btn.first.click()
                portal_page.wait_for_timeout(800)
                log("  Cookie banner cerrado.")
        except Exception:
            pass

        # Esperar a que cargue el formulario
        log("  Esperando contenido del formulario (hasta 30s)...")
        encontrado = False
        for selector in ["text=ENCABEZAMIENTO", "ng-select", "mat-select", "form", "input"]:
            try:
                portal_page.wait_for_selector(selector, timeout=8_000)
                log(f"  Formulario detectado: {selector}")
                encontrado = True
                break
            except Exception:
                pass

        if not encontrado:
            log("  AVISO: no se detectó formulario.")

        portal_page.wait_for_timeout(2_000)
        guardar(portal_page, "paso4b_formulario_cargado", OUT_DIR)

        # ── PASO 5: volcar todos los elementos ───────────────────────
        log("\n[PASO 5] Extrayendo elementos del formulario...")
        datos = volcar_elementos(portal_page, OUT_DIR)

        log(f"\n  ng-select  : {len(datos['ng_select'])}")
        for s in datos["ng_select"]:
            log(f"    [{s['nth']}] placeholder='{s['placeholder']}' | aria='{s['aria_label']}' | texto='{s['text']}'")

        log(f"\n  inputs     : {len(datos['inputs'])}")
        for inp in datos["inputs"]:
            log(f"    [{inp['nth']}] type={inp['type']} name='{inp['name']}' placeholder='{inp['placeholder']}' id='{inp['id']}' fcn='{inp['formcontrolname']}'")

        log(f"\n  botones    : {len(datos['buttons'])}")
        for b in datos["buttons"]:
            log(f"    [{b['nth']}] '{b['text']}'")

        log(f"\n  labels     : {datos['labels']}")
        log(f"\n  texto (15) : {datos['text_visible'][:15]}")

        # ── PASO 6: screenshot final ─────────────────────────────────
        log("\n[PASO 6] Screenshot final...")
        guardar(portal_page, "paso6_final", OUT_DIR)

        # ── Guardar log ──────────────────────────────────────────────
        log_path = OUT_DIR / "log.txt"
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

        perfil_info("ANTES DE CERRAR")

        log("")
        log("=" * 60)
        log("  DIAGNOSTICO COMPLETADO")
        log(f"  Archivos en: {OUT_DIR}")
        log("  Comparte esa carpeta (o un zip).")
        log("=" * 60)

        input("\nPulsa ENTER para cerrar el navegador...")
        context.close()

    perfil_info("TRAS CERRAR")


if __name__ == "__main__":
    main()

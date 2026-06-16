"""
ifco_diagnostico.py — Explora el portal MyIFCO y vuelca el formulario.

Uso:
    python ifco_diagnostico.py

Guarda screenshots + HTML + JSON en la carpeta  diagnostico_ifco/
"""

import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── Configuración ──────────────────────────────────────────────────────────
SSO_URL    = "https://sso.ifco-online.com/login"
PORTAL_URL = "https://www.ifco-online.com/myifco-core-fe"

_ROOT       = Path(__file__).resolve().parent
PROFILE_DIR = _ROOT / "output" / "ifco_profile"
OUT_DIR     = _ROOT / "diagnostico_ifco"

# ── Credenciales (leer del .env si existen, si no pedir) ──────────────────
try:
    from config.settings import settings
    IFCO_NUMBER   = settings.ifco_number
    IFCO_USER     = settings.ifco_user
    IFCO_PASSWORD = settings.ifco_password
except Exception:
    IFCO_NUMBER = IFCO_USER = IFCO_PASSWORD = ""


# ── Helpers ────────────────────────────────────────────────────────────────

def guardar(page, nombre: str, out: Path) -> None:
    ts = datetime.now().strftime("%H%M%S")
    slug = f"{ts}_{nombre}"
    try:
        page.screenshot(path=str(out / f"{slug}.png"), full_page=True)
        print(f"  [IMG]  {slug}.png")
    except Exception as e:
        print(f"  [IMG]  ERROR: {e}")
    try:
        (out / f"{slug}.html").write_text(page.content(), encoding="utf-8")
        print(f"  [HTML] {slug}.html")
    except Exception as e:
        print(f"  [HTML] ERROR: {e}")


def volcar_elementos(page, out: Path, nombre: str) -> dict:
    data = {"url": page.url, "inputs": [], "buttons": [], "selects": [],
            "labels": [], "links": [], "text_visible": []}

    for sel, key in [
        ("input:visible", "inputs"),
        ("select:visible", "selects"),
    ]:
        try:
            for i, el in enumerate(page.locator(sel).all()[:20]):
                try:
                    data[key].append({
                        "nth": i,
                        "type": el.get_attribute("type") or "",
                        "name": el.get_attribute("name") or "",
                        "id": el.get_attribute("id") or "",
                        "placeholder": el.get_attribute("placeholder") or "",
                        "value": (el.input_value() or "")[:50],
                    })
                except Exception:
                    pass
        except Exception:
            pass

    try:
        for i, el in enumerate(page.locator("button:visible").all()[:20]):
            try:
                t = (el.text_content() or "").strip()[:80]
                if t:
                    data["buttons"].append({"nth": i, "text": t,
                                            "type": el.get_attribute("type") or ""})
            except Exception:
                pass
    except Exception:
        pass

    try:
        for sel in ["label", "mat-label", ".label", "span[class*='label']",
                    "div[class*='label']", "p", "h1", "h2", "h3"]:
            for el in page.locator(sel).all()[:30]:
                try:
                    t = (el.text_content() or "").strip()
                    if 2 < len(t) < 100 and t not in data["labels"]:
                        data["labels"].append(t)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        for el in page.locator("a:visible").all()[:20]:
            try:
                t = (el.text_content() or "").strip()
                h = el.get_attribute("href") or ""
                if t:
                    data["links"].append({"text": t, "href": h[:80]})
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

    path = out / f"{nombre}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [JSON] {path.name}")
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
    log("  DIAGNOSTICO IFCO")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    log(f"  Perfil: {PROFILE_DIR}")
    log(f"  Salida: {OUT_DIR}")
    log("")

    with sync_playwright() as p:
        context = None
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
                log(f"  Navegador: {channel or 'chromium'}")
                break
            except Exception as e:
                log(f"  {channel or 'chromium'} no disponible: {e}")

        if context is None:
            log("ERROR: no hay navegador.")
            return

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(30_000)

        # ── PASO 1: portal ───────────────────────────────────────────
        log("\n[PASO 1] Abriendo portal IFCO...")
        page.goto(PORTAL_URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3_000)
        log(f"  URL: {page.url}")
        guardar(page, "paso1_portal", OUT_DIR)

        # ── PASO 2: login si hace falta ──────────────────────────────
        # La app React carga en la misma URL con o sin sesión; detectar
        # por presencia del botón de login, no por URL
        necesita_login = (
            "sso.ifco-online.com" in page.url
            or page.locator("button:has-text('INICIAR SESIÓN')").count() > 0
            or page.locator("text=Clearing").count() == 0
        )
        if necesita_login:
            log("\n[PASO 2] Pantalla de login detectada. Rellenando...")
            guardar(page, "paso2_login_form", OUT_DIR)

            num   = IFCO_NUMBER   or input("  IFCO-N°: ")
            user  = IFCO_USER     or input("  Usuario: ")
            passw = IFCO_PASSWORD or input("  Contraseña: ")

            # IFCO-N°
            for sel in ["input[name='ifcoNumber']", "input[id='ifcoNumber']",
                        "input[placeholder*='612']", "input:nth-of-type(1)"]:
                try:
                    f = page.locator(sel).first
                    if f.is_visible(timeout=2_000):
                        f.fill(num)
                        log(f"  IFCO-N° rellenado con: {sel}")
                        break
                except Exception:
                    pass
            else:
                try:
                    page.get_by_label("IFCO-N", exact=False).first.fill(num)
                except Exception:
                    log("  AVISO: no se pudo rellenar IFCO-N°")

            # Usuario
            for sel in ["input[name='username']", "input[id='username']",
                        "input[placeholder*='sno']"]:
                try:
                    f = page.locator(sel).first
                    if f.is_visible(timeout=2_000):
                        f.fill(user)
                        log(f"  Usuario rellenado con: {sel}")
                        break
                except Exception:
                    pass
            else:
                try:
                    page.get_by_label("Identificación", exact=False).first.fill(user)
                except Exception:
                    log("  AVISO: no se pudo rellenar usuario")

            # Contraseña
            try:
                page.locator("input[type='password']").first.fill(passw)
            except Exception:
                log("  AVISO: no se pudo rellenar contraseña")

            guardar(page, "paso2b_login_relleno", OUT_DIR)

            # Submit
            try:
                page.locator("button:has-text('INICIAR SESIÓN'), button[type='submit']").first.click()
            except Exception:
                log("  AVISO: no se pudo hacer click en submit")

            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(4_000)
            log(f"  URL tras login: {page.url}")
            guardar(page, "paso2c_tras_login", OUT_DIR)
        else:
            log("\n[PASO 2] Sesión activa, no hace falta login.")

        # ── PASO 3: explorar portal ──────────────────────────────────
        log(f"\n[PASO 3] Portal cargado. URL: {page.url}")
        log("  Extrayendo elementos de la página principal...")
        datos = volcar_elementos(page, OUT_DIR, "portal_principal")
        log(f"  inputs: {len(datos['inputs'])}  botones: {len(datos['buttons'])}")
        log(f"  links: {[l['text'] for l in datos['links'][:10]]}")
        log(f"  texto: {datos['text_visible'][:10]}")

        # ── PASO 4: buscar formulario de declaración ─────────────────
        log("\n[PASO 4] Buscando formulario de declaración...")
        log("  Mira la pantalla. ¿Hay un botón para crear nueva declaración?")
        log("  Menús posibles: 'Return', 'Delivery', 'Movements', 'Nueva declaración'...")
        log("")
        log("  Navega al formulario de declaración manualmente si es necesario.")
        input("  Pulsa ENTER cuando estés en el formulario de declaración...")
        page.wait_for_timeout(2_000)

        log(f"  URL formulario: {page.url}")
        guardar(page, "paso4_formulario", OUT_DIR)
        datos2 = volcar_elementos(page, OUT_DIR, "formulario_declaracion")

        log(f"\n  inputs  : {len(datos2['inputs'])}")
        for inp in datos2["inputs"]:
            log(f"    [{inp['nth']}] type={inp['type']} name='{inp['name']}' id='{inp['id']}' placeholder='{inp['placeholder']}'")

        log(f"\n  selects : {len(datos2['selects'])}")
        log(f"\n  botones : {len(datos2['buttons'])}")
        for b in datos2["buttons"]:
            log(f"    [{b['nth']}] '{b['text']}'")

        log(f"\n  labels  : {datos2['labels']}")
        log(f"\n  texto   : {datos2['text_visible'][:15]}")

        # ── Guardar log ──────────────────────────────────────────────
        (OUT_DIR / "log.txt").write_text("\n".join(log_lines), encoding="utf-8")
        log("")
        log("=" * 60)
        log(f"  DIAGNOSTICO COMPLETADO. Archivos en: {OUT_DIR}")
        log("=" * 60)

        input("\nPulsa ENTER para cerrar...")
        context.close()


if __name__ == "__main__":
    main()

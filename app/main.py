# app/main.py

# --- Fix Windows: Playwright necesita un event loop que soporte subprocess ---
import sys, asyncio
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, field_validator
from typing import Any, Dict
import base64, time, os, re

# Playwright (API síncrona para mantener el ejemplo simple)
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Parser HTML (solo para obtener el texto lineal)
from bs4 import BeautifulSoup


# ------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------

SOI_URL = os.getenv(
    "SOI_URL",
    "https://servicio.nuevosoi.com.co/soi/pagoPlanillaPSEHomeComercial.do"
)

app = FastAPI(
    title="SOI Planilla Proxy",
    description="Wrapper legal que envía el formulario público de SOI y parsea el resultado.",
    version="1.2.0",
)


# ------------------------------------------------------------------------------
# Modelos
# ------------------------------------------------------------------------------

class ConsultaRequest(BaseModel):
    correo: EmailStr
    numero_planilla: str

    @field_validator("numero_planilla")
    @classmethod
    def only_digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("numero_planilla debe contener solo dígitos")
        if len(v) > 20:
            raise ValueError("numero_planilla demasiado largo (máx 20)")
        return v


# ------------------------------------------------------------------------------
# Utils
# ------------------------------------------------------------------------------

def b64_png(page) -> str:
    png = page.screenshot(full_page=True)
    return base64.b64encode(png).decode("utf-8")

def first_kb(html: str, kb: int = 8) -> str:
    return html[: kb * 1024]

def has_search_result(html: str) -> bool:
    low = html.lower()
    needles = [
        "resultado de la búsqueda",
        "resultado de la busqueda",
        "valor a pagar",
        "día de pago efectivo",
        "dia de pago efectivo",
        "información de la planilla",
        "informacion de la planilla",
    ]
    return any(n in low for n in needles)

def _text_clean(s: str) -> str:
    # Normaliza NBSP y espacios
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_result_html(html: str) -> Dict[str, Any]:
    """
    Parser robusto por regex: convierte el HTML a texto lineal y extrae
    campos por patrones cercanos a las etiquetas visibles.
    """
    soup = BeautifulSoup(html, "html.parser")
    full_text = " ".join(list(soup.stripped_strings))
    full_text = _text_clean(full_text)

    out: Dict[str, Any] = {}

    # Razón social (entre esa etiqueta y la siguiente conocida)
    m = re.search(
        r"(Raz[oó]n Social\s*/\s*Nombres y Apellidos del Aportante:\s*)(.*?)(?:\s+Periodo Liquidaci[oó]n Salud:)",
        full_text, flags=re.IGNORECASE
    )
    if m:
        out["razon_social"] = _text_clean(m.group(2))

    # Periodo Liquidación Salud: YYYY-MM
    m = re.search(r"Periodo Liquidaci[oó]n Salud:\s*([0-9]{4}-[0-9]{2})", full_text, flags=re.IGNORECASE)
    if m:
        out["periodo_salud"] = m.group(1)

    # Tipo de Planilla: valor corto (letra/número)
    m = re.search(r"Tipo de Planilla:\s*([A-Za-z0-9]+)", full_text, flags=re.IGNORECASE)
    if m:
        out["tipo_planilla"] = m.group(1)

    # Días de Mora: número
    m = re.search(r"D[ií]as de Mora:\s*([0-9]+)", full_text, flags=re.IGNORECASE)
    if m:
        out["dias_mora"] = m.group(1)

    # Valor Mora: $ X
    m = re.search(r"Valor Mora:\s*\$?\s*([\d\.\,]+)", full_text, flags=re.IGNORECASE)
    if m:
        out["valor_mora"] = f"$ {m.group(1)}"

    # Día de Pago Efectivo: YYYY-MM-DD
    m = re.search(r"D[ií]a de Pago Efectivo:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", full_text, flags=re.IGNORECASE)
    if m:
        out["dia_pago_efectivo"] = m.group(1)

    # Valor a Pagar: $ X
    m = re.search(r"Valor a Pagar:\s*\$?\s*([\d\.\,]+)", full_text, flags=re.IGNORECASE)
    if m:
        out["valor_a_pagar"] = f"$ {m.group(1)}"

    return out


# ------------------------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------------------------

@app.post("/planillas/consultar")
def consultar(req: ConsultaRequest):
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ])
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(SOI_URL, wait_until="domcontentloaded", timeout=30000)

            # Completar campos visibles
            page.fill("#correoElectronico", req.correo)
            page.fill("#numeroPlanilla", req.numero_planilla)

            # Click en "Buscar"
            clicked = False
            for sel in ["#btnBuscar", "input[name='buscarPlanilla']", "input[value='Buscar']"]:
                try:
                    page.click(sel, timeout=2000)
                    clicked = True
                    break
                except PWTimeout:
                    continue
            if not clicked:
                # Fallback: submit del form
                try:
                    page.evaluate("document.getElementById('formPagarPSEPago').submit();")
                except Exception:
                    pass

            # Espera de red/render
            page.wait_for_load_state("networkidle", timeout=20000)
            html = page.content().replace("&nbsp;", " ")

            # Detecta captcha/intersticial SOLO si no vemos un resultado claro
            low = html.lower()
            seen_captcha = ("g-recaptcha" in low or "recaptcha" in low or "are you a robot" in low or "captcha" in low)
            if seen_captcha and not has_search_result(html):
                return JSONResponse(
                    status_code=200,
                    content={
                        "ok": False,
                        "error": "captcha_or_interstitial",
                        "screenshot_png": b64_png(page),
                        "html_snippet": first_kb(html),
                        "meta": {"elapsed_ms": int((time.time() - t0) * 1000)},
                    },
                )

            # Parseo de campos
            parsed = parse_result_html(html)

            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "data": parsed,
                    "meta": {"elapsed_ms": int((time.time() - t0) * 1000)},
                },
            )

        except PWTimeout as e:
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "error": "timeout",
                    "detail": str(e),
                    "screenshot_png": b64_png(page),
                    "meta": {"elapsed_ms": int((time.time() - t0) * 1000)},
                },
            )
        except Exception as e:
            return JSONResponse(
                status_code=200,
                content={
                    "ok": False,
                    "error": "unexpected_error",
                    "detail": str(e),
                    "meta": {"elapsed_ms": int((time.time() - t0) * 1000)},
                },
            )
        finally:
            context.close()
            browser.close()

from __future__ import annotations
import os, re, sys, time, asyncio, unicodedata
from typing import Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore
    except Exception:
        pass

SOI_URL = os.getenv("SOI_URL", "https://servicio.nuevosoi.com.co/soi/pagoPlanillaPSEHomeComercial.do")
CORS_ALLOWED = os.getenv("CORS_ALLOWED", "")
ALLOW_ORIGINS = [o.strip() for o in CORS_ALLOWED.split(",") if o.strip()] if CORS_ALLOWED else ["*"]

app = FastAPI(title="SOI Planilla Proxy", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=ALLOW_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ConsultaRequest(BaseModel):
    correo: EmailStr
    numero_planilla: str

def _strip_accents(t:str)->str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch))

def _clean(t:str)->str:
    return re.sub(r"\s+"," ",t).strip()

def parse_result_html(html:str)->Dict[str,Any]:
    s = BeautifulSoup(html, "html.parser")
    txt = _clean(_strip_accents(s.get_text(separator=" ", strip=True)).lower())
    labels = {
        "razon_social":"razon social / nombres y apellidos del aportante:",
        "periodo_salud":"periodo liquidacion salud:",
        "tipo_planilla":"tipo de planilla:",
        "dias_mora":"dias de mora:",
        "valor_mora":"valor mora:",
        "dia_pago_efectivo":"dia de pago efectivo:",
        "valor_a_pagar":"valor a pagar:",
    }
    order=[labels[k] for k in ["razon_social","periodo_salud","tipo_planilla","dias_mora","valor_mora","dia_pago_efectivo","valor_a_pagar"]]
    def between(lbl, after):
        try: start=txt.index(lbl)+len(lbl)
        except ValueError: return None
        ends=[txt.find(a,start) for a in after if txt.find(a,start)!=-1]
        end=min(ends) if ends else len(txt)
        return _clean(txt[start:end])
    out={}
    keys=["razon_social","periodo_salud","tipo_planilla","dias_mora","valor_mora","dia_pago_efectivo","valor_a_pagar"]
    for i,k in enumerate(keys):
        v = between(labels[k], order[i+1:]) or ""
        if k in ("valor_mora","valor_a_pagar"):
            m=re.search(r"\$?\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?", v); v=m.group(0) if m else v
        if k=="dias_mora":
            m=re.search(r"\b\d+\b", v); v=m.group(0) if m else v
        out[k]= v or None
    if not out.get("razon_social") and not out.get("valor_a_pagar"):
        raise ValueError("No se encontró resultado")
    return out

def consultar_soi(correo:str, numero_planilla:str)->Dict[str,Any]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width":1366,"height":900}, locale="es-CO")
        page = ctx.new_page()
        page.goto(SOI_URL, wait_until="domcontentloaded", timeout=60000)
        page.fill("#correoElectronico", correo)
        page.fill("#numeroPlanilla", numero_planilla)
        page.click("input[name='buscarPlanilla']")
        try: page.wait_for_load_state("networkidle", timeout=25000)
        except Exception: pass
        html = page.content()
        ctx.close(); browser.close()
    return parse_result_html(html)

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/planillas/consultar")
def consultar(req:ConsultaRequest):
    t=time.perf_counter()
    try:
        data=consultar_soi(req.correo, req.numero_planilla)
        return JSONResponse({"ok":True,"data":data,"meta":{"elapsed_ms":int((time.perf_counter()-t)*1000)}})
    except ValueError as ve:
        return JSONResponse({"ok":False,"error":str(ve),"meta":{"elapsed_ms":int((time.perf_counter()-t)*1000)}}, status_code=422)
    except Exception as e:
        return JSONResponse({"ok":False,"error":f"unexpected_error: {e.__class__.__name__}","meta":{"elapsed_ms":int((time.perf_counter()-t)*1000)}}, status_code=500)

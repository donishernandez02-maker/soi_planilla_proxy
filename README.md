
# SOI Planilla Proxy (Legal, non-bypass wrapper)

This service exposes a **single endpoint** that automates the *public search form* at
`https://servicio.nuevosoi.com.co/soi/pagoPlanillaPSEHomeComercial.do` using **Playwright**.
It is intended for legitimate, rate-limited, and ToS-compliant use by the planilla owner
(or with their consent). It does **not** bypass reCAPTCHA, logins, or CSRF; it simply
loads the page, fills the visible form fields, and parses the visible result.

> ⚖️ You are responsible for complying with all applicable laws, site Terms of Use, and robots.txt.
> This code **does not** attempt to bypass reCAPTCHA or access private endpoints.

## Quickstart (local)

1) Python 3.10+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload --port 8080
```

Test:
```bash
curl -X POST http://127.0.0.1:8080/planillas/consultar   -H "Content-Type: application/json"   -d '{"correo":"alguien@example.com","numero_planilla":"123456"}'
```

## Docker

```bash
docker build -t soi-planilla-proxy .
docker run --rm -p 8080:8080 soi-planilla-proxy
```

## Endpoint

- **POST** `/planillas/consultar`
- Body:
```json
{
  "correo": "correo@dominio.com",
  "numero_planilla": "123456"
}
```
- Response (example):
```json
{
  "ok": true,
  "data": {
    "estado": "Encontrada",
    "valor": 125000,
    "fecha_limite": "2025-09-30",
    "detalle": "…"
  },
  "meta": {
    "elapsed_ms": 2145
  }
}
```

If a captcha interstitial or unexpected layout appears, the service returns:
```json
{
  "ok": false,
  "error": "captcha_or_interstitial",
  "screenshot_png": "<base64>",
  "html_snippet": "<first_kb_of_html>"
}
```

## Notes

- We intentionally do **not** click “Pagar” nor advance to PSE. Only “Buscar” is used.
- Selectors are conservative; you may need to tweak them if the site layout changes.
- Respect rate limits. Consider adding a queue, per-IP throttling, and request logging.

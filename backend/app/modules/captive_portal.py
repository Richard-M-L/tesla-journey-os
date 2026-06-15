"""
Captive Portal — intercepts OS detection URLs and serves a landing page.

When phones/laptops connect to the Pi's WiFi hotspot, the OS probes
known URLs to detect if a captive portal is present. This module
intercepts those probes and returns a branded landing page.

Detection URLs intercepted:
  - Apple: /hotspot-detect.html, /library/test/success.html → "Success" (skip portal)
  - Android: /generate_204 → HTTP 204
  - Windows: /connecttest.txt, /ncsi.txt → "Microsoft Connect Test"
  - Firefox: /success.txt → "success"
  - Everything else → redirect to TJOS home page

Adapted from TeslaUSB's captive_portal.py.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

router = APIRouter()


# ── HTML landing page ──

def _portal_html(ssid: str = "Tesla Journey OS") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tesla Journey OS</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
    min-height: 100vh; display: flex; align-items: center; justify-content: center;
    color: #fff;
  }}
  .card {{
    background: rgba(255,255,255,0.05); backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.1); border-radius: 20px;
    padding: 48px 40px; max-width: 420px; width: 90%; text-align: center;
    animation: slideUp 0.6s ease-out;
  }}
  @keyframes slideUp {{
    from {{ opacity: 0; transform: translateY(30px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  .logo {{ width: 64px; height: 64px; margin: 0 auto 20px;
    background: linear-gradient(135deg, #E82127, #ff4444); border-radius: 18px;
    display: flex; align-items: center; justify-content: center; font-size: 32px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
  .tagline {{ color: rgba(255,255,255,0.5); font-size: 13px; margin-bottom: 28px; }}
  .features {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 28px; text-align: left; }}
  .feature {{
    display: flex; align-items: center; gap: 8px; padding: 10px 12px;
    background: rgba(255,255,255,0.05); border-radius: 10px; font-size: 13px;
    color: rgba(255,255,255,0.7);
  }}
  .feature-icon {{ font-size: 18px; }}
  .btn {{
    display: inline-block; padding: 12px 32px; border-radius: 10px;
    background: linear-gradient(135deg, #E82127, #cc1a1f); color: #fff;
    text-decoration: none; font-weight: 600; font-size: 15px;
    transition: transform 0.2s, box-shadow 0.2s;
  }}
  .btn:hover {{ transform: scale(1.03); box-shadow: 0 4px 20px rgba(232,33,39,0.4); }}
  .footer {{ margin-top: 24px; font-size: 12px; color: rgba(255,255,255,0.3); }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">&#9889;</div>
  <h1>Tesla Journey OS</h1>
  <p class="tagline">Local-First Driving Behavior Platform</p>
  <div class="features">
    <div class="feature"><span class="feature-icon">&#128202;</span> Telemetry Analysis</div>
    <div class="feature"><span class="feature-icon">&#128663;</span> Trip Detection</div>
    <div class="feature"><span class="feature-icon">&#9888;</span> Event Alerts</div>
    <div class="feature"><span class="feature-icon">&#128264;</span> Lock Chimes</div>
  </div>
  <a href="/" class="btn">Open Dashboard</a>
  <p class="footer">Connected to {ssid}</p>
</div>
</body>
</html>"""


# ── Detection endpoint routes ──

@router.get("/hotspot-detect.html")
async def apple_hotspot():
    """Apple iOS/macOS captive portal detection."""
    return HTMLResponse("Success")

@router.get("/library/test/success.html")
async def apple_success():
    return HTMLResponse("Success")

@router.get("/generate_204")
async def android_204():
    """Android captive portal detection — expects HTTP 204."""
    return Response(status_code=204)

@router.get("/gen_204")
async def android_gen204():
    return Response(status_code=204)

@router.get("/connecttest.txt")
async def windows_connecttest():
    """Windows NCSI detection."""
    return PlainTextResponse("Microsoft Connect Test")

@router.get("/ncsi.txt")
async def windows_ncsi():
    return PlainTextResponse("Microsoft NCSI")

@router.get("/redirect")
async def windows_redirect():
    return RedirectResponse(url="/")

@router.get("/success.txt")
async def firefox_success():
    """Firefox captive portal detection."""
    return PlainTextResponse("success")

@router.get("/canonical.html")
async def generic_canonical(request: Request):
    """Generic captive portal landing page."""
    from app.modules.ap import get_portal_info
    info = get_portal_info()
    return HTMLResponse(_portal_html(info["ssid"]))

@router.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

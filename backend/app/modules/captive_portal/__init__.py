"""
Captive portal detection endpoints.

Apple and Android devices probe specific URLs to detect captive portals.
Responding correctly ensures the device shows the login/splash page
when connecting to the TJOS offline AP.
"""

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["captive-portal"])

# Apple captive portal detection endpoints
APPLE_PATHS = [
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/generate_204",
    "/redirect",
]

# Android / generic detection
ANDROID_PATHS = [
    "/connecttest.txt",
    "/gen_204",
    "/ncsi.txt",
    "/redirect",
]


@router.get("/hotspot-detect.html")
async def apple_hotspot_detect():
    return Response(content="Success", media_type="text/html")


@router.get("/generate_204")
async def generate_204():
    return Response(status_code=204)


@router.get("/connecttest.txt")
async def connecttest():
    return Response(content="OK", media_type="text/plain")


@router.get("/gen_204")
async def gen_204():
    return Response(status_code=204)


@router.get("/ncsi.txt")
async def ncsi():
    return Response(content="Microsoft NCSI", media_type="text/plain")

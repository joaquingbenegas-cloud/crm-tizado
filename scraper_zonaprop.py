"""
scraper_zonaprop.py
Scraper de propiedades en venta para Bella Vista / Muñiz / San Miguel.
Fuentes: ZonaProp, MercadoLibre Inmuebles, Argenprop (dueño directo).
Deduplica con alertas_vistas.json y sube al Google Sheet via Apps Script.

Uso:
    python3 scraper_zonaprop.py
"""

import json
import re
import time
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from curl_cffi import requests
from bs4 import BeautifulSoup

# ── Configuración ──────────────────────────────────────────────────────────────

SHEETS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzb7MYnH34TTOfs6Uy9ZBg3KM32p4_1m2e6ggHV1ZtVhNwGRjpkhNeTlg-5Yxw9D9AWOA/exec"
)
VISTAS_FILE = Path(__file__).parent / "alertas_vistas.json"

ZONAS_ZP = {
    "bella-vista-san-miguel":           "Bella Vista",
    "muniz-san-miguel":                 "Muñiz",
    "san-miguel-partido-de-san-miguel": "San Miguel",
}

TIPOLOGIAS_ZP = {
    "casas":               "Casa",
    "terrenos":            "Terreno/Lote",
    "departamentos":       "Departamento",
    "locales-comerciales": "Local/Oficina",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def cargar_vistas() -> set:
    if VISTAS_FILE.exists():
        try:
            return set(json.loads(VISTAS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def guardar_vistas(vistas: set):
    VISTAS_FILE.write_text(
        json.dumps(sorted(vistas), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_page(url: str, referer: str = "") -> Optional[BeautifulSoup]:
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    for intento in range(3):
        try:
            r = requests.get(url, headers=h, timeout=20, impersonate="chrome110")
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  ⚠ Error (intento {intento+1}): {e}")
            if intento < 2:
                time.sleep(3 + random.uniform(1, 3))
    return None


def hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════════════════════
# ZONAPROP
# ══════════════════════════════════════════════════════════════════════════════

def zp_extraer_state(soup: BeautifulSoup) -> Optional[dict]:
    tag = soup.find("script", {"id": "preloadedData"})
    if not tag or not tag.string:
        return None
    raw = tag.string.strip()
    assignments = re.findall(
        r'window\.(\w+)\s*=\s*(\{[\s\S]*?\})(?=\s*;\s*window\.|;\s*$)', raw
    )
    for name, val_str in assignments:
        if name == "__PRELOADED_STATE__":
            try:
                return json.loads(val_str)
            except Exception:
                return None
    return None


def zp_parsear_precio(p: dict) -> tuple:
    try:
        for op in p.get("priceOperationTypes", []):
            for pr in op.get("prices", []):
                if pr.get("amount"):
                    return float(pr["amount"]), pr.get("currency", "")
    except Exception:
        pass
    return None, ""


def zp_parsear_m2(p: dict) -> tuple:
    feats = p.get("mainFeatures", {}) or {}
    m2_cub = m2_ter = None
    for fid, feat in feats.items():
        try:
            val = float(re.sub(r"[^\d.]", "", str(feat.get("value", ""))))
        except Exception:
            continue
        if fid == "CFT101":
            m2_cub = val
        elif fid == "CFT100":
            m2_ter = val
    return m2_cub, m2_ter


def zp_parsear_publicador(p: dict) -> str:
    pub = p.get("publisher", {}) or {}
    if pub.get("publisherTypeId") == "1":
        return "Dueño directo"
    return pub.get("name", "").strip() or "Inmobiliaria"


CUTOFF_DIAS = 7

def zp_es_de_esta_semana(p: dict) -> bool:
    raw = p.get("modified_date") or ""
    if not raw:
        return True
    try:
        ts = datetime.fromisoformat(raw)
        ahora = datetime.now(timezone.utc).astimezone(ts.tzinfo)
        return (ahora - ts) <= timedelta(days=CUTOFF_DIAS)
    except Exception:
        return True

def zp_parsear_foto(p: dict) -> str:
    try:
        pics = (p.get("visiblePictures") or {}).get("pictures") or []
        if pics:
            return pics[0].get("url730x532") or pics[0].get("url360x266") or ""
    except Exception:
        pass
    return ""

def zp_parsear_postings(state: dict, tipologia: str, zona: str) -> list:
    postings = state.get("listStore", {}).get("listPostings", []) or []
    out = []
    for p in postings:
        try:
            if not zp_es_de_esta_semana(p):
                continue
            zp_id = "zp_" + str(p.get("postingId") or p.get("postingCode") or "")
            if not zp_id or zp_id == "zp_":
                continue
            precio, moneda = zp_parsear_precio(p)
            m2_cub, m2_ter = zp_parsear_m2(p)
            publicador = zp_parsear_publicador(p)
            loc = p.get("postingLocation") or {}
            addr = (loc.get("address") or {}).get("name", "Sin dirección")
            url_rel = p.get("url", "")
            url = ("https://www.zonaprop.com.ar" + url_rel) if url_rel.startswith("/") else url_rel
            base_m2 = m2_cub or m2_ter
            precio_m2 = round(precio / base_m2, 2) if precio and base_m2 else None
            out.append({
                "id": zp_id, "fuente": "ZonaProp", "tipologia": tipologia,
                "titulo": p.get("title", ""), "direccion": addr,
                "precio": precio, "moneda": moneda,
                "m2_cubiertos": m2_cub, "m2_terreno": m2_ter, "precio_m2": precio_m2,
                "quien_publica": publicador, "url": url, "zona": zona,
                "fecha": (p.get("modified_date") or hoy())[:10],
                "foto": zp_parsear_foto(p),
            })
        except Exception as e:
            print(f"  ⚠ ZP posting error: {e}")
    return out


def scrape_zonaprop(vistas: set) -> list:
    todas = []
    BASE = "https://www.zonaprop.com.ar"

    for tipo_slug, tipo_label in TIPOLOGIAS_ZP.items():
        for zona_slug, zona_label in ZONAS_ZP.items():
            url = f"{BASE}/{tipo_slug}-venta-{zona_slug}.html?orden=mas-recientes"
            print(f"\n  [ZP] {tipo_label} — {zona_label}")
            print(f"  GET {url}")
            soup = fetch_page(url, BASE + "/")
            if not soup:
                time.sleep(random.uniform(2, 4))
                continue
            state = zp_extraer_state(soup)
            if not state:
                print("  ⚠ No se encontró __PRELOADED_STATE__")
                time.sleep(random.uniform(2, 4))
                continue
            total = state.get("listStore", {}).get("totalPosting", "?")
            items = zp_parsear_postings(state, tipo_label, zona_label)
            nuevos = [x for x in items if x["id"] not in vistas]
            print(f"  → ZP total: {total} | página: {len(items)} | nuevos: {len(nuevos)}")
            todas.extend(nuevos)
            time.sleep(random.uniform(2, 4))

    return todas


# ══════════════════════════════════════════════════════════════════════════════
# ARGENPROP (dueño directo)
# Datos en atributos del <a class="card">:
#   idaviso, montonormalizado, idmoneda (2=USD, 1=ARS), href
# ══════════════════════════════════════════════════════════════════════════════

def scrape_argenprop(vistas: set) -> list:
    todas = []
    BASE = "https://www.argenprop.com"

    TIPOS_AP = {
        "casas":         "Casa",
        "terrenos":      "Terreno/Lote",
        "departamentos": "Departamento",
        "locales":       "Local/Oficina",
    }
    ZONAS_AP_URL = {
        "bella-vista": "Bella Vista",
        "muniz":       "Muñiz",
        "san-miguel":  "San Miguel",
    }

    for tipo_slug, tipo_label in TIPOS_AP.items():
        for zona_slug, zona_label in ZONAS_AP_URL.items():
            url = f"{BASE}/{tipo_slug}/venta/{zona_slug}?duenodirecto=true&orden=masnuevo"
            print(f"\n  [AP] {tipo_label} dueño directo — {zona_label}")
            print(f"  GET {url}")
            soup = fetch_page(url, BASE + "/")
            if not soup:
                time.sleep(random.uniform(2, 4))
                continue

            cards = soup.select("a.card[idaviso]")
            print(f"  → cards: {len(cards)}")

            for card in cards:
                try:
                    aviso_id = card.get("idaviso", "")
                    if not aviso_id:
                        continue
                    ap_id = "ap_" + aviso_id
                    if ap_id in vistas or any(x["id"] == ap_id for x in todas):
                        continue

                    href = card.get("href", "")
                    if href and not href.startswith("http"):
                        href = BASE + href

                    h2 = card.select_one("h2")
                    titulo = h2.get_text(strip=True) if h2 else tipo_label

                    addr_el = card.select_one("[class*=address], [class*=ubicacion]")
                    if not addr_el:
                        # La dirección suele ser el texto entre el precio y el título
                        addr_el = card.select_one("p")
                    addr = addr_el.get_text(strip=True) if addr_el else zona_label

                    monto_raw = card.get("montonormalizado", "")
                    precio = float(monto_raw) if monto_raw else None
                    moneda = "USD" if card.get("idmoneda") == "2" else "ARS"

                    # M² en los features de la card
                    m2_cub = m2_ter = None
                    for feat in card.select("[class*=feature], [class*=detail], li, span"):
                        txt = feat.get_text(strip=True).lower()
                        nums = re.findall(r"[\d]+", txt)
                        if not nums:
                            continue
                        val = float(nums[0])
                        if "cubierto" in txt:
                            m2_cub = val
                        elif "total" in txt or "terreno" in txt or "m²" in txt:
                            m2_ter = val

                    base_m2 = m2_cub or m2_ter
                    precio_m2 = round(precio / base_m2, 2) if precio and base_m2 else None

                    todas.append({
                        "id": ap_id, "fuente": "Argenprop", "tipologia": tipo_label,
                        "titulo": titulo, "direccion": addr,
                        "precio": precio, "moneda": moneda,
                        "m2_cubiertos": m2_cub, "m2_terreno": m2_ter, "precio_m2": precio_m2,
                        "quien_publica": "Dueño directo", "url": href, "zona": zona_label,
                        "fecha": hoy(),
                    })
                except Exception as e:
                    print(f"  ⚠ AP card error: {e}")

            print(f"  → nuevos: {len([x for x in todas if x['zona']==zona_label])}")
            time.sleep(random.uniform(2, 4))

    return todas


# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

def subir_a_sheets(alertas: list):
    try:
        r = requests.post(
            SHEETS_URL,
            data=json.dumps({"action": "saveAlertas", "alertas": alertas}),
            headers={"Content-Type": "application/json"},
            timeout=120,
            impersonate="chrome110",
            allow_redirects=True,
        )
        print(f"\nSheets → HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"\n⚠ Error subiendo a Sheets: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print(f"Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Fuente: ZonaProp")
    print("Zonas: Bella Vista · Muñiz · San Miguel")
    print("=" * 60)

    vistas = cargar_vistas()
    nuevas_vistas = set(vistas)

    print("\n── ZonaProp ─────────────────────────────────────────────")
    zp = scrape_zonaprop(vistas)
    for x in zp:
        nuevas_vistas.add(x["id"])

    todas = zp
    guardar_vistas(nuevas_vistas)

    print(f"\n{'=' * 60}")
    print(f"Total nuevas alertas: {len(todas)}")
    por_fuente = {}
    for a in todas:
        por_fuente.setdefault(a["fuente"], 0)
        por_fuente[a["fuente"]] += 1
    for fuente, n in por_fuente.items():
        print(f"  {fuente}: {n}")

    if not todas:
        print("Nada nuevo.")
        return

    print("\nSubiendo a Google Sheets...")
    subir_a_sheets(todas)

    debug = Path(__file__).parent / "alertas_debug.json"
    debug.write_text(json.dumps(todas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Debug → {debug}")


if __name__ == "__main__":
    main()

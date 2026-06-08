"""
scraper_zonaprop.py
Scraper de ZonaProp para alertas de propiedades nuevas (últimas 24hs).
Filtra duplicados con alertas_vistas.json y sube resultados al Google Sheet
via el Apps Script del proyecto.

Uso:
    python3 scraper_zonaprop.py

El Apps Script debe incluir el handler saveAlertas — ver comentario al final.
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
BASE_URL    = "https://www.zonaprop.com.ar"
CUTOFF_HORAS = 24

# slug ZonaProp → label legible
ZONAS = {
    "bella-vista-san-miguel":          "Bella Vista",
    "muniz-san-miguel":                "Muñiz",
    "san-miguel-partido-de-san-miguel": "San Miguel",
}

# prefijo URL → label tipología
TIPOLOGIAS = {
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
    "Referer": "https://www.zonaprop.com.ar/",
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


def fetch_page(url: str) -> Optional[BeautifulSoup]:
    for intento in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20, impersonate="chrome110")
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"  ⚠ Error (intento {intento+1}): {e}")
            if intento < 2:
                time.sleep(3 + random.uniform(1, 3))
    return None


def extraer_preloaded_state(soup: BeautifulSoup) -> Optional[dict]:
    """Extrae window.__PRELOADED_STATE__ del script id=preloadedData."""
    tag = soup.find("script", {"id": "preloadedData"})
    if not tag or not tag.string:
        return None
    raw = tag.string.strip()
    # Múltiples assignments: window.__X__ = {...}; window.__Y__ = {...};
    assignments = re.findall(
        r'window\.(\w+)\s*=\s*(\{[\s\S]*?\})(?=\s*;\s*window\.|;\s*$)', raw
    )
    for name, val_str in assignments:
        if name == "__PRELOADED_STATE__":
            try:
                return json.loads(val_str)
            except json.JSONDecodeError:
                return None
    return None


def parsear_precio(posting: dict) -> tuple:
    """Devuelve (monto_float, moneda_str)."""
    try:
        for op in posting.get("priceOperationTypes", []):
            if op.get("operationType", {}).get("operationTypeId") == "1":  # Venta
                for p in op.get("prices", []):
                    if p.get("amount"):
                        return float(p["amount"]), p.get("currency", "")
    except Exception:
        pass
    return None, ""


def parsear_m2(posting: dict) -> tuple:
    """Devuelve (m2_cubiertos, m2_terreno). mainFeatures es un dict keyed por featureId."""
    feats = posting.get("mainFeatures", {}) or {}
    m2_cub = None
    m2_ter = None
    try:
        for fid, feat in feats.items():
            val_raw = feat.get("value", "")
            try:
                val = float(re.sub(r"[^\d.]", "", str(val_raw)))
            except (ValueError, TypeError):
                continue
            if fid == "CFT101" or "cubierta" in feat.get("label", "").lower():
                m2_cub = val
            elif fid == "CFT100" or "total" in feat.get("label", "").lower():
                m2_ter = val
    except Exception:
        pass
    return m2_cub, m2_ter


def parsear_publicador(posting: dict) -> str:
    pub = posting.get("publisher", {}) or {}
    type_id = pub.get("publisherTypeId", "")
    name = pub.get("name", "").strip()
    # publisherTypeId "1" = particular/dueño directo, "2" = inmobiliaria
    if type_id == "1" or not name:
        return "Dueño directo"
    return name


def parsear_fecha(posting: dict) -> str:
    raw = posting.get("modified_date", "") or ""
    if raw:
        return raw[:10]  # "YYYY-MM-DD"
    return datetime.now().strftime("%Y-%m-%d")


def es_reciente(posting: dict) -> bool:
    raw = posting.get("modified_date", "") or ""
    if not raw:
        return True
    try:
        # Formato: "2026-06-08T14:50:17-0400"
        ts = datetime.fromisoformat(raw)
        ahora = datetime.now(timezone.utc).astimezone(ts.tzinfo)
        return (ahora - ts) <= timedelta(hours=CUTOFF_HORAS)
    except Exception:
        return True


def parsear_postings(state: dict, tipologia: str, zona_label: str) -> list:
    postings = state.get("listStore", {}).get("listPostings", []) or []
    resultados = []
    for p in postings:
        try:
            zp_id = str(p.get("postingId") or p.get("postingCode") or "")
            if not zp_id:
                continue

            precio, moneda = parsear_precio(p)
            m2_cub, m2_ter = parsear_m2(p)
            publicador = parsear_publicador(p)
            fecha = parsear_fecha(p)

            # Dirección
            loc = p.get("postingLocation") or {}
            addr = (loc.get("address") or {}).get("name", "Sin dirección")

            # URL
            url_rel = p.get("url", "")
            url = (BASE_URL + url_rel) if url_rel.startswith("/") else url_rel

            # Precio/m²
            precio_m2 = None
            base_m2 = m2_cub or m2_ter
            if precio and base_m2 and base_m2 > 0:
                precio_m2 = round(precio / base_m2, 2)

            resultados.append({
                "id":            zp_id,
                "tipologia":     tipologia,
                "titulo":        p.get("title", ""),
                "direccion":     addr,
                "precio":        precio,
                "moneda":        moneda,
                "m2_cubiertos":  m2_cub,
                "m2_terreno":    m2_ter,
                "precio_m2":     precio_m2,
                "quien_publica": publicador,
                "url":           url,
                "zona":          zona_label,
                "fecha":         fecha,
            })
        except Exception as e:
            print(f"  ⚠ Error parseando posting {p.get('postingId')}: {e}")
    return resultados


# ── Scraping ───────────────────────────────────────────────────────────────────

def scrape_url(url: str, tipologia: str, zona_slug: str) -> list:
    zona_label = ZONAS[zona_slug]
    print(f"  GET {url}")
    soup = fetch_page(url)
    if not soup:
        return []
    state = extraer_preloaded_state(soup)
    if not state:
        print(f"  ⚠ No se encontró __PRELOADED_STATE__")
        return []
    total = state.get("listStore", {}).get("totalPosting", "?")
    postings = parsear_postings(state, tipologia, zona_label)
    recientes = [p for p in postings if es_reciente(p)]
    print(f"  → total en ZP: {total} | en página: {len(postings)} | recientes: {len(recientes)}")
    return recientes


def scrape_todo() -> list:
    todas = []
    vistas = cargar_vistas()
    nuevas_vistas = set(vistas)

    # 1. Por tipología × zona
    for tipo_slug, tipo_label in TIPOLOGIAS.items():
        for zona_slug in ZONAS:
            url = f"{BASE_URL}/{tipo_slug}-venta-{zona_slug}.html?orden=mas-recientes"
            print(f"\n[{tipo_label} — {ZONAS[zona_slug]}]")
            for r in scrape_url(url, tipo_label, zona_slug):
                if r["id"] not in nuevas_vistas:
                    todas.append(r)
                    nuevas_vistas.add(r["id"])
            time.sleep(random.uniform(2.0, 4.0))

    # 2. Dueño directo × zona — ZonaProp no soporta publisherTypeId como query param.
    #    Scrapeamos propiedades generales y filtramos los particulares (typeId="1").
    for zona_slug in ZONAS:
        url = (
            f"{BASE_URL}/propiedades-venta-{zona_slug}.html"
            "?orden=mas-recientes"
        )
        print(f"\n[Dueño directo — {ZONAS[zona_slug]}]")
        soup = fetch_page(url)
        if not soup:
            time.sleep(random.uniform(2.0, 4.0))
            continue
        state = extraer_preloaded_state(soup)
        if not state:
            time.sleep(random.uniform(2.0, 4.0))
            continue
        postings_raw = state.get("listStore", {}).get("listPostings", []) or []
        # Solo particulares que aún no vimos
        for p in postings_raw:
            pub = p.get("publisher", {}) or {}
            if pub.get("publisherTypeId") != "1":
                continue
            zp_id = str(p.get("postingId") or p.get("postingCode") or "")
            if not zp_id or zp_id in nuevas_vistas:
                continue
            if not es_reciente(p):
                continue
            results = parsear_postings({"listStore": {"listPostings": [p]}}, "Dueño directo", ZONAS[zona_slug])
            for r in results:
                todas.append(r)
                nuevas_vistas.add(r["id"])
        print(f"  → dueños directos nuevos acumulados: {sum(1 for x in todas if x['tipologia']=='Dueño directo')}")
        time.sleep(random.uniform(2.0, 4.0))

    guardar_vistas(nuevas_vistas)
    return todas


# ── Upload a Google Sheets ─────────────────────────────────────────────────────

def subir_a_sheets(alertas: list):
    """
    POST al Apps Script con action='saveAlertas'.

    ══ AGREGAR AL APPS SCRIPT (doPost) ══════════════════════════════
    if (payload.action === 'saveAlertas') {
      const ss = SpreadsheetApp.openById('1Vx-VP8NdeOxZybm0Bcqq0idYiWQDNWmelAm0nU9FIXM');
      let sheet = ss.getSheetByName('Alertas');
      if (!sheet) {
        sheet = ss.insertSheet('Alertas');
        sheet.appendRow(['fecha','id','tipologia','direccion','precio','moneda',
                         'm2_cubiertos','m2_terreno','precio_m2','quien_publica','url','zona']);
      }
      (payload.alertas || []).forEach(a => {
        sheet.appendRow([
          a.fecha, a.id, a.tipologia, a.direccion,
          a.precio ?? '', a.moneda ?? '', a.m2_cubiertos ?? '',
          a.m2_terreno ?? '', a.precio_m2 ?? '',
          a.quien_publica, a.url, a.zona
        ]);
      });
      return ContentService
        .createTextOutput(JSON.stringify({ok: true, saved: (payload.alertas||[]).length}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    ═════════════════════════════════════════════════════════════════
    """
    try:
        r = requests.post(
            SHEETS_URL,
            data=json.dumps({"action": "saveAlertas", "alertas": alertas}),
            headers={"Content-Type": "application/json"},
            timeout=30,
            impersonate="chrome110",
            allow_redirects=True,
        )
        print(f"\nSheets → HTTP {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"\n⚠ Error subiendo a Sheets: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"Scraper ZonaProp — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Últimas {CUTOFF_HORAS}hs | zonas: {', '.join(ZONAS.values())}")
    print("=" * 60)

    alertas = scrape_todo()

    print(f"\n{'=' * 60}")
    print(f"Alertas nuevas: {len(alertas)}")

    if not alertas:
        print("Nada nuevo. Sin subir.")
        return

    por_tipo = {}
    for a in alertas:
        por_tipo.setdefault(a["tipologia"], []).append(a)
    for tipo, items in sorted(por_tipo.items()):
        print(f"  {tipo}: {len(items)}")

    print("\nSubiendo a Google Sheets...")
    subir_a_sheets(alertas)

    # Debug local
    debug = Path(__file__).parent / "alertas_debug.json"
    debug.write_text(json.dumps(alertas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Debug → {debug}")


if __name__ == "__main__":
    main()

"""
descargar_localizados_ve.py
============================
Descarga todos los registros de localizadosvenezuela.com
y los agrega al CSV consolidado.

Uso:
  python3 descargar_localizados_ve.py

No requiere librerías externas (usa solo requests, ya instalado).
"""

import csv
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Instala requests: pip3 install requests")
    sys.exit(1)

BASE_URL   = "https://localizadosvenezuela.com/api/v1"
SALIDA_CSV = "desaparecidos_consolidado.csv"
FUENTE     = "localizados_ve"
LIMIT      = 50

CAMPOS = [
    "fuente", "id_fuente", "nombre", "cedula", "edad", "sexo",
    "descripcion", "ubicacion", "lat", "lng", "estado",
    "contacto", "creado", "url",
]


def extraer_nombre(item):
    """Extrae el nombre del item."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (item.get("nombreCompleto") or item.get("nombre") or
                item.get("name") or item.get("full_name") or "").strip()
    return ""


def extraer_campo(item, *keys, default=""):
    if isinstance(item, str):
        return default
    for k in keys:
        v = item.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def mapear_condicion(item):
    """Mapea el campo 'condicion' al formato del CSV."""
    c = (item.get("condicion") or "").lower() if isinstance(item, dict) else ""
    if "fallec" in c or "muert" in c:
        return "fallecido"
    if "desaparec" in c or "buscado" in c or "desconocido" in c:
        return "desaparecido"
    return "localizado"


def diagnostico():
    """Muestra la estructura real de la API para depuración."""
    print("\n🔬 DIAGNÓSTICO — estructura de la API:")
    # Endpoint principal
    r = requests.get(f"{BASE_URL}/localizados?page=1&limit=2", timeout=15)
    print(f"\n  GET /localizados?page=1&limit=2  →  {r.status_code}")
    import json
    print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:1500])

    # Endpoint lugares
    r2 = requests.get(f"{BASE_URL}/lugares", timeout=15)
    print(f"\n  GET /lugares  →  {r2.status_code}")
    lugares = r2.json()
    print(json.dumps(lugares[:2] if isinstance(lugares, list) else lugares, indent=2, ensure_ascii=False)[:800])

    # Primer lugar
    if isinstance(lugares, list) and lugares:
        primer = lugares[0]
        slug = primer.get("slug") or primer.get("id") or primer if isinstance(primer, str) else ""
        if slug:
            r3 = requests.get(f"{BASE_URL}/lugares/{slug}", timeout=15)
            print(f"\n  GET /lugares/{slug}  →  {r3.status_code}")
            print(json.dumps(r3.json(), indent=2, ensure_ascii=False)[:1200])


def descargar_todos():
    """Descarga todos los localizados paginando la API."""
    registros = []
    page = 1

    while True:
        url = f"{BASE_URL}/localizados?page={page}&limit={LIMIT}"
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ⚠️  Error en página {page}: {e}")
            break

        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("data","results","localizados","items","records"):
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break
            if page == 1:
                total = data.get("total") or data.get("count") or data.get("total_count") or "?"
                print(f"   Total reportado por API: {total}")
                print(f"   Claves del response: {list(data.keys())}")

        if not items:
            break

        extraidos = 0
        for i, item in enumerate(items):
            nombre = extraer_nombre(item)
            if not nombre or len(nombre) < 3:
                continue

            slug_item = extraer_campo(item, "slug", "id")
            direccion = extraer_campo(item, "direccion", "address")
            lugar     = extraer_campo(item, "lugarNombre", "lugar", "ubicacion", "location")
            ubicacion = f"{lugar} · {direccion}" if lugar and direccion else (lugar or direccion)
            desc      = extraer_campo(item, "observaciones", "descripcion", "description", "notas")
            creado    = extraer_campo(item, "publicadoEn", "creado", "created_at", "fecha", "date")[:10]
            url_item  = (extraer_campo(item, "url", "link") or
                         f"https://localizadosvenezuela.com/localizados/{slug_item}")

            registros.append({
                "fuente":      "localizados_ve",
                "id_fuente":   f"lve_{slug_item or f'p{page}i{i}'}",
                "nombre":      nombre,
                "cedula":      re.sub(r"[^\d]", "", extraer_campo(item, "cedula", "ci")),
                "edad":        re.sub(r"[^\d]", "", extraer_campo(item, "edad", "age")),
                "sexo":        extraer_campo(item, "sexo", "genero"),
                "descripcion": desc,
                "ubicacion":   ubicacion,
                "lat":         extraer_campo(item, "lat"),
                "lng":         extraer_campo(item, "lng", "lon"),
                "estado":      mapear_condicion(item),
                "contacto":    "",
                "creado":      creado,
                "url":         url_item,
            })
            extraidos += 1

        print(f"  Página {page}: {len(items)} items → {extraidos} válidos  (total: {len(registros)})")

        if len(items) < LIMIT:
            break
        page += 1
        time.sleep(0.3)

    return registros


def descargar_por_lugares():
    """Alternativa: descarga usando el endpoint /lugares."""
    print("\n🔁 Intentando por endpoint /lugares ...")
    registros = []

    try:
        r = requests.get(f"{BASE_URL}/lugares?limit=200", timeout=15)
        lugares_raw = r.json()
        if isinstance(lugares_raw, dict):
            lugares = lugares_raw.get("data") or lugares_raw.get("lugares") or []
        else:
            lugares = lugares_raw
    except Exception as e:
        print(f"  ❌ Error obteniendo lugares: {e}")
        return []

    print(f"   {len(lugares)} lugares encontrados")

    for lugar in lugares:
        # lugar puede ser dict o string
        if isinstance(lugar, str):
            slug = lugar
            nombre_lugar = lugar
        elif isinstance(lugar, dict):
            slug = lugar.get("slug") or lugar.get("id") or ""
            nombre_lugar = lugar.get("nombre") or lugar.get("name") or slug
        else:
            continue
        if not slug:
            continue

        try:
            r2 = requests.get(f"{BASE_URL}/lugares/{slug}", timeout=15)
            data = r2.json()
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("localizados") or data.get("data") or data.get("personas") or []
            else:
                items = []
        except Exception as e:
            print(f"  ⚠️  Error en lugar {slug}: {e}")
            continue

        extraidos = 0
        for i, item in enumerate(items):
            nombre = extraer_nombre(item)
            if not nombre or len(nombre) < 3:
                continue
            slug_i    = extraer_campo(item, "slug", "id") or f"{slug}_{i}"
            direccion = extraer_campo(item, "direccion", "address")
            ubi_item  = extraer_campo(item, "lugarNombre") or nombre_lugar
            ubicacion = f"{ubi_item} · {direccion}" if ubi_item and direccion else (ubi_item or direccion)
            desc      = extraer_campo(item, "observaciones", "descripcion", "description")
            creado    = extraer_campo(item, "publicadoEn", "creado", "created_at", "fecha")[:10]
            url_i     = (extraer_campo(item, "url", "link") or
                         f"https://localizadosvenezuela.com/localizados/{slug_i}")

            registros.append({
                "fuente":      "localizados_ve",
                "id_fuente":   f"lve_{slug_i}",
                "nombre":      nombre,
                "cedula":      re.sub(r"[^\d]", "", extraer_campo(item, "cedula", "ci")),
                "edad":        re.sub(r"[^\d]", "", extraer_campo(item, "edad", "age")),
                "sexo":        extraer_campo(item, "sexo", "genero"),
                "descripcion": desc,
                "ubicacion":   ubicacion,
                "lat":         "", "lng":         "",
                "estado":      mapear_condicion(item),
                "contacto":    "",
                "creado":      creado,
                "url":         url_i,
            })
            extraidos += 1

        if extraidos:
            print(f"  {nombre_lugar}: {extraidos} localizados")
        time.sleep(0.3)

    return registros


def agregar_al_csv(registros_nuevos):
    # Campos que pueden cambiar entre corridas (actualizables)
    CAMPOS_MUTABLES = ["estado", "ubicacion", "descripcion", "contacto"]

    csv_path = Path(SALIDA_CSV)
    fieldnames_out = CAMPOS  # default si no existe CSV previo

    if not csv_path.exists():
        print(f"⚠️  No existe {SALIDA_CSV}")
        registros_existentes = []
    else:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Preservar las columnas del CSV existente (puede tener más que CAMPOS)
            if reader.fieldnames:
                fieldnames_out = list(reader.fieldnames)
                # Agregar columnas de CAMPOS que no estén ya
                for col in CAMPOS:
                    if col not in fieldnames_out:
                        fieldnames_out.append(col)
            registros_existentes = list(reader)
        print(f"   CSV existente: {len(registros_existentes):,} registros")

    # Índice de registros existentes de esta fuente: id_fuente → posición en lista
    indice = {r["id_fuente"]: i
              for i, r in enumerate(registros_existentes)
              if r.get("fuente") == FUENTE}

    nuevos       = []
    actualizados = 0

    for r in registros_nuevos:
        id_f = r["id_fuente"]
        if id_f not in indice:
            # Registro nuevo: agregar al final
            nuevos.append(r)
        else:
            # Ya existe: comparar campos mutables y actualizar si cambiaron
            existente = registros_existentes[indice[id_f]]
            cambio = False
            for campo in CAMPOS_MUTABLES:
                nuevo_val = (r.get(campo) or "").strip()
                viejo_val = (existente.get(campo) or "").strip()
                if nuevo_val and nuevo_val != viejo_val:
                    existente[campo] = nuevo_val
                    cambio = True
            if cambio:
                actualizados += 1

    todos = registros_existentes + nuevos

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_out, extrasaction="ignore")
        w.writeheader()
        w.writerows(todos)

    print(f"\n💾 CSV actualizado: {SALIDA_CSV}")
    print(f"   Anteriores:               {len(registros_existentes):,}")
    print(f"   Nuevos agregados:         {len(nuevos):,}")
    print(f"   Actualizados (estado/ubi):{actualizados:,}")
    print(f"   Total:                    {len(todos):,}")
    print(f"\n✅ Listo. Sube {SALIDA_CSV} a GitHub.")


def main():
    if "--diag" in sys.argv:
        diagnostico()
        return

    print("\n🌐 Descargando de localizadosvenezuela.com ...")

    # Intento 1: endpoint principal paginado
    registros = descargar_todos()

    # Si no trajo nada, intento por lugares
    if not registros:
        registros = descargar_por_lugares()

    if not registros:
        print("❌ No se pudieron descargar registros. Verifica la conexión.")
        sys.exit(1)

    print(f"\n✅ Total descargado: {len(registros):,} localizados")
    agregar_al_csv(registros)


if __name__ == "__main__":
    main()

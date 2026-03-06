"""
upload_to_github.py
===================
Sube los 3 CSVs procesados al repositorio de GitHub automáticamente.
Se ejecuta después de process_attendance.py desde el .bat semanal.

Configuración:
  - Editá las variables GITHUB_USER, REPO_NAME y PROCESSED_DIR si cambian
  - El token se lee desde la variable de entorno GITHUB_TOKEN (más seguro)
    o desde el archivo .github_token en la carpeta del proyecto
"""

import os
import base64
import json
import urllib.request
import urllib.error

# ── Configuración ────────────────────────────────────────────────────────────
GITHUB_USER   = "nadiaruppelmx-dot"
REPO_NAME     = "process_attendance"
BRANCH        = "main"
PROCESSED_DIR = r"C:\Users\nadia\OneDrive\Documents\ASISTENCIA POR SEMANAS\Registro con Parkimovil\reportes_asistencia\data\processed"

ARCHIVOS = [
    "registros_diarios.csv",
    "salidas_intermedias.csv",
    "resumen_semanal.csv",
]

# ── Leer token ───────────────────────────────────────────────────────────────
def obtener_token():
    """Lee el token desde variable de entorno o archivo local."""
    # Opción 1: variable de entorno (recomendada)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # Opción 2: archivo .github_token en la carpeta del proyecto
    token_file = os.path.join(os.path.dirname(__file__), ".github_token")
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            return f.read().strip()

    raise ValueError(
        "No se encontró el token de GitHub.\n"
        "Opciones:\n"
        "  1. Creá el archivo .github_token en la carpeta del proyecto con tu token\n"
        "  2. Configurá la variable de entorno GITHUB_TOKEN"
    )

# ── GitHub API ───────────────────────────────────────────────────────────────
def get_file_sha(token, path_in_repo):
    """Obtiene el SHA del archivo en GitHub (necesario para actualizar)."""
    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{path_in_repo}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # Archivo nuevo
        raise

def subir_archivo(token, local_path, path_in_repo):
    """Sube o actualiza un archivo en GitHub."""
    with open(local_path, "rb") as f:
        contenido = base64.b64encode(f.read()).decode("utf-8")

    sha = get_file_sha(token, path_in_repo)

    url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/{path_in_repo}"
    payload = {
        "message": f"Actualización semanal: {os.path.basename(local_path)}",
        "content": contenido,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha  # Necesario para actualizar archivo existente

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as resp:
        return resp.status

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("\n📤 Subiendo CSVs a GitHub...")
    print(f"   Repositorio: {GITHUB_USER}/{REPO_NAME}")

    try:
        token = obtener_token()
    except ValueError as e:
        print(f"\n❌ {e}")
        return False

    exito = True
    for archivo in ARCHIVOS:
        local_path    = os.path.join(PROCESSED_DIR, archivo)
        path_in_repo  = f"data/processed/{archivo}"

        if not os.path.exists(local_path):
            print(f"   ⚠️  No encontrado: {archivo}")
            continue

        try:
            status = subir_archivo(token, local_path, path_in_repo)
            print(f"   ✅ {archivo} → GitHub ({status})")
        except Exception as e:
            print(f"   ❌ Error subiendo {archivo}: {e}")
            exito = False

    if exito:
        print(f"\n✅ Todos los archivos subidos correctamente.")
        print(f"   URL: https://github.com/{GITHUB_USER}/{REPO_NAME}/tree/{BRANCH}/data/processed")
    else:
        print(f"\n⚠️  Algunos archivos no se pudieron subir. Revisá el token y la conexión.")

    return exito

if __name__ == "__main__":
    main()

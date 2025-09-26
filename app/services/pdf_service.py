# services/pdf_service.py
from flask import current_app
import os
from datetime import datetime

# --- pikepdf en "lazy import" (Windows/Py 3.13 peut poser problème) ---
try:
    import pikepdf  # type: ignore
except Exception:
    pikepdf = None

def protect_pdf_with_password(filepath: str, password: str) -> bool:
    """
    Protège un PDF avec un mot de passe via pikepdf si dispo.
    Retourne True si OK, False sinon (et on continue sans planter l'app).
    """
    if pikepdf is None:
        current_app.logger.warning("[pdf] pikepdf indisponible → protection ignorée")
        return False
    try:
        with pikepdf.open(filepath, allow_overwriting_input=True) as pdf:
            pdf.save(filepath, encryption=pikepdf.Encryption(user=password, owner=password))
        current_app.logger.info(f"[pdf] Protection OK: {os.path.basename(filepath)}")
        return True
    except Exception as e:
        current_app.logger.error(f"[pdf] Erreur protection: {e}")
        return False

def generate_timestamp_folder() -> str:
    """Génère un nom de dossier au format aaaammjjhhmmss."""
    now = datetime.now()
    return now.strftime('%Y%m%d%H%M%S')

def extract_employee_name_from_page(page_text: str) -> str | None:
    """Extrait le nom de l'employé depuis le texte d'une page."""
    lines = page_text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if "Catégorie" in line:
            if " M " in line:
                parts = line.split(" M ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:
                        return name
            elif " Mme " in line:
                parts = line.split(" Mme ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:
                        return name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 5 and next_line.isupper():
                    return next_line
    return None

def extract_employee_matricule_from_page(page_text: str) -> str | None:
    """Extrait le matricule de l'employé depuis le texte d'une page."""
    lines = page_text.split('\n')
    import re
    for i, line in enumerate(lines):
        line = line.strip()
        if "Matricule" in line:
            m = re.search(r'Matricule\s+(\d+)', line)
            if m:
                return m.group(1)
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                m = re.search(r'^(\d{4})(?:\s|$)', next_line)
                if m:
                    return m.group(1)
    return None

def extract_period_from_page(page_text: str) -> str:
    """Extrait la période du bulletin (YYYY_MM). Si rien trouvé → maintenant."""
    lines = page_text.split('\n')
    import re
    patterns = [
        r'Période du \d{2}/(\d{2})/(\d{2}) au',
        r'Période du \d{2}/(\d{2})/(\d{4}) au',
        r'du \d{2}/(\d{2})/(\d{2}) au',
        r'Mois\s*:\s*(\d{2})/(\d{4})',
        r'(\d{1,2})/(\d{1,2})/(\d{2,4})'
    ]
    for line in lines:
        line = line.strip()
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, line)
            if match:
                if i in [0, 2]:  # année 2 chiffres
                    month = match.group(1).zfill(2)
                    year2 = match.group(2)
                    full_year = f"20{year2}" if int(year2) < 50 else f"19{year2}"
                    return f"{full_year}_{month}"
                elif i == 1:
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                elif i == 3:
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                elif i == 4:
                    day = match.group(1).zfill(2)  # non utilisé mais gardé
                    month = match.group(2).zfill(2)
                    year = match.group(3)
                    full_year = f"20{year}" if len(year) == 2 and int(year) < 50 else (f"19{year}" if len(year) == 2 else year)
                    return f"{full_year}_{month}"
    return datetime.now().strftime('%Y_%m')

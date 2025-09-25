# services/pdf_service.py
from flask import current_app
import os
import pikepdf

def protect_pdf_with_password(filepath: str, password: str) -> bool:
    """
    Protège un PDF avec un mot de passe (utilise pikepdf).
    Retourne True si OK, False sinon.
    """
    try:
        with pikepdf.open(filepath, allow_overwriting_input=True) as pdf:
            pdf.save(filepath, encryption=pikepdf.Encryption(user=password, owner=password))
        current_app.logger.info(f"[pdf] Protection OK pour {os.path.basename(filepath)}")
        return True
    except Exception as e:
        current_app.logger.error(f"[pdf] Erreur protection: {e}")
        # Fallback simple: pas de protection
        return False

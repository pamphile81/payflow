# services/link_service.py
from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional
from flask import current_app
from app.extensions import db
from app.models.models import DownloadLink, Traitement

def get_current_traitement(output_dir: str) -> Optional[Traitement]:
    """Retrouve le Traitement via le nom du dossier timestamp."""
    try:
        timestamp_folder = os.path.basename(output_dir)
        return Traitement.query.filter_by(timestamp_folder=timestamp_folder).first()
    except Exception as e:
        current_app.logger.error(f"[link] get_current_traitement: {e}")
        return None

def generate_secure_download_link(employee_record, traitement: Traitement, file_path: str, matricule: str):
    """Crée un DownloadLink en base pour un fichier généré."""
    try:
        max_attempts = current_app.config.get("MAX_DOWNLOAD_ATTEMPTS", 10)
        expiry_days = current_app.config.get("DOWNLOAD_LINK_EXPIRY_DAYS", 30)

        dl = DownloadLink(
            employe_id=employee_record.id,
            traitement_id=traitement.id,
            nom_fichier=os.path.basename(file_path),
            chemin_fichier=file_path,
            matricule_requis=matricule,
            max_tentatives=max_attempts,
            date_expiration=datetime.utcnow() + timedelta(days=expiry_days),
        )
        db.session.add(dl)
        db.session.commit()
        current_app.logger.info(f"[link] Lien créé pour {employee_record.nom_employe}: {dl.token[:8]}…")
        return dl
    except Exception as e:
        current_app.logger.error(f"[link] Erreur création: {e}")
        db.session.rollback()
        return None

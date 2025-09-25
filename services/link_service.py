# services/link_service.py
from datetime import datetime, timedelta
from flask import current_app
from extensions import db
from models import DownloadLink, Traitement, Employee

def get_current_traitement(output_dir: str) -> Traitement | None:
    try:
        timestamp_folder = output_dir.split(os.sep)[-1]
    except Exception:
        timestamp_folder = output_dir
    try:
        return Traitement.query.filter_by(timestamp_folder=timestamp_folder).first()
    except Exception as e:
        current_app.logger.error(f"[link] Erreur récupération traitement: {e}")
        return None

def generate_secure_download_link(employee: Employee, traitement: Traitement,
                                  file_path: str, matricule: str) -> DownloadLink | None:
    """
    Crée et enregistre un DownloadLink en base.
    """
    try:
        expiry_days = int(current_app.config.get("DOWNLOAD_LINK_EXPIRY_DAYS", 30))
        max_attempts = int(current_app.config.get("MAX_DOWNLOAD_ATTEMPTS", 10))

        link = DownloadLink(
            employe_id=employee.id,
            traitement_id=traitement.id,
            nom_fichier=os.path.basename(file_path),
            chemin_fichier=file_path,
            matricule_requis=matricule,
            max_tentatives=max_attempts,
            date_expiration=datetime.utcnow() + timedelta(days=expiry_days),
        )
        db.session.add(link)
        db.session.commit()
        current_app.logger.info(f"[link] Lien généré pour {employee.nom_employe} → {link.token[:8]}...")
        return link
    except Exception as e:
        current_app.logger.error(f"[link] Erreur génération lien: {e}")
        db.session.rollback()
        return None

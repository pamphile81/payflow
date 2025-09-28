# app.py - Version v1.2 avec PostgreSQL
import os
from datetime import datetime, timedelta
import threading

from app.model.models import db,  DownloadLink

# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False


def generate_secure_download_link(employee_record, traitement, file_path, matricule,app):
    with app.app_context():
        """Génère un lien de téléchargement sécurisé"""
        try:
            # Créer l'enregistrement du lien
            download_link = DownloadLink(
                employe_id=employee_record.id,
                traitement_id=traitement.id,
                nom_fichier=os.path.basename(file_path),
                chemin_fichier=file_path,
                matricule_requis=matricule,
                max_tentatives=10,  # Configurable
                date_expiration=datetime.utcnow() + timedelta(days=30)  # 30 jours
            )
            
            db.session.add(download_link)
            db.session.commit()
            
             # Forcer le rafraîchissement des attributs
            db.session.refresh(download_link)
            
            #app.logger.info(f"Lien sécurisé généré: {download_link.token[:8]}...")
            return download_link
            
        except Exception as e:
            app.logger.error(f"Erreur génération lien: {str(e)}")
            db.session.rollback()
            return None
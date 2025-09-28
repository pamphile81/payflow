import os
from datetime import datetime, timedelta
import threading
from sqlalchemy import func

from app.model.models import db, Employee, Traitement, TraitementEmploye, DownloadLink
from app.services.file_service import format_file_size
# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False


# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False


def get_treatments_from_filesystem(app):
    with app.app_context():
        """Votre ancienne fonction pour compatibilité"""
        treatments = []
        uploads_path = app.config['UPLOAD_FOLDER']
        output_path = app.config['OUTPUT_FOLDER']
        
        if os.path.exists(uploads_path):
            for folder in os.listdir(uploads_path):
                folder_path = os.path.join(uploads_path, folder)
                if os.path.isdir(folder_path):
                    treatment_info = analyze_treatment_folder(folder, folder_path, output_path)
                    if treatment_info:
                        treatments.append(treatment_info)
        
        treatments.sort(key=lambda x: x['timestamp'], reverse=True)
        return treatments


def get_current_traitement(output_dir,app):
    with app.app_context():
        """Récupère le traitement actuel basé sur le dossier de sortie"""
        try:
            timestamp_folder = os.path.basename(output_dir)
            return Traitement.query.filter_by(timestamp_folder=timestamp_folder).first()
        except Exception as e:
            app.logger.error(f" Erreur récupération traitement: {str(e)}")
            return None


def analyze_treatment_folder(folder_name, upload_path, output_path):
    """Analyse un dossier de traitement pour extraire les statistiques"""
    try:
        from datetime import datetime
        
        # Parse du timestamp
        timestamp_str = folder_name
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
        except ValueError:
            return None
        
        # Fichier original
        original_files = [f for f in os.listdir(upload_path) if f.endswith('.pdf')]
        original_file = original_files[0] if original_files else 'Inconnu'
        
        # Dossier de sortie correspondant
        output_folder_path = os.path.join(output_path, folder_name)
        
        # Comptage des PDFs générés
        generated_files = []
        if os.path.exists(output_folder_path):
            generated_files = [f for f in os.listdir(output_folder_path) if f.endswith('.pdf')]
        
        # Calcul de la taille du fichier original
        original_file_path = os.path.join(upload_path, original_file)
        file_size = 0
        if os.path.exists(original_file_path):
            file_size = os.path.getsize(original_file_path)
        
        return {
            'timestamp': timestamp,
            'timestamp_str': timestamp_str,
            'date_formatted': timestamp.strftime('%d/%m/%Y à %H:%M:%S'),
            'original_file': original_file,
            'file_size': format_file_size(file_size),
            'employees_count': len(generated_files),
            'generated_files': generated_files,
            'status': 'Réussi' if generated_files else 'Échec'
        }
        
    except Exception as e:
        return None


def calculate_global_stats(treatments):
    """Calcule les statistiques globales"""
    if not treatments:
        return {
            'total_treatments': 0,
            'total_employees': 0,
            'total_files_generated': 0,
            'success_rate': 0,
            'last_treatment': None
        }
    
    successful_treatments = [t for t in treatments if t['status'] == 'Réussi']
    
    return {
        'total_treatments': len(treatments),
        'total_employees': sum(t['employees_count'] for t in treatments),
        'total_files_generated': sum(t['employees_count'] for t in successful_treatments),
        'success_rate': round(len(successful_treatments) / len(treatments) * 100, 1) if treatments else 0,
        'last_treatment': treatments[0]['date_formatted'] if treatments else None
    }

# Nouvelles fonctions pour dashboard PostgreSQL
def calculate_stats_from_db(app):
    with app.app_context():
        """Calcule les statistiques depuis PostgreSQL"""
        try:
            total_treatments = Traitement.query.count()
            if total_treatments == 0:
                return {
                    'total_treatments': 0,
                    'total_employees': 0,
                    'total_files_generated': 0,
                    'success_rate': 0,
                    'last_treatment': None
                }
            
            successful_treatments = Traitement.query.filter_by(statut='termine').all()
            total_employees = sum(t.nombre_employes_traites for t in Traitement.query.all())
            total_files = sum(t.nombre_employes_traites for t in successful_treatments)
            
            last_treatment = Traitement.query.order_by(Traitement.date_creation.desc()).first()
            
            return {
                'total_treatments': total_treatments,
                'total_employees': total_employees,
                'total_files_generated': total_files,
                'success_rate': round(len(successful_treatments) / total_treatments * 100, 1) if total_treatments > 0 else 0,
                'last_treatment': last_treatment.date_creation.strftime('%d/%m/%Y à %H:%M:%S') if last_treatment else None
            }
            
        except Exception as e:
            app.logger.error(f"❌Erreur calcul stats DB: {str(e)}")
            return {
                'total_treatments': 0,
                'total_employees': 0,
                'total_files_generated': 0,
                'success_rate': 0,
                'last_treatment': None
            }


def get_treatments_from_db(app):
    with app.app_context():
        """Récupère les traitements depuis PostgreSQL"""
        try:
            treatments = []
            db_treatments = Traitement.query.order_by(Traitement.date_creation.desc()).all()
            
            for treatment in db_treatments:
                # Récupération des fichiers générés depuis le filesystem
                output_folder_path = os.path.join(app.config['OUTPUT_FOLDER'], treatment.timestamp_folder)
                generated_files = []
                if os.path.exists(output_folder_path):
                    generated_files = [f for f in os.listdir(output_folder_path) if f.endswith('.pdf')]
                
                treatments.append({
                    'timestamp': treatment.date_creation,
                    'timestamp_str': treatment.timestamp_folder,
                    'date_formatted': treatment.date_creation.strftime('%d/%m/%Y à %H:%M:%S'),
                    'original_file': treatment.fichier_original,
                    'file_size': format_file_size(treatment.taille_fichier),
                    'employees_count': treatment.nombre_employes_traites,
                    'generated_files': generated_files,
                    'status': 'Réussi' if treatment.statut == 'termine' else 'Échec',
                    'source': 'PostgreSQL'
                })
            
            return treatments
            
        except Exception as e:
            app.logger.error(f"Erreur récupération traitements DB: {str(e)}")
            return []


def get_v12_dashboard_stats(app):
    with app.app_context():
        """Statistiques complètes pour dashboard v1.2"""
        try:
            now = datetime.utcnow()
            last_30_days = now - timedelta(days=30)
            last_7_days = now - timedelta(days=7)
            
            # Statistiques générales
            stats = {
                # Traitements
                'total_treatments': Traitement.query.count(),
                'treatments_last_30_days': Traitement.query.filter(Traitement.date_creation >= last_30_days).count(),
                'treatments_last_7_days': Traitement.query.filter(Traitement.date_creation >= last_7_days).count(),
                'successful_treatments': Traitement.query.filter_by(statut='termine').count(),
                'failed_treatments': Traitement.query.filter_by(statut='echec').count(),
                
                # Employés
                'total_employees': Employee.query.count(),
                'active_employees': Employee.query.filter_by(statut='actif').count(),
                'pdf_imported_employees': Employee.query.filter_by(source_creation='pdf_import').count(),
                'manual_employees': Employee.query.filter_by(source_creation='manual').count(),
                
                # Liens de téléchargement
                'total_download_links': DownloadLink.query.count(),
                'active_links': DownloadLink.query.filter_by(statut='actif').count(),
                'expired_links': DownloadLink.query.filter(DownloadLink.date_expiration < now).count(),
                'total_downloads': db.session.query(func.sum(DownloadLink.nombre_telechargements)).scalar() or 0,
                
                # Sécurité
                'blocked_attempts': DownloadLink.query.filter(DownloadLink.tentatives_acces >= DownloadLink.max_tentatives).count(),
                'links_with_attempts': DownloadLink.query.filter(DownloadLink.tentatives_acces > 0).count(),
            }
            
            # Calculs dérivés
            stats['success_rate'] = round(
                (stats['successful_treatments'] / stats['total_treatments'] * 100) if stats['total_treatments'] > 0 else 0, 1
            )
            
            stats['security_rate'] = round(
                ((stats['active_links'] - stats['blocked_attempts']) / stats['active_links'] * 100) if stats['active_links'] > 0 else 100, 1
            )
            
            return stats
            
        except Exception as e:
            app.logger.error(f" Erreur calcul stats v1.2: {str(e)}")
            return {}


def get_employee_top_stats(app):
    with app.app_context():
        """Top 10 des employés par nombre de fiches reçues"""
        try:
            top_employees = db.session.query(
                Employee.nom_employe,
                func.count(TraitementEmploye.id).label('nb_fiches')
            ).join(
                TraitementEmploye
            ).group_by(
                Employee.id, Employee.nom_employe
            ).order_by(
                func.count(TraitementEmploye.id).desc()
            ).limit(10).all()
            
            return [
                {
                    'name': emp.nom_employe,
                    'count': emp.nb_fiches
                }
                for emp in top_employees
            ]
            
        except Exception as e:
            app.logger.error(f" Erreur top employés: {str(e)}")
            return []
        

def get_recent_activity(app):
    with app.app_context():
        """Activité récente (dernières 24h)"""
        try:
            last_24h = datetime.utcnow() - timedelta(hours=24)
            
            # Derniers traitements
            recent_treatments = Traitement.query.filter(
                Traitement.date_creation >= last_24h
            ).order_by(Traitement.date_creation.desc()).limit(5).all()
            
            # Derniers téléchargements
            recent_downloads = DownloadLink.query.filter(
                DownloadLink.date_dernier_acces >= last_24h,
                DownloadLink.nombre_telechargements > 0
            ).order_by(DownloadLink.date_dernier_acces.desc()).limit(5).all()
            
            return {
                'treatments': recent_treatments,
                'downloads': recent_downloads
            }
            
        except Exception as e:
            app.logger.error(f" Erreur activité récente: {str(e)}")
            return {'treatments': [], 'downloads': []}


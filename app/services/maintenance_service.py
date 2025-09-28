
import os
from datetime import datetime, timedelta
import threading

from app.model.models import db, Employee, Traitement, TraitementEmploye, DownloadLink

# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False


# Fonctions de maintenance
def get_maintenance_stats(app):
    """Collecte les statistiques de maintenance"""
    with app.app_context():
        try:
            now = datetime.utcnow()
            
            # Liens expirés
            expired_links = DownloadLink.query.filter(
                DownloadLink.date_expiration < now
            ).count()
            
            # Fichiers anciens (plus de 30 jours)
            old_files_info = analyze_old_files()
            
            # Taille des dossiers
            uploads_size = get_folder_size('uploads')
            output_size = get_folder_size('output')
            
            # Statistiques base de données
            db_stats = get_database_stats()

            return {
                'expired_links': expired_links,
                'old_files_count': old_files_info['count'],
                'old_files_size': old_files_info['size'],
                'uploads_size': uploads_size,
                'output_size': output_size,
                'total_size': uploads_size + output_size,
                'db_stats': db_stats,
                'last_cleanup': get_last_cleanup_date(),
                'system_health': calculate_system_health()
            }
        
        except Exception as e:
            app.logger.error(f"Erreur stats maintenance: {str(e)}")
        return {}

def analyze_old_files(app):
    with app.app_context():
        """Analyse les fichiers anciens"""
        try:
            now = datetime.utcnow()
            cutoff_date = now - timedelta(days=30)
            
            old_count = 0
            total_size = 0
            
            for folder in ['uploads', 'output']:
                if os.path.exists(folder):
                    for subfolder in os.listdir(folder):
                        subfolder_path = os.path.join(folder, subfolder)
                        if os.path.isdir(subfolder_path):
                            try:
                                # Parse la date du dossier (format: YYYYMMDDHHMMSS)
                                if len(subfolder) == 14 and subfolder.isdigit():
                                    folder_date = datetime.strptime(subfolder, '%Y%m%d%H%M%S')
                                    if folder_date < cutoff_date:
                                        old_count += 1
                                        total_size += get_folder_size(subfolder_path)
                            except ValueError:
                                continue
            
            return {
                'count': old_count,
                'size': total_size
            }
            
        except Exception as e:
            app.logger.error(f"Erreur analyse fichiers anciens: {str(e)}")
            return {'count': 0, 'size': 0}

def get_folder_size(folder_path):
    """Calcule la taille d'un dossier en bytes"""
    try:
        total_size = 0
        if os.path.exists(folder_path):
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
        return total_size
    except Exception:
        return 0

def format_file_size(size_bytes):
    """Formate la taille en format lisible"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

def perform_system_cleanup(cleanup_type='all'):
    """Effectue le nettoyage système"""
    try:
        results = {
            'expired_links_removed': 0,
            'old_files_removed': 0,
            'space_freed': 0
        }
        
        if cleanup_type in ['all', 'links']:
            # Nettoyer les liens expirés
            expired_links = DownloadLink.query.filter(
                DownloadLink.date_expiration < datetime.utcnow()
            ).all()
            
            for link in expired_links:
                db.session.delete(link)
                results['expired_links_removed'] += 1
            
            db.session.commit()
        
        if cleanup_type in ['all', 'files']:
            # Nettoyer les fichiers anciens
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            for folder in ['uploads', 'output']:
                if os.path.exists(folder):
                    for subfolder in os.listdir(folder):
                        subfolder_path = os.path.join(folder, subfolder)
                        if os.path.isdir(subfolder_path):
                            try:
                                if len(subfolder) == 14 and subfolder.isdigit():
                                    folder_date = datetime.strptime(subfolder, '%Y%m%d%H%M%S')
                                    if folder_date < cutoff_date:
                                        folder_size = get_folder_size(subfolder_path)
                                        import shutil
                                        shutil.rmtree(subfolder_path)
                                        results['old_files_removed'] += 1
                                        results['space_freed'] += folder_size
                            except (ValueError, OSError):
                                continue
        
        # Enregistrer la date de nettoyage
        save_cleanup_date()
        
        message = f"{results['expired_links_removed']} liens expirés, {results['old_files_removed']} dossiers anciens supprimés, {format_file_size(results['space_freed'])} d'espace libéré"
        
        return {
            'success': True,
            'message': message,
            'details': results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_database_stats():
    """Statistiques de la base de données"""
    try:
        return {
            'employees_count': Employee.query.count(),
            'treatments_count': Traitement.query.count(),
            'treatment_employees_count': TraitementEmploye.query.count(),
            'download_links_count': DownloadLink.query.count()
        }
    except Exception:
        return {}

def calculate_system_health():
    """Calcule l'état de santé du système"""
    try:
        # Critères de santé
        health_score = 100
        issues = []
        
        # Vérifier les liens expirés
        expired_links = DownloadLink.query.filter(
            DownloadLink.date_expiration < datetime.utcnow()
        ).count()
        
        if expired_links > 50:
            health_score -= 20
            issues.append(f"{expired_links} liens expirés")
        elif expired_links > 10:
            health_score -= 10
            issues.append(f"{expired_links} liens expirés")
        
        # Vérifier l'espace disque
        total_size = get_folder_size('uploads') + get_folder_size('output')
        if total_size > 1024 * 1024 * 1024:  # > 1GB
            health_score -= 15
            issues.append("Espace disque élevé")
        
        # Vérifier les tentatives bloquées
        blocked_attempts = DownloadLink.query.filter(
            DownloadLink.tentatives_acces >= DownloadLink.max_tentatives
        ).count()
        
        if blocked_attempts > 5:
            health_score -= 10
            issues.append(f"{blocked_attempts} accès bloqués")
        
        return {
            'score': max(0, health_score),
            'status': 'excellent' if health_score >= 90 else ('good' if health_score >= 70 else ('warning' if health_score >= 50 else 'critical')),
            'issues': issues
        }
        
    except Exception:
        return {'score': 0, 'status': 'unknown', 'issues': ['Erreur de calcul']}

def get_last_cleanup_date():
    """Récupère la date du dernier nettoyage"""
    try:
        cleanup_file = 'last_cleanup.txt'
        if os.path.exists(cleanup_file):
            with open(cleanup_file, 'r') as f:
                date_str = f.read().strip()
                return datetime.fromisoformat(date_str)
    except Exception:
        pass
    return None

def save_cleanup_date():
    """Sauvegarde la date du nettoyage"""
    try:
        with open('last_cleanup.txt', 'w') as f:
            f.write(datetime.utcnow().isoformat())
    except Exception:
        pass

def create_database_backup():
    """Crée une sauvegarde de la base PostgreSQL"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"payflow_backup_{timestamp}.sql"
        
        # Commande pg_dump
        import subprocess
        cmd = [
            'pg_dump',
            '-h', 'localhost',
            '-U', 'payflow_user',
            '-d', 'payflow_db',
            '-f', filename
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return {
                'success': True,
                'filename': filename
            }
        else:
            return {
                'success': False,
                'error': result.stderr or 'Erreur pg_dump'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def perform_database_optimization():
    """Optimise la base de données"""
    try:
        # Commandes d'optimisation PostgreSQL
        db.session.execute('VACUUM ANALYZE;')
        db.session.commit()
        
        return {
            'success': True,
            'message': 'Base de données optimisée (VACUUM ANALYZE effectué)'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

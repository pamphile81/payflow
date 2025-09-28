# app.py - Version v1.2 avec PostgreSQL
import os
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False

# Configuration des dossiers
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'pdf'}

#app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
#app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

def setup_logging(app):
    """Configure le système de logging pour PayFlow"""
    
    # Créer le dossier logs s'il n'existe pas
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configuration du format des logs
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    # 1. Log général de l'application (rotation 10MB, 10 fichiers)
    file_handler = RotatingFileHandler(
        'logs/payflow.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    # 2. Log des erreurs uniquement
    error_handler = RotatingFileHandler(
        'logs/payflow_errors.log',
        maxBytes=5*1024*1024,   # 5MB
        backupCount=5
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app.logger.addHandler(error_handler)
    
    # 3. Log des accès sécurisés (téléchargements)
    security_handler = RotatingFileHandler(
        'logs/payflow_security.log',
        maxBytes=5*1024*1024,   # 5MB  
        backupCount=10
    )
    security_handler.setFormatter(formatter)
    security_handler.setLevel(logging.WARNING)
    
    # Logger sécurité séparé
    security_logger = logging.getLogger('payflow.security')
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
    
    # 4. Console pour le développement
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)
    
    # Niveau global
    app.logger.setLevel(logging.INFO)
    
    app.logger.info(" PayFlow v1.2 - Système de logging initialisé")
    return security_logger

def generate_timestamp_folder():
    """Génère un nom de dossier avec timestamp au format aaaammjjhhmmss"""
    now = datetime.now()
    return now.strftime('%Y%m%d%H%M%S')

def allowed_file(filename):
    """Vérifie si le fichier est un PDF"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def format_file_size(size_bytes):
    """Formate la taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"


def format_file_size(size_bytes):
    """Formate la taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

def get_file_size(filepath):
    """Retourne la taille d'un fichier formatée"""
    try:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            return format_file_size(size)
        return "0 B"
    except:
        return "N/A"
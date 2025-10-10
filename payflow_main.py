# app.py - Version v1.2 avec PostgreSQL
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, session
import os
from werkzeug.utils import secure_filename
import PyPDF2
import threading
from flask_migrate import Migrate
import logging
from logging.handlers import RotatingFileHandler

# Import des modèles et configuration
#from config import Config
from config import get_config
from app.model.models import db, Employee, Traitement, DownloadLink

from app.services.file_service import allowed_file, generate_timestamp_folder 
from app.services.pdf_service import process_pdf
from app.services.link_service import generate_secure_download_link
from app.services.treatment_service import get_treatments_from_filesystem, get_treatments_from_db, get_v12_dashboard_stats, get_recent_activity, get_employee_top_stats
from app.services.maintenance_service import  get_maintenance_stats, perform_system_cleanup, create_database_backup, perform_database_optimization
from app.services.file_service import setup_logging, format_file_size, get_file_size
# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
'''def setup_logging(app: Flask):
    if not os.path.exists('logs'):
        os.makedirs('logs')

    formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

    file_handler = RotatingFileHandler('logs/payflow.log', maxBytes=10*1024*1024, backupCount=10)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    error_handler = RotatingFileHandler('logs/payflow_errors.log', maxBytes=5*1024*1024, backupCount=5)
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app.logger.addHandler(error_handler)

    security_handler = RotatingFileHandler('logs/payflow_security.log', maxBytes=5*1024*1024, backupCount=10)
    security_handler.setFormatter(formatter)
    security_handler.setLevel(logging.WARNING)
    sec_logger = logging.getLogger('payflow.security')
    sec_logger.addHandler(security_handler)
    sec_logger.setLevel(logging.WARNING)

    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info("PayFlow v1.2 - logging initialisé")'''



def create_app(config_name='default'):
    """Factory pour créer l'application Flask"""
    app = Flask(__name__)

    # Ajouter à votre create_app() ou au début de app.py
    security_logger = setup_logging(app)
    
    # Configuration
    #app.config.from_object(config[config_name])
    app.config.from_object(get_config(config_name))
    
    # Initialisation des extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    # Configuration des dossiers (existant)
    app.config['UPLOAD_FOLDER'] = app.config.get('UPLOAD_FOLDER', 'uploads')
    app.config['OUTPUT_FOLDER'] = app.config.get('OUTPUT_FOLDER', 'output')
    
    return app

# Création de l'application
app = create_app(os.getenv('FLASK_ENV', 'development'))

#app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # À changer en production




@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])  
def upload_file():
    """Traite le fichier PDF uploadé avec débogage"""

    #if 'file' in request.files:
     #   app.logger.info(f"Nom du fichier chargé: {request.files['file'].filename}")
    #app.logger.info("===============")

    """Traite le fichier PDF uploadé avec protection contre les soumissions multiples"""
    global is_processing
    
    # Vérification côté serveur pour empêcher les traitements multiples
    with processing_lock:
        if is_processing:
            flash('Un traitement est déjà en cours. Veuillez patienter.', 'error')
            return redirect(request.url)
        is_processing = True
    
    try:
        if 'file' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(url_for('index'))
        
        file = request.files['file']
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(url_for('index'))
        
        if file and allowed_file(file.filename):
            try:
                # Génération du timestamp pour l'organisation des dossiers
                timestamp_folder = generate_timestamp_folder()
                
                # Création des dossiers avec timestamp
                upload_timestamp_dir = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_folder)
                output_timestamp_dir = os.path.join(app.config['OUTPUT_FOLDER'], timestamp_folder)
                
                os.makedirs(upload_timestamp_dir, exist_ok=True)
                os.makedirs(output_timestamp_dir, exist_ok=True)
                
                # Sauvegarde du fichier dans le dossier timestampé
                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_timestamp_dir, filename)
                file.save(filepath)
                
                # Traitement du PDF avec les nouveaux chemins
                result = process_pdf(filepath, output_timestamp_dir, app)
                
                if result['success']:
                    flash(f'✅ Traitement terminé avec succès ! {result["count"]} fiches traitées. Dossier : {timestamp_folder}', 'success')
                else:
                    flash(f'❌ Erreur lors du traitement: {result["error"]}', 'error')
                
            except Exception as e:
                flash(f'❌ Erreur inattendue: {str(e)}', 'error')
                
        else:
            flash('❌ Format de fichier non autorisé. Utilisez un PDF.', 'error')
            
    finally:
        # Libérer le verrou même en cas d'erreur
        with processing_lock:
            is_processing = False
            
    return redirect(url_for('index'))


    
@app.route('/download/<token>')
def secure_download_page(token):
    """Page de téléchargement sécurisé"""
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        
        if not download_link:
            flash('Lien de téléchargement invalide ou expiré', 'error')
            return render_template('download_error.html', error="Lien invalide")
        
        if not download_link.is_valid:
            if download_link.tentatives_acces >= download_link.max_tentatives:
                error_msg = "Nombre maximum de tentatives dépassé"
            else:
                error_msg = "Lien expiré"
            
            flash(f'Accès refusé : {error_msg}', 'error')
            return render_template('download_error.html', error=error_msg)
        
        return render_template('secure_download.html', 
                             download_link=download_link,
                             employee=download_link.employee)
        
    except Exception as e:
        flash(f'Erreur lors de l\'accès au lien : {str(e)}', 'error')
        return render_template('download_error.html', error="Erreur système")


@app.route('/download/<token>/verify', methods=['POST'])
def verify_and_download(token):
    """Vérification avec réponse JSON pour gestion JavaScript"""
    
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        matricule_saisi = request.form.get('matricule', '').strip()
        client_ip = request.remote_addr
        
        # Log de la tentative d'accès
        app.logger.info(f"🔑 Tentative d'accès - Token: {token[:8]}... IP: {client_ip}")
        
        download_link.tentatives_acces += 1
        download_link.adresse_ip_derniere = client_ip
        
        if matricule_saisi != download_link.matricule_requis:
            db.session.commit()
            app.logger.error(f"🚨 ÉCHEC D'AUTHENTIFICATION - Token: {token[:8]}...")
            remaining = download_link.max_tentatives - download_link.tentatives_acces
            
            return jsonify({
                'success': False,
                'message': f'Matricule incorrect. {remaining} tentatives restantes.',
                'remaining_attempts': remaining
            }), 400
        
        # Log succès
        app.logger.info(f"✅ TÉLÉCHARGEMENT AUTORISÉ - Employé: {download_link.employee.nom_employe}")
        
        download_link.nombre_telechargements += 1
        download_link.derniere_date_telechargement = datetime.utcnow()
        db.session.commit()
        
        if not os.path.exists(download_link.chemin_fichier):
            return jsonify({
                'success': False,
                'message': 'Fichier non trouvé sur le serveur.'
            }), 404
        
        # 🔧 RETOURNER SUCCÈS AVEC URL DE TÉLÉCHARGEMENT
        return jsonify({
            'success': True,
            'message': 'Téléchargement autorisé avec succès !',
            'download_url': f'/download/file/{token}',
            'employee_name': download_link.employee.nom_employe,
            'filename': download_link.nom_fichier,
            'download_count': download_link.nombre_telechargements
        })
        
    except Exception as e:
        app.logger.error(f"❌ Erreur téléchargement sécurisé: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Erreur serveur lors du téléchargement.'
        }), 500


@app.route('/download/file/<token>')
def download_file_direct(token):
    """Téléchargement direct du fichier"""
    
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        
        if not download_link or download_link.nombre_telechargements == 0:
            return "Téléchargement non autorisé", 403
        
        if not os.path.exists(download_link.chemin_fichier):
            return "Fichier non trouvé", 404
        
        return send_file(download_link.chemin_fichier, 
                        as_attachment=True, 
                        download_name=download_link.nom_fichier)
        
    except Exception as e:
        app.logger.error(f"❌ Erreur téléchargement direct: {str(e)}")
        return "Erreur de téléchargement", 500


@app.route('/download/success')
def download_success():
    """Page de remerciement après téléchargement réussi"""
    
    token = request.args.get('token')
    employee_name = request.args.get('employee_name', 'Employé')
    filename = request.args.get('filename', 'votre fiche de paie')
    
    if not token:
        return redirect(url_for('index'))
    
    # Vérifier que le lien existe et a été utilisé
    download_link = DownloadLink.query.filter_by(token=token).first()
    if not download_link or download_link.nombre_telechargements == 0:
        return redirect(url_for('index'))
    
    return render_template('download_success.html',
                         employee_name=employee_name,
                         filename=filename,
                         download_count=download_link.nombre_telechargements,
                         company_name="PayFlow")


'''
@app.route('/download/file/<token>')
def download_file_secure(token):
    """Téléchargement direct du fichier (appelé depuis la page de succès)"""
    
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        
        if not download_link or download_link.nombre_telechargements == 0:
            flash('Lien de téléchargement non autorisé', 'error')
            return redirect(url_for('index'))
        
        # Vérifier que le fichier existe
        if not os.path.exists(download_link.chemin_fichier):
            flash('Fichier non trouvé', 'error')
            return redirect(url_for('download_success', token=token))
        
        # Téléchargement du fichier
        return send_file(download_link.chemin_fichier, 
                        as_attachment=True, 
                        download_name=download_link.nom_fichier)
        
    except Exception as e:
        app.logger.error(f"Erreur téléchargement fichier: {str(e)}")
        flash('Erreur lors du téléchargement', 'error')
        return redirect(url_for('index'))
'''

@app.route('/download/show-success')
def show_download_success():
    """Affiche la page de succès après téléchargement"""
    
    # 🔍 DEBUG : Afficher le contenu de la session
    app.logger.info(f"🔍 SESSION CONTENT: {dict(session)}")
    
    # Récupérer les infos depuis la session
    success_info = session.get('download_success')
    
    if not success_info:
        app.logger.warning("⚠️ Pas d'info de succès en session, redirection vers index")
        return redirect(url_for('index'))
    
    app.logger.info(f"✅ Info succès trouvée: {success_info}")
    
    # Garder les infos mais ne pas les supprimer tout de suite pour debug
    # session.pop('download_success', None)  # Commenté temporairement
    
    return render_template('download_success.html',
                         employee_name=success_info['employee_name'],
                         filename=success_info['filename'],
                         download_count=success_info['download_count'],
                         company_name="PayFlow")


@app.route('/dashboard')
def dashboard():
    """Dashboard simplifié v1.2 - Sans graphiques"""
    try:
        # Statistiques v1.2 essentielles
        stats_v12 = get_v12_dashboard_stats(app)
        
        # Activité récente
        recent_activity = get_recent_activity(app)

        # Top employés (sans graphique)
        top_employees = get_employee_top_stats(app)

        # Derniers traitements (PostgreSQL prioritaire)
        treatments = get_treatments_from_db(app)
        if not treatments:
            treatments = get_treatments_from_filesystem(app)
            for treatment in treatments:
                treatment['source'] = 'Filesystem'
        
        # Limiter à 10 pour performance
        treatments = treatments[:10]
        
        return render_template('dashboard.html', 
                             stats_v12=stats_v12,
                             recent_activity=recent_activity,
                             top_employees=top_employees,
                             treatments=treatments)
        
    except Exception as e:
        flash(f'Erreur dashboard: {str(e)}', 'error')
        return redirect(url_for('index'))


from flask import send_file

@app.route('/download/<timestamp>/<filename>')
def download_file(timestamp, filename):
    """Permet de télécharger un fichier PDF généré"""
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], timestamp, filename)
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            flash('Fichier non trouvé', 'error')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        flash(f'Erreur lors du téléchargement: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/cleanup')
def cleanup_files():
    """Nettoie les fichiers de plus de 30 jours"""
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=30)
        deleted_folders = 0
        
        # Nettoyage des uploads
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for folder in os.listdir(app.config['UPLOAD_FOLDER']):
                try:
                    folder_date = datetime.strptime(folder, '%Y%m%d%H%M%S')
                    if folder_date < cutoff_date:
                        import shutil
                        shutil.rmtree(os.path.join(app.config['UPLOAD_FOLDER'], folder))
                        deleted_folders += 1
                except ValueError:
                    continue  # Ignore les dossiers qui ne correspondent pas au format
        
        # Nettoyage des outputs
        if os.path.exists(app.config['OUTPUT_FOLDER']):
            for folder in os.listdir(app.config['OUTPUT_FOLDER']):
                try:
                    folder_date = datetime.strptime(folder, '%Y%m%d%H%M%S')
                    if folder_date < cutoff_date:
                        import shutil
                        shutil.rmtree(os.path.join(app.config['OUTPUT_FOLDER'], folder))
                except ValueError:
                    continue
        
        flash(f'Nettoyage terminé ! {deleted_folders} dossier(s) supprimé(s) (+ de 30 jours)', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Erreur lors du nettoyage: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    

# Routes pour la gestion des employés
@app.route('/admin')
def admin_dashboard():
    """Dashboard administrateur"""
    return redirect(url_for('manage_employees'))


@app.route('/admin/employees')
def manage_employees():
    """Interface de gestion des employés"""
    try:
        # Pagination pour de gros volumes
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str)
        
        # Construction de la requête
        query = Employee.query
        
        if search:
            query = query.filter(
                db.or_(
                    Employee.nom_employe.ilike(f'%{search}%'),
                    Employee.email.ilike(f'%{search}%'),
                    Employee.matricule.ilike(f'%{search}%')
                )
            )
        
        employees = query.order_by(Employee.nom_employe.asc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Statistiques rapides
        stats = {
            'total_employees': Employee.query.count(),
            'active_employees': Employee.query.filter_by(statut='actif').count(),
            'pdf_imported': Employee.query.filter_by(source_creation='pdf_import').count(),
            'manual_added': Employee.query.filter_by(source_creation='manual').count()
        }
        
        return render_template('admin/manage_employees.html', 
                             employees=employees, 
                             stats=stats,
                             search=search)
        
    except Exception as e:
        flash(f'Erreur lors du chargement : {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/admin/employees/add', methods=['GET', 'POST'])
def add_employee():
    """Ajouter un nouvel employé"""
    if request.method == 'POST':
        try:
            nom_employe = request.form.get('nom_employe', '').strip()
            email = request.form.get('email', '').strip()
            matricule = request.form.get('matricule', '').strip()
            
            # Validations
            if not nom_employe or not email:
                flash('Nom et email sont obligatoires', 'error')
                return render_template('admin/add_employee.html')
            
            # Vérifier unicité email
            if Employee.query.filter_by(email=email).first():
                flash('Un employé avec cet email existe déjà', 'error')
                return render_template('admin/add_employee.html')
            
            # Vérifier unicité matricule si fourni
            if matricule and Employee.query.filter_by(matricule=matricule).first():
                flash('Un employé avec ce matricule existe déjà', 'error')
                return render_template('admin/add_employee.html')
            
            # Création de l'employé
            new_employee = Employee(
                nom_employe=nom_employe,
                email=email,
                matricule=matricule if matricule else None,
                statut='actif',
                source_creation='manual'
            )
            
            db.session.add(new_employee)
            db.session.commit()
            
            flash(f'Employé {nom_employe} ajouté avec succès', 'success')
            return redirect(url_for('manage_employees'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erreur lors de l\'ajout : {str(e)}', 'error')
    
    return render_template('admin/add_employee.html')


@app.route('/admin/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
def edit_employee(employee_id):
    """Modifier un employé existant avec restrictions selon la source"""
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        try:
            #  Restrictions selon la source de création
            is_pdf_imported = employee.source_creation == 'pdf_import'
            
            if is_pdf_imported:
                #  Employé PDF : Email + Statut modifiables seulement
                email = request.form.get('email', '').strip()
                statut = request.form.get('statut', 'actif')
                
                if not email:
                    flash('Email obligatoire', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité email (sauf pour l'employé actuel)
                existing_email = Employee.query.filter(
                    Employee.email == email,
                    Employee.id != employee_id
                ).first()
                if existing_email:
                    flash('Un autre employé utilise déjà cet email', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Mise à jour email + statut seulement
                employee.email = email
                employee.statut = statut
                employee.date_derniere_maj = datetime.utcnow()
                
                db.session.commit()
                flash(f'Email et statut mis à jour pour {employee.nom_employe} (importé PDF)', 'success')
                
            else:
                # Employé manuel : Toutes modifications autorisées
                nom_employe = request.form.get('nom_employe', '').strip()
                email = request.form.get('email', '').strip()
                matricule = request.form.get('matricule', '').strip()
                statut = request.form.get('statut', 'actif')
                
                # Validations complètes
                if not nom_employe or not email:
                    flash('Nom et email sont obligatoires', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité email
                existing_email = Employee.query.filter(
                    Employee.email == email,
                    Employee.id != employee_id
                ).first()
                if existing_email:
                    flash('Un autre employé utilise déjà cet email', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité matricule
                if matricule:
                    existing_matricule = Employee.query.filter(
                        Employee.matricule == matricule,
                        Employee.id != employee_id
                    ).first()
                    if existing_matricule:
                        flash('Un autre employé utilise déjà ce matricule', 'error')
                        return render_template('admin/edit_employee.html', employee=employee)
                
                # Mise à jour complète
                employee.nom_employe = nom_employe
                employee.email = email
                employee.matricule = matricule if matricule else None
                employee.statut = statut
                employee.date_derniere_maj = datetime.utcnow()
                
                db.session.commit()
                flash(f'Employé {nom_employe} modifié avec succès', 'success')
            
            return redirect(url_for('manage_employees'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erreur lors de la modification : {str(e)}', 'error')
    
    return render_template('admin/edit_employee.html', employee=employee)


@app.route('/admin/employees/<int:employee_id>/delete', methods=['POST'])
def delete_employee(employee_id):
    """Supprimer un employé (soft delete)"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Soft delete - changement de statut
        employee.statut = 'supprime'
        employee.date_derniere_maj = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Employé {employee.nom_employe} supprimé', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))


@app.route('/admin/employees/export')
def export_employees():
    """Exporter la liste des employés en CSV"""
    try:
        import io
        import csv
        
        # Créer le CSV en mémoire
        output = io.StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow(['Matricule', 'Nom', 'Email', 'Statut', 'Source', 'Date création'])
        
        # Données
        employees = Employee.query.order_by(Employee.nom_employe.asc()).all()
        for emp in employees:
            writer.writerow([
                emp.matricule or '',
                emp.nom_employe,
                emp.email,
                emp.statut,
                emp.source_creation,
                emp.date_creation.strftime('%d/%m/%Y %H:%M')
            ])
        
        # Préparation du téléchargement
        output.seek(0)
        
        from flask import make_response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=employes_payflow_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
        
    except Exception as e:
        flash(f'Erreur lors de l\'export : {str(e)}', 'error')
        return redirect(url_for('manage_employees'))

# Nouvelles fonctions pour dashboard enrichi v1.2
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta


# Routes de maintenance système
@app.route('/admin/maintenance')
def maintenance_page():
    """Page de maintenance et nettoyage système"""
    try:
        # Statistiques de maintenance
        maintenance_stats = get_maintenance_stats(app)
        
        return render_template('admin/maintenance.html', 
                             stats=maintenance_stats)
        
    except Exception as e:
        flash(f'Erreur lors du chargement de la maintenance: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/admin/maintenance/cleanup', methods=['POST'])
def execute_cleanup():
    """Exécute le nettoyage système"""
    try:
        cleanup_type = request.form.get('cleanup_type', 'all')
        confirm = request.form.get('confirm', '') == 'true'
        
        if not confirm:
            flash('Veuillez confirmer l\'opération de nettoyage', 'error')
            return redirect(url_for('maintenance_page'))
        
        results = perform_system_cleanup(cleanup_type)
        
        if results['success']:
            flash(f'Nettoyage réussi: {results["message"]}', 'success')
        else:
            flash(f'Erreur nettoyage: {results["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors du nettoyage: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))


@app.route('/admin/maintenance/backup', methods=['POST'])
def create_backup():
    """Crée une sauvegarde de la base de données"""
    try:
        backup_result = create_database_backup()
        
        if backup_result['success']:
            flash(f'Sauvegarde créée: {backup_result["filename"]}', 'success')
        else:
            flash(f'Erreur sauvegarde: {backup_result["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors de la sauvegarde: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))


@app.route('/admin/maintenance/optimize', methods=['POST'])
def optimize_database():
    """Optimise la base de données"""
    try:
        optimize_result = perform_database_optimization()
        
        if optimize_result['success']:
            flash(f'Optimisation réussie: {optimize_result["message"]}', 'success')
        else:
            flash(f'Erreur optimisation: {optimize_result["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors de l\'optimisation: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))


@app.route('/admin/treatment/<timestamp>/details')
def treatment_details(timestamp):
    """Affiche les détails d'un traitement avec liste des PDFs générés"""
    try:
        # Récupérer le traitement depuis PostgreSQL
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Récupérer les fichiers générés depuis le dossier output
        output_folder = os.path.join(app.config['OUTPUT_FOLDER'], timestamp)
        generated_files = []
        
        if os.path.exists(output_folder):
            for filename in os.listdir(output_folder):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(output_folder, filename)
                    file_size = os.path.getsize(file_path)
                    
                    # Extraire le nom de l'employé du nom de fichier
                    employee_name = filename.replace('.pdf', '').replace('_', ' ')
                    # Enlever la période si présente (ex: "2025_08")
                    import re
                    employee_name = re.sub(r'_\d{4}_\d{2}$', '', employee_name)
                    
                    # 🆕 RÉCUPÉRER LES STATISTIQUES DEPUIS LA BASE
                    access_count = 0
                    download_count = 0
                    
                    # Chercher dans les download_links du traitement
                    for link in traitement.download_links:
                        # Correspondance par nom de fichier exact
                        if link.nom_fichier == filename:
                            access_count = link.tentatives_acces
                            download_count = link.nombre_telechargements
                            break
                        # Correspondance par nom d'employé dans le nom de fichier
                        elif link.employee and link.employee.nom_employe:
                            # Normaliser les noms pour comparaison
                            db_name = link.employee.nom_employe.strip().upper()
                            file_name = employee_name.strip().upper()
                            if db_name == file_name or db_name in filename.upper():
                                access_count = link.tentatives_acces
                                download_count = link.nombre_telechargements
                                break
                    
                    generated_files.append({
                        'filename': filename,
                        'employee_name': employee_name,
                        'file_size': format_file_size(file_size),
                        'file_path': file_path,
                        'access_count': access_count,      
                        'download_count': download_count   
                    })
        
        # Trier par nom d'employé
        generated_files.sort(key=lambda x: x['employee_name'])
        
        return render_template('admin/treatment_details.html',
                             traitement=traitement,
                             generated_files=generated_files,
                             total_files=len(generated_files))
        
    except Exception as e:
        flash(f'Erreur lors du chargement des détails : {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.route('/admin/treatment/<timestamp>/download/<filename>')
def download_generated_pdf(timestamp, filename):
    """Télécharge un PDF généré spécifique"""
    try:
        # Vérifier que le traitement existe
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Construire le chemin du fichier
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], timestamp, filename)
        
        if not os.path.exists(file_path):
            flash('Fichier non trouvé', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        # Téléchargement sécurisé
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        flash(f'Erreur lors du téléchargement : {str(e)}', 'error')
        return redirect(url_for('treatment_details', timestamp=timestamp))


@app.route('/admin/treatment/<timestamp>/download-all')
def download_all_generated_pdfs(timestamp):
    """Télécharge tous les PDFs générés d'un traitement en ZIP"""
    try:
        import zipfile
        import io
        
        # Vérifier que le traitement existe
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Dossier des fichiers générés
        output_folder = os.path.join(app.config['OUTPUT_FOLDER'], timestamp)
        if not os.path.exists(output_folder):
            flash('Dossier de fichiers non trouvé', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        # Créer le ZIP en mémoire
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Ajouter tous les PDFs au ZIP
            pdf_count = 0
            for filename in os.listdir(output_folder):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(output_folder, filename)
                    zip_file.write(file_path, filename)
                    pdf_count += 1
        
        if pdf_count == 0:
            flash('Aucun PDF trouvé dans ce traitement', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        zip_buffer.seek(0)
        
        # Nom du fichier ZIP
        zip_filename = f"payflow_fiches_{timestamp}_{pdf_count}files.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        flash(f'Erreur lors de la création du ZIP : {str(e)}', 'error')
        return redirect(url_for('treatment_details', timestamp=timestamp))


@app.route('/admin/logs')
def view_logs():
    """Interface de consultation des logs"""
    try:
        log_type = request.args.get('type', 'general')
        lines = int(request.args.get('lines', 100))
        
        log_files = {
            'general': 'logs/payflow.log',
            'errors': 'logs/payflow_errors.log', 
            'security': 'logs/payflow_security.log'
        }
        
        log_file = log_files.get(log_type, 'logs/payflow.log')
        log_content = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.readlines()[-lines:]  # Dernières lignes
        
        # Statistiques des logs
        log_stats = {
            'general_size': get_file_size('logs/payflow.log'),
            'errors_size': get_file_size('logs/payflow_errors.log'),
            'security_size': get_file_size('logs/payflow_security.log'),
            'total_lines': len(log_content)
        }
        
        return render_template('admin/logs.html', 
                             log_content=log_content,
                             log_type=log_type,
                             log_stats=log_stats,
                             lines=lines)
        
    except Exception as e:
        app.logger.error(f"Erreur consultation logs: {str(e)}")
        flash(f'Erreur lors de la consultation des logs: {str(e)}', 'error')
        return redirect(url_for('dashboard'))



# Démarrage de l'application
if __name__ == '__main__':
    # Création des dossiers
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

    # Certificats mkcert
    ##cert_file = '192.168.1.55+2.pem'
    ##key_file = '192.168.1.55+2-key.pem'

    print("🔒 PayFlow v2.0")
    print("🌐 Accès : http://192.168.1.55:5000")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True,
       # ssl_context=(cert_file, key_file)
    )

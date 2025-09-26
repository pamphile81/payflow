# models.py
from datetime import datetime, timedelta
#from flask_sqlalchemy import SQLAlchemy
import secrets
#import hashlib
import secrets
from app.extensions import db


#db = SQLAlchemy()

class Employee(db.Model):
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(20), unique=True, nullable=False)  # Maintenant obligatoire et unique
    nom_employe = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_derniere_maj = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    statut = db.Column(db.String(20), default='actif')
    source_creation = db.Column(db.String(50), default='pdf_import')
    
    # Relations
    traitements_employes = db.relationship('TraitementEmploye', backref='employee', lazy=True)
    #download_links = db.relationship('DownloadLink', backref='employee', lazy=True)
    
    def __repr__(self):
        return f'<Employee {self.matricule}: {self.nom_employe}>'

# Index pour performance
db.Index('idx_employee_matricule', Employee.matricule)


class Traitement(db.Model):
    """Modèle pour l'historique des traitements"""
    __tablename__ = 'traitements'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp_folder = db.Column(db.String(20), unique=True, nullable=False)
    fichier_original = db.Column(db.String(500))
    taille_fichier = db.Column(db.BigInteger)
    nombre_pages = db.Column(db.Integer)
    nombre_employes_detectes = db.Column(db.Integer)
    nombre_employes_traites = db.Column(db.Integer)
    nombre_nouveaux_employes = db.Column(db.Integer, default=0)
    duree_traitement_secondes = db.Column(db.Integer)
    statut = db.Column(db.String(20), default='en_cours')
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    erreurs = db.Column(db.Text)
    
    # Relations
    traitement_employes = db.relationship('TraitementEmploye', backref='traitement', lazy=True)
    
    def __repr__(self):
        return f'<Traitement {self.timestamp_folder}>'

class TraitementEmploye(db.Model):
    """Modèle de liaison traitement-employé"""
    __tablename__ = 'traitement_employes'
    
    id = db.Column(db.Integer, primary_key=True)
    traitement_id = db.Column(db.Integer, db.ForeignKey('traitements.id'), nullable=False)
    employe_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    matricule_extrait = db.Column(db.String(20))
    periode_extraite = db.Column(db.String(10))  # Format: YYYY_MM
    nom_fichier_genere = db.Column(db.String(500))
    email_envoye = db.Column(db.Boolean, default=False)
    date_email = db.Column(db.DateTime)
    erreur_email = db.Column(db.Text)
    
    def __repr__(self):
        return f'<TraitementEmploye {self.employe_id}>'


import secrets
from datetime import datetime, timedelta

class DownloadLink(db.Model):
    """Liens de téléchargement sécurisés pour les fiches de paie"""
    __tablename__ = 'download_links'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    employe_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    traitement_id = db.Column(db.Integer, db.ForeignKey('traitements.id'), nullable=False)
    nom_fichier = db.Column(db.String(500), nullable=False)
    chemin_fichier = db.Column(db.String(1000), nullable=False)
    
    # Sécurité
    matricule_requis = db.Column(db.String(20), nullable=False)
    tentatives_acces = db.Column(db.Integer, default=0)
    max_tentatives = db.Column(db.Integer, default=10)
    
    # Audit
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_expiration = db.Column(db.DateTime, nullable=False)  #  CORRECT
    date_premier_acces = db.Column(db.DateTime)
    date_dernier_acces = db.Column(db.DateTime)
    nombre_telechargements = db.Column(db.Integer, default=0)
    adresse_ip_derniere = db.Column(db.String(45))
    
    # Statut
    statut = db.Column(db.String(20), default='actif')
    
    def __init__(self, **kwargs):
        super(DownloadLink, self).__init__(**kwargs)
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.date_expiration:
            self.date_expiration = datetime.utcnow() + timedelta(days=30)
    
    @property
    def is_valid(self):
        """Vérifie si le lien est encore valide"""
        return (
            self.statut == 'actif' and
            datetime.utcnow() < self.date_expiration and
            self.tentatives_acces < self.max_tentatives
        )
    
    @property
    def expires_in_days(self):
        """Nombre de jours avant expiration"""
        if datetime.utcnow() > self.date_expiration:
            return 0
        delta = self.date_expiration - datetime.utcnow()
        return delta.days
    
    def __repr__(self):
        return f'<DownloadLink {self.token[:8]}... pour {self.employee.nom_employe}>'

#  Relations à la fin du fichier models.py
Employee.download_links = db.relationship('DownloadLink', backref='employee', lazy=True)
Traitement.download_links = db.relationship('DownloadLink', backref='traitement', lazy=True)

    
# Index pour améliorer les performances
db.Index('idx_download_token', DownloadLink.token)
##db.Index('idx_download_expires', DownloadLink.expires_at)
db.Index('idx_employee_email', Employee.email)
db.Index('idx_traitement_timestamp', Traitement.timestamp_folder)

# Relations
Employee.download_links = db.relationship('DownloadLink', backref='employee', lazy=True)
Traitement.download_links = db.relationship('DownloadLink', backref='traitement', lazy=True)

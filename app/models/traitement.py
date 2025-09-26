from datetime import datetime
from app.extensions import db

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
    download_links = db.relationship('DownloadLink', backref='traitement', lazy=True)

    def __repr__(self):
        return f'<Traitement {self.timestamp_folder}>'

# Index
db.Index('idx_traitement_timestamp', Traitement.timestamp_folder)

from app.extensions import db

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

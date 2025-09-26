from datetime import datetime
from app.extensions import db

class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(20), unique=True, nullable=False)
    nom_employe = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_derniere_maj = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    statut = db.Column(db.String(20), default='actif')
    source_creation = db.Column(db.String(50), default='pdf_import')

    # Relations
    traitements_employes = db.relationship('TraitementEmploye', backref='employee', lazy=True)
    download_links = db.relationship('DownloadLink', backref='employee', lazy=True)

    def __repr__(self):
        return f'<Employee {self.matricule}: {self.nom_employe}>'

# Index
db.Index('idx_employee_matricule', Employee.matricule)
db.Index('idx_employee_email', Employee.email)

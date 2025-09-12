
# PayFlow v1.2 - Gestionnaire de Fiches de Paie Automatisé

🚀 **Application Flask complète pour la gestion et distribution automatisée des fiches de paie**

## ✨ Fonctionnalités v1.2

### 🎯 Fonctionnalités principales
- **📄 Traitement PDF intelligent** : Découpage automatique des PDFs multi-employés
- **🔐 Protection sécurisée** : Chaque fiche protégée par le matricule employé
- **📧 Distribution par liens** : Envoi de liens de téléchargement sécurisés
- **👥 Gestion des employés** : Interface complète CRUD avec restrictions
- **📊 Dashboard analytique** : Statistiques temps réel et historique
- **🛠️ Maintenance système** : Nettoyage automatique et optimisation
- **🗃️ Base PostgreSQL** : Stockage robuste avec migration automatique

### 🆕 Nouveautés v1.2
- **Auto-import employés** depuis les PDFs traités
- **Téléchargements sécurisés** avec authentification par matricule
- **Gestion différenciée** : Restrictions pour employés importés PDF
- **Interface moderne** : Templates responsive et intuitifs
- **Détails des traitements** : Visualisation et téléchargement des PDFs générés
- **Maintenance avancée** : Outils de nettoyage et optimisation

## 🏗️ Architecture Technique

### Technologies utilisées
- **Backend** : Python 3.7+ / Flask 2.3+
- **Base de données** : PostgreSQL avec SQLAlchemy
- **Frontend** : HTML5 / CSS3 / JavaScript ES6
- **Traitement PDF** : PyPDF2 / pikepdf
- **Email** : SMTP avec authentification sécurisée
- **Sécurité** : Liens tokenisés / Authentification matricule

### Structure du projet
payflow/
├── app.py # Application Flask principale
├── models.py # Modèles de données SQLAlchemy
├── email_config.py # Configuration SMTP
├── requirements.txt # Dépendances Python
├── templates/
│ ├── index.html # Page d'upload
│ ├── dashboard_simple_v12.html # Dashboard principal
│ ├── secure_download.html # Interface téléchargement
│ └── admin/ # Templates administration
│ ├── manage_employees.html
│ ├── add_employee.html
│ ├── edit_employee.html
│ ├── maintenance.html
│ └── treatment_details.html
├── uploads/ # PDFs uploadés (temporaire)
├── output/ # PDFs individuels générés
└── migrations/ # Migrations base de données

text

## 🚀 Installation et Déploiement

### Prérequis
Système requis
Python 3.7 ou supérieur

PostgreSQL 12+

Git

Compte email avec authentification 2FA (recommandé Gmail)
text

### Installation rapide
1. Cloner le repository
git clone https://github.com/votre-username/payflow.git
cd payflow

2. Créer l'environnement virtuel
python -m venv venv

3. Activer l'environnement
Windows
venv\Scripts\activate

Linux/Mac
source venv/bin/activate

4. Installer les dépendances
pip install -r requirements.txt

5. Configurer PostgreSQL
createdb payflow_db
createuser payflow_user --password

6. Configurer l'email dans email_config.py
cp email_config.py.example email_config.py

Éditer avec vos paramètres SMTP
7. Initialiser la base de données
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

8. Lancer l'application
python app.py

text

### Accès à l'application
- **Interface principale** : http://127.0.0.1:5000
- **Dashboard** : http://127.0.0.1:5000/dashboard
- **Gestion employés** : http://127.0.0.1:5000/admin/employees
- **Maintenance** : http://127.0.0.1:5000/admin/maintenance

## 📖 Guide d'utilisation

### 1. Configuration initiale
1. **Configurer SMTP** dans `email_config.py`
2. **Ajouter des employés** via l'interface ou CSV
3. **Tester avec un PDF** de démonstration

### 2. Traitement des fiches de paie
1. **Accéder** à l'interface d'upload
2. **Sélectionner** votre PDF multi-employés  
3. **Lancer** le traitement automatique
4. **Vérifier** les résultats dans le dashboard

### 3. Gestion des employés
- **Ajout manuel** : Interface dédiée avec validation
- **Import automatique** : Détection lors du traitement PDF
- **Modification** : Restrictions selon la source (PDF vs manuel)
- **Export** : Sauvegarde CSV de la base employés

### 4. Téléchargements sécurisés
- **Liens par email** : Envoi automatique aux employés
- **Authentification** : Matricule requis pour accéder
- **Expiration** : Liens valides 30 jours par défaut
- **Audit** : Traçabilité complète des accès

## 🔧 Configuration Avancée

### Variables d'environnement
Database
DATABASE_URL=postgresql://payflow_user:password@localhost/payflow_db

Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=votre-email@gmail.com
SMTP_PASSWORD=votre-mot-de-passe-app

Security
SECRET_KEY=votre-clé-secrète-très-longue
DOWNLOAD_EXPIRY_DAYS=30
MAX_ATTEMPTS=10

text

### Personnalisation
- **Templates** : Modifier les fichiers HTML dans `/templates/`
- **Emails** : Personnaliser les messages dans les fonctions d'envoi
- **Sécurité** : Ajuster les paramètres d'expiration et tentatives
- **Logos** : Remplacer les émoticônes par vos logos d'entreprise

## 🔒 Sécurité

### Mesures implémentées
- **🔐 Authentification matricule** pour chaque téléchargement
- **⏰ Expiration automatique** des liens de téléchargement  
- **🚫 Limitation des tentatives** d'accès par lien
- **📝 Audit complet** des actions utilisateurs
- **🛡️ Protection CSRF** sur tous les formulaires
- **🔒 PDFs chiffrés** avec mots de passe individuels

### Bonnes pratiques
- Utiliser **HTTPS en production**
- Configurer **mots de passe forts** pour la base
- **Sauvegarder régulièrement** via l'interface maintenance
- **Nettoyer périodiquement** les fichiers temporaires

## 📊 Monitoring et Maintenance

### Dashboard de surveillance
- **Statistiques temps réel** : Traitements, employés, téléchargements
- **Indicateurs de sécurité** : Tentatives bloquées, incidents
- **Historique complet** : Tous les traitements avec détails
- **État système** : Santé globale de l'application

### Outils de maintenance
- **Nettoyage automatique** : Suppression fichiers expirés
- **Sauvegarde base** : Export PostgreSQL intégré  
- **Optimisation** : VACUUM ANALYZE automatique
- **Logs détaillés** : Traçabilité complète des opérations

## 🤝 Contribution

### Pour les développeurs
Setup développement
git clone https://github.com/votre-username/payflow.git
cd payflow
python -m venv venv
source venv/bin/activate # ou venv\Scripts\activate sur Windows
pip install -r requirements.txt

Tests
python -m pytest tests/

Nouveau feature
git checkout -b feature/nouvelle-fonctionnalité

... développement ...
git commit -m "feat: description de la fonctionnalité"
git push origin feature/nouvelle-fonctionnalité

text

### Standards de code
- **PEP 8** pour Python
- **Commentaires** en français dans le code
- **Templates** responsives et accessibles
- **Messages** utilisateur clairs et informatifs

## 📝 Changelog

### v1.2.0 (2025-09-12)
#### ✨ Ajouts
- Interface complète de gestion des employés
- Téléchargements sécurisés avec authentification matricule
- Auto-import des employés depuis les PDFs
- Page de maintenance avec outils de nettoyage
- Dashboard enrichi avec détails des traitements
- Migration PostgreSQL avec données historiques
- Templates modernes et responsives

#### 🔧 Améliorations  
- Restrictions de modification pour employés PDF
- Navigation améliorée entre les sections
- Gestion d'erreurs renforcée
- Performance optimisée des requêtes
- Interface utilisateur moderne et intuitive

#### 🐛 Corrections
- Problèmes de templating JavaScript
- Gestion des caractères spéciaux dans les noms
- Validation des données utilisateur
- Stabilité des téléchargements

### v1.1.0 (2025-09-10)
#### ✨ Ajouts
- Dashboard avec statistiques
- Nettoyage automatique des fichiers
- Interface responsive améliorée

### v1.0.0 (2025-09-08)
#### ✨ Version initiale
- Traitement PDF de base
- Protection par mot de passe
- Envoi email avec pièces jointes

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 🆘 Support

### Documentation
- **Wiki** : [Documentation complète](https://github.com/votre-username/payflow/wiki)
- **FAQ** : [Questions fréquentes](https://github.com/votre-username/payflow/wiki/FAQ)
- **Tutoriels** : [Guides pas à pas](https://github.com/votre-username/payflow/wiki/Tutorials)

### Obtenir de l'aide
- **Issues** : [Signaler un bug](https://github.com/votre-username/payflow/issues)
- **Discussions** : [Forum communautaire](https://github.com/votre-username/payflow/discussions)
- **Email** : support@payflow.com

---

## ⭐ Remerciements

Merci à tous les contributeurs qui ont rendu PayFlow possible !

**PayFlow v1.2** - Automatisation intelligente des fiches de paie 🚀
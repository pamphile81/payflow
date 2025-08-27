# PayFlow v1.0 🚀

**Application web automatique de gestion et distribution des fiches de paie**

![Version](https://img.shields.io/badge/version-1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.7+-green.svg)
![License](https://img.shields.io/badge/license-MIT-yellow.svg)

---

## 📋 Table des matières

- [🎯 Présentation](#-présentation)
- [✨ Fonctionnalités](#-fonctionnalités)  
- [🛠️ Technologies](#️-technologies)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [🚀 Utilisation](#-utilisation)
- [📁 Structure des fichiers](#-structure-des-fichiers)
- [🔒 Sécurité](#-sécurité)
- [🤝 Contribution](#-contribution)
- [📄 Licence](#-licence)

---

## 🎯 Présentation

PayFlow automatise entièrement le processus de distribution des fiches de paie en entreprise. L'application analyse un fichier PDF contenant plusieurs bulletins de paie, découpe automatiquement chaque fiche individuelle, la protège par mot de passe, et l'envoie directement à l'employé concerné par email.

### 🎪 Cas d'usage

- **PME/ETI** : Automatisation complète de la distribution mensuelle
- **Services RH** : Gain de temps considérable sur les tâches répétitives
- **Comptabilité** : Traçabilité parfaite et archivage automatique
- **Conformité RGPD** : Sécurisation maximale des données sensibles

---

## ✨ Fonctionnalités

### 🔍 Analyse intelligente
- **Reconnaissance automatique** des noms d'employés dans les PDFs
- **Extraction du matricule** directement depuis le bulletin de paie
- **Détection de la période** (année/mois) du bulletin traité
- **Support multi-pages** par employé

### 🔒 Sécurité renforcée
- **Protection par matricule** : Chaque PDF est protégé par le matricule de l'employé (extrait du bulletin)
- **Aucune transmission du mot de passe** : Le matricule n'est jamais envoyé par email
- **Isolation des données** : Chaque traitement est isolé dans un dossier horodaté
- **Base CSV sécurisée** : Seuls nom et email stockés (pas de matricule)

### 📧 Distribution automatique
- **Envoi email automatique** vers chaque employé
- **Support multi-providers** : Gmail, Outlook, Yahoo, SMTP personnalisé
- **Messages personnalisés** avec instructions d'ouverture
- **Gestion des erreurs d'envoi** avec logs détaillés

### 🗂️ Organisation avancée
- **Horodatage automatique** : Format `aaaammjjhhmmss`
- **Nomenclature intelligente** : `NOM_EMPLOYE_YYYY_MM.pdf`
- **Archivage structuré** : uploads/20250827095430/ ← PDF original ; output/20250827095430/ ← Fiches individuelles
- **Traçabilité complète** : Aucun écrasement de fichiers possible

### 🛡️ Robustesse
- **Protection anti-clics multiples** : Prévention des traitements simultanés
- **Validation des données** : Vérification des formats et contenu
- **Logs détaillés** : Suivi complet des opérations
- **Gestion d'erreurs** : Recovery automatique et messages explicites

---

## 🛠️ Technologies

### Backend
- **Python 3.7+** : Langage principal
- **Flask 2.3+** : Framework web léger et robuste
- **PyPDF2 3.0+** : Manipulation et analyse des PDFs
- **pikepdf 8.7+** : Protection par mot de passe des PDFs

### Frontend
- **HTML5** : Structure sémantique
- **CSS3** : Styles responsives avec animations
- **JavaScript ES6** : Interactions utilisateur et validations

### Email et sécurité
- **SMTP intégré** : Support natif des principaux providers
- **Threading** : Gestion des processus simultanés
- **Regex avancées** : Extraction précise des données

---

## 📦 Installation

### Prérequis
- **Python 3.7+**
- **Compte email** avec authentification 2FA (Gmail recommandé)
- **Fichier PDF** contenant les bulletins de paie

### Installation rapide

1. Cloner le repository
git clone https://github.com/pamphile81/payflow.git
cd payflow

2. Créer l'environnement virtuel
python -m venv venv

3. Activer l'environnement
Windows
venv\Scripts\activate

macOS/Linux
source venv/bin/activate

4. Installer les dépendances
pip install -r requirements.txt

5. Lancer l'application
python app.py

L'application sera accessible sur `http://127.0.0.1:5000`

---

## ⚙️ Configuration

### 1. Base de données des employés

Créez/modifiez le fichier `employees.csv` :
nom_employe,email
DUPONT JEAN MARIE,jean.dupont@entreprise.com
MARTIN SOPHIE CLAIRE,sophie.martin@entreprise.com
BERNARD ALEXANDRE,alexandre.bernard@entreprise.com


⚠️ **Important** : Le matricule n'est pas stocké dans ce fichier pour des raisons de sécurité. Il est extrait directement du bulletin de paie.

### 2. Configuration email

Dans le fichier `app.py`, modifiez la fonction `send_email_with_pdf` :
smtp_server = "smtp.gmail.com" # Votre serveur SMTP
smtp_port = 587 # Port SMTP
smtp_username = "votre-email@gmail.com" # Votre email
smtp_password = "mot-de-passe-app" # Mot de passe d'application 


### 3. Configuration Gmail (recommandée)

1. **Activez l'authentification 2FA** sur votre compte Google
2. **Générez un mot de passe d'application** :
   - Allez sur https://myaccount.google.com/security
   - "Mots de passe des applications" → "Autre" → "PayFlow"
   - Copiez le mot de passe généré (16 caractères)
3. **Utilisez ce mot de passe** dans la configuration

---

## 🚀 Utilisation

### Interface web

1. **Accédez** à http://127.0.0.1:5000
2. **Sélectionnez** votre fichier PDF multi-fiches
3. **Cliquez** sur "Traiter le fichier"
4. **Attendez** le traitement automatique
5. **Vérifiez** les logs dans le terminal

### Processus automatisé

PDF multi-fiches
↓
Analyse + reconnaissance des employés
↓
Extraction matricule + période
↓
Découpage individuel
↓
Protection par matricule
↓
Envoi email automatique
↓
Archivage horodaté


---

## 📁 Structure des fichiers

payflow/
├── app.py # Application principale Flask
├── employees.csv # Base de données employés (nom + email)
├── requirements.txt # Dépendances Python
├── README.md # Documentation complète
├── .gitignore # Fichiers ignorés par Git
├── templates/
│ └── index.html # Interface utilisateur web
├── uploads/
│ └── 20250827095430/ # PDFs originaux horodatés
│ └── bulletin_paie.pdf
├── output/
│ └── 20250827095430/ # Fiches individuelles horodatées
│ ├── DUPONT_JEAN_MARIE_2025_08.pdf
│ └── MARTIN_SOPHIE_CLAIRE_2025_08.pdf
└── venv/ # Environnement virtuel Python

## 🔒 Sécurité

### Principe de sécurité par conception

- **Aucun stockage du matricule** : Extrait uniquement du PDF source
- **Transmission sécurisée** : Le matricule n'est jamais envoyé par email  
- **Isolation des traitements** : Chaque session dans un dossier unique
- **Authentification robuste** : Support 2FA et mots de passe d'application

### Bonnes pratiques

- ✅ Utilisez des mots de passe d'application (pas votre mot de passe principal)
- ✅ Activez l'authentification 2FA sur votre compte email
- ✅ Limitez les accès au serveur hébergeant PayFlow
- ✅ Sauvegardez régulièrement le fichier `employees.csv`
- ✅ Nettoyez périodiquement les dossiers `uploads/` et `output/`

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour contribuer :

1. **Fork** le repository
2. **Créez** une branche feature (`git checkout -b feature/nouvelle-fonctionnalite`)  
3. **Committez** vos changements (`git commit -am 'Ajout nouvelle fonctionnalité'`)
4. **Pushez** vers la branche (`git push origin feature/nouvelle-fonctionnalite`)
5. **Créez** une Pull Request

### Roadmap

- **v1.1** : Interface utilisateur améliorée + dashboard
- **v1.2** : Gestion web des employés + statistiques  
- **v2.0** : Migration PostgreSQL + multi-utilisateurs

---

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

**Développé avec ❤️ pour simplifier la gestion RH**

*PayFlow v1.0 - Automatisation intelligente des fiches de paie*


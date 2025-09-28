# sync_filesystem_to_db.py
from app import create_app
from app.model.models import db, Traitement, Employee
import os
from datetime import datetime

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

def migrate_existing_treatments():
    """Migre l'historique des traitements depuis le système de fichiers vers PostgreSQL"""
    
    app = create_app('development')
    with app.app_context():
        try:
            uploads_path = 'uploads'
            output_path = 'output'
            
            print("🔄 Début de la migration filesystem → PostgreSQL")
            
            if not os.path.exists(uploads_path):
                print("❌ Dossier uploads non trouvé")
                return
            
            # Lister tous les dossiers timestampés
            folders = [f for f in os.listdir(uploads_path) 
                      if os.path.isdir(os.path.join(uploads_path, f)) 
                      and len(f) == 14 and f.isdigit()]  # Format YYYYMMDDHHMMSS
            
            print(f"📂 {len(folders)} dossiers de traitement trouvés")
            
            migrated_count = 0
            skipped_count = 0
            error_count = 0
            
            for folder in sorted(folders):  # Tri chronologique
                try:
                    # Parse du timestamp
                    timestamp = datetime.strptime(folder, '%Y%m%d%H%M%S')
                    
                    # Vérifier si ce traitement existe déjà
                    existing = Traitement.query.filter_by(timestamp_folder=folder).first()
                    if existing:
                        print(f"⚠️ Traitement {folder} déjà en base - ignoré")
                        skipped_count += 1
                        continue
                    
                    # Analyser le dossier
                    folder_path = os.path.join(uploads_path, folder)
                    
                    # Fichier original
                    original_files = [f for f in os.listdir(folder_path) if f.endswith('.pdf')]
                    if not original_files:
                        print(f"❌ Aucun PDF trouvé dans {folder}")
                        error_count += 1
                        continue
                    
                    original_file = original_files[0]
                    original_path = os.path.join(folder_path, original_file)
                    file_size = os.path.getsize(original_path) if os.path.exists(original_path) else 0
                    
                    # Fichiers générés
                    output_folder_path = os.path.join(output_path, folder)
                    generated_files = []
                    if os.path.exists(output_folder_path):
                        generated_files = [f for f in os.listdir(output_folder_path) 
                                         if f.endswith('.pdf')]
                    
                    # Déterminer le statut
                    status = 'termine' if generated_files else 'echec'
                    
                    # Créer l'enregistrement
                    traitement = Traitement(
                        timestamp_folder=folder,
                        fichier_original=original_file,
                        taille_fichier=file_size,
                        nombre_pages=0,  # Non déterminable sans réanalyse
                        nombre_employes_detectes=len(generated_files),
                        nombre_nouveaux_employes=0,  # Non déterminable
                        nombre_employes_traites=len(generated_files),
                        duree_traitement_secondes=0,  # Non déterminable
                        statut=status,
                        date_creation=timestamp
                    )
                    
                    db.session.add(traitement)
                    migrated_count += 1
                    
                    print(f"✅ {folder}: {original_file} → {len(generated_files)} fiches ({format_file_size(file_size)})")
                    
                except ValueError as e:
                    print(f"❌ Format timestamp invalide pour {folder}: {str(e)}")
                    error_count += 1
                except Exception as e:
                    print(f"❌ Erreur traitement {folder}: {str(e)}")
                    error_count += 1
            
            # Sauvegarde en base
            if migrated_count > 0:
                db.session.commit()
                print(f"\n💾 Sauvegarde en base réussie")
            else:
                print(f"\n⚠️ Aucun nouveau traitement à migrer")
            
            # Résumé
            print(f"\n📊 Résumé de la migration:")
            print(f"   ✅ Migrés: {migrated_count}")
            print(f"   ⏭️ Ignorés (déjà en base): {skipped_count}")
            print(f"   ❌ Erreurs: {error_count}")
            print(f"   📁 Total analysé: {len(folders)}")
            
            # Vérification finale
            total_db = Traitement.query.count()
            print(f"   🎯 Total en base PostgreSQL: {total_db}")
            
        except Exception as e:
            print(f"❌ Erreur critique migration: {str(e)}")
            db.session.rollback()

def verify_migration():
    """Vérifie que la migration s'est bien déroulée"""
    
    app = create_app('development')
    with app.app_context():
        try:
            # Statistiques base
            total_traitements = Traitement.query.count()
            traitements_reussis = Traitement.query.filter_by(statut='termine').count()
            traitements_echec = Traitement.query.filter_by(statut='echec').count()
            
            print(f"\n🔍 Vérification de la migration:")
            print(f"   📈 Total traitements: {total_traitements}")
            print(f"   ✅ Réussis: {traitements_reussis}")
            print(f"   ❌ Échecs: {traitements_echec}")
            
            # Derniers traitements
            recent = Traitement.query.order_by(Traitement.date_creation.desc()).limit(5).all()
            print(f"\n📅 5 derniers traitements:")
            for t in recent:
                print(f"   - {t.timestamp_folder}: {t.fichier_original} ({t.statut})")
                
            return total_traitements > 0
            
        except Exception as e:
            print(f"❌ Erreur vérification: {str(e)}")
            return False

if __name__ == '__main__':
    print("🚀 PayFlow - Migration filesystem vers PostgreSQL")
    print("=" * 50)
    
    migrate_existing_treatments()
    
    print("\n" + "=" * 50)
    if verify_migration():
        print("🎉 Migration terminée avec succès !")
        print("👉 Vous pouvez maintenant relancer l'application")
        print("👉 Le dashboard affichera les données PostgreSQL")
    else:
        print("⚠️ Problème détecté - Vérifiez les logs ci-dessus")

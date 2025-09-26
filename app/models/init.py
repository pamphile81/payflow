# Permet d'importer facilement les modèles ailleurs dans l'app
from .employee import Employee
from .traitement import Traitement
from .traitementEmploye import TraitementEmploye
from .downloadLink import DownloadLink

__all__ = ["Employee", "Traitement", "TraitementEmploye", "DownloadLink"]

# Lightroom Recover - Scanner de Photos

Ce projet permet de scanner un répertoire de photos et de stocker les informations de chaque fichier (répertoire, nom, hauteur, largeur).

## Installation

1. Créer un environnement virtuel :
```bash
python -m venv .venv
```

2. Activer l'environnement virtuel :
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

## Utilisation

### Lancer le script principal

```bash
python scan_photos.py
```

Le script va scanner le répertoire `\\hal9001\Volume_1\photos` et sauvegarder les résultats dans le dossier `resultats_scan/`.

### Formats de sauvegarde

Les résultats sont sauvegardés dans **3 formats** :

1. **JSON** (`photos_scan_YYYYMMDD_HHMMSS.json`) : Format lisible et structuré
2. **CSV** (`photos_scan_YYYYMMDD_HHMMSS.csv`) : Format tableur (Excel, LibreOffice)
3. **SQLite** (`photos_scan_YYYYMMDD_HHMMSS.db`) : Base de données pour faciliter les requêtes et la comparaison avec le catalogue Lightroom

Chaque fichier contient :
- Le répertoire de la photo
- Le nom du fichier
- La hauteur (en pixels)
- La largeur (en pixels)
- La date du scan (pour SQLite)

## Tests

### Lancer tous les tests

```bash
pytest
```

### Lancer les tests avec détails

```bash
pytest -v
```

### Lancer les tests avec couverture

```bash
pytest --cov=scan_photos --cov-report=term-missing
```

Ou pour un rapport HTML :

```bash
pytest --cov=scan_photos --cov-report=html
```

### Lancer un test spécifique

```bash
pytest tests/test_scan_photos.py::test_get_image_dimensions_valid_image
```

## Vérification du code

### Vérifier le typage avec MyPy

```bash
mypy scan_photos.py
```

### Vérifier les docstrings avec pydocstyle

```bash
pydocstyle scan_photos.py
```

### Vérifier tout le projet

```bash
mypy .
pydocstyle .
```


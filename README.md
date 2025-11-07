# Lightroom Recover

Ce projet permet de :
1. **Scanner un répertoire de photos** et stocker les informations de chaque fichier (répertoire, nom, hauteur, largeur)
2. **Mettre à jour les répertoires obsolètes** du catalogue Lightroom avec les nouveaux répertoires basés sur les données du scan

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

## Configuration

Le projet utilise un fichier `.env` pour la configuration. Copiez `.env.example` en `.env` et modifiez les valeurs selon vos besoins :

```bash
# Windows PowerShell
Copy-Item .env.example .env

# Windows CMD / Linux / macOS
cp .env.example .env
```

Variables disponibles dans `.env` :
- `DRY_RUN_MODE` : Mode simulation (true/false) pour `update_lightroom_paths.py`
- `PHOTOS_DIRECTORY` : Répertoire de base des photos
- `SCAN_DB_FILENAME` : Nom du fichier de base de données du scan
- `CATALOG_FILENAME` : Nom du fichier catalogue Lightroom

## Utilisation

### 1. Scanner les photos (`scan_photos.py`)

```bash
python scan_photos.py
```

Le script va scanner le répertoire configuré dans `.env` (par défaut `\\hal9001\Volume_1\photos`) et sauvegarder les résultats dans le dossier `resultats_scan/`.

### 2. Mettre à jour les chemins Lightroom (`update_lightroom_paths.py`)

```bash
python update_lightroom_paths.py
```

Le script va :
- Charger les photos depuis la base de données du scan
- Charger les fichiers depuis le catalogue Lightroom
- Trouver les correspondances entre les fichiers
- Mettre à jour les répertoires racine dans le catalogue Lightroom

**⚠️ Important** : Par défaut, le script fonctionne en mode `DRY_RUN` (simulation). Pour appliquer les modifications, modifiez `DRY_RUN_MODE=false` dans le fichier `.env`.

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

**Pour tous les modules** (recommandé) :
```bash
pytest --cov=scan_photos --cov=update_lightroom_paths --cov-report=term-missing --cov-report=html
```

**Pour un module spécifique** :
```bash
# scan_photos uniquement
pytest --cov=scan_photos --cov-report=term-missing --cov-report=html

# update_lightroom_paths uniquement
pytest --cov=update_lightroom_paths --cov-report=term-missing --cov-report=html
```

**Rapports disponibles** :
- `--cov-report=term-missing` : Affiche dans le terminal les lignes non couvertes
- `--cov-report=html` : Génère un rapport HTML interactif dans `htmlcov/`
- `--cov-report=xml` : Génère un rapport XML (pour CI/CD)
- `--cov-report=json` : Génère un rapport JSON

### Couverture actuelle

- **scan_photos.py** : 99% de couverture (37 tests)
- **update_lightroom_paths.py** : 78% de couverture (7 tests)
- **Total** : 87% de couverture (44 tests)

### Lancer un test spécifique

```bash
# Test spécifique dans scan_photos
pytest tests/test_scan_photos.py::test_get_image_dimensions_valid_image

# Test spécifique dans update_lightroom_paths
pytest tests/test_update_lightroom_paths.py::test_load_scan_photos
```

## Vérification du code

### Vérifier le typage avec MyPy

```bash
# Un module spécifique
mypy scan_photos.py
mypy update_lightroom_paths.py

# Tous les modules
mypy scan_photos.py update_lightroom_paths.py
```

### Vérifier les docstrings avec pydocstyle

```bash
# Un module spécifique
pydocstyle scan_photos.py
pydocstyle update_lightroom_paths.py

# Tous les modules
pydocstyle scan_photos.py update_lightroom_paths.py
```

### Vérifier tout le projet

```bash
mypy scan_photos.py update_lightroom_paths.py
pydocstyle scan_photos.py update_lightroom_paths.py
pytest --cov=scan_photos --cov=update_lightroom_paths --cov-report=term-missing
```

## Structure du projet

```
lightroom_recover/
├── scan_photos.py              # Script de scan des photos
├── update_lightroom_paths.py    # Script de mise à jour des chemins Lightroom
├── .env                        # Configuration (non versionné)
├── .env.example                # Exemple de configuration
├── requirements.txt            # Dépendances Python
├── pyproject.toml              # Configuration MyPy, pytest, pydocstyle
├── tests/
│   ├── test_scan_photos.py     # Tests pour scan_photos.py
│   └── test_update_lightroom_paths.py  # Tests pour update_lightroom_paths.py
├── resultats_scan/             # Résultats du scan (non versionné)
└── catalogue_lightroom/        # Catalogue Lightroom (non versionné)
```

## Standards de code

- **Typage** : Toutes les fonctions sont typées avec MyPy
- **Docstrings** : Toutes les fonctions sont documentées (pydocstyle)
- **Limite de lignes** : Les fonctions ne dépassent pas 50 lignes
- **Tests** : Chaque fonction a des tests pytest
- **Couverture** : Objectif de 90%+ de couverture de code


# Explication du Typage Python

## Décomposition de `List[Dict[str, str | int]]`

Analysons cette annotation de type étape par étape :

```python
results: List[Dict[str, str | int]]
```

### 1. `List[...]` - Liste
Une **liste** est une collection ordonnée d'éléments.

**Exemple :**
```python
ma_liste: List[str] = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
```

### 2. `Dict[...]` - Dictionnaire
Un **dictionnaire** est une collection de paires clé-valeur.

**Exemple :**
```python
mon_dict: Dict[str, int] = {
    "hauteur": 200,
    "largeur": 300
}
```

### 3. `str | int` - Union de types
Signifie que la valeur peut être **soit** une chaîne de caractères (`str`) **soit** un entier (`int`).

**Exemple :**
```python
# Python 3.10+ (syntaxe moderne)
valeur: str | int = "texte"  # OK
valeur: str | int = 42       # OK aussi
```

**Ancienne syntaxe (Python < 3.10) :**
```python
from typing import Union
valeur: Union[str, int] = "texte"
```

### 4. `Dict[str, str | int]` - Dictionnaire complet
Un dictionnaire où :
- Les **clés** sont des chaînes (`str`)
- Les **valeurs** sont soit des chaînes (`str`) soit des entiers (`int`)

**Exemple :**
```python
photo: Dict[str, str | int] = {
    "repertoire": "photos/2024",      # str
    "nom_fichier": "photo.jpg",       # str
    "hauteur": 200,                   # int
    "largeur": 300                    # int
}
```

### 5. `List[Dict[str, str | int]]` - Liste de dictionnaires
Une **liste** contenant plusieurs **dictionnaires**.

**Exemple concret dans votre code :**
```python
results: List[Dict[str, str | int]] = [
    {
        "repertoire": "photos/2024",
        "nom_fichier": "photo1.jpg",
        "hauteur": 200,
        "largeur": 300
    },
    {
        "repertoire": "photos/2024",
        "nom_fichier": "photo2.jpg",
        "hauteur": 150,
        "largeur": 250
    }
]
```

## Types de base en Python

### Types simples

```python
# Chaîne de caractères
nom: str = "photo.jpg"

# Entier
largeur: int = 200

# Nombre décimal
prix: float = 19.99

# Booléen
est_valide: bool = True

# Aucune valeur
rien: None = None
```

### Types composés

```python
from typing import List, Dict, Tuple, Set, Optional

# Liste de chaînes
fichiers: List[str] = ["fichier1.jpg", "fichier2.jpg"]

# Dictionnaire
photo: Dict[str, int] = {"hauteur": 200, "largeur": 300}

# Tuple (immuable, ordonné)
dimensions: Tuple[int, int] = (200, 300)

# Ensemble (sans doublons)
extensions: Set[str] = {".jpg", ".png", ".gif"}

# Optionnel (peut être None)
chemin: Optional[str] = None  # ou "photos/2024"
```

### Types avancés

```python
from typing import Union, Any, Callable

# Union (plusieurs types possibles)
valeur: Union[str, int] = "texte"  # ou 42
# Syntaxe moderne (Python 3.10+) :
valeur: str | int = "texte"

# N'importe quel type
donnee: Any = "peut être n'importe quoi"

# Fonction
fonction: Callable[[str], int] = len  # prend str, retourne int
```

## Exemples dans votre code

### Exemple 1 : Fonction simple
```python
def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    # Prend : Path
    # Retourne : Optional[Tuple[int, int]]
    #   - None si erreur
    #   - Tuple[int, int] = (largeur, hauteur) si succès
```

### Exemple 2 : Fonction avec dictionnaire
```python
def process_image_file(
    file_path: Path,
    base_directory: Path
) -> Optional[Dict[str, str | int]]:
    # Prend : Path, Path
    # Retourne : Optional[Dict[str, str | int]]
    #   - None si erreur
    #   - Dict avec clés str et valeurs str ou int
```

### Exemple 3 : Fonction avec liste
```python
def scan_photos_directory(
    photos_directory: str | Path
) -> List[Dict[str, str | int]]:
    # Prend : str OU Path
    # Retourne : List[Dict[str, str | int]]
    #   - Liste de dictionnaires
    #   - Chaque dict a des clés str et valeurs str ou int
```

## Syntaxe moderne vs ancienne

### Python 3.10+ (moderne)
```python
# Union
valeur: str | int = "texte"

# Optional
chemin: str | None = None
# ou
chemin: str | None = "photos"
```

### Python < 3.10 (ancienne)
```python
from typing import Union, Optional

# Union
valeur: Union[str, int] = "texte"

# Optional
chemin: Optional[str] = None
```

## Pourquoi utiliser le typage ?

1. **Documentation** : Le code est auto-documenté
2. **Détection d'erreurs** : MyPy trouve les bugs avant l'exécution
3. **IDE** : Meilleure autocomplétion dans votre éditeur
4. **Maintenance** : Plus facile de comprendre le code plus tard

## Exemple complet

```python
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# Type pour une photo
PhotoInfo = Dict[str, str | int]

# Type pour une liste de photos
PhotosList = List[PhotoInfo]

def traiter_photos(chemin: Path) -> PhotosList:
    """Traite les photos et retourne leurs informations."""
    results: PhotosList = []
    
    # ... traitement ...
    
    photo: PhotoInfo = {
        "repertoire": "photos/2024",
        "nom_fichier": "photo.jpg",
        "hauteur": 200,
        "largeur": 300
    }
    
    results.append(photo)
    return results
```


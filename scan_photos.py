"""Script pour scanner et stocker les informations des fichiers photos.

Ce module permet de scanner un répertoire de photos et de stocker
les informations de chaque fichier (répertoire, nom, hauteur, largeur).
"""

import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PIL import Image
from tqdm import tqdm


def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    """Récupère les dimensions (largeur, hauteur) d'une image.

    Args:
        image_path: Chemin vers le fichier image.

    Returns:
        Tuple contenant (largeur, hauteur) ou None si erreur.

    """
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            return (width, height)
    except (OSError, IOError, Exception):
        return None


def is_image_file(file_path: Path) -> bool:
    """Vérifie si un fichier est une image supportée.

    Args:
        file_path: Chemin vers le fichier à vérifier.

    Returns:
        True si le fichier est une image, False sinon.

    """
    image_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp',
        '.tiff', '.tif', '.webp', '.raw', '.cr2',
        '.nef', '.orf', '.sr2', '.arw', '.dng'
    }
    return file_path.suffix.lower() in image_extensions


def scan_directory(directory_path: Path) -> List[Path]:
    """Scanne un répertoire et retourne la liste des fichiers images.

    Args:
        directory_path: Chemin du répertoire à scanner.

    Returns:
        Liste des chemins vers les fichiers images trouvés.

    """
    image_files: List[Path] = []
    if not directory_path.exists():
        return image_files

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file
            if is_image_file(file_path):
                image_files.append(file_path)

    return image_files


def process_image_file(
    file_path: Path,
    base_directory: Path
) -> Optional[Dict[str, str | int]]:
    """Traite un fichier image et retourne ses informations.

    Args:
        file_path: Chemin vers le fichier image.
        base_directory: Répertoire de base pour le chemin relatif.

    Returns:
        Dictionnaire avec les informations du fichier ou None si erreur.

    """
    dimensions = get_image_dimensions(file_path)
    if dimensions is None:
        return None

    width, height = dimensions
    relative_path = file_path.relative_to(base_directory)
    directory = str(relative_path.parent)
    filename = file_path.name

    return {
        'repertoire': directory,
        'nom_fichier': filename,
        'hauteur': height,
        'largeur': width
    }


def scan_photos_directory(
    photos_directory: str | Path
) -> List[Dict[str, str | int]]:
    """Scanne un répertoire de photos et retourne les informations.

    Args:
        photos_directory: Chemin vers le répertoire de photos.

    Returns:
        Liste de dictionnaires contenant les informations de chaque photo.

    """
    base_path = Path(photos_directory)
    if not base_path.exists():
        raise FileNotFoundError(
            f"Le répertoire {photos_directory} n'existe pas."
        )

    print(f"Scan du répertoire: {base_path}")
    image_files = scan_directory(base_path)
    print(f"Nombre de fichiers images trouvés: {len(image_files)}")

    results: List[Dict[str, str | int]] = []
    failed_files: List[Path] = []

    for file_path in tqdm(image_files, desc="Traitement des images"):
        file_info = process_image_file(file_path, base_path)
        if file_info is not None:
            results.append(file_info)
        else:
            failed_files.append(file_path)

    if failed_files:
        print(f"\n{len(failed_files)} fichiers n'ont pas pu être traités:")
        for failed_file in failed_files[:10]:
            print(f"  - {failed_file}")
        if len(failed_files) > 10:
            print(f"  ... et {len(failed_files) - 10} autres")

    return results


def main() -> None:
    """Fonction principale du script."""
    photos_directory = r"\\hal9001\Volume_1\photos"
    results = scan_photos_directory(photos_directory)
    print(f"\nTotal de photos traitées avec succès: {len(results)}")
    print("\nExemple de résultats (5 premiers):")
    for i, result in enumerate(results[:5], 1):
        print(f"{i}. {result}")


if __name__ == "__main__":
    main()


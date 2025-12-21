"""Script pour lister les images non trouvées dans le catalogue Lightroom.

Ce module permet de lister tous les fichiers du catalogue Lightroom qui ne sont
pas situés dans le répertoire de base des photos (par défaut
\\hal9001\Volume_1\photos).
"""

import sqlite3
import csv
from pathlib import Path
from typing import List, Tuple
import os
from datetime import datetime
from dotenv import load_dotenv


def _load_photos_directory() -> str:
    """Charge le répertoire de base des photos depuis le fichier .env.

    Returns:
        Chemin du répertoire de base des photos.

    """
    load_dotenv()
    return os.getenv(
        'PHOTOS_DIRECTORY',
        r'\\hal9001\Volume_1\photos'
    )


def _load_catalog_filename() -> str:
    """Charge le nom du fichier catalogue Lightroom depuis le fichier .env.

    Returns:
        Nom du fichier catalogue Lightroom.

    """
    load_dotenv()
    return os.getenv(
        'CATALOG_FILENAME',
        'catalogue 2 - dès juin 2017-2-2-v12.lrcat'
    )


def _build_full_path(
    root_path: str,
    path_from_root: str,
    base_name: str,
    extension: str
) -> str:
    """Construit le chemin complet d'un fichier.

    Args:
        root_path: Chemin racine du répertoire.
        path_from_root: Chemin relatif depuis la racine.
        base_name: Nom de base du fichier.
        extension: Extension du fichier.

    Returns:
        Chemin complet normalisé.

    """
    # Normaliser les séparateurs
    root = root_path.replace('/', '\\').rstrip('\\')
    path_rel = path_from_root.replace('/', '\\').strip('\\')
    
    # Construire le chemin (ajouter le point entre base_name et extension)
    filename = f"{base_name}.{extension}"
    if path_rel:
        full_path = f"{root}\\{path_rel}\\{filename}"
    else:
        full_path = f"{root}\\{filename}"
    
    return full_path


def load_missing_images(
    catalog_path: Path,
    photos_base_path: str
) -> List[Tuple[str, str]]:
    """Charge les images non trouvées depuis le catalogue Lightroom.

    Args:
        catalog_path: Chemin vers le fichier catalogue Lightroom (.lrcat).
        photos_base_path: Chemin de base des photos à rechercher.

    Returns:
        Liste de tuples (répertoire, nom_fichier) pour les images non trouvées.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()

    query = '''
        SELECT
            rf.absolutePath,
            f.pathFromRoot,
            fl.baseName,
            fl.extension
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    missing_images: List[Tuple[str, str]] = []
    photos_base_normalized = photos_base_path.replace('/', '\\').rstrip('\\').lower()
    
    for row in rows:
        root_path, path_from_root, base_name, extension = row
        full_path = _build_full_path(
            root_path,
            path_from_root,
            base_name,
            extension
        )
        
        # Vérifier si le chemin commence par le répertoire de base
        if not full_path.lower().startswith(photos_base_normalized):
            # Extraire le répertoire et le nom du fichier
            directory = os.path.dirname(full_path)
            filename = f"{base_name}.{extension}"
            missing_images.append((directory, filename))

    conn.close()
    return missing_images


def save_to_csv(
    missing_images: List[Tuple[str, str]],
    output_path: Path
) -> None:
    """Sauvegarde les images non trouvées dans un fichier CSV.

    Args:
        missing_images: Liste de tuples (répertoire, nom_fichier).
        output_path: Chemin du fichier CSV de sortie.

    """
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow(['repertoire', 'nom_fichier'])
        writer.writerows(missing_images)


def main() -> None:
    """Fonction principale du script."""
    base_dir = Path(__file__).parent
    
    # Charger les chemins depuis le fichier .env
    catalog_filename = _load_catalog_filename()
    photos_directory = _load_photos_directory()
    
    catalog = base_dir / 'catalogue_lightroom' / catalog_filename
    
    if not catalog.exists():
        print(f"❌ Erreur : Le catalogue {catalog} n'existe pas")
        return
    
    print(f"Chargement du catalogue : {catalog_filename}")
    print(f"Recherche des images non trouvées (hors de {photos_directory})...")
    
    missing_images = load_missing_images(catalog, photos_directory)
    
    print(f"  {len(missing_images)} images non trouvées")
    
    if missing_images:
        # Générer le nom du fichier de sortie avec timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_dir = base_dir / 'resultats_scan'
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f'images_non_trouvees_{timestamp}.csv'
        
        save_to_csv(missing_images, output_file)
        print(f"\n✅ Résultats sauvegardés dans : {output_file}")
    else:
        print("\n✅ Toutes les images sont dans le répertoire de base !")


if __name__ == '__main__':
    main()


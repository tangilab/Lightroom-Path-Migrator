"""Script pour scanner et stocker les informations des fichiers photos.

Ce module permet de scanner un répertoire de photos et de stocker
les informations de chaque fichier (répertoire, nom, hauteur, largeur).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import os
import pandas as pd
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
    photos_directory: str | Path,
    sqlite_path: Path | None = None,
    batch_size: int = 1000
) -> List[Dict[str, str | int]]:
    """Scanne un répertoire de photos et retourne les informations.

    Args:
        photos_directory: Chemin vers le répertoire de photos.
        sqlite_path: Chemin vers la base SQLite pour sauvegarde par lots.
        batch_size: Nombre de photos à traiter avant sauvegarde SQLite.

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
    total_saved = 0

    for file_path in tqdm(image_files, desc="Traitement des images"):
        file_info = process_image_file(file_path, base_path)
        if file_info is not None:
            results.append(file_info)

            if sqlite_path and len(results) >= batch_size:
                save_results_sqlite(results, sqlite_path, append=True)
                total_saved += len(results)
                print(f"\n✓ {len(results)} photos sauvegardées dans la BDD (total: {total_saved})")
                results = []
        else:
            failed_files.append(file_path)

    if failed_files:
        print(f"\n{len(failed_files)} fichiers n'ont pas pu être traités:")
        for failed_file in failed_files[:10]:
            print(f"  - {failed_file}")
        if len(failed_files) > 10:
            print(f"  ... et {len(failed_files) - 10} autres")

    return results


def save_results_json(
    results: List[Dict[str, str | int]],
    output_path: Path
) -> Path:
    """Sauvegarde les résultats au format JSON.

    Args:
        results: Liste des résultats à sauvegarder.
        output_path: Chemin du fichier de sortie.

    Returns:
        Chemin du fichier créé.

    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'timestamp': datetime.now().isoformat(),
        'total_photos': len(results),
        'photos': results
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_path


def save_results_csv(
    results: List[Dict[str, str | int]],
    output_path: Path
) -> Path:
    """Sauvegarde les résultats au format CSV.

    Args:
        results: Liste des résultats à sauvegarder.
        output_path: Chemin du fichier de sortie.

    Returns:
        Chemin du fichier créé.

    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    return output_path


def save_results_sqlite(
    results: List[Dict[str, str | int]],
    output_path: Path,
    append: bool = False
) -> Path:
    """Sauvegarde les résultats dans une base SQLite.

    Args:
        results: Liste des résultats à sauvegarder.
        output_path: Chemin du fichier de sortie.
        append: Si True, ajoute les données à la base existante.

    Returns:
        Chemin du fichier créé.

    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repertoire TEXT NOT NULL,
            nom_fichier TEXT NOT NULL,
            hauteur INTEGER NOT NULL,
            largeur INTEGER NOT NULL,
            scan_date TEXT NOT NULL
        )
    ''')

    scan_date = datetime.now().isoformat()
    data_to_insert = [
        (
            result['repertoire'],
            result['nom_fichier'],
            result['hauteur'],
            result['largeur'],
            scan_date
        )
        for result in results
    ]

    cursor.executemany('''
        INSERT INTO photos (repertoire, nom_fichier, hauteur, largeur, scan_date)
        VALUES (?, ?, ?, ?, ?)
    ''', data_to_insert)

    conn.commit()
    conn.close()
    return output_path


def get_total_photos_count(sqlite_path: Path) -> int:
    """Récupère le nombre total de photos dans la base SQLite.

    Args:
        sqlite_path: Chemin vers la base SQLite.

    Returns:
        Nombre total de photos dans la base.

    """
    if not sqlite_path.exists():
        return 0

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    result = cursor.fetchone()
    conn.close()
    return int(result[0]) if result else 0


def load_all_photos_from_sqlite(sqlite_path: Path) -> List[Dict[str, str | int]]:
    """Charge toutes les photos depuis la base SQLite.

    Args:
        sqlite_path: Chemin vers la base SQLite.

    Returns:
        Liste de dictionnaires contenant toutes les photos.

    """
    if not sqlite_path.exists():
        return []

    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT repertoire, nom_fichier, hauteur, largeur
        FROM photos
    """)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            'repertoire': row[0],
            'nom_fichier': row[1],
            'hauteur': row[2],
            'largeur': row[3]
        }
        for row in rows
    ]


def main() -> None:
    """Fonction principale du script."""
    photos_directory = r"\\hal9001\Volume_1\photos"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("resultats_scan")
    output_dir.mkdir(exist_ok=True)

    sqlite_path = output_dir / f"photos_scan_{timestamp}.db"

    print("Sauvegarde par lots de 1000 photos dans la BDD SQLite")
    print(f"Base SQLite: {sqlite_path}\n")

    results = scan_photos_directory(
        photos_directory,
        sqlite_path=sqlite_path,
        batch_size=1000
    )

    if results:
        save_results_sqlite(results, sqlite_path, append=True)
        print(f"\n✓ {len(results)} photos restantes sauvegardées dans la BDD")

    total_in_db = get_total_photos_count(sqlite_path)

    if total_in_db > 0:
        all_photos = load_all_photos_from_sqlite(sqlite_path)

        json_path = save_results_json(
            all_photos,
            output_dir / f"photos_scan_{timestamp}.json"
        )
        csv_path = save_results_csv(
            all_photos,
            output_dir / f"photos_scan_{timestamp}.csv"
        )

        print("\n" + "="*60)
        print("RÉSUMÉ")
        print("="*60)
        print(f"Total de photos dans la BDD SQLite: {total_in_db}")
        print(f"\nRésultats sauvegardés dans:")
        print(f"  - JSON: {json_path}")
        print(f"  - CSV: {csv_path}")
        print(f"  - SQLite: {sqlite_path}")

        if all_photos:
            print("\nExemple de résultats (5 premiers):")
            for i, result in enumerate(all_photos[:5], 1):
                print(f"{i}. {result}")
    else:
        print("\nAucun résultat à sauvegarder.")


if __name__ == "__main__":
    main()


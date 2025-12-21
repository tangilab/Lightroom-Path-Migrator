"""Script pour rechercher les fichiers en double dans le catalogue Lightroom."""

import sqlite3
from pathlib import Path
import csv
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple
import os
from datetime import datetime
from dotenv import load_dotenv


@dataclass
class DuplicateFile:
    """Représente un fichier en double.

    Attributes:
        file_id: ID du fichier dans AgLibraryFile.
        base_name: Nom de base du fichier.
        extension: Extension du fichier.
        root_folder_id: ID du root_folder.
        root_folder_path: Chemin du root_folder.
        folder_path: Chemin relatif du dossier (pathFromRoot).
        full_path: Chemin complet du fichier.

    """

    file_id: int
    base_name: str
    extension: str
    root_folder_id: int
    root_folder_path: str
    folder_path: str
    full_path: str


def _load_catalog_filename() -> str:
    """Charge le nom du catalogue depuis le fichier .env.

    Returns:
        Nom du fichier catalogue.

    """
    load_dotenv()
    return os.getenv('CATALOG_FILENAME', 'catalogue 2 - dès juin 2017-2-2-v12.lrcat')


def _find_duplicates_by_filename(
    cursor: sqlite3.Cursor
) -> Dict[str, List[DuplicateFile]]:
    """Trouve les fichiers en double par nom de fichier.

    Recherche les fichiers avec le même lc_idx_filename ET le même
    chemin complet (root_path + pathFromRoot) mais dans des
    root_folders différents. Les fichiers avec le même nom mais des
    chemins complets différents ne sont pas considérés comme des doublons.

    Args:
        cursor: Curseur de base de données.

    Returns:
        Dictionnaire avec lc_idx_filename comme clé et liste de
        fichiers en double comme valeur.

    """
    # Récupérer tous les fichiers avec leurs informations
    cursor.execute('''
        SELECT
            fl.id_local,
            fl.baseName,
            fl.extension,
            fl.lc_idx_filename,
            f.rootFolder,
            rf.absolutePath,
            f.pathFromRoot
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
        ORDER BY fl.lc_idx_filename, rf.absolutePath, f.pathFromRoot
    ''')
    
    # Utiliser (nom, chemin_complet_sans_nom) comme clé pour identifier les vrais doublons
    # Le chemin complet sans nom = root_path + pathFromRoot
    files_by_name_and_full_path: Dict[Tuple[str, str], List[DuplicateFile]] = defaultdict(list)
    
    for row in cursor.fetchall():
        file_id, base_name, extension, lc_idx_filename, root_folder_id, root_path, folder_path = row
        
        folder_path_str = folder_path or ''
        root_path_str = root_path or ''
        full_path = f"{root_path_str}{folder_path_str}{base_name}.{extension}"
        
        duplicate = DuplicateFile(
            file_id=file_id,
            base_name=base_name,
            extension=extension,
            root_folder_id=root_folder_id,
            root_folder_path=root_path_str,
            folder_path=folder_path_str,
            full_path=full_path
        )
        
        # Clé : (nom fichier, chemin complet sans nom)
        # Cela permet de distinguer les fichiers avec le même nom mais des chemins différents
        path_without_name = f"{root_path_str}{folder_path_str}"
        key = (lc_idx_filename, path_without_name)
        files_by_name_and_full_path[key].append(duplicate)
    
    # Filtrer pour ne garder que les doublons (plus d'un fichier)
    # ET seulement si les fichiers sont dans des root_folders différents
    duplicates: Dict[str, List[DuplicateFile]] = {}
    for (name, path_without_name), files in files_by_name_and_full_path.items():
        if len(files) > 1:
            # Vérifier si les fichiers sont dans des root_folders différents
            root_folders = {f.root_folder_id for f in files}
            if len(root_folders) > 1:
                # Vrais doublons : même nom et même chemin complet dans des root_folders différents
                # Utiliser le nom comme clé pour l'affichage
                duplicates[name] = files
    
    return duplicates


def _find_duplicates_by_path(
    cursor: sqlite3.Cursor
) -> Dict[str, List[DuplicateFile]]:
    """Trouve les fichiers en double par chemin complet.

    Recherche les fichiers avec le même chemin complet exact mais dans
    des root_folders différents. Les chemins sont comparés de manière stricte,
    sans normalisation.

    Args:
        cursor: Curseur de base de données.

    Returns:
        Dictionnaire avec le chemin complet comme clé et liste de
        fichiers en double comme valeur.

    """
    cursor.execute('''
        SELECT
            fl.id_local,
            fl.baseName,
            fl.extension,
            f.rootFolder,
            rf.absolutePath,
            f.pathFromRoot
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
        ORDER BY rf.absolutePath, f.pathFromRoot, fl.baseName, fl.extension
    ''')
    
    files_by_path: Dict[str, List[DuplicateFile]] = defaultdict(list)
    
    for row in cursor.fetchall():
        file_id, base_name, extension, root_folder_id, root_path, folder_path = row
        
        # Construire le chemin complet de manière stricte, sans normalisation
        root_path_str = root_path or ''
        folder_path_str = folder_path or ''
        full_path = f"{root_path_str}{folder_path_str}{base_name}.{extension}"
        
        duplicate = DuplicateFile(
            file_id=file_id,
            base_name=base_name,
            extension=extension,
            root_folder_id=root_folder_id,
            root_folder_path=root_path_str,
            folder_path=folder_path_str,
            full_path=full_path
        )
        
        files_by_path[full_path].append(duplicate)
    
    # Filtrer pour ne garder que les doublons (plus d'un fichier)
    # ET seulement si les fichiers sont dans des root_folders différents
    duplicates: Dict[str, List[DuplicateFile]] = {}
    for path, files in files_by_path.items():
        if len(files) > 1:
            # Vérifier si les fichiers sont dans des root_folders différents
            root_folders = {f.root_folder_id for f in files}
            if len(root_folders) > 1:
                # Vrais doublons : même chemin dans des root_folders différents
                duplicates[path] = files
    
    return duplicates


def _save_duplicates_to_csv(
    duplicates: Dict[str, List[DuplicateFile]],
    output_path: Path,
    duplicate_type: str
) -> None:
    """Sauvegarde les doublons dans un fichier CSV.

    Args:
        duplicates: Dictionnaire de doublons.
        output_path: Chemin du fichier CSV de sortie.
        duplicate_type: Type de doublon ('filename' ou 'path').

    """
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'nom_fichier',
            'file_id',
            'base_name',
            'extension',
            'root_folder_id',
            'root_folder_path',
            'folder_path',
            'full_path',
            'nombre_doublons'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for key, files in duplicates.items():
            for duplicate in files:
                writer.writerow({
                    'nom_fichier': key if duplicate_type == 'filename' else duplicate.base_name + '.' + duplicate.extension,
                    'file_id': duplicate.file_id,
                    'base_name': duplicate.base_name,
                    'extension': duplicate.extension,
                    'root_folder_id': duplicate.root_folder_id,
                    'root_folder_path': duplicate.root_folder_path,
                    'folder_path': duplicate.folder_path,
                    'full_path': duplicate.full_path,
                    'nombre_doublons': len(files)
                })


def find_duplicates(catalog_path: Path) -> Tuple[Dict[str, List[DuplicateFile]], Dict[str, List[DuplicateFile]]]:
    """Trouve tous les fichiers en double dans le catalogue.

    Args:
        catalog_path: Chemin vers le catalogue Lightroom.

    Returns:
        Tuple contenant :
        - Dictionnaire des doublons par nom de fichier.
        - Dictionnaire des doublons par chemin complet.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()
    
    duplicates_by_filename = _find_duplicates_by_filename(cursor)
    duplicates_by_path = _find_duplicates_by_path(cursor)
    
    conn.close()
    
    return duplicates_by_filename, duplicates_by_path


def main() -> None:
    """Fonction principale du script."""
    load_dotenv()
    
    base_dir = Path(__file__).parent
    catalog_filename = _load_catalog_filename()
    catalog_path = base_dir / 'catalogue_lightroom' / catalog_filename
    
    if not catalog_path.exists():
        print(f"Erreur : Le catalogue {catalog_path} n'existe pas")
        return
    
    print("Recherche des fichiers en double...")
    duplicates_by_filename, duplicates_by_path = find_duplicates(catalog_path)
    
    # Calculer le nombre total de fichiers en double
    total_files_by_filename = sum(len(files) for files in duplicates_by_filename.values())
    total_files_by_path = sum(len(files) for files in duplicates_by_path.values())
    
    print(f"\nResume des doublons :")
    print(f"  Doublons par nom de fichier : {len(duplicates_by_filename)} noms uniques")
    print(f"    Total fichiers concernes : {total_files_by_filename}")
    print(f"  Doublons par chemin complet : {len(duplicates_by_path)} chemins uniques")
    print(f"    Total fichiers concernes : {total_files_by_path}")
    
    # Sauvegarder les résultats
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if duplicates_by_filename:
        output_filename = base_dir / f'doublons_par_nom_{timestamp}.csv'
        _save_duplicates_to_csv(duplicates_by_filename, output_filename, 'filename')
        print(f"\nResultats sauvegardes dans : {output_filename}")
    
    if duplicates_by_path:
        output_path = base_dir / f'doublons_par_chemin_{timestamp}.csv'
        _save_duplicates_to_csv(duplicates_by_path, output_path, 'path')
        print(f"Resultats sauvegardes dans : {output_path}")


if __name__ == '__main__':
    main()


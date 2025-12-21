"""Script pour tester le hash des fichiers sur le disque dur.

Ce script :
1. Identifie les répertoires qui peuvent être remplacés
2. Calcule le hash BLAKE256 du contenu réel des fichiers sur le disque
3. Détecte les doublons basés sur le hash du contenu
4. Stocke les résultats dans un CSV
"""

import sqlite3
import csv
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dotenv import load_dotenv
from tqdm import tqdm

from update_lightroom_paths import (
    MatchResult,
    load_scan_photos,
    load_lightroom_files,
    find_matches,
    _load_photos_directory,
    _load_scan_db_filename,
    _load_catalog_filename,
    _group_matches_by_root,
)


@dataclass
class FileHashInfo:
    """Informations sur un fichier avec son hash."""

    file_id_local: int
    root_folder_id: int
    old_path: str
    new_path: str
    file_path_on_disk: str
    file_hash: str
    file_exists: bool
    match_count: int


def _build_file_path_on_disk(
    root_path: str,
    path_from_root: str,
    base_name: str,
    extension: str
) -> str:
    """Construit le chemin complet du fichier sur le disque.

    Args:
        root_path: Chemin racine du répertoire.
        path_from_root: Chemin relatif depuis la racine.
        base_name: Nom de base du fichier.
        extension: Extension du fichier.

    Returns:
        Chemin complet du fichier sur le disque.

    """
    root = root_path.replace('/', '\\').rstrip('\\')
    path_rel = path_from_root.replace('/', '\\').strip('\\')
    
    filename = f"{base_name}.{extension}"
    if path_rel:
        full_path = f"{root}\\{path_rel}\\{filename}"
    else:
        full_path = f"{root}\\{filename}"
    
    return full_path


def _calculate_file_content_hash(
    file_path: Path
) -> Optional[str]:
    """Calcule le hash BLAKE256 du contenu d'un fichier.

    Args:
        file_path: Chemin vers le fichier sur le disque.

    Returns:
        Hash BLAKE256 en hexadécimal, ou None si le fichier n'existe pas.

    """
    if not file_path.exists():
        return None
    
    hash_obj = hashlib.blake2b(digest_size=32)
    
    try:
        with open(file_path, 'rb') as f:
            # Lire le fichier par chunks pour gérer les gros fichiers
            while chunk := f.read(8192):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except (IOError, OSError):
        return None


def _process_file_batch_worker(
    batch_tasks: List[Tuple[int, int, str, str, str, str]]
) -> str:
    """Fonction worker pour traiter un lot de fichiers et écrire dans un CSV.

    Args:
        batch_tasks: Liste de tuples (file_id, root_id, root_path, new_path,
                     file_path_on_disk, match_count_str).

    Returns:
        Chemin du fichier CSV créé.

    """
    # Créer un fichier temporaire pour ce batch
    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        delete=False,
        suffix='.csv',
        newline='',
        encoding='utf-8'
    )
    temp_path = temp_file.name
    temp_file.close()
    
    # Écrire les en-têtes
    with open(temp_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow([
            'file_id_local',
            'root_folder_id',
            'old_path',
            'new_path',
            'file_path_on_disk',
            'file_hash',
            'file_exists',
            'match_count',
            'is_duplicate',
            'duplicate_count'
        ])
        
        # Traiter chaque fichier du batch
        for task in batch_tasks:
            file_id, root_id, root_path, new_path, file_path_on_disk, match_count_str = task
            
            # Calculer le hash
            file_path = Path(file_path_on_disk)
            file_exists = file_path.exists()
            file_hash = _calculate_file_content_hash(file_path) if file_exists else None
            
            # Écrire la ligne (sans détection de doublons pour l'instant)
            writer.writerow([
                file_id,
                root_id,
                root_path,
                new_path,
                file_path_on_disk,
                file_hash or '',
                'OUI' if file_exists else 'NON',
                match_count_str,
                'NON',  # Sera mis à jour lors de la fusion
                0
            ])
    
    return temp_path


def _load_num_cores() -> int:
    """Charge le nombre de cœurs depuis les variables d'environnement.

    Returns:
        Nombre de cœurs à utiliser (par défaut 4).

    """
    num_cores_str = os.getenv('NUM_CORES', '4')
    try:
        num_cores = int(num_cores_str)
        if num_cores < 1:
            num_cores = 1
        elif num_cores > os.cpu_count() or num_cores is None:
            num_cores = os.cpu_count() or 4
        return num_cores
    except ValueError:
        return 4


def _merge_csv_files(
    csv_files: List[str],
    output_path: Path
) -> None:
    """Fusionne plusieurs fichiers CSV en un seul.

    Args:
        csv_files: Liste des chemins vers les fichiers CSV à fusionner.
        output_path: Chemin du fichier CSV de sortie fusionné.

    """
    with open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.writer(outfile, delimiter=';')
        
        # Écrire les en-têtes une seule fois
        header_written = False
        
        for csv_file in csv_files:
            with open(csv_file, 'r', encoding='utf-8') as infile:
                reader = csv.reader(infile, delimiter=';')
                
                for i, row in enumerate(reader):
                    # Ignorer l'en-tête sauf pour le premier fichier
                    if i == 0:
                        if not header_written:
                            writer.writerow(row)
                            header_written = True
                    else:
                        writer.writerow(row)
            
            # Supprimer le fichier temporaire
            Path(csv_file).unlink()


def _detect_duplicates_from_csv(
    csv_path: Path
) -> Dict[str, List[FileHashInfo]]:
    """Charge les données du CSV et détecte les doublons.

    Args:
        csv_path: Chemin vers le fichier CSV.

    Returns:
        Dictionnaire des doublons {hash: [liste des fichiers]}.

    """
    hash_groups: Dict[str, List[FileHashInfo]] = {}
    
    with open(csv_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        
        for row in reader:
            file_hash = row['file_hash']
            if file_hash:  # Ignorer les fichiers sans hash
                if file_hash not in hash_groups:
                    hash_groups[file_hash] = []
                
                hash_info = FileHashInfo(
                    file_id_local=int(row['file_id_local']),
                    root_folder_id=int(row['root_folder_id']),
                    old_path=row['old_path'],
                    new_path=row['new_path'],
                    file_path_on_disk=row['file_path_on_disk'],
                    file_hash=file_hash,
                    file_exists=row['file_exists'] == 'OUI',
                    match_count=int(row['match_count'])
                )
                hash_groups[file_hash].append(hash_info)
    
    # Retourner seulement les groupes avec plus d'un fichier (doublons)
    return {
        h: files for h, files in hash_groups.items()
        if len(files) > 1
    }


def _update_csv_with_duplicates(
    csv_path: Path,
    duplicates: Dict[str, List[FileHashInfo]]
) -> None:
    """Met à jour le CSV avec les informations de doublons.

    Args:
        csv_path: Chemin vers le fichier CSV à mettre à jour.
        duplicates: Dictionnaire des doublons détectés.

    """
    # Lire le CSV, mettre à jour et réécrire
    temp_path = csv_path.with_suffix('.tmp')
    
    with open(csv_path, 'r', encoding='utf-8') as infile, \
         open(temp_path, 'w', newline='', encoding='utf-8') as outfile:
        
        reader = csv.DictReader(infile, delimiter=';')
        writer = csv.writer(outfile, delimiter=';')
        
        # Écrire les en-têtes
        writer.writerow([
            'file_id_local',
            'root_folder_id',
            'old_path',
            'new_path',
            'file_path_on_disk',
            'file_hash',
            'file_exists',
            'match_count',
            'is_duplicate',
            'duplicate_count'
        ])
        
        # Mettre à jour chaque ligne
        for row in reader:
            file_hash = row['file_hash']
            is_duplicate = file_hash in duplicates
            duplicate_count = len(duplicates.get(file_hash, []))
            
            writer.writerow([
                row['file_id_local'],
                row['root_folder_id'],
                row['old_path'],
                row['new_path'],
                row['file_path_on_disk'],
                file_hash,
                row['file_exists'],
                row['match_count'],
                'OUI' if is_duplicate else 'NON',
                duplicate_count if is_duplicate else 0
            ])
    
    # Remplacer l'ancien fichier par le nouveau
    temp_path.replace(csv_path)


def process_matches_for_hashing(
    matches: List[MatchResult],
    catalog_path: Path,
    photos_base_path: str,
    output_path: Path,
    duplicates: Dict[str, List[FileHashInfo]],
    batch_size: int = 1000,
    num_cores: int = 4
) -> None:
    """Traite les matches pour calculer les hash des fichiers en parallèle.

    Chaque cœur traite un groupe de fichiers et écrit dans son propre CSV.
    Les CSV sont fusionnés à la fin et les doublons sont détectés.

    Args:
        matches: Liste des correspondances trouvées.
        catalog_path: Chemin vers le catalogue Lightroom.
        photos_base_path: Chemin de base des photos.
        output_path: Chemin du fichier CSV de sortie.
        duplicates: Dictionnaire des doublons (mis à jour après fusion).
        batch_size: Nombre de fichiers par groupe (1000 par défaut).
        num_cores: Nombre de cœurs à utiliser pour le traitement parallèle.

    """
    # Charger les fichiers Lightroom pour obtenir les chemins complets
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()
    
    # Récupérer les informations des fichiers
    file_infos: Dict[int, Tuple[str, str, str, str]] = {}
    for match in matches:
        file_id = match.lightroom_file.id_local
        if file_id not in file_infos:
            cursor.execute('''
                SELECT fl.baseName, fl.extension, f.pathFromRoot, rf.absolutePath
                FROM AgLibraryFile fl
                JOIN AgLibraryFolder f ON fl.folder = f.id_local
                JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
                WHERE fl.id_local = ?
            ''', (file_id,))
            result = cursor.fetchone()
            if result:
                file_infos[file_id] = result
    
    conn.close()
    
    # Grouper les matches par root_folder_id pour obtenir match_count
    updates_by_root, match_counts = _group_matches_by_root(matches)
    
    # Préparer les données pour le traitement parallèle
    file_tasks: List[Tuple[int, int, str, str, str, str]] = []
    for match in matches:
        file_id = match.lightroom_file.id_local
        root_id = match.lightroom_file.root_folder_id
        
        if file_id not in file_infos:
            continue
        
        base_name, extension, path_from_root, root_path = file_infos[file_id]
        
        # Construire le chemin du fichier sur le disque (nouveau chemin)
        new_path_normalized = match.new_absolute_path.replace('/', '\\').rstrip('\\')
        file_path_on_disk = f"{new_path_normalized}\\{base_name}.{extension}"
        
        file_tasks.append((
            file_id,
            root_id,
            root_path,
            match.new_absolute_path,
            file_path_on_disk,
            str(match_counts.get(root_id, 0))
        ))
    
    # Découper en groupes de batch_size
    batches: List[List[Tuple[int, int, str, str, str, str]]] = []
    for i in range(0, len(file_tasks), batch_size):
        batches.append(file_tasks[i:i + batch_size])
    
    total_batches = len(batches)
    print(f"  {total_batches} groupes de {batch_size} fichiers à traiter")
    
    # Traiter les groupes en parallèle
    csv_files: List[str] = []
    
    with ProcessPoolExecutor(max_workers=num_cores) as executor:
        # Soumettre tous les batches
        future_to_batch = {
            executor.submit(_process_file_batch_worker, batch): i
            for i, batch in enumerate(batches)
        }
        
        # Collecter les résultats au fur et à mesure
        with tqdm(total=total_batches, desc="Calcul des hash", unit="groupe") as pbar:
            for future in as_completed(future_to_batch):
                batch_num = future_to_batch[future]
                try:
                    csv_file = future.result()
                    csv_files.append(csv_file)
                    pbar.set_postfix({
                        'groupes': len(csv_files),
                        'coeurs': num_cores
                    })
                    pbar.update(1)
                except Exception as e:
                    print(f"\n  Erreur lors du traitement du groupe {batch_num}: {e}")
                    pbar.update(1)
                    continue
    
    # Fusionner tous les CSV
    print(f"\n  Fusion de {len(csv_files)} fichiers CSV...")
    _merge_csv_files(csv_files, output_path)
    
    # Détecter les doublons sur l'ensemble fusionné
    print("  Detection des doublons sur l'ensemble fusionne...")
    detected_duplicates = _detect_duplicates_from_csv(output_path)
    duplicates.update(detected_duplicates)
    
    # Mettre à jour le CSV avec les informations de doublons
    print("  Mise a jour du CSV avec les informations de doublons...")
    _update_csv_with_duplicates(output_path, duplicates)


def detect_duplicate_hashes(
    hash_infos: List[FileHashInfo]
) -> Dict[str, List[FileHashInfo]]:
    """Détecte les doublons basés sur le hash du contenu.

    Args:
        hash_infos: Liste des informations de hash.

    Returns:
        Dictionnaire {hash: [liste des fichiers avec ce hash]}.

    """
    hash_groups: Dict[str, List[FileHashInfo]] = {}
    
    for hash_info in hash_infos:
        if hash_info.file_hash:  # Ignorer les fichiers sans hash (inexistants)
            if hash_info.file_hash not in hash_groups:
                hash_groups[hash_info.file_hash] = []
            hash_groups[hash_info.file_hash].append(hash_info)
    
    # Retourner seulement les groupes avec plus d'un fichier (doublons)
    duplicates: Dict[str, List[FileHashInfo]] = {
        h: files for h, files in hash_groups.items()
        if len(files) > 1
    }
    
    return duplicates


def save_results_to_csv(
    hash_infos: List[FileHashInfo],
    duplicates: Dict[str, List[FileHashInfo]],
    output_path: Path,
    append: bool = False
) -> None:
    """Sauvegarde les résultats dans un fichier CSV.

    Args:
        hash_infos: Liste des informations de hash.
        duplicates: Dictionnaire des doublons détectés.
        output_path: Chemin du fichier CSV de sortie.
        append: Si True, ajoute les données au fichier existant.

    """
    mode = 'a' if append else 'w'
    with open(output_path, mode, newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        
        # En-têtes seulement si on crée un nouveau fichier
        if not append:
            writer.writerow([
                'file_id_local',
                'root_folder_id',
                'old_path',
                'new_path',
                'file_path_on_disk',
                'file_hash',
                'file_exists',
                'match_count',
                'is_duplicate',
                'duplicate_count'
            ])
        
        # Écrire les données
        for hash_info in hash_infos:
            is_duplicate = hash_info.file_hash in duplicates
            duplicate_count = len(duplicates.get(hash_info.file_hash, []))
            
            writer.writerow([
                hash_info.file_id_local,
                hash_info.root_folder_id,
                hash_info.old_path,
                hash_info.new_path,
                hash_info.file_path_on_disk,
                hash_info.file_hash,
                'OUI' if hash_info.file_exists else 'NON',
                hash_info.match_count,
                'OUI' if is_duplicate else 'NON',
                duplicate_count if is_duplicate else 0
            ])


def main() -> None:
    """Fonction principale du script."""
    load_dotenv()
    
    base_dir = Path(__file__).parent
    scan_db_filename = _load_scan_db_filename()
    catalog_filename = _load_catalog_filename()
    photos_directory = _load_photos_directory()
    
    scan_db = base_dir / 'resultats_scan' / scan_db_filename
    catalog = base_dir / 'catalogue_lightroom' / catalog_filename
    
    print("1. Identification des repertoires qui peuvent etre remplaces...")
    print("Chargement des donnees du scan...")
    photos_by_filename = load_scan_photos(scan_db)
    print(f"  {len(photos_by_filename)} fichiers uniques charges")
    
    print("Chargement des fichiers Lightroom...")
    lightroom_files = load_lightroom_files(catalog)
    print(f"  {len(lightroom_files)} fichiers Lightroom charges")
    
    print("Recherche des correspondances...")
    matches = find_matches(lightroom_files, photos_by_filename, base_path=photos_directory)
    print(f"  {len(matches)} correspondances trouvees")
    
    # Filtrer les matches avec au moins 5 fichiers (comme dans update_lightroom_paths)
    updates_by_root, match_counts = _group_matches_by_root(matches)
    valid_matches = [
        m for m in matches
        if match_counts.get(m.lightroom_file.root_folder_id, 0) >= 5
    ]
    print(f"  {len(valid_matches)} correspondances valides (>= 5 fichiers par root_folder)")
    
    print("\n2. Calcul du hash BLAKE256 du contenu des fichiers sur le disque...")
    print(f"  Traitement de {len(valid_matches)} fichiers (cela peut prendre du temps)...")
    print(f"  Sauvegarde par tranches de 1000 fichiers...")
    
    # Préparer le fichier CSV de sortie
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = base_dir / 'resultats_scan'
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f'test_file_hashes_{timestamp}.csv'
    
    # Dictionnaire pour stocker les doublons au fur et à mesure
    duplicates: Dict[str, List[FileHashInfo]] = {}
    
    # Charger le nombre de cœurs depuis .env
    num_cores = _load_num_cores()
    print(f"  Utilisation de {num_cores} cœurs pour le traitement parallèle")
    
    # Traiter les matches avec sauvegarde par tranches
    process_matches_for_hashing(
        valid_matches,
        catalog,
        photos_directory,
        output_file,
        duplicates,
        batch_size=1000,
        num_cores=num_cores
    )
    
    print(f"\n  {len(valid_matches)} fichiers traites")
    
    print("\n3. Detection des doublons basés sur le hash du contenu...")
    # Filtrer les doublons (seulement ceux avec plus d'un fichier)
    final_duplicates = {
        h: files for h, files in duplicates.items()
        if len(files) > 1
    }
    duplicate_count = sum(len(files) for files in final_duplicates.values())
    print(f"  {len(final_duplicates)} hash uniques avec doublons")
    print(f"  {duplicate_count} fichiers concernes par des doublons")
    
    if final_duplicates:
        print("\n  Exemples de doublons detectes :")
        for i, (file_hash, files) in enumerate(list(final_duplicates.items())[:5], 1):
            print(f"    Doublon {i} (hash: {file_hash[:16]}...):")
            for f in files[:3]:  # Afficher max 3 fichiers par doublon
                print(f"      - File ID {f.file_id_local}: {f.file_path_on_disk}")
            if len(files) > 3:
                print(f"      ... et {len(files) - 3} autres fichiers")
    
    print(f"\n4. Resultats sauvegardes dans : {output_file}")
    
    print("\n[OK] Analyse terminee !")


if __name__ == '__main__':
    main()


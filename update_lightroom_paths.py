"""Script pour mettre à jour les répertoires obsolètes du catalogue Lightroom.

Ce module permet de remplacer les anciens répertoires du catalogue Lightroom
par les nouveaux répertoires basés sur les données du scan des photos.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import Counter
import os
from dotenv import load_dotenv


@dataclass
class PhotoScan:
    """Représente une photo du scan avec ses informations."""

    repertoire: str
    nom_fichier: str
    id: int


@dataclass
class LightroomFile:
    """Représente un fichier dans le catalogue Lightroom."""

    id_local: int
    base_name: str
    extension: str
    folder_id: int
    root_folder_id: int
    old_absolute_path: str
    path_from_root: str


@dataclass
class MatchResult:
    """Résultat de la correspondance entre un fichier Lightroom et un scan."""

    lightroom_file: LightroomFile
    photo_scan: PhotoScan
    new_absolute_path: str
    confidence: float


def load_scan_photos(
    db_path: Path,
) -> Dict[str, List[PhotoScan]]:
    """Charge les photos depuis la base de données du scan.

    Args:
        db_path: Chemin vers la base de données SQLite du scan.

    Returns:
        Dictionnaire indexé par nom de fichier contenant les photos.

    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, repertoire, nom_fichier FROM photos'
    )
    rows = cursor.fetchall()

    photos_by_filename: Dict[str, List[PhotoScan]] = {}
    for row in rows:
        photo_id, repertoire, nom_fichier = row
        photo = PhotoScan(
            repertoire=repertoire,
            nom_fichier=nom_fichier,
            id=photo_id
        )
        if nom_fichier not in photos_by_filename:
            photos_by_filename[nom_fichier] = []
        photos_by_filename[nom_fichier].append(photo)

    conn.close()
    return photos_by_filename


def load_lightroom_files(
    catalog_path: Path,
) -> List[LightroomFile]:
    """Charge les fichiers depuis le catalogue Lightroom.

    Args:
        catalog_path: Chemin vers le fichier catalogue Lightroom (.lrcat).

    Returns:
        Liste des fichiers Lightroom avec leurs informations.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()

    query = '''
        SELECT
            fl.id_local,
            fl.baseName,
            fl.extension,
            fl.folder,
            f.rootFolder,
            rf.absolutePath,
            f.pathFromRoot
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
    '''
    cursor.execute(query)
    rows = cursor.fetchall()

    files: List[LightroomFile] = []
    for row in rows:
        file_obj = LightroomFile(
            id_local=row[0],
            base_name=row[1],
            extension=row[2],
            folder_id=row[3],
            root_folder_id=row[4],
            old_absolute_path=row[5],
            path_from_root=row[6]
        )
        files.append(file_obj)

    conn.close()
    return files


def extract_path_components(path: str) -> List[str]:
    """Extrait les composants d'un chemin.

    Args:
        path: Chemin à analyser.

    Returns:
        Liste des composants du chemin (normalisés).

    """
    normalized = path.replace('\\', '/').strip('/')
    if not normalized:
        return []
    components = [
        c for c in normalized.split('/') if c
    ]
    return components


def compare_paths(
    old_path: str,
    new_repertoire: str,
) -> float:
    """Compare deux chemins en se basant sur les 1-2 derniers composants.

    Args:
        old_path: Ancien chemin absolu.
        new_repertoire: Nouveau répertoire relatif.

    Returns:
        Score de correspondance entre 0.0 et 1.0.

    """
    old_components = extract_path_components(old_path)
    new_components = extract_path_components(new_repertoire)

    if not old_components or not new_components:
        return 0.0

    # Comparer les 1-2 derniers composants
    old_last = old_components[-1].lower()
    new_last = new_components[-1].lower()

    if old_last == new_last:
        if len(old_components) >= 2 and len(new_components) >= 2:
            old_second = old_components[-2].lower()
            new_second = new_components[-2].lower()
            if old_second == new_second:
                return 1.0
        return 0.8

    if len(old_components) >= 2 and len(new_components) >= 2:
        old_second = old_components[-2].lower()
        new_second = new_components[-2].lower()
        if old_second == new_last or old_last == new_second:
            return 0.6

    return 0.0


def verify_filename_match(
    lr_base_name: str,
    lr_extension: str,
    scan_filename: str,
) -> bool:
    """Vérifie que les noms de fichiers correspondent.

    Args:
        lr_base_name: Nom de base du fichier Lightroom.
        lr_extension: Extension du fichier Lightroom.
        scan_filename: Nom complet du fichier du scan.

    Returns:
        True si les fichiers correspondent, False sinon.

    """
    lr_full_name = f"{lr_base_name}.{lr_extension}".lower()
    scan_name_lower = scan_filename.lower()

    # Correspondance exacte (BaseName+extension)
    return lr_full_name == scan_name_lower


def _build_new_path(
    base_path: str,
    repertoire: str,
) -> str:
    """Construit le nouveau chemin absolu.

    Args:
        base_path: Chemin de base.
        repertoire: Répertoire relatif.

    Returns:
        Nouveau chemin absolu normalisé.

    """
    new_path = os.path.join(
        base_path,
        repertoire
    ).replace('\\', '/')
    if not new_path.endswith('/'):
        new_path += '/'
    return new_path


def _find_best_match_for_file(
    lr_file: LightroomFile,
    candidates: List[PhotoScan],
    base_path: str,
) -> Optional[MatchResult]:
    """Trouve la meilleure correspondance pour un fichier Lightroom.

    Args:
        lr_file: Fichier Lightroom à matcher.
        candidates: Liste des photos candidates.
        base_path: Chemin de base pour les nouveaux répertoires.

    Returns:
        Meilleure correspondance trouvée ou None.

    """
    best_match: Optional[MatchResult] = None
    best_score = 0.0

    for photo in candidates:
        if not verify_filename_match(
            lr_file.base_name,
            lr_file.extension,
            photo.nom_fichier
        ):
            continue

        score = compare_paths(
            lr_file.old_absolute_path,
            photo.repertoire
        )

        if score > best_score:
            new_path = _build_new_path(base_path, photo.repertoire)
            best_match = MatchResult(
                lightroom_file=lr_file,
                photo_scan=photo,
                new_absolute_path=new_path,
                confidence=score
            )
            best_score = score

    return best_match if best_score >= 0.6 else None


def find_matches(
    lightroom_files: List[LightroomFile],
    photos_by_filename: Dict[str, List[PhotoScan]],
    base_path: Optional[str] = None,
) -> List[MatchResult]:
    """Trouve les correspondances entre fichiers Lightroom et photos scannées.

    Args:
        lightroom_files: Liste des fichiers Lightroom.
        photos_by_filename: Dictionnaire des photos indexées par nom.
        base_path: Chemin de base pour les nouveaux répertoires.
                   Si None, charge depuis le fichier .env.

    Returns:
        Liste des correspondances trouvées.

    """
    if base_path is None:
        base_path = _load_photos_directory()
    
    matches: List[MatchResult] = []

    for lr_file in lightroom_files:
        filename = f"{lr_file.base_name}.{lr_file.extension}"
        if filename not in photos_by_filename:
            continue

        candidates = photos_by_filename[filename]
        best_match = _find_best_match_for_file(
            lr_file,
            candidates,
            base_path
        )

        if best_match:
            matches.append(best_match)

    return matches


def _count_total_files_in_root_folder(
    cursor: sqlite3.Cursor,
    root_id: int,
) -> int:
    """Compte le nombre total de fichiers dans un root_folder.

    Args:
        cursor: Curseur de base de données.
        root_id: ID du root_folder.

    Returns:
        Nombre total de fichiers dans ce root_folder.

    """
    cursor.execute('''
        SELECT COUNT(fl.id_local)
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        WHERE f.rootFolder = ?
    ''', (root_id,))
    result = cursor.fetchone()
    return result[0] if result else 0


def _group_matches_by_root(
    matches: List[MatchResult],
) -> Tuple[Dict[int, str], Dict[int, int]]:
    """Group les correspondances par root_folder_id.

    Args:
        matches: Liste des correspondances.

    Returns:
        Tuple (dictionnaire root_id -> nouveau chemin, dictionnaire root_id -> nombre de matches).

    """
    updates_by_root: Dict[int, str] = {}
    match_counts: Dict[int, int] = {}
    for match in matches:
        root_id = match.lightroom_file.root_folder_id
        if root_id not in updates_by_root:
            updates_by_root[root_id] = match.new_absolute_path
        match_counts[root_id] = match_counts.get(root_id, 0) + 1
    return updates_by_root, match_counts


def _normalize_path_for_comparison(path: str) -> str:
    """Normalise un chemin pour la comparaison.

    Args:
        path: Chemin à normaliser.

    Returns:
        Chemin normalisé.

    """
    if not path:
        return ''
    normalized = path.replace('\\', '/').strip()
    if normalized and not normalized.endswith('/'):
        normalized += '/'
    return normalized.lower()


def _merge_root_folders(
    cursor: sqlite3.Cursor,
    source_root_id: int,
    target_root_id: int,
    dry_run: bool,
) -> int:
    """Fusionne les fichiers d'un root_folder vers un autre.

    Pour chaque fichier du second root_folder, applique l'ID du premier
    root_folder en trouvant le dossier correspondant (même pathFromRoot).

    Args:
        cursor: Curseur de base de données.
        source_root_id: ID du root_folder source (à fusionner).
        target_root_id: ID du root_folder cible (qui recevra les fichiers).
        dry_run: Si True, ne fait que simuler.

    Returns:
        Nombre de fichiers fusionnés.

    """
    # Récupérer tous les fichiers du source avec leur dossier, pathFromRoot et lc_idx_filename
    cursor.execute('''
        SELECT fl.id_local, fl.folder, f.pathFromRoot, fl.lc_idx_filename
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        WHERE f.rootFolder = ?
    ''', (source_root_id,))
    source_files = cursor.fetchall()
    
    if not source_files:
        return 0
    
    total_files_merged = 0
    
    if not dry_run:
        for file_id, source_folder_id, path_from_root, lc_idx_filename in source_files:
            # Trouver le dossier correspondant dans le target (même pathFromRoot)
            cursor.execute('''
                SELECT id_local
                FROM AgLibraryFolder
                WHERE rootFolder = ? AND pathFromRoot = ?
            ''', (target_root_id, path_from_root))
            target_folder = cursor.fetchone()
            
            if target_folder:
                target_folder_id = target_folder[0]
                
                # Vérifier si un fichier avec le même lc_idx_filename existe déjà dans le dossier cible
                cursor.execute('''
                    SELECT id_local
                    FROM AgLibraryFile
                    WHERE folder = ? AND lc_idx_filename = ?
                ''', (target_folder_id, lc_idx_filename))
                existing_file = cursor.fetchone()
                
                if not existing_file:
                    # Le fichier n'existe pas dans le dossier cible, on peut le fusionner
                    cursor.execute('''
                        UPDATE AgLibraryFile
                        SET folder = ?
                        WHERE id_local = ?
                    ''', (target_folder_id, file_id))
                    total_files_merged += 1
                # Si le fichier existe déjà, on ignore (doublon)
            # Si le dossier n'existe pas dans le target, on ignore le fichier
    else:
        # Mode dry_run : compter seulement les fichiers qui peuvent être fusionnés
        for file_id, source_folder_id, path_from_root, lc_idx_filename in source_files:
            cursor.execute('''
                SELECT id_local
                FROM AgLibraryFolder
                WHERE rootFolder = ? AND pathFromRoot = ?
            ''', (target_root_id, path_from_root))
            target_folder = cursor.fetchone()
            
            if target_folder:
                target_folder_id = target_folder[0]
                
                # Vérifier si un fichier avec le même lc_idx_filename existe déjà
                cursor.execute('''
                    SELECT id_local
                    FROM AgLibraryFile
                    WHERE folder = ? AND lc_idx_filename = ?
                ''', (target_folder_id, lc_idx_filename))
                existing_file = cursor.fetchone()
                
                if not existing_file:
                    total_files_merged += 1
    
    return total_files_merged


def _update_single_root_folder(
    cursor: sqlite3.Cursor,
    root_id: int,
    new_path: str,
    dry_run: bool,
) -> Tuple[bool, bool, bool, int]:
    """Met à jour un seul répertoire racine.

    Args:
        cursor: Curseur de base de données.
        root_id: ID du répertoire racine.
        new_path: Nouveau chemin.
        dry_run: Si True, ne fait que simuler.

    Returns:
        Tuple (updated, skipped, conflict, merged_count).

    """
    cursor.execute(
        'SELECT absolutePath FROM AgLibraryRootFolder WHERE id_local = ?',
        (root_id,)
    )
    result = cursor.fetchone()
    
    if result:
        current_path = result[0] or ''
        # Normaliser les deux chemins pour la comparaison
        current_normalized = _normalize_path_for_comparison(current_path)
        new_normalized = _normalize_path_for_comparison(new_path)
        
        if current_normalized == new_normalized:
            return (False, True, False, 0)

    # Vérifier si le nouveau chemin existe déjà pour un autre root_folder_id
    cursor.execute(
        'SELECT id_local FROM AgLibraryRootFolder WHERE absolutePath = ? AND id_local != ?',
        (new_path, root_id)
    )
    existing = cursor.fetchone()
    
    if existing:
        # Le chemin existe déjà pour un autre root_folder_id
        # Fusionner les fichiers du second root_folder vers le premier
        existing_root_id = existing[0]
        merged_count = _merge_root_folders(cursor, root_id, existing_root_id, dry_run)
        if merged_count > 0:
            return (True, False, False, merged_count)  # Fusionné avec succès
        return (False, False, True, 0)  # Conflit non résolu

    # Le chemin est différent et n'existe pas déjà, on peut mettre à jour
    if not dry_run:
        cursor.execute(
            'UPDATE AgLibraryRootFolder SET absolutePath = ? WHERE id_local = ?',
            (new_path, root_id)
        )
        return (True, False, False, 0)
    
    # Mode dry_run : on simule la mise à jour
    return (True, False, False, 0)


def _find_matches_by_filename_only(
    catalog_path: Path,
    root_id: int,
    photos_by_filename: Dict[str, List[PhotoScan]],
    photos_base_path: str
) -> List[MatchResult]:
    """Trouve des correspondances par nom de fichier uniquement pour un root_folder.

    Args:
        catalog_path: Chemin vers le catalogue Lightroom.
        root_id: ID du root_folder à traiter.
        photos_by_filename: Dictionnaire des photos indexées par nom.
        photos_base_path: Chemin de base des photos.

    Returns:
        Liste des correspondances trouvées par nom uniquement.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()
    
    # Récupérer tous les fichiers de ce root_folder
    cursor.execute('''
        SELECT
            fl.id_local,
            fl.baseName,
            fl.extension,
            fl.folder,
            f.rootFolder,
            rf.absolutePath,
            f.pathFromRoot
        FROM AgLibraryFile fl
        JOIN AgLibraryFolder f ON fl.folder = f.id_local
        JOIN AgLibraryRootFolder rf ON f.rootFolder = rf.id_local
        WHERE rf.id_local = ?
    ''', (root_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    matches: List[MatchResult] = []
    
    for row in rows:
        file_id, base_name, extension, folder_id, root_folder_id, old_path, path_from_root = row
        
        filename = f"{base_name}.{extension}"
        if filename not in photos_by_filename:
            continue
        
        # Prendre le premier candidat trouvé (par nom uniquement)
        candidates = photos_by_filename[filename]
        if not candidates:
            continue
        
        # Utiliser le premier candidat trouvé
        photo = candidates[0]
        
        lr_file = LightroomFile(
            id_local=file_id,
            base_name=base_name,
            extension=extension,
            folder_id=folder_id,
            root_folder_id=root_folder_id,
            old_absolute_path=old_path or '',
            path_from_root=path_from_root or ''
        )
        
        new_path = _build_new_path(photos_base_path, photo.repertoire)
        
        match = MatchResult(
            lightroom_file=lr_file,
            photo_scan=photo,
            new_absolute_path=new_path,
            confidence=0.5  # Score faible car correspondance par nom uniquement
        )
        matches.append(match)
    
    return matches


def _count_root_folders_without_matches(
    cursor: sqlite3.Cursor,
    photos_base_path: str,
) -> int:
    """Compte les root_folders qui ne sont pas dans le nouveau chemin.

    Args:
        cursor: Curseur de base de données.
        photos_base_path: Chemin de base des photos.

    Returns:
        Nombre de root_folders sans matches.

    """
    cursor.execute('''
        SELECT COUNT(DISTINCT rf.id_local)
        FROM AgLibraryRootFolder rf
        WHERE rf.absolutePath NOT LIKE ? || '%'
    ''', (photos_base_path,))
    result = cursor.fetchone()
    return result[0] if result else 0


def _find_root_folders_without_matches(
    cursor: sqlite3.Cursor,
    root_ids_with_matches: set,
    photos_base_path: str,
) -> List[int]:
    """Trouve les root_folders sans matches qui ont des fichiers.

    Args:
        cursor: Curseur de base de données.
        root_ids_with_matches: Ensemble des IDs de root_folders avec matches.
        photos_base_path: Chemin de base des photos.

    Returns:
        Liste des IDs de root_folders sans matches.

    """
    cursor.execute('''
        SELECT DISTINCT rf.id_local
        FROM AgLibraryRootFolder rf
        JOIN AgLibraryFolder f ON rf.id_local = f.rootFolder
        JOIN AgLibraryFile fl ON f.id_local = fl.folder
        WHERE rf.absolutePath NOT LIKE ? || '%'
    ''', (photos_base_path,))
    
    root_folders_with_files = cursor.fetchall()
    root_ids_without_matches = [
        root_id for root_id, in root_folders_with_files
        if root_id not in root_ids_with_matches
    ]
    
    return root_ids_without_matches


def _find_most_common_path_from_matches(
    filename_matches: List[MatchResult],
    root_id: int,
) -> Optional[Tuple[str, int]]:
    """Trouve le chemin le plus fréquent parmi les matches.

    Args:
        filename_matches: Liste des matches par nom de fichier.
        root_id: ID du root_folder à traiter.

    Returns:
        Tuple (chemin le plus fréquent, nombre de matches) ou None.

    """
    path_counts: Counter[str] = Counter()
    for match in filename_matches:
        if match.lightroom_file.root_folder_id == root_id:
            path_counts[match.new_absolute_path] += 1
    
    if not path_counts:
        return None
    
    most_common_path, path_count = path_counts.most_common(1)[0]
    return (most_common_path, path_count)


def _process_single_root_folder_by_filename(
    cursor: sqlite3.Cursor,
    catalog_path: Path,
    root_id: int,
    photos_by_filename: Dict[str, List[PhotoScan]],
    photos_base_path: str,
    min_matches: int,
    dry_run: bool,
) -> Tuple[bool, bool, bool, int]:
    """Traite un root_folder sans match avec recherche par nom.

    Args:
        cursor: Curseur de base de données.
        catalog_path: Chemin vers le catalogue Lightroom.
        root_id: ID du root_folder à traiter.
        photos_by_filename: Dictionnaire des photos indexées par nom.
        photos_base_path: Chemin de base des photos.
        min_matches: Nombre minimum de matches requis.
        dry_run: Si True, ne fait que simuler.

    Returns:
        Tuple (updated, skipped, conflict, merged_count).

    """
    filename_matches = _find_matches_by_filename_only(
        catalog_path,
        root_id,
        photos_by_filename,
        photos_base_path
    )
    
    if not filename_matches:
        return (False, False, False, 0)
    
    result = _find_most_common_path_from_matches(filename_matches, root_id)
    if not result:
        return (False, False, False, 0)
    
    most_common_path, filename_match_count = result
    total_files = _count_total_files_in_root_folder(cursor, root_id)
    
    if not _validate_root_folder_update(
        total_files,
        filename_match_count,
        min_matches
    ):
        return (False, False, False, 0)
    
    return _update_single_root_folder(
        cursor,
        root_id,
        most_common_path,
        dry_run
    )


def _update_stats_from_result(
    stats: Dict[str, int],
    was_updated: bool,
    was_skipped: bool,
    has_conflict: bool,
    merged_count: int,
) -> None:
    """Met à jour les statistiques à partir d'un résultat.

    Args:
        stats: Dictionnaire de statistiques à mettre à jour.
        was_updated: Si True, le root_folder a été mis à jour.
        was_skipped: Si True, le root_folder a été ignoré.
        has_conflict: Si True, il y a eu un conflit.
        merged_count: Nombre de fichiers fusionnés.

    """
    if was_updated:
        stats['updated'] += 1
        stats['merged'] += merged_count
        stats['no_matches'] -= 1
    elif was_skipped:
        stats['skipped'] += 1
        stats['no_matches'] -= 1
    elif has_conflict:
        stats['conflicts'] += 1
        stats['no_matches'] -= 1


def _process_root_folders_without_matches(
    cursor: sqlite3.Cursor,
    catalog_path: Path,
    root_ids_without_matches: List[int],
    photos_by_filename: Optional[Dict[str, List[PhotoScan]]],
    photos_base_path: Optional[str],
    min_matches: int,
    dry_run: bool,
) -> Dict[str, int]:
    """Traite les root_folders sans matches avec recherche par nom.

    Args:
        cursor: Curseur de base de données.
        catalog_path: Chemin vers le catalogue Lightroom.
        root_ids_without_matches: Liste des IDs de root_folders sans matches.
        photos_by_filename: Dictionnaire des photos (optionnel).
        photos_base_path: Chemin de base des photos (optionnel).
        min_matches: Nombre minimum de matches requis.
        dry_run: Si True, ne fait que simuler.

    Returns:
        Dictionnaire avec les statistiques (updated, skipped, conflicts,
        merged, no_matches).

    """
    stats = {
        'updated': 0,
        'skipped': 0,
        'conflicts': 0,
        'merged': 0,
        'no_matches': len(root_ids_without_matches)
    }
    
    if not photos_by_filename or not photos_base_path:
        return stats
    
    for root_id in root_ids_without_matches:
        result = _process_single_root_folder_by_filename(
            cursor,
            catalog_path,
            root_id,
            photos_by_filename,
            photos_base_path,
            min_matches,
            dry_run
        )
        
        _update_stats_from_result(stats, *result)
    
    return stats


def _validate_root_folder_update(
    total_files: int,
    match_count: int,
    min_matches: int,
) -> bool:
    """Valide si un root_folder peut être mis à jour.

    Args:
        total_files: Nombre total de fichiers dans le root_folder.
        match_count: Nombre de matches trouvés.
        min_matches: Nombre minimum de matches requis.

    Returns:
        True si le root_folder peut être mis à jour, False sinon.

    """
    if total_files < min_matches:
        # Si le répertoire a moins de min_matches fichiers,
        # accepter seulement si toutes les photos correspondent
        return match_count == total_files
    
    # Si le répertoire a min_matches fichiers ou plus,
    # appliquer le seuil de min_matches normalement
    return match_count >= min_matches


def _process_root_folders_with_matches(
    cursor: sqlite3.Cursor,
    updates_by_root: Dict[int, str],
    match_counts: Dict[int, int],
    min_matches: int,
    dry_run: bool,
) -> Dict[str, int]:
    """Traite les root_folders avec matches.

    Args:
        cursor: Curseur de base de données.
        updates_by_root: Dictionnaire root_id -> nouveau chemin.
        match_counts: Dictionnaire root_id -> nombre de matches.
        min_matches: Nombre minimum de matches requis.
        dry_run: Si True, ne fait que simuler.

    Returns:
        Dictionnaire avec les statistiques (updated, skipped, conflicts,
        rejected, merged).

    """
    stats = {
        'updated': 0,
        'skipped': 0,
        'conflicts': 0,
        'rejected': 0,
        'merged': 0
    }
    
    for root_id, new_path in updates_by_root.items():
        total_files = _count_total_files_in_root_folder(cursor, root_id)
        match_count = match_counts.get(root_id, 0)
        
        if not _validate_root_folder_update(total_files, match_count, min_matches):
            stats['rejected'] += 1
            continue
        
        was_updated, was_skipped, has_conflict, merged_count = (
            _update_single_root_folder(
                cursor,
                root_id,
                new_path,
                dry_run
            )
        )
        
        if was_updated:
            stats['updated'] += 1
            stats['merged'] += merged_count
        elif was_skipped:
            stats['skipped'] += 1
        elif has_conflict:
            stats['conflicts'] += 1
    
    return stats


def _merge_update_stats(
    stats_with_matches: Dict[str, int],
    stats_no_matches: Dict[str, int],
) -> Dict[str, int]:
    """Fusionne les statistiques des mises à jour.

    Args:
        stats_with_matches: Statistiques des root_folders avec matches.
        stats_no_matches: Statistiques des root_folders sans matches.

    Returns:
        Dictionnaire avec les statistiques fusionnées.

    """
    return {
        'updated': stats_with_matches['updated'] + stats_no_matches['updated'],
        'skipped': stats_with_matches['skipped'] + stats_no_matches['skipped'],
        'conflicts': stats_with_matches['conflicts'] + stats_no_matches['conflicts'],
        'rejected': stats_with_matches['rejected'],
        'no_matches': stats_no_matches['no_matches'],
        'merged': stats_with_matches['merged'] + stats_no_matches['merged']
    }


def update_root_folders(
    catalog_path: Path,
    matches: List[MatchResult],
    dry_run: bool = False,
    min_matches: int = 5,
    photos_by_filename: Optional[Dict[str, List[PhotoScan]]] = None,
    photos_base_path: Optional[str] = None,
) -> Dict[str, int]:
    """Met à jour les répertoires racine dans le catalogue Lightroom.

    Args:
        catalog_path: Chemin vers le catalogue Lightroom.
        matches: Liste des correspondances à appliquer.
        dry_run: Si True, ne fait que simuler les modifications.
        min_matches: Nombre minimum de fichiers en commun requis pour mettre à jour.
        photos_by_filename: Dictionnaire des photos pour recherche par nom (optionnel).
        photos_base_path: Chemin de base des photos pour recherche par nom (optionnel).

    Returns:
        Dictionnaire avec les statistiques des mises à jour.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()
    
    photos_base_path_normalized = _load_photos_directory().replace('\\', '/')
    
    if not matches:
        no_matches = _count_root_folders_without_matches(
            cursor,
            photos_base_path_normalized
        )
        conn.close()
        return {
            'updated': 0,
            'skipped': 0,
            'conflicts': 0,
            'rejected': 0,
            'no_matches': no_matches,
            'merged': 0
        }
    
    updates_by_root, match_counts = _group_matches_by_root(matches)
    root_ids_with_matches = set(updates_by_root.keys())
    
    root_ids_without_matches = _find_root_folders_without_matches(
        cursor,
        root_ids_with_matches,
        photos_base_path_normalized
    )
    
    stats_no_matches = _process_root_folders_without_matches(
        cursor,
        catalog_path,
        root_ids_without_matches,
        photos_by_filename,
        photos_base_path or photos_base_path_normalized,
        min_matches,
        dry_run
    )
    
    stats_with_matches = _process_root_folders_with_matches(
        cursor,
        updates_by_root,
        match_counts,
        min_matches,
        dry_run
    )
    
    stats = _merge_update_stats(stats_with_matches, stats_no_matches)
    
    if not dry_run:
        conn.commit()
    conn.close()
    
    return stats


def _load_dry_run_mode() -> bool:
    """Charge le mode dry_run depuis le fichier .env.

    Returns:
        True si DRY_RUN_MODE=true dans .env, False sinon.
        Par défaut retourne True (mode simulation).

    """
    load_dotenv()
    dry_run_str = os.getenv('DRY_RUN_MODE', 'true').lower()
    return dry_run_str in ('true', '1', 'yes', 'on')


def _load_photos_directory() -> str:
    """Charge le répertoire de base des photos depuis le fichier .env.

    Returns:
        Chemin du répertoire de base des photos.

    """
    load_dotenv()
    return os.getenv('PHOTOS_DIRECTORY', r'\\hal9001\Volume_1\photos')


def _load_scan_db_filename() -> str:
    """Charge le nom du fichier de base de données du scan depuis le fichier .env.

    Returns:
        Nom du fichier de base de données du scan.

    """
    load_dotenv()
    return os.getenv('SCAN_DB_FILENAME', 'photos_scan_20251107_192045.db')


def _load_catalog_filename() -> str:
    """Charge le nom du fichier catalogue Lightroom depuis le fichier .env.

    Returns:
        Nom du fichier catalogue Lightroom.

    """
    load_dotenv()
    return os.getenv('CATALOG_FILENAME', 'catalogue 2 - dès juin 2017-2-2-v12.lrcat')


def main() -> None:
    """Fonction principale du script."""
    base_dir = Path(__file__).parent
    
    # Charger les chemins depuis le fichier .env
    scan_db_filename = _load_scan_db_filename()
    catalog_filename = _load_catalog_filename()
    photos_directory = _load_photos_directory()
    
    scan_db = base_dir / 'resultats_scan' / scan_db_filename
    catalog = base_dir / 'catalogue_lightroom' / catalog_filename

    print("Chargement des données du scan...")
    photos_by_filename = load_scan_photos(scan_db)
    print(f"  {len(photos_by_filename)} fichiers uniques chargés")

    print("Chargement des fichiers Lightroom...")
    lightroom_files = load_lightroom_files(catalog)
    print(f"  {len(lightroom_files)} fichiers Lightroom chargés")

    print("Recherche des correspondances...")
    matches = find_matches(lightroom_files, photos_by_filename, base_path=photos_directory)
    print(f"  {len(matches)} correspondances trouvées")

    dry_run_mode = _load_dry_run_mode()
    print(f"\nMise à jour des répertoires (mode {'DRY-RUN' if dry_run_mode else 'APPLICATION'})...")
    stats = update_root_folders(
        catalog,
        matches,
        dry_run=dry_run_mode,
        min_matches=5,
        photos_by_filename=photos_by_filename,
        photos_base_path=photos_directory
    )
    print(f"  {stats['updated']} répertoires mis à jour")
    print(f"  {stats['skipped']} répertoires déjà à jour")
    if stats.get('conflicts', 0) > 0:
        print(f"  ⚠️  {stats['conflicts']} conflits (chemin déjà utilisé par un autre root_folder)")
    if stats.get('rejected', 0) > 0:
        print(f"  ⚠️  {stats['rejected']} répertoires rejetés (moins de 5 fichiers en commun)")
    if stats.get('no_matches', 0) > 0:
        print(f"  ⚠️  {stats['no_matches']} répertoires sans correspondances trouvées")
    if stats.get('merged', 0) > 0:
        print(f"  ✅ {stats['merged']} fichiers fusionnés vers d'autres root_folders")

    if dry_run_mode:
        print("\n⚠️  Mode DRY-RUN : aucune modification n'a été appliquée")
        print("Pour appliquer les modifications, modifiez DRY_RUN_MODE=false dans le fichier .env")
    else:
        print("\n✅ Modifications appliquées avec succès !")


if __name__ == '__main__':
    main()


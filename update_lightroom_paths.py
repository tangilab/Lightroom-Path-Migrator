"""Script pour mettre à jour les répertoires obsolètes du catalogue Lightroom.

Ce module permet de remplacer les anciens répertoires du catalogue Lightroom
par les nouveaux répertoires basés sur les données du scan des photos.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
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


def _update_single_root_folder(
    cursor: sqlite3.Cursor,
    root_id: int,
    new_path: str,
    dry_run: bool,
) -> Tuple[bool, bool, bool]:
    """Met à jour un seul répertoire racine.

    Args:
        cursor: Curseur de base de données.
        root_id: ID du répertoire racine.
        new_path: Nouveau chemin.
        dry_run: Si True, ne fait que simuler.

    Returns:
        Tuple (updated, skipped, conflict).

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
            return (False, True, False)

    # Vérifier si le nouveau chemin existe déjà pour un autre root_folder_id
    cursor.execute(
        'SELECT id_local FROM AgLibraryRootFolder WHERE absolutePath = ? AND id_local != ?',
        (new_path, root_id)
    )
    existing = cursor.fetchone()
    
    if existing:
        # Le chemin existe déjà pour un autre root_folder_id
        # On ne peut pas mettre à jour à cause de la contrainte UNIQUE
        return (False, False, True)

    # Le chemin est différent et n'existe pas déjà, on peut mettre à jour
    if not dry_run:
        cursor.execute(
            'UPDATE AgLibraryRootFolder SET absolutePath = ? WHERE id_local = ?',
            (new_path, root_id)
        )
        return (True, False, False)
    
    # Mode dry_run : on simule la mise à jour
    return (True, False, False)


def update_root_folders(
    catalog_path: Path,
    matches: List[MatchResult],
    dry_run: bool = False,
    min_matches: int = 5,
) -> Dict[str, int]:
    """Met à jour les répertoires racine dans le catalogue Lightroom.

    Args:
        catalog_path: Chemin vers le catalogue Lightroom.
        matches: Liste des correspondances à appliquer.
        dry_run: Si True, ne fait que simuler les modifications.
        min_matches: Nombre minimum de fichiers en commun requis pour mettre à jour.

    Returns:
        Dictionnaire avec les statistiques des mises à jour.

    """
    if not matches:
        return {'updated': 0, 'skipped': 0, 'conflicts': 0, 'rejected': 0}

    updates_by_root, match_counts = _group_matches_by_root(matches)

    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()

    updated = 0
    skipped = 0
    conflicts = 0
    rejected = 0

    for root_id, new_path in updates_by_root.items():
        # Vérifier si on a assez de matches pour ce root_folder_id
        if match_counts.get(root_id, 0) < min_matches:
            rejected += 1
            continue

        was_updated, was_skipped, has_conflict = _update_single_root_folder(
            cursor,
            root_id,
            new_path,
            dry_run
        )
        if was_updated:
            updated += 1
        elif was_skipped:
            skipped += 1
        elif has_conflict:
            conflicts += 1

    if not dry_run:
        conn.commit()
    conn.close()

    return {'updated': updated, 'skipped': skipped, 'conflicts': conflicts, 'rejected': rejected}


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
    stats = update_root_folders(catalog, matches, dry_run=dry_run_mode, min_matches=5)
    print(f"  {stats['updated']} répertoires mis à jour")
    print(f"  {stats['skipped']} répertoires déjà à jour")
    if stats.get('conflicts', 0) > 0:
        print(f"  ⚠️  {stats['conflicts']} conflits (chemin déjà utilisé par un autre root_folder)")
    if stats.get('rejected', 0) > 0:
        print(f"  ⚠️  {stats['rejected']} répertoires rejetés (moins de 5 fichiers en commun)")

    if dry_run_mode:
        print("\n⚠️  Mode DRY-RUN : aucune modification n'a été appliquée")
        print("Pour appliquer les modifications, modifiez DRY_RUN_MODE=false dans le fichier .env")
    else:
        print("\n✅ Modifications appliquées avec succès !")


if __name__ == '__main__':
    main()


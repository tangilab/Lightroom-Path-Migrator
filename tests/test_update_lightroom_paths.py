"""Tests pour le module update_lightroom_paths."""

import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List, Generator

import pytest

from update_lightroom_paths import (
    PhotoScan,
    LightroomFile,
    MatchResult,
    load_scan_photos,
    load_lightroom_files,
    extract_path_components,
    compare_paths,
    verify_filename_match,
    find_matches,
    update_root_folders,
    _build_new_path,
    _find_best_match_for_file,
    _normalize_path_for_comparison,
    _group_matches_by_root,
    _load_dry_run_mode,
    _load_photos_directory,
    _load_scan_db_filename,
    _load_catalog_filename,
)


@pytest.fixture
def temp_scan_db() -> Generator[Path, None, None]:
    """Crée une base de données temporaire pour les tests."""
    db_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.db'
    )
    db_path = Path(db_file.name)
    db_file.close()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE photos (
            id INTEGER PRIMARY KEY,
            repertoire TEXT NOT NULL,
            nom_fichier TEXT NOT NULL,
            hauteur INTEGER,
            largeur INTEGER,
            scan_date TEXT
        )
    ''')

    cursor.execute('''
        INSERT INTO photos (id, repertoire, nom_fichier, hauteur, largeur)
        VALUES
            (1, 'test/folder1', 'photo1.jpg', 100, 200),
            (2, 'test/folder2', 'photo2.jpg', 150, 250),
            (3, 'test/folder1', 'photo3.png', 200, 300)
    ''')

    conn.commit()
    conn.close()

    yield db_path

    db_path.unlink()


@pytest.fixture
def temp_lightroom_catalog() -> Generator[Path, None, None]:
    """Crée un catalogue Lightroom temporaire pour les tests."""
    catalog_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.lrcat'
    )
    catalog_path = Path(catalog_file.name)
    catalog_file.close()

    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE AgLibraryRootFolder (
            id_local INTEGER PRIMARY KEY,
            id_global TEXT,
            absolutePath TEXT NOT NULL,
            name TEXT NOT NULL,
            relativePathFromCatalog TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE AgLibraryFolder (
            id_local INTEGER PRIMARY KEY,
            id_global TEXT,
            parentId INTEGER,
            pathFromRoot TEXT NOT NULL,
            rootFolder INTEGER NOT NULL,
            visibility INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE AgLibraryFile (
            id_local INTEGER PRIMARY KEY,
            id_global TEXT,
            baseName TEXT NOT NULL,
            extension TEXT NOT NULL,
            folder INTEGER NOT NULL,
            idx_filename TEXT NOT NULL,
            lc_idx_filename TEXT NOT NULL,
            lc_idx_filenameExtension TEXT NOT NULL,
            originalFilename TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        INSERT INTO AgLibraryRootFolder (id_local, id_global, absolutePath, name)
        VALUES
            (1, 'guid1', 'G:/old/path/folder1/', 'folder1'),
            (2, 'guid2', 'G:/old/path/folder2/', 'folder2')
    ''')

    cursor.execute('''
        INSERT INTO AgLibraryFolder (id_local, id_global, pathFromRoot, rootFolder)
        VALUES
            (10, 'guid10', '', 1),
            (20, 'guid20', '', 2)
    ''')

    cursor.execute('''
        INSERT INTO AgLibraryFile (id_local, id_global, baseName, extension, folder, idx_filename, lc_idx_filename, lc_idx_filenameExtension, originalFilename)
        VALUES
            (100, 'guid100', 'photo1', 'jpg', 10, 'photo1.jpg', 'photo1.jpg', 'photo1.jpg', 'photo1.jpg'),
            (200, 'guid200', 'photo2', 'jpg', 20, 'photo2.jpg', 'photo2.jpg', 'photo2.jpg', 'photo2.jpg')
    ''')

    conn.commit()
    conn.close()

    yield catalog_path

    catalog_path.unlink()


def test_load_scan_photos(temp_scan_db: Path) -> None:
    """Test du chargement des photos depuis la base de scan."""
    photos = load_scan_photos(temp_scan_db)

    assert len(photos) == 3
    assert 'photo1.jpg' in photos
    assert 'photo2.jpg' in photos
    assert 'photo3.png' in photos

    assert len(photos['photo1.jpg']) == 1
    assert photos['photo1.jpg'][0].repertoire == 'test/folder1'
    assert photos['photo1.jpg'][0].nom_fichier == 'photo1.jpg'


def test_load_lightroom_files(temp_lightroom_catalog: Path) -> None:
    """Test du chargement des fichiers Lightroom."""
    files = load_lightroom_files(temp_lightroom_catalog)

    assert len(files) == 2
    assert files[0].id_local == 100
    assert files[0].base_name == 'photo1'
    assert files[0].extension == 'jpg'
    assert files[0].root_folder_id == 1
    assert files[0].old_absolute_path == 'G:/old/path/folder1/'


def test_extract_path_components() -> None:
    """Test de l'extraction des composants de chemin."""
    assert extract_path_components('test/folder1') == ['test', 'folder1']
    assert extract_path_components('G:/old/path/folder1/') == ['G:', 'old', 'path', 'folder1']
    assert extract_path_components('folder1') == ['folder1']
    assert extract_path_components('') == []
    assert extract_path_components('test\\folder1') == ['test', 'folder1']


def test_compare_paths() -> None:
    """Test de la comparaison de chemins."""
    # Correspondance exacte du dernier composant
    assert compare_paths('G:/old/path/folder1/', 'test/folder1') == 0.8

    # Correspondance des 2 derniers composants
    assert compare_paths('G:/old/path/folder1/', 'path/folder1') == 1.0

    # Pas de correspondance
    assert compare_paths('G:/old/path/folder1/', 'test/folder2') == 0.0

    # Correspondance partielle
    assert compare_paths('G:/old/path/folder1/', 'folder1/path') == 0.6


def test_verify_filename_match() -> None:
    """Test de la vérification des noms de fichiers."""
    # Correspondance exacte
    assert verify_filename_match('photo1', 'jpg', 'photo1.jpg') is True

    # Correspondance avec extension différente
    assert verify_filename_match('photo1', 'jpg', 'photo1.png') is False

    # Correspondance insensible à la casse
    assert verify_filename_match('photo1', 'jpg', 'photo1.JPG') is True

    # Pas de correspondance
    assert verify_filename_match('photo1', 'jpg', 'photo2.jpg') is False


def test_find_matches(
    temp_scan_db: Path,
    temp_lightroom_catalog: Path,
) -> None:
    """Test de la recherche de correspondances."""
    photos = load_scan_photos(temp_scan_db)
    files = load_lightroom_files(temp_lightroom_catalog)

    matches = find_matches(files, photos, base_path=r'\\hal9001\Volume_1\photos')

    assert len(matches) > 0
    assert matches[0].lightroom_file.id_local == 100
    assert matches[0].photo_scan.nom_fichier == 'photo1.jpg'
    assert 'hal9001' in matches[0].new_absolute_path


def test_update_root_folders(
    temp_lightroom_catalog: Path,
) -> None:
    """Test de la mise à jour des répertoires racine."""
    matches = [
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=100,
                base_name='photo1',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(
                id=1,
                repertoire='test/folder1',
                nom_fichier='photo1.jpg'
            ),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder1' + '\\',
            confidence=0.8
        )
    ]

    # Test en mode dry-run avec min_matches=1 (pour que le test passe)
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=True,
        min_matches=1
    )
    assert stats['updated'] == 1
    assert stats.get('conflicts', 0) == 0

    # Vérifier que rien n'a été modifié en dry-run
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    cursor.execute(
        'SELECT absolutePath FROM AgLibraryRootFolder WHERE id_local = 1'
    )
    result = cursor.fetchone()
    assert result[0] == 'G:/old/path/folder1/'
    conn.close()

    # Test avec modification réelle avec min_matches=1 (pour que le test passe)
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False,
        min_matches=1
    )
    assert stats['updated'] == 1
    assert stats.get('conflicts', 0) == 0

    # Vérifier la modification
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    cursor.execute(
        'SELECT absolutePath FROM AgLibraryRootFolder WHERE id_local = 1'
    )
    result = cursor.fetchone()
    assert r'hal9001' in result[0]
    conn.close()


def test_compare_paths_empty_components() -> None:
    """Test de compare_paths avec composants vides."""
    # Cas où old_components est vide
    assert compare_paths('', 'test/folder1') == 0.0
    # Cas où new_components est vide
    assert compare_paths('G:/old/path/folder1/', '') == 0.0
    # Cas où les deux sont vides
    assert compare_paths('', '') == 0.0


def test_compare_paths_single_component() -> None:
    """Test de compare_paths avec un seul composant."""
    # Un seul composant dans les deux
    assert compare_paths('folder1', 'folder1') == 0.8
    # Un seul composant, pas de correspondance
    assert compare_paths('folder1', 'folder2') == 0.0


def test_find_best_match_for_file_no_match() -> None:
    """Test de _find_best_match_for_file sans correspondance."""
    lr_file = LightroomFile(
        id_local=100,
        base_name='photo1',
        extension='jpg',
        folder_id=10,
        root_folder_id=1,
        old_absolute_path='G:/old/path/folder1/',
        path_from_root=''
    )
    candidates = [
        PhotoScan(id=1, repertoire='test/folder1', nom_fichier='photo2.jpg')
    ]
    result = _find_best_match_for_file(
        lr_file,
        candidates,
        r'\\hal9001\Volume_1\photos'
    )
    assert result is None


def test_find_best_match_for_file_low_score() -> None:
    """Test de _find_best_match_for_file avec score trop bas."""
    lr_file = LightroomFile(
        id_local=100,
        base_name='photo1',
        extension='jpg',
        folder_id=10,
        root_folder_id=1,
        old_absolute_path='G:/old/path/folder1/',
        path_from_root=''
    )
    candidates = [
        PhotoScan(id=1, repertoire='test/folder2', nom_fichier='photo1.jpg')
    ]
    result = _find_best_match_for_file(
        lr_file,
        candidates,
        r'\\hal9001\Volume_1\photos'
    )
    # Score devrait être 0.0 (pas de correspondance), donc None
    assert result is None


def test_find_matches_with_none_base_path(
    temp_scan_db: Path,
    temp_lightroom_catalog: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test de find_matches avec base_path=None."""
    photos = load_scan_photos(temp_scan_db)
    files = load_lightroom_files(temp_lightroom_catalog)
    
    # Mock _load_photos_directory pour retourner un chemin
    monkeypatch.setattr(
        'update_lightroom_paths._load_photos_directory',
        lambda: r'\\hal9001\Volume_1\photos'
    )
    
    matches = find_matches(files, photos, base_path=None)
    assert len(matches) > 0


def test_find_matches_filename_not_found(
    temp_lightroom_catalog: Path,
) -> None:
    """Test de find_matches quand le filename n'est pas trouvé."""
    files = load_lightroom_files(temp_lightroom_catalog)
    photos_by_filename: Dict[str, List[PhotoScan]] = {}
    
    matches = find_matches(files, photos_by_filename, base_path=r'\\hal9001\Volume_1\photos')
    assert len(matches) == 0


def test_normalize_path_for_comparison() -> None:
    """Test de _normalize_path_for_comparison."""
    # Chemin vide
    assert _normalize_path_for_comparison('') == ''
    
    # Chemin avec backslash
    assert _normalize_path_for_comparison('G:\\old\\path\\folder1') == 'g:/old/path/folder1/'
    
    # Chemin avec slash final
    assert _normalize_path_for_comparison('G:/old/path/folder1/') == 'g:/old/path/folder1/'
    
    # Chemin sans slash final
    assert _normalize_path_for_comparison('G:/old/path/folder1') == 'g:/old/path/folder1/'


def test_update_root_folders_empty_matches() -> None:
    """Test de update_root_folders avec matches vide."""
    catalog_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.lrcat'
    )
    catalog_path = Path(catalog_file.name)
    catalog_file.close()
    
    try:
        conn = sqlite3.connect(str(catalog_path))
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE AgLibraryRootFolder (
                id_local INTEGER PRIMARY KEY,
                absolutePath TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        
        stats = update_root_folders(catalog_path, [], dry_run=False)
        assert stats['updated'] == 0
        assert stats['skipped'] == 0
        assert stats['conflicts'] == 0
        assert stats.get('rejected', 0) == 0
    finally:
        catalog_path.unlink()


def test_update_root_folders_with_conflict(
    temp_lightroom_catalog: Path,
) -> None:
    """Test de update_root_folders avec conflit."""
    # Créer un root_folder avec le même chemin que celui qu'on veut mettre à jour
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO AgLibraryRootFolder (id_local, id_global, absolutePath, name)
        VALUES (3, 'guid3', ?, 'folder3')
    ''', (r'\\hal9001\Volume_1\photos\test\folder1' + '\\',))
    conn.commit()
    conn.close()
    
    matches = [
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=100,
                base_name='photo1',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(
                id=1,
                repertoire='test/folder1',
                nom_fichier='photo1.jpg'
            ),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder1' + '\\',
            confidence=0.8
        )
    ]
    
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False,
        min_matches=1
    )
    assert stats['conflicts'] == 1
    assert stats['updated'] == 0


def test_update_root_folders_already_up_to_date(
    temp_lightroom_catalog: Path,
) -> None:
    """Test de update_root_folders quand le chemin est déjà à jour."""
    # Mettre à jour le root_folder avec le nouveau chemin
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    new_path = r'\\hal9001\Volume_1\photos\test\folder1' + '\\'
    cursor.execute(
        'UPDATE AgLibraryRootFolder SET absolutePath = ? WHERE id_local = 1',
        (new_path,)
    )
    conn.commit()
    conn.close()
    
    matches = [
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=100,
                base_name='photo1',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(
                id=1,
                repertoire='test/folder1',
                nom_fichier='photo1.jpg'
            ),
            new_absolute_path=new_path,
            confidence=0.8
        )
    ]
    
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False,
        min_matches=1
    )
    assert stats['skipped'] == 1
    assert stats['updated'] == 0
    assert stats['conflicts'] == 0


def test_group_matches_by_root() -> None:
    """Test de _group_matches_by_root."""
    matches = [
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=100,
                base_name='photo1',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(id=1, repertoire='test/folder1', nom_fichier='photo1.jpg'),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder1' + '\\',
            confidence=0.8
        ),
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=200,
                base_name='photo2',
                extension='jpg',
                folder_id=20,
                root_folder_id=2,
                old_absolute_path='G:/old/path/folder2/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(id=2, repertoire='test/folder2', nom_fichier='photo2.jpg'),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder2' + '\\',
            confidence=0.8
        ),
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=300,
                base_name='photo3',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(id=3, repertoire='test/folder1', nom_fichier='photo3.jpg'),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder1' + '\\',
            confidence=0.8
        ),
    ]
    
    updates_by_root, match_counts = _group_matches_by_root(matches)
    assert len(updates_by_root) == 2
    assert 1 in updates_by_root
    assert 2 in updates_by_root
    # Le root_folder_id=1 devrait avoir le chemin du premier match
    assert updates_by_root[1] == r'\\hal9001\Volume_1\photos\test\folder1' + '\\'
    # Vérifier les compteurs
    assert match_counts[1] == 2  # 2 matches pour root_folder_id=1
    assert match_counts[2] == 1  # 1 match pour root_folder_id=2


def test_build_new_path() -> None:
    """Test de _build_new_path."""
    base_path = r'\\hal9001\Volume_1\photos'
    repertoire = 'test/folder1'
    
    result = _build_new_path(base_path, repertoire)
    assert result.endswith('/')
    assert 'hal9001' in result
    assert 'test/folder1' in result


def test_load_dry_run_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test de _load_dry_run_mode."""
    from update_lightroom_paths import _load_dry_run_mode
    from unittest.mock import patch
    
    # Test avec DRY_RUN_MODE=true
    with patch('update_lightroom_paths.os.getenv', return_value='true'):
        assert _load_dry_run_mode() is True
    
    # Test avec DRY_RUN_MODE=false
    with patch('update_lightroom_paths.os.getenv', return_value='false'):
        assert _load_dry_run_mode() is False
    
    # Test avec DRY_RUN_MODE=1
    with patch('update_lightroom_paths.os.getenv', return_value='1'):
        assert _load_dry_run_mode() is True
    
    # Test avec valeur par défaut
    with patch('update_lightroom_paths.os.getenv', return_value=None) as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: default if key == 'DRY_RUN_MODE' else None
        assert _load_dry_run_mode() is True


def test_load_photos_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test de _load_photos_directory."""
    from update_lightroom_paths import _load_photos_directory
    from unittest.mock import patch
    
    # Test avec variable d'environnement
    test_path = r'\\test\photos'
    with patch('update_lightroom_paths.os.getenv', return_value=test_path):
        assert _load_photos_directory() == test_path
    
    # Test avec valeur par défaut
    with patch('update_lightroom_paths.os.getenv', return_value=None) as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: default if key == 'PHOTOS_DIRECTORY' else None
        assert _load_photos_directory() == r'\\hal9001\Volume_1\photos'


def test_load_scan_db_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test de _load_scan_db_filename."""
    from update_lightroom_paths import _load_scan_db_filename
    from unittest.mock import patch
    
    # Test avec variable d'environnement
    test_filename = 'test_scan.db'
    with patch('update_lightroom_paths.os.getenv', return_value=test_filename):
        assert _load_scan_db_filename() == test_filename
    
    # Test avec valeur par défaut
    with patch('update_lightroom_paths.os.getenv', return_value=None) as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: default if key == 'SCAN_DB_FILENAME' else None
        assert _load_scan_db_filename() == 'photos_scan_20251107_192045.db'


def test_load_catalog_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test de _load_catalog_filename."""
    from update_lightroom_paths import _load_catalog_filename
    from unittest.mock import patch
    
    # Test avec variable d'environnement
    test_filename = 'test_catalog.lrcat'
    with patch('update_lightroom_paths.os.getenv', return_value=test_filename):
        assert _load_catalog_filename() == test_filename
    
    # Test avec valeur par défaut
    with patch('update_lightroom_paths.os.getenv', return_value=None) as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: default if key == 'CATALOG_FILENAME' else None
        assert _load_catalog_filename() == 'catalogue 2 - dès juin 2017-2-2-v12.lrcat'


def test_update_root_folders_min_matches_rejection(
    temp_lightroom_catalog: Path,
) -> None:
    """Test de update_root_folders avec rejet si moins de 5 matches."""
    # Ajouter 5 fichiers dans root_folder_id=1 pour le test
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO AgLibraryFile (id_local, id_global, baseName, extension, folder, idx_filename, lc_idx_filename, lc_idx_filenameExtension, originalFilename)
        VALUES
            (101, 'guid101', 'photo2', 'jpg', 10, 'photo2.jpg', 'photo2.jpg', 'photo2.jpg', 'photo2.jpg'),
            (102, 'guid102', 'photo3', 'jpg', 10, 'photo3.jpg', 'photo3.jpg', 'photo3.jpg', 'photo3.jpg'),
            (103, 'guid103', 'photo4', 'jpg', 10, 'photo4.jpg', 'photo4.jpg', 'photo4.jpg', 'photo4.jpg'),
            (104, 'guid104', 'photo5', 'jpg', 10, 'photo5.jpg', 'photo5.jpg', 'photo5.jpg', 'photo5.jpg')
    ''')
    
    conn.commit()
    conn.close()
    
    # Créer seulement 3 matches pour root_folder_id=1 (moins que le minimum de 5)
    # Le root_folder a 5 fichiers, mais seulement 3 matches, donc il sera rejeté
    matches = [
        MatchResult(
            lightroom_file=LightroomFile(
                id_local=100 + i,
                base_name=f'photo{i+1}',
                extension='jpg',
                folder_id=10,
                root_folder_id=1,
                old_absolute_path='G:/old/path/folder1/',
                path_from_root=''
            ),
            photo_scan=PhotoScan(
                id=i+1,
                repertoire='test/folder1',
                nom_fichier=f'photo{i+1}.jpg'
            ),
            new_absolute_path=r'\\hal9001\Volume_1\photos\test\folder1' + '\\',
            confidence=0.8
        )
        for i in range(3)  # Seulement 3 matches sur 5 fichiers
    ]
    
    # Test avec min_matches=5 (par défaut)
    # Le root_folder a 5 fichiers, mais seulement 3 matches, donc il sera rejeté
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False,
        min_matches=5
    )
    assert stats['rejected'] == 1
    assert stats['updated'] == 0
    assert stats['skipped'] == 0
    assert stats['conflicts'] == 0
    
    # Test avec min_matches=2 (devrait passer car 3 matches >= 2)
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False,
        min_matches=2
    )
    assert stats['rejected'] == 0
    assert stats['updated'] == 1


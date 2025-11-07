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

    # Test en mode dry-run
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=True
    )
    assert stats['updated'] == 1

    # Vérifier que rien n'a été modifié en dry-run
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    cursor.execute(
        'SELECT absolutePath FROM AgLibraryRootFolder WHERE id_local = 1'
    )
    result = cursor.fetchone()
    assert result[0] == 'G:/old/path/folder1/'
    conn.close()

    # Test avec modification réelle
    stats = update_root_folders(
        temp_lightroom_catalog,
        matches,
        dry_run=False
    )
    assert stats['updated'] == 1

    # Vérifier la modification
    conn = sqlite3.connect(str(temp_lightroom_catalog))
    cursor = conn.cursor()
    cursor.execute(
        'SELECT absolutePath FROM AgLibraryRootFolder WHERE id_local = 1'
    )
    result = cursor.fetchone()
    assert r'hal9001' in result[0]
    conn.close()


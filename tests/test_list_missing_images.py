"""Tests pour le module list_missing_images."""

import sqlite3
import tempfile
import csv
from pathlib import Path
from typing import Generator
from unittest.mock import patch, mock_open

import pytest

from list_missing_images import (
    _load_photos_directory,
    _load_catalog_filename,
    _build_full_path,
    load_missing_images,
    save_to_csv,
)


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

    # Root folders : un dans le répertoire de base, un autre
    cursor.execute('''
        INSERT INTO AgLibraryRootFolder (id_local, id_global, absolutePath, name)
        VALUES
            (1, 'guid1', '\\\\hal9001\\Volume_1\\photos', 'photos'),
            (2, 'guid2', 'G:\\old\\path', 'old_path')
    ''')

    # Folders
    cursor.execute('''
        INSERT INTO AgLibraryFolder (id_local, id_global, pathFromRoot, rootFolder)
        VALUES
            (10, 'guid10', 'subfolder1', 1),
            (20, 'guid20', '', 2),
            (30, 'guid30', 'subfolder2', 1)
    ''')

    # Files : certains dans le répertoire de base, d'autres non
    cursor.execute('''
        INSERT INTO AgLibraryFile (id_local, id_global, baseName, extension, folder, idx_filename, lc_idx_filename, lc_idx_filenameExtension, originalFilename)
        VALUES
            (100, 'guid100', 'photo1', 'jpg', 10, 'photo1.jpg', 'photo1.jpg', 'photo1.jpg', 'photo1.jpg'),
            (200, 'guid200', 'photo2', 'png', 20, 'photo2.png', 'photo2.png', 'photo2.png', 'photo2.png'),
            (300, 'guid300', 'photo3', 'jpg', 30, 'photo3.jpg', 'photo3.jpg', 'photo3.jpg', 'photo3.jpg')
    ''')

    conn.commit()
    conn.close()

    yield catalog_path

    catalog_path.unlink()


def test_build_full_path() -> None:
    """Test de la construction du chemin complet."""
    result = _build_full_path(
        r'\\hal9001\Volume_1\photos',
        'subfolder1',
        'photo1',
        'jpg'
    )
    assert result == r'\\hal9001\Volume_1\photos\subfolder1\photo1.jpg'

    result = _build_full_path(
        r'\\hal9001\Volume_1\photos',
        '',
        'photo1',
        'jpg'
    )
    assert result == r'\\hal9001\Volume_1\photos\photo1.jpg'

    result = _build_full_path(
        'G:/old/path',
        'subfolder',
        'photo2',
        'png'
    )
    assert result == r'G:\old\path\subfolder\photo2.png'


def test_load_missing_images(temp_lightroom_catalog: Path) -> None:
    """Test du chargement des images non trouvées."""
    photos_base = r'\\hal9001\Volume_1\photos'
    missing = load_missing_images(temp_lightroom_catalog, photos_base)
    
    # Seul le fichier dans G:\old\path devrait être manquant
    assert len(missing) == 1
    assert missing[0][0] == r'G:\old\path'
    assert missing[0][1] == 'photo2.png'


def test_load_missing_images_all_found(temp_lightroom_catalog: Path) -> None:
    """Test quand toutes les images sont trouvées."""
    # Créer un catalogue avec seulement des images dans le répertoire de base
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
            absolutePath TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE AgLibraryFolder (
            id_local INTEGER PRIMARY KEY,
            pathFromRoot TEXT NOT NULL,
            rootFolder INTEGER NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE AgLibraryFile (
            id_local INTEGER PRIMARY KEY,
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
        INSERT INTO AgLibraryRootFolder (id_local, absolutePath)
        VALUES (1, '\\\\hal9001\\Volume_1\\photos')
    ''')

    cursor.execute('''
        INSERT INTO AgLibraryFolder (id_local, pathFromRoot, rootFolder)
        VALUES (10, 'subfolder1', 1)
    ''')

    cursor.execute('''
        INSERT INTO AgLibraryFile (id_local, baseName, extension, folder, idx_filename, lc_idx_filename, lc_idx_filenameExtension, originalFilename)
        VALUES (100, 'photo1', 'jpg', 10, 'photo1.jpg', 'photo1.jpg', 'photo1.jpg', 'photo1.jpg')
    ''')

    conn.commit()
    conn.close()

    photos_base = r'\\hal9001\Volume_1\photos'
    missing = load_missing_images(catalog_path, photos_base)
    
    assert len(missing) == 0
    
    catalog_path.unlink()


def test_save_to_csv(tmp_path: Path) -> None:
    """Test de la sauvegarde en CSV."""
    missing_images = [
        (r'G:\old\path', 'photo1.jpg'),
        (r'D:\other\path', 'photo2.png')
    ]
    
    output_file = tmp_path / 'test_output.csv'
    save_to_csv(missing_images, output_file)
    
    assert output_file.exists()
    
    with open(output_file, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        rows = list(reader)
    
    assert rows[0] == ['repertoire', 'nom_fichier']
    assert rows[1] == [r'G:\old\path', 'photo1.jpg']
    assert rows[2] == [r'D:\other\path', 'photo2.png']


def test_load_photos_directory_default() -> None:
    """Test du chargement du répertoire de base par défaut."""
    with patch('list_missing_images.load_dotenv'), \
         patch('list_missing_images.os.getenv', return_value=None):
        result = _load_photos_directory()
        assert result == r'\\hal9001\Volume_1\photos'


def test_load_photos_directory_from_env() -> None:
    """Test du chargement du répertoire depuis .env."""
    with patch('list_missing_images.load_dotenv'), \
         patch('list_missing_images.os.getenv', return_value=r'D:\photos'):
        result = _load_photos_directory()
        assert result == r'D:\photos'


def test_load_catalog_filename_default() -> None:
    """Test du chargement du nom de catalogue par défaut."""
    with patch('list_missing_images.load_dotenv'), \
         patch('list_missing_images.os.getenv', return_value=None):
        result = _load_catalog_filename()
        assert result == 'catalogue 2 - dès juin 2017-2-2-v12.lrcat'


def test_load_catalog_filename_from_env() -> None:
    """Test du chargement du nom de catalogue depuis .env."""
    with patch('list_missing_images.load_dotenv'), \
         patch('list_missing_images.os.getenv', return_value='test.lrcat'):
        result = _load_catalog_filename()
        assert result == 'test.lrcat'


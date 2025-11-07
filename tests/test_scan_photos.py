"""Tests unitaires pour le module scan_photos."""

import json
import sqlite3
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import pandas as pd
from PIL import Image

from scan_photos import (
    get_image_dimensions,
    is_image_file,
    scan_directory,
    process_image_file,
    scan_photos_directory,
    save_results_json,
    save_results_csv,
    save_results_sqlite,
    get_total_photos_count,
    load_all_photos_from_sqlite,
    _load_photos_directory
)


def test_get_image_dimensions_valid_image(tmp_path: Path) -> None:
    """Test get_image_dimensions avec une image valide."""
    # Créer une image de test
    img = Image.new('RGB', (100, 200), color='red')
    img_path = tmp_path / "test.jpg"
    img.save(img_path)

    result = get_image_dimensions(img_path)
    assert result is not None
    assert result == (100, 200)


def test_get_image_dimensions_invalid_file(tmp_path: Path) -> None:
    """Test get_image_dimensions avec un fichier invalide."""
    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("not an image")

    result = get_image_dimensions(invalid_path)
    assert result is None


def test_get_image_dimensions_nonexistent_file(tmp_path: Path) -> None:
    """Test get_image_dimensions avec un fichier inexistant."""
    nonexistent_path = tmp_path / "nonexistent.jpg"
    result = get_image_dimensions(nonexistent_path)
    assert result is None


def test_is_image_file_jpg() -> None:
    """Test is_image_file avec un fichier JPG."""
    file_path = Path("test.jpg")
    assert is_image_file(file_path) is True


def test_is_image_file_jpeg() -> None:
    """Test is_image_file avec un fichier JPEG."""
    file_path = Path("test.jpeg")
    assert is_image_file(file_path) is True


def test_is_image_file_png() -> None:
    """Test is_image_file avec un fichier PNG."""
    file_path = Path("test.png")
    assert is_image_file(file_path) is True


def test_is_image_file_raw() -> None:
    """Test is_image_file avec un fichier RAW."""
    file_path = Path("test.cr2")
    assert is_image_file(file_path) is True


def test_is_image_file_not_image() -> None:
    """Test is_image_file avec un fichier non-image."""
    file_path = Path("test.txt")
    assert is_image_file(file_path) is False


def test_is_image_file_case_insensitive() -> None:
    """Test is_image_file avec extension en majuscules."""
    file_path = Path("test.JPG")
    assert is_image_file(file_path) is True


def test_scan_directory_with_images(tmp_path: Path) -> None:
    """Test scan_directory avec des images."""
    # Créer des images de test
    img1 = Image.new('RGB', (100, 100), color='red')
    img2 = Image.new('RGB', (200, 200), color='blue')
    img1.save(tmp_path / "image1.jpg")
    img2.save(tmp_path / "image2.png")
    (tmp_path / "not_image.txt").write_text("text")

    result = scan_directory(tmp_path)
    assert len(result) == 2
    assert all(is_image_file(f) for f in result)


def test_scan_directory_empty(tmp_path: Path) -> None:
    """Test scan_directory avec un répertoire vide."""
    result = scan_directory(tmp_path)
    assert result == []


def test_scan_directory_nonexistent() -> None:
    """Test scan_directory avec un répertoire inexistant."""
    nonexistent_path = Path("/nonexistent/path/12345")
    result = scan_directory(nonexistent_path)
    assert result == []


def test_scan_directory_subdirectories(tmp_path: Path) -> None:
    """Test scan_directory avec des sous-répertoires."""
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    img = Image.new('RGB', (100, 100), color='red')
    img.save(tmp_path / "image1.jpg")
    img.save(subdir / "image2.jpg")

    result = scan_directory(tmp_path)
    assert len(result) == 2


def test_process_image_file_valid(tmp_path: Path) -> None:
    """Test process_image_file avec une image valide."""
    base_dir = tmp_path
    img = Image.new('RGB', (150, 250), color='green')
    img_path = base_dir / "test_image.jpg"
    img.save(img_path)

    result = process_image_file(img_path, base_dir)
    assert result is not None
    assert result['nom_fichier'] == "test_image.jpg"
    assert result['hauteur'] == 250
    assert result['largeur'] == 150
    assert result['repertoire'] == "."


def test_process_image_file_invalid(tmp_path: Path) -> None:
    """Test process_image_file avec une image invalide."""
    base_dir = tmp_path
    invalid_path = tmp_path / "invalid.txt"
    invalid_path.write_text("not an image")

    result = process_image_file(invalid_path, base_dir)
    assert result is None


def test_process_image_file_subdirectory(tmp_path: Path) -> None:
    """Test process_image_file avec un fichier dans un sous-répertoire."""
    base_dir = tmp_path
    subdir = tmp_path / "photos" / "2024"
    subdir.mkdir(parents=True)
    img = Image.new('RGB', (100, 100), color='red')
    img_path = subdir / "photo.jpg"
    img.save(img_path)

    result = process_image_file(img_path, base_dir)
    assert result is not None
    assert result['repertoire'] == "photos\\2024" or result['repertoire'] == "photos/2024"
    assert result['nom_fichier'] == "photo.jpg"


@patch('scan_photos.scan_directory')
@patch('scan_photos.process_image_file')
def test_scan_photos_directory_success(
    mock_process: MagicMock,
    mock_scan: MagicMock,
    tmp_path: Path
) -> None:
    """Test scan_photos_directory avec succès."""
    mock_scan.return_value = [
        tmp_path / "image1.jpg",
        tmp_path / "image2.png"
    ]
    mock_process.side_effect = [
        {
            'repertoire': '.',
            'nom_fichier': 'image1.jpg',
            'hauteur': 100,
            'largeur': 200
        },
        {
            'repertoire': '.',
            'nom_fichier': 'image2.png',
            'hauteur': 150,
            'largeur': 250
        }
    ]

    result = scan_photos_directory(tmp_path)
    assert len(result) == 2
    assert result[0]['nom_fichier'] == 'image1.jpg'
    assert result[1]['nom_fichier'] == 'image2.png'


def test_scan_photos_directory_nonexistent() -> None:
    """Test scan_photos_directory avec un répertoire inexistant."""
    nonexistent_path = Path("/nonexistent/path/12345")
    with pytest.raises(FileNotFoundError):
        scan_photos_directory(nonexistent_path)


def test_scan_photos_directory_with_failures(tmp_path: Path) -> None:
    """Test scan_photos_directory avec certains fichiers en échec."""
    # Créer une image valide
    img = Image.new('RGB', (100, 100), color='red')
    img.save(tmp_path / "valid.jpg")
    # Créer un fichier texte (non-image)
    (tmp_path / "invalid.txt").write_text("text")

    result = scan_photos_directory(tmp_path)
    # Seule l'image valide devrait être traitée
    assert len(result) >= 1
    assert result[0]['nom_fichier'] == "valid.jpg"


def test_save_results_json(tmp_path: Path) -> None:
    """Test save_results_json."""
    results = [
        {
            'repertoire': 'test',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        },
        {
            'repertoire': 'test',
            'nom_fichier': 'photo2.jpg',
            'hauteur': 150,
            'largeur': 250
        }
    ]
    output_path = tmp_path / "test.json"
    saved_path = save_results_json(results, output_path)

    assert saved_path == output_path
    assert output_path.exists()

    with open(output_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    assert data['total_photos'] == 2
    assert len(data['photos']) == 2
    assert 'timestamp' in data


def test_save_results_csv(tmp_path: Path) -> None:
    """Test save_results_csv."""
    results = [
        {
            'repertoire': 'test',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        }
    ]
    output_path = tmp_path / "test.csv"
    saved_path = save_results_csv(results, output_path)

    assert saved_path == output_path
    assert output_path.exists()

    df = pd.read_csv(output_path)
    assert len(df) == 1
    assert df.iloc[0]['nom_fichier'] == 'photo1.jpg'
    assert df.iloc[0]['hauteur'] == 100


def test_save_results_sqlite(tmp_path: Path) -> None:
    """Test save_results_sqlite."""
    results = [
        {
            'repertoire': 'test',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        },
        {
            'repertoire': 'test2',
            'nom_fichier': 'photo2.jpg',
            'hauteur': 150,
            'largeur': 250
        }
    ]
    output_path = tmp_path / "test.db"
    saved_path = save_results_sqlite(results, output_path)

    assert saved_path == output_path
    assert output_path.exists()

    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 2

    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM photos WHERE nom_fichier = 'photo1.jpg'")
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[1] == 'test'  # repertoire
    assert row[2] == 'photo1.jpg'  # nom_fichier
    assert row[3] == 100  # hauteur
    assert row[4] == 200  # largeur


def test_save_results_sqlite_append(tmp_path: Path) -> None:
    """Test save_results_sqlite avec append=True."""
    results1 = [
        {
            'repertoire': 'test1',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        }
    ]
    results2 = [
        {
            'repertoire': 'test2',
            'nom_fichier': 'photo2.jpg',
            'hauteur': 150,
            'largeur': 250
        }
    ]
    output_path = tmp_path / "test.db"
    
    save_results_sqlite(results1, output_path, append=False)
    save_results_sqlite(results2, output_path, append=True)
    
    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    count = cursor.fetchone()[0]
    conn.close()
    
    assert count == 2


def test_get_total_photos_count_existing(tmp_path: Path) -> None:
    """Test get_total_photos_count avec une base existante."""
    results = [
        {
            'repertoire': 'test',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        },
        {
            'repertoire': 'test',
            'nom_fichier': 'photo2.jpg',
            'hauteur': 150,
            'largeur': 250
        }
    ]
    output_path = tmp_path / "test.db"
    save_results_sqlite(results, output_path)
    
    count = get_total_photos_count(output_path)
    assert count == 2


def test_get_total_photos_count_nonexistent(tmp_path: Path) -> None:
    """Test get_total_photos_count avec une base inexistante."""
    nonexistent_path = tmp_path / "nonexistent.db"
    count = get_total_photos_count(nonexistent_path)
    assert count == 0


def test_get_total_photos_count_empty_db(tmp_path: Path) -> None:
    """Test get_total_photos_count avec une base vide."""
    output_path = tmp_path / "empty.db"
    save_results_sqlite([], output_path)
    
    count = get_total_photos_count(output_path)
    assert count == 0


def test_load_all_photos_from_sqlite_existing(tmp_path: Path) -> None:
    """Test load_all_photos_from_sqlite avec une base existante."""
    results = [
        {
            'repertoire': 'test1',
            'nom_fichier': 'photo1.jpg',
            'hauteur': 100,
            'largeur': 200
        },
        {
            'repertoire': 'test2',
            'nom_fichier': 'photo2.jpg',
            'hauteur': 150,
            'largeur': 250
        }
    ]
    output_path = tmp_path / "test.db"
    save_results_sqlite(results, output_path)
    
    loaded = load_all_photos_from_sqlite(output_path)
    assert len(loaded) == 2
    assert loaded[0]['nom_fichier'] == 'photo1.jpg'
    assert loaded[0]['hauteur'] == 100
    assert loaded[1]['nom_fichier'] == 'photo2.jpg'
    assert loaded[1]['hauteur'] == 150


def test_load_all_photos_from_sqlite_nonexistent(tmp_path: Path) -> None:
    """Test load_all_photos_from_sqlite avec une base inexistante."""
    nonexistent_path = tmp_path / "nonexistent.db"
    loaded = load_all_photos_from_sqlite(nonexistent_path)
    assert loaded == []


def test_load_all_photos_from_sqlite_empty(tmp_path: Path) -> None:
    """Test load_all_photos_from_sqlite avec une base vide."""
    output_path = tmp_path / "empty.db"
    save_results_sqlite([], output_path)
    
    loaded = load_all_photos_from_sqlite(output_path)
    assert loaded == []


@patch('scan_photos.load_dotenv')
@patch('scan_photos.os.getenv')
def test_load_photos_directory_with_env(
    mock_getenv: MagicMock,
    mock_load_dotenv: MagicMock
) -> None:
    """Test _load_photos_directory avec variable d'environnement."""
    mock_getenv.return_value = r'\\test\photos'
    result = _load_photos_directory()
    assert result == r'\\test\photos'
    mock_load_dotenv.assert_called_once()


@patch('scan_photos.load_dotenv')
@patch('scan_photos.os.getenv')
def test_load_photos_directory_default(
    mock_getenv: MagicMock,
    mock_load_dotenv: MagicMock
) -> None:
    """Test _load_photos_directory avec valeur par défaut."""
    # os.getenv('PHOTOS_DIRECTORY', default) retourne default si la variable n'existe pas
    # On simule ici que la variable n'existe pas en retournant le paramètre default
    def side_effect(key: str, default: str = None) -> str:
        if key == 'PHOTOS_DIRECTORY' and default:
            return default
        return default if default else None
    
    mock_getenv.side_effect = side_effect
    result = _load_photos_directory()
    assert result == r'\\hal9001\Volume_1\photos'
    mock_load_dotenv.assert_called_once()


@patch('scan_photos.scan_directory')
@patch('scan_photos.process_image_file')
def test_scan_photos_directory_with_batch_save(
    mock_process: MagicMock,
    mock_scan: MagicMock,
    tmp_path: Path
) -> None:
    """Test scan_photos_directory avec sauvegarde par lots."""
    # Créer des images de test
    img1 = Image.new('RGB', (100, 200), color='red')
    img2 = Image.new('RGB', (150, 250), color='blue')
    img1.save(tmp_path / "img1.jpg")
    img2.save(tmp_path / "img2.jpg")
    
    mock_scan.return_value = [tmp_path / "img1.jpg", tmp_path / "img2.jpg"]
    mock_process.side_effect = [
        {'repertoire': '.', 'nom_fichier': 'img1.jpg', 'hauteur': 200, 'largeur': 100},
        {'repertoire': '.', 'nom_fichier': 'img2.jpg', 'hauteur': 250, 'largeur': 150}
    ]
    
    sqlite_path = tmp_path / "test.db"
    result = scan_photos_directory(
        tmp_path,
        sqlite_path=sqlite_path,
        batch_size=1
    )
    
    # Vérifier que la base de données a été créée et contient les données
    assert sqlite_path.exists()
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM photos")
    count = cursor.fetchone()[0]
    conn.close()
    
    # Les deux images devraient être sauvegardées (batch_size=1)
    assert count >= 2


def test_scan_photos_directory_with_failed_files_display(tmp_path: Path) -> None:
    """Test scan_photos_directory avec affichage des fichiers échoués."""
    # Créer une image valide
    img = Image.new('RGB', (100, 100), color='red')
    img.save(tmp_path / "valid.jpg")
    
    # Créer plusieurs fichiers texte (non-images) pour déclencher l'affichage
    for i in range(12):
        (tmp_path / f"invalid{i}.txt").write_text("text")
    
    result = scan_photos_directory(tmp_path)
    # Seule l'image valide devrait être traitée
    assert len(result) >= 1
    assert result[0]['nom_fichier'] == "valid.jpg"


@patch('scan_photos.process_image_file')
@patch('scan_photos.scan_directory')
def test_scan_photos_directory_with_process_failures(
    mock_scan: MagicMock,
    mock_process: MagicMock,
    tmp_path: Path
) -> None:
    """Test scan_photos_directory avec des échecs de process_image_file."""
    # Créer des fichiers images
    img1 = Image.new('RGB', (100, 100), color='red')
    img2 = Image.new('RGB', (100, 100), color='blue')
    img1.save(tmp_path / "img1.jpg")
    img2.save(tmp_path / "img2.jpg")
    
    mock_scan.return_value = [tmp_path / "img1.jpg", tmp_path / "img2.jpg"]
    # Premier fichier réussit, deuxième échoue
    mock_process.side_effect = [
        {'repertoire': '.', 'nom_fichier': 'img1.jpg', 'hauteur': 100, 'largeur': 100},
        None  # Échec pour le deuxième
    ]
    
    result = scan_photos_directory(tmp_path)
    # Seul le premier devrait être dans les résultats
    assert len(result) == 1
    assert result[0]['nom_fichier'] == 'img1.jpg'
    # Le deuxième devrait être dans failed_files
    assert mock_process.call_count == 2


@patch('scan_photos.process_image_file')
@patch('scan_photos.scan_directory')
def test_scan_photos_directory_with_many_failed_files(
    mock_scan: MagicMock,
    mock_process: MagicMock,
    tmp_path: Path
) -> None:
    """Test scan_photos_directory avec plus de 10 fichiers échoués."""
    # Créer 15 fichiers images
    image_files = []
    for i in range(15):
        img = Image.new('RGB', (100, 100), color='red')
        img_path = tmp_path / f"img{i}.jpg"
        img.save(img_path)
        image_files.append(img_path)
    
    mock_scan.return_value = image_files
    # Tous les fichiers échouent
    mock_process.return_value = None
    
    result = scan_photos_directory(tmp_path)
    # Aucun résultat ne devrait être retourné
    assert len(result) == 0
    # Tous les fichiers devraient être dans failed_files
    assert mock_process.call_count == 15


@patch('scan_photos.scan_photos_directory')
@patch('scan_photos.save_results_sqlite')
@patch('scan_photos.get_total_photos_count')
@patch('scan_photos.load_all_photos_from_sqlite')
@patch('scan_photos.save_results_json')
@patch('scan_photos.save_results_csv')
@patch('scan_photos._load_photos_directory')
def test_main_with_results(
    mock_load_dir: MagicMock,
    mock_save_csv: MagicMock,
    mock_save_json: MagicMock,
    mock_load_all: MagicMock,
    mock_get_count: MagicMock,
    mock_save_sqlite: MagicMock,
    mock_scan: MagicMock,
    tmp_path: Path
) -> None:
    """Test main() avec des résultats."""
    from scan_photos import main
    
    mock_load_dir.return_value = str(tmp_path)
    mock_scan.return_value = [
        {'repertoire': '.', 'nom_fichier': 'img1.jpg', 'hauteur': 100, 'largeur': 200}
    ]
    mock_get_count.return_value = 1
    mock_load_all.return_value = [
        {'repertoire': '.', 'nom_fichier': 'img1.jpg', 'hauteur': 100, 'largeur': 200}
    ]
    
    main()
    
    # Vérifier que les fonctions ont été appelées
    mock_load_dir.assert_called_once()
    mock_scan.assert_called_once()
    mock_get_count.assert_called_once()
    mock_load_all.assert_called_once()
    mock_save_json.assert_called_once()
    mock_save_csv.assert_called_once()


@patch('scan_photos.scan_photos_directory')
@patch('scan_photos.save_results_sqlite')
@patch('scan_photos.get_total_photos_count')
@patch('scan_photos._load_photos_directory')
def test_main_without_results(
    mock_load_dir: MagicMock,
    mock_get_count: MagicMock,
    mock_save_sqlite: MagicMock,
    mock_scan: MagicMock,
    tmp_path: Path
) -> None:
    """Test main() sans résultats."""
    from scan_photos import main
    
    mock_load_dir.return_value = str(tmp_path)
    mock_scan.return_value = []
    mock_get_count.return_value = 0
    
    main()
    
    # Vérifier que les fonctions ont été appelées
    mock_load_dir.assert_called_once()
    mock_scan.assert_called_once()
    mock_get_count.assert_called_once()


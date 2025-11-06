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
    save_results_sqlite
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


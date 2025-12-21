"""Script pour visualiser les hash BLAKE256 de la table intermédiaire.

Ce script permet d'afficher les hash calculés pour les fichiers
dans la table intermédiaire pending_root_folder_updates.
"""

import sqlite3
from pathlib import Path
import os
from dotenv import load_dotenv


def _load_catalog_filename() -> str:
    """Charge le nom du fichier catalogue Lightroom depuis le fichier .env.

    Returns:
        Nom du fichier catalogue Lightroom.

    """
    load_dotenv()
    return os.getenv(
        'CATALOG_FILENAME',
        'catalogue 2 - dès juin 2017-2-2-v12.lrcat'
    )


def view_hashes(
    catalog_path: Path,
    limit: int = 20
) -> None:
    """Affiche les hash de la table intermédiaire.

    Args:
        catalog_path: Chemin vers le catalogue Lightroom.
        limit: Nombre maximum d'enregistrements à afficher.

    """
    conn = sqlite3.connect(str(catalog_path))
    cursor = conn.cursor()
    
    # Vérifier si la table existe
    cursor.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='pending_root_folder_updates'
    ''')
    result = cursor.fetchone()
    
    if not result:
        print("La table intermediaire 'pending_root_folder_updates' n'existe pas.")
        print("Lancez d'abord update_lightroom_paths.py pour creer la table.")
        conn.close()
        return
    
    # Compter le nombre total d'enregistrements
    cursor.execute('SELECT COUNT(*) FROM pending_root_folder_updates')
    total = cursor.fetchone()[0]
    
    print(f"Total d'enregistrements dans la table intermediaire : {total}\n")
    
    if total == 0:
        print("La table est vide.")
        conn.close()
        return
    
    # Récupérer les enregistrements avec les hash
    cursor.execute('''
        SELECT 
            id,
            root_folder_id,
            file_id_local,
            old_path,
            new_path,
            file_hash,
            match_count,
            created_at
        FROM pending_root_folder_updates
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    
    print(f"Afficher les {len(rows)} premiers enregistrements :\n")
    print(f"{'ID':<6} {'Root ID':<10} {'File ID':<10} {'Hash':<20} {'Matches':<8} {'Date':<20}")
    print("-" * 100)
    
    for row in rows:
        record_id, root_id, file_id, old_path, new_path, file_hash, match_count, created_at = row
        hash_short = file_hash[:20] + "..." if len(file_hash) > 20 else file_hash
        print(f"{record_id:<6} {root_id:<10} {file_id:<10} {hash_short:<20} {match_count:<8} {created_at:<20}")
    
    # Afficher quelques exemples complets
    if rows:
        print(f"\nExemples de hash complets (BLAKE256 - 64 caracteres) :\n")
        for i, row in enumerate(rows[:5], 1):
            record_id, root_id, file_id, old_path, new_path, file_hash, match_count, created_at = row
            print(f"Exemple {i}:")
            print(f"  Root Folder ID: {root_id}")
            print(f"  File ID: {file_id}")
            print(f"  Ancien chemin: {old_path}")
            print(f"  Nouveau chemin: {new_path}")
            print(f"  Hash BLAKE256: {file_hash}")
            print(f"  Matches: {match_count}")
            print()
    
    # Statistiques sur les hash
    cursor.execute('''
        SELECT 
            COUNT(DISTINCT file_hash) as unique_hashes,
            COUNT(*) as total_records
        FROM pending_root_folder_updates
    ''')
    stats = cursor.fetchone()
    unique_hashes, total_records = stats
    
    print(f"Statistiques :")
    print(f"  Hash uniques : {unique_hashes}")
    print(f"  Total d'enregistrements : {total_records}")
    if total_records > 0:
        duplicates = total_records - unique_hashes
        if duplicates > 0:
            print(f"  [WARN] {duplicates} doublons potentiels detectes")
        else:
            print(f"  [OK] Aucun doublon detecte")
    
    conn.close()


def main() -> None:
    """Fonction principale du script."""
    load_dotenv()
    
    base_dir = Path(__file__).parent
    catalog_filename = _load_catalog_filename()
    catalog = base_dir / 'catalogue_lightroom' / catalog_filename
    
    if not catalog.exists():
        print(f"ERREUR : Le catalogue {catalog} n'existe pas")
        return
    
    print(f"Visualisation des hash depuis : {catalog_filename}\n")
    view_hashes(catalog, limit=50)


if __name__ == '__main__':
    main()


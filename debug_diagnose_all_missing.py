"""Script de diagnostic pour analyser tous les répertoires non trouvés.

Ce script analyse tous les répertoires contenant des images non trouvées
et génère un rapport détaillé avec les statistiques et les raisons.
"""

import sqlite3
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
import os
from dotenv import load_dotenv

from update_lightroom_paths import (
    load_scan_photos,
    load_lightroom_files,
    find_matches,
    compare_paths,
    verify_filename_match,
    _load_photos_directory,
    _load_scan_db_filename,
    _load_catalog_filename,
    _group_matches_by_root,
    _normalize_path_for_comparison,
)


def load_missing_images_from_csv(csv_path: Path) -> Dict[str, List[str]]:
    """Charge les images non trouvées depuis un fichier CSV.

    Args:
        csv_path: Chemin vers le fichier CSV.

    Returns:
        Dictionnaire {répertoire: [liste des fichiers]}.

    """
    missing_by_directory: Dict[str, List[str]] = defaultdict(list)
    
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Skip header
        
        for row in reader:
            if len(row) >= 2:
                directory = row[0]
                filename = row[1]
                missing_by_directory[directory].append(filename)
    
    return dict(missing_by_directory)


def analyze_directory(
    directory: str,
    files_in_directory: List[str],
    catalog_path: Path,
    scan_db_path: Path,
    photos_base_path: str
) -> Dict:
    """Analyse un répertoire pour comprendre pourquoi il n'a pas été mis à jour.

    Args:
        directory: Chemin du répertoire à analyser.
        files_in_directory: Liste des fichiers dans ce répertoire.
        catalog_path: Chemin vers le catalogue Lightroom.
        scan_db_path: Chemin vers la base de données du scan.
        photos_base_path: Chemin de base des photos.

    Returns:
        Dictionnaire avec les résultats de l'analyse.

    """
    # Charger les données
    photos_by_filename = load_scan_photos(scan_db_path)
    lightroom_files = load_lightroom_files(catalog_path)
    
    # Trouver les fichiers Lightroom dans ce répertoire
    directory_normalized = directory.replace('\\', '/').lower().rstrip('/')
    lr_files_in_dir: List = []
    
    for lr_file in lightroom_files:
        file_path_normalized = lr_file.old_absolute_path.replace('\\', '/').lower().rstrip('/')
        if file_path_normalized.startswith(directory_normalized):
            lr_files_in_dir.append(lr_file)
    
    if not lr_files_in_dir:
        return {
            'directory': directory,
            'file_count': len(files_in_directory),
            'lr_file_count': 0,
            'status': 'NO_LR_FILES',
            'matches': 0,
            'in_scan': 0,
            'not_in_scan': 0,
            'low_score': 0,
            'conflict': False,
            'reason': 'Aucun fichier trouve dans le catalogue Lightroom pour ce repertoire'
        }
    
    # Analyser les correspondances
    matches_found = 0
    in_scan_count = 0
    not_in_scan_count = 0
    low_score_count = 0
    
    for lr_file in lr_files_in_dir:
        filename = f"{lr_file.base_name}.{lr_file.extension}"
        
        if filename not in photos_by_filename:
            not_in_scan_count += 1
            continue
        
        in_scan_count += 1
        candidates = photos_by_filename[filename]
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
                best_score = score
        
        if best_score >= 0.6:
            matches_found += 1
        else:
            low_score_count += 1
    
    # Chercher les correspondances avec find_matches
    all_matches = find_matches(lr_files_in_dir, photos_by_filename, base_path=photos_base_path)
    
    # Vérifier les conflits
    has_conflict = False
    conflict_reason = None
    root_folder_id = None
    new_path = None
    
    if all_matches:
        updates_by_root, match_counts = _group_matches_by_root(all_matches)
        
        for root_id, count in match_counts.items():
            if count >= 5:  # Seuil min_matches
                root_folder_id = root_id
                new_path = updates_by_root.get(root_id)
                
                # Vérifier si le nouveau chemin existe déjà pour un autre root_folder_id
                conn = sqlite3.connect(str(catalog_path))
                cursor = conn.cursor()
                
                cursor.execute(
                    'SELECT id_local FROM AgLibraryRootFolder WHERE absolutePath = ? AND id_local != ?',
                    (new_path, root_id)
                )
                existing = cursor.fetchone()
                
                if existing:
                    has_conflict = True
                    conflict_reason = f"Le nouveau chemin existe deja pour root_folder_id={existing[0]}"
                
                conn.close()
                break
    
    # Déterminer le statut et la raison
    status = 'UNKNOWN'
    reason = None
    
    if matches_found < 5:
        status = 'INSUFFICIENT_MATCHES'
        reason = f"Seulement {matches_found} correspondances trouvees (minimum 5 requis)"
    elif has_conflict:
        status = 'CONFLICT'
        reason = conflict_reason
    elif not_in_scan_count == len(lr_files_in_dir):
        status = 'NOT_IN_SCAN'
        reason = "Aucun fichier n'est dans la base de donnees du scan"
    elif low_score_count > 0:
        status = 'LOW_SCORE'
        reason = f"{low_score_count} fichiers avec un score de correspondance < 0.6"
    elif matches_found >= 5 and not has_conflict:
        status = 'SHOULD_UPDATE'
        reason = f"{matches_found} correspondances trouvees, devrait pouvoir etre mis a jour"
    
    return {
        'directory': directory,
        'file_count': len(files_in_directory),
        'lr_file_count': len(lr_files_in_dir),
        'status': status,
        'matches': matches_found,
        'in_scan': in_scan_count,
        'not_in_scan': not_in_scan_count,
        'low_score': low_score_count,
        'conflict': has_conflict,
        'root_folder_id': root_folder_id,
        'new_path': new_path,
        'reason': reason
    }


def generate_report(
    analyses: List[Dict],
    output_path: Path
) -> None:
    """Génère un rapport CSV avec les résultats de l'analyse.

    Args:
        analyses: Liste des analyses de répertoires.
        output_path: Chemin du fichier CSV de sortie.

    """
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow([
            'repertoire',
            'nb_fichiers',
            'nb_fichiers_lr',
            'statut',
            'correspondances',
            'dans_scan',
            'pas_dans_scan',
            'score_faible',
            'conflit',
            'root_folder_id',
            'nouveau_chemin',
            'raison'
        ])
        
        for analysis in analyses:
            writer.writerow([
                analysis['directory'],
                analysis['file_count'],
                analysis['lr_file_count'],
                analysis['status'],
                analysis['matches'],
                analysis['in_scan'],
                analysis['not_in_scan'],
                analysis['low_score'],
                'OUI' if analysis['conflict'] else 'NON',
                analysis.get('root_folder_id', ''),
                analysis.get('new_path', ''),
                analysis.get('reason', '')
            ])


def print_summary(analyses: List[Dict]) -> None:
    """Affiche un résumé des analyses.

    Args:
        analyses: Liste des analyses de répertoires.

    """
    total_directories = len(analyses)
    total_files = sum(a['file_count'] for a in analyses)
    
    status_counts = defaultdict(int)
    for analysis in analyses:
        status_counts[analysis['status']] += 1
    
    print(f"\n{'='*80}")
    print(f"RESUME GLOBAL")
    print(f"{'='*80}")
    print(f"Total de repertoires analyses : {total_directories}")
    print(f"Total de fichiers non trouves : {total_files}")
    print(f"\nRepartition par statut :")
    
    status_labels = {
        'CONFLIT': 'Conflit (chemin deja utilise)',
        'INSUFFICIENT_MATCHES': 'Correspondances insuffisantes (< 5)',
        'NOT_IN_SCAN': 'Fichiers absents du scan',
        'LOW_SCORE': 'Score de correspondance trop faible',
        'SHOULD_UPDATE': 'Devrait pouvoir etre mis a jour',
        'NO_LR_FILES': 'Aucun fichier dans le catalogue Lightroom',
        'UNKNOWN': 'Raison inconnue'
    }
    
    for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
        label = status_labels.get(status, status)
        percentage = (count / total_directories * 100) if total_directories > 0 else 0
        print(f"  {label:40} : {count:5} ({percentage:5.1f}%)")
    
    # Top 10 des répertoires avec le plus de fichiers
    print(f"\nTop 10 des repertoires avec le plus de fichiers non trouves :")
    sorted_by_files = sorted(analyses, key=lambda x: x['file_count'], reverse=True)[:10]
    for i, analysis in enumerate(sorted_by_files, 1):
        print(f"  {i:2}. {analysis['directory'][:60]:60} : {analysis['file_count']:4} fichiers ({analysis['status']})")


def main() -> None:
    """Fonction principale du script."""
    load_dotenv()
    
    base_dir = Path(__file__).parent
    scan_db_filename = _load_scan_db_filename()
    catalog_filename = _load_catalog_filename()
    photos_directory = _load_photos_directory()
    
    scan_db = base_dir / 'resultats_scan' / scan_db_filename
    catalog = base_dir / 'catalogue_lightroom' / catalog_filename
    
    # Trouver le dernier fichier CSV d'images non trouvées
    resultats_dir = base_dir / 'resultats_scan'
    csv_files = list(resultats_dir.glob('images_non_trouvees_*.csv'))
    
    if not csv_files:
        print("ERREUR : Aucun fichier CSV d'images non trouvees trouve")
        print("Lancez d'abord list_missing_images.py")
        return
    
    latest_csv = max(csv_files, key=lambda p: p.stat().st_mtime)
    print(f"Chargement du fichier CSV : {latest_csv.name}")
    
    if not catalog.exists():
        print(f"ERREUR : Le catalogue {catalog} n'existe pas")
        return
    
    if not scan_db.exists():
        print(f"ERREUR : La base de donnees {scan_db} n'existe pas")
        return
    
    # Charger les images non trouvées
    print("Chargement des images non trouvees...")
    missing_by_directory = load_missing_images_from_csv(latest_csv)
    print(f"  {len(missing_by_directory)} repertoires uniques trouves")
    
    total_files = sum(len(files) for files in missing_by_directory.values())
    print(f"  {total_files} fichiers au total\n")
    
    # Analyser chaque répertoire
    print("Analyse des repertoires...")
    analyses: List[Dict] = []
    
    for i, (directory, files) in enumerate(missing_by_directory.items(), 1):
        if i % 10 == 0:
            print(f"  Traitement : {i}/{len(missing_by_directory)} repertoires...")
        
        analysis = analyze_directory(
            directory,
            files,
            catalog,
            scan_db,
            photos_directory
        )
        analyses.append(analysis)
    
    print(f"  Analyse terminee : {len(analyses)} repertoires analyses\n")
    
    # Afficher le résumé
    print_summary(analyses)
    
    # Générer le rapport CSV
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = resultats_dir / f'diagnostic_repertoires_non_trouves_{timestamp}.csv'
    
    print(f"\nGeneration du rapport CSV...")
    generate_report(analyses, report_file)
    print(f"  Rapport sauvegarde dans : {report_file}")


if __name__ == '__main__':
    main()


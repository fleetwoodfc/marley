import csv
import os
import sqlite3
from typing import List, Dict, Optional


DEFAULT_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'radlex.db')


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def build_index_from_csv(csv_path: str, db_path: Optional[str] = None):
    """Build an SQLite FTS5 index from a Playbook CSV.

    CSV must include columns for RPID/code, name/term, and description. The import
    script tries to be tolerant about header names.
    """
    db_path = db_path or DEFAULT_DB
    _ensure_dir(db_path)

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create an FTS5 virtual table for fast full-text queries
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS radlex_fts USING fts5(rpid, name, description, modality, body_part);")
    c.execute("DELETE FROM radlex_fts;")

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            # tolerant column mapping
            rpid = r.get('RPID') or r.get('rpid') or r.get('Code') or r.get('code') or r.get('ID') or ''
            name = r.get('Term') or r.get('term') or r.get('Name') or r.get('name') or ''
            description = r.get('Description') or r.get('description') or r.get('Definition') or r.get('definition') or ''
            modality = r.get('Modality') or r.get('modality') or ''
            body_part = r.get('BodyPart') or r.get('Body Part') or r.get('body_part') or r.get('body part') or ''
            rows.append((rpid.strip(), name.strip(), description.strip(), modality.strip(), body_part.strip()))

    # Insert into FTS table
    c.executemany('INSERT INTO radlex_fts(rpid, name, description, modality, body_part) VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()
    conn.close()


def query_index(query: str, modality: Optional[str] = None, body_part: Optional[str] = None, limit: int = 20, db_path: Optional[str] = None) -> List[Dict]:
    db_path = db_path or DEFAULT_DB
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Build an FTS5 MATCH query. Use phrase match for multi-word queries.
    q = (query or '').strip()
    if not q:
        conn.close()
        return []

    # prefer phrase match for multi-word queries
    if ' ' in q:
        match = '"{}"'.format(q.replace('"', ''))
    else:
        match = q.replace('"', '')

    # Add column filters into MATCH if provided
    if modality:
        match = match + ' modality:' + modality
    if body_part:
        match = match + ' body_part:' + body_part

    sql = 'SELECT rpid, name, description FROM radlex_fts WHERE radlex_fts MATCH ? LIMIT ?'
    try:
        c.execute(sql, (match, limit))
        rows = c.fetchall()
    except Exception:
        rows = []

    conn.close()
    return [{'rpid': r[0], 'name': r[1], 'description': r[2]} for r in rows]


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--csv', required=True, help='Path to Playbook CSV file')
    p.add_argument('--db', help='Path to SQLite DB file')
    args = p.parse_args()
    build_index_from_csv(args.csv, args.db)

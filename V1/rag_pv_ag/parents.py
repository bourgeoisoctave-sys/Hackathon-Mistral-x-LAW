"""Stockage des « parents » : l'unité entière (décision, article, tableau) rendue à l'agent.

Les petits chunks (enfants) sont indexés dans ChromaDB pour la recherche ; leur texte
parent complet est conservé ici (SQLite) et récupéré après la recherche.
"""
import sqlite3
from pathlib import Path

import config as config


class ParentStore:
    def __init__(self, reset: bool = False):
        Path(config.DB_PATH).mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(Path(config.DB_PATH) / "parents.sqlite")
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS parents (id TEXT PRIMARY KEY, source TEXT, text TEXT)"
        )
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_source ON parents(source)")
        if reset:
            self.con.execute("DELETE FROM parents")
            self.con.commit()

    def delete_source(self, source: str) -> None:
        self.con.execute("DELETE FROM parents WHERE source = ?", (source,))
        self.con.commit()

    def put_many(self, items: dict[str, str], source: str) -> None:
        self.con.executemany(
            "INSERT OR REPLACE INTO parents (id, source, text) VALUES (?, ?, ?)",
            [(pid, source, text) for pid, text in items.items()],
        )
        self.con.commit()

    def get_many(self, ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.con.execute(f"SELECT id, text FROM parents WHERE id IN ({marks})", ids).fetchall()
        return dict(rows)
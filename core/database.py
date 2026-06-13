"""Registro simple de declaraciones enviadas para trazabilidad y evitar duplicados."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("./output/declaraciones.db")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS declaraciones (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                num_albaran      TEXT NOT NULL,
                portal           TEXT NOT NULL,
                fecha_declaracion TEXT NOT NULL,
                status           TEXT NOT NULL,
                confirmation_num TEXT,
                declaration_pdf  TEXT,
                merged_pdf       TEXT,
                error_message    TEXT
            )
        """)


def ya_declarado(num_albaran: str, portal: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT id FROM declaraciones WHERE num_albaran=? AND portal=? AND status='confirmed'",
            (num_albaran, portal),
        ).fetchone()
    return row is not None


def guardar_declaracion(
    num_albaran: str,
    portal: str,
    status: str,
    confirmation_num: str | None = None,
    declaration_pdf: str | None = None,
    merged_pdf: str | None = None,
    error_message: str | None = None,
) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO declaraciones
                (num_albaran, portal, fecha_declaracion, status, confirmation_num,
                 declaration_pdf, merged_pdf, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                num_albaran,
                portal,
                datetime.now().isoformat(),
                status,
                confirmation_num,
                declaration_pdf,
                merged_pdf,
                error_message,
            ),
        )


def listar_declaraciones() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM declaraciones ORDER BY fecha_declaracion DESC"
        ).fetchall()

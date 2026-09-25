"""Acesso ao SQLite: uma conexão por operação, sem conexão global compartilhada."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/estante.db"))


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Confirma a transação no sucesso, desfaz no erro e sempre fecha a conexão."""
    conexao = sqlite3.connect(DATABASE_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row
    try:
        with conexao:
            yield conexao
    finally:
        conexao.close()


def iniciar_banco() -> None:
    """Cria a pasta e a tabela, sem apagar cadastros existentes."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conectar() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autores TEXT NOT NULL DEFAULT '',
                ano_publicacao INTEGER,
                status TEXT NOT NULL DEFAULT 'quero_ler'
                    CHECK (status IN ('quero_ler', 'lendo', 'concluido')),
                observacoes TEXT NOT NULL DEFAULT '',
                open_library_id TEXT UNIQUE
            )
        """)

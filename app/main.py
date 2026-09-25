"""API da Estante Acadêmica: cadastro persistente e filtros de leitura."""

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Query, Response

from app.database import conectar, iniciar_banco
from app.schemas import LivroEntrada, LivroSaida, StatusLeitura


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    iniciar_banco()
    yield


app = FastAPI(
    title="Estante Acadêmica API",
    description="Cadastro de livros com SQLite e filtros por leitura, título e autor.",
    version="0.2.0",
    lifespan=lifespan,
)

IdLivro = Annotated[int, Path(ge=1, description="ID devolvido ao cadastrar o livro.")]


@app.get("/", tags=["Sistema"], summary="Verificar funcionamento")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": "estante-academica-api"}


@app.get("/livros", response_model=list[LivroSaida], tags=["Livros"],
         summary="Listar livros e aplicar filtros")
def listar_livros(
    status: Annotated[StatusLeitura | None, Query(description="Estado da leitura.")] = None,
    busca: Annotated[str, Query(max_length=200, description="Trecho do título ou autor.")] = "",
) -> list[dict]:
    # Apenas valores são fornecidos pelo usuário; o SQL permanece fixo.
    termo = busca.strip()
    termo_escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with conectar() as conexao:
        linhas = conexao.execute(r"""
            SELECT * FROM livros
            WHERE (:status IS NULL OR status = :status)
              AND (:busca = ''
                   OR titulo LIKE :padrao ESCAPE '\'
                   OR autores LIKE :padrao ESCAPE '\')
            ORDER BY id DESC
        """, {"status": status, "busca": termo, "padrao": f"%{termo_escapado}%"}).fetchall()
        return [dict(linha) for linha in linhas]


@app.post("/livros", response_model=LivroSaida, status_code=201, tags=["Livros"],
          summary="Cadastrar um livro",
          responses={409: {"description": "Identificador externo já cadastrado."}})
def cadastrar_livro(livro: LivroEntrada) -> dict:
    try:
        with conectar() as conexao:
            cursor = conexao.execute("""
                INSERT INTO livros
                    (titulo, autores, ano_publicacao, status, observacoes, open_library_id)
                VALUES
                    (:titulo, :autores, :ano_publicacao, :status, :observacoes, :open_library_id)
            """, livro.model_dump())
            linha = conexao.execute(
                "SELECT * FROM livros WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return dict(linha)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Este identificador da Open Library já está na estante.") from exc


@app.put("/livros/{livro_id}", response_model=LivroSaida, tags=["Livros"],
         summary="Substituir os dados de um livro",
         responses={404: {"description": "Livro não encontrado."},
                    409: {"description": "Identificador externo já cadastrado."}})
def atualizar_livro(livro_id: IdLivro, livro: LivroEntrada) -> dict:
    """Envie os dados completos, inclusive os valores que deseja manter."""
    dados = livro.model_dump()
    dados["id"] = livro_id
    try:
        with conectar() as conexao:
            cursor = conexao.execute("""
                UPDATE livros
                SET titulo = :titulo, autores = :autores,
                    ano_publicacao = :ano_publicacao, status = :status,
                    observacoes = :observacoes, open_library_id = :open_library_id
                WHERE id = :id
            """, dados)
            if cursor.rowcount == 0:
                raise HTTPException(404, "Livro não encontrado.")
            linha = conexao.execute(
                "SELECT * FROM livros WHERE id = ?", (livro_id,)
            ).fetchone()
            return dict(linha)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Este identificador da Open Library já está na estante.") from exc


@app.delete("/livros/{livro_id}", status_code=204, response_class=Response,
            tags=["Livros"], summary="Excluir um livro",
            responses={404: {"description": "Livro não encontrado."}})
def excluir_livro(livro_id: IdLivro) -> Response:
    with conectar() as conexao:
        cursor = conexao.execute("DELETE FROM livros WHERE id = ?", (livro_id,))
        if cursor.rowcount == 0:
            raise HTTPException(404, "Livro não encontrado.")
    return Response(status_code=204)


# BEGIN ESTANTE ETAPA 3
# Registro do componente de busca externa, sem alterar o CRUD existente.
from app.catalogo import router as catalogo_router

app.include_router(catalogo_router)
app.version = "0.3.0"
app.description = "Cadastro com SQLite e busca bibliográfica na Open Library."
# END ESTANTE ETAPA 3

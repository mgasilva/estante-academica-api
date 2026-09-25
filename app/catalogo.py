"""Busca bibliográfica na Open Library: adaptação, cache e erros controlados.

A busca não grava dados. Cada item retornado é compatível com POST /livros.
Uma única instância/processo de Uvicorn é a configuração prevista neste MVP.
"""

import copy
import http.client
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from threading import Lock
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import LivroEntrada

router = APIRouter(tags=["Catálogo externo"])
logger = logging.getLogger(__name__)

ENDPOINT = "https://openlibrary.org/search.json"
CAMPOS = "key,title,author_name,first_publish_year"
TIMEOUT_SEGUNDOS = 10
MAX_BYTES = 1_000_000
CACHE_SEGUNDOS = 300
MAX_CACHE = 100
INTERVALO_SEGUNDOS = 1.1


class ResultadoCatalogo(BaseModel):
    fonte: Literal["Open Library"] = "Open Library"
    busca: str
    pagina: int
    limite: int
    total: int | None = Field(
        default=None,
        description="Total informado pelo serviço externo, não o número de livros da estante.",
    )
    itens: list[LivroEntrada]


class ErroCatalogo(Exception):
    """Falha esperada da dependência externa, sem expor seu corpo de resposta."""

    def __init__(self, codigo: int, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # O destino é fixo. Uma mudança de URL deve ser revisada no código.
        return None


def normalizar_documento(documento: object) -> dict | None:
    """Adapta os metadados para os limites do cadastro, sem inventar informações."""
    if not isinstance(documento, dict):
        return None
    titulo = documento.get("title")
    chave = documento.get("key")
    if not isinstance(titulo, str) or not titulo.strip():
        return None
    if not isinstance(chave, str) or len(chave) > 100:
        return None
    encontrado = re.fullmatch(r"(?:/works/)?(OL[0-9]+W)", chave.strip())
    if encontrado is None:
        return None
    identificador = f"/works/{encontrado.group(1)}"
    if len(identificador) > 100:
        return None

    nomes = documento.get("author_name", [])
    if isinstance(nomes, str):
        nomes = [nomes]
    if not isinstance(nomes, list):
        nomes = []
    autores = "; ".join(n.strip() for n in nomes if isinstance(n, str) and n.strip())
    ano = documento.get("first_publish_year")
    # bool é subclasse de int em Python, mas não é um ano válido.
    if type(ano) is not int or not 1 <= ano <= 9999:
        ano = None

    return LivroEntrada(
        titulo=titulo.strip()[:300].rstrip(),
        autores=autores[:500].rstrip(),
        ano_publicacao=ano,
        status="quero_ler",
        observacoes="",
        open_library_id=identificador,
    ).model_dump()


def tratar_resposta(dados: object, limite: int) -> tuple[int | None, list[dict]]:
    if not isinstance(dados, dict) or not isinstance(dados.get("docs"), list):
        raise ErroCatalogo(502, "A Open Library devolveu um formato inesperado.")
    total = dados.get("numFound", dados.get("num_found"))
    if type(total) is not int or total < 0:
        total = None
    itens = []
    vistos = set()
    for documento in dados["docs"][:limite]:
        livro = normalizar_documento(documento)
        if livro is not None and livro["open_library_id"] not in vistos:
            vistos.add(livro["open_library_id"])
            itens.append(livro)
    return total, itens


class ClienteOpenLibrary:
    """Cliente de baixo volume com cache limitado e chamadas externas espaçadas."""

    def __init__(self):
        self._cache: OrderedDict = OrderedDict()
        self._lock = Lock()
        self._ultima_chamada = float("-inf")
        self._opener = urllib.request.build_opener(SemRedirecionamento())

    def _consultar(self, busca: str, limite: int, pagina: int) -> object:
        parametros = urllib.parse.urlencode({
            "q": busca, "fields": CAMPOS, "limit": limite, "page": pagina,
        })
        # Configure um email de contato para uso regular, sem colocar senha/token.
        contato = os.environ.get("OPEN_LIBRARY_CONTACT", "").strip()
        if any(ord(c) < 32 or ord(c) > 126 for c in contato):
            contato = ""
        agente = "EstanteAcademica/0.3 (projeto educacional; baixo volume)"
        if contato:
            agente = f"EstanteAcademica/0.3 ({contato[:200]})"
        req = urllib.request.Request(
            ENDPOINT + "?" + parametros,
            headers={"Accept": "application/json", "User-Agent": agente},
        )
        try:
            with self._opener.open(req, timeout=TIMEOUT_SEGUNDOS) as resposta:
                bruto = resposta.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            codigo = exc.code
            exc.close()
            logger.warning("Open Library: HTTP %s", codigo)
            if codigo == 429 or codigo == 503:
                raise ErroCatalogo(503, "A Open Library está ocupada. Aguarde e tente novamente.") from exc
            raise ErroCatalogo(502, "Não foi possível consultar a Open Library agora.") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ErroCatalogo(504, "A Open Library demorou a responder. Tente novamente.") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ErroCatalogo(504, "A Open Library demorou a responder. Tente novamente.") from exc
            raise ErroCatalogo(502, "Falha de conexão com a Open Library.") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise ErroCatalogo(502, "Falha de comunicação com a Open Library.") from exc
        if len(bruto) > MAX_BYTES:
            raise ErroCatalogo(502, "A resposta da Open Library excedeu o limite permitido.")
        try:
            return json.loads(bruto)
        except (ValueError, UnicodeError) as exc:
            raise ErroCatalogo(502, "A Open Library devolveu uma resposta JSON inválida.") from exc

    def buscar(self, busca: str, limite: int, pagina: int) -> dict:
        chave = (busca, limite, pagina)
        # Sem fila ilimitada: chamadas concorrentes recebem erro recuperável.
        if not self._lock.acquire(timeout=1):
            raise ErroCatalogo(503, "Já há uma busca em andamento. Aguarde e tente novamente.")
        try:
            agora = time.monotonic()
            expiradas = [k for k, (fim, _) in self._cache.items() if fim <= agora]
            for k in expiradas:
                del self._cache[k]
            if chave in self._cache:
                self._cache.move_to_end(chave)
                return copy.deepcopy(self._cache[chave][1])

            espera = INTERVALO_SEGUNDOS - (agora - self._ultima_chamada)
            if espera > 0:
                time.sleep(espera)
            self._ultima_chamada = time.monotonic()
            bruto = self._consultar(busca, limite, pagina)
            total, itens = tratar_resposta(bruto, limite)
            resultado = {
                "fonte": "Open Library", "busca": busca, "pagina": pagina,
                "limite": limite, "total": total, "itens": itens,
            }
            self._cache[chave] = (time.monotonic() + CACHE_SEGUNDOS, copy.deepcopy(resultado))
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)
            return resultado
        finally:
            self._lock.release()


cliente = ClienteOpenLibrary()


@router.get(
    "/catalogo", response_model=ResultadoCatalogo,
    summary="Buscar livros na Open Library",
    responses={
        502: {"description": "Falha de conexão ou resposta externa inválida."},
        503: {"description": "Busca ocupada ou serviço externo temporariamente indisponível."},
        504: {"description": "O serviço externo não respondeu no prazo."},
    },
)
def buscar_catalogo(
    busca: Annotated[str, Query(min_length=2, max_length=120, description="Título, autor ou assunto.")],
    limite: Annotated[int, Query(ge=1, le=20, description="Máximo de itens por página.")] = 5,
    pagina: Annotated[int, Query(ge=1, le=100, description="Página do catálogo externo.")] = 1,
) -> dict:
    """Consulta e trata metadados externos, sem redirecionar e sem gravar no banco.

    O campo ano_publicacao representa a primeira publicação da OBRA, não a edição
    específica. Para salvar uma escolha, envie um objeto de 'itens' ao POST /livros.
    O total vem do catálogo externo; itens incompletos podem ser descartados.
    """
    termo = busca.strip()
    if len(termo) < 2:
        raise HTTPException(422, "Informe ao menos dois caracteres na busca.")
    try:
        return cliente.buscar(termo, limite, pagina)
    except ErroCatalogo as exc:
        headers = {"Retry-After": "5"} if exc.codigo == 503 else None
        raise HTTPException(exc.codigo, exc.mensagem, headers=headers) from exc

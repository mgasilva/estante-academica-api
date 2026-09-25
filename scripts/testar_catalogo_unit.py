#!/usr/bin/env python3
"""Testes locais com respostas SIMULADAS: sem internet e sem alterar o SQLite.

No Codespace, após construir a imagem:
    docker exec -i estante-api python - < scripts/testar_catalogo_unit.py
"""

import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

if __file__ != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalogo import (
    ClienteOpenLibrary, ErroCatalogo, ResultadoCatalogo,
    buscar_catalogo, normalizar_documento, tratar_resposta,
)
from app.schemas import LivroEntrada
from fastapi import HTTPException

DOCUMENTO = {
    "key": "/works/OL12345W", "title": "Livro fictício para teste",
    "author_name": ["Autora A", "Autor B"], "first_publish_year": 2020,
}
RESPOSTA = {"numFound": 1, "docs": [DOCUMENTO]}


class TestarCatalogo(unittest.TestCase):
    def setUp(self):
        self.cliente = ClienteOpenLibrary()
        patcher = patch("app.catalogo.INTERVALO_SEGUNDOS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_01_normalizacao_basica(self):
        livro = normalizar_documento(DOCUMENTO)
        self.assertEqual(livro["autores"], "Autora A; Autor B")
        self.assertEqual(livro["ano_publicacao"], 2020)
        self.assertEqual(livro["status"], "quero_ler")
        self.assertEqual(LivroEntrada(**livro).model_dump(), livro)
        self.assertNotIn("id", livro)

    def test_02_id_sem_prefixo(self):
        livro = normalizar_documento({**DOCUMENTO, "key": "OL12345W"})
        self.assertEqual(livro["open_library_id"], "/works/OL12345W")

    def test_03_rejeita_registro_incompleto(self):
        for valor in (None, [], {}, {**DOCUMENTO, "title": "   "}, {**DOCUMENTO, "key": "https://outro.site"}):
            with self.subTest(valor=valor):
                self.assertIsNone(normalizar_documento(valor))

    def test_04_dados_ausentes(self):
        livro = normalizar_documento({"key": "OL123W", "title": "Só título"})
        self.assertEqual(livro["autores"], "")
        self.assertIsNone(livro["ano_publicacao"])

    def test_05_anos_invalidos_nao_inventados(self):
        for ano in (True, -1, 0, 10000, "2020", None):
            with self.subTest(ano=ano):
                livro = normalizar_documento({**DOCUMENTO, "first_publish_year": ano})
                self.assertIsNone(livro["ano_publicacao"])

    def test_06_limites_do_cadastro(self):
        livro = normalizar_documento({**DOCUMENTO, "title": "a" * 600, "author_name": ["b" * 900]})
        self.assertEqual(len(livro["titulo"]), 300)
        self.assertEqual(len(livro["autores"]), 500)
        LivroEntrada(**livro)

    def test_07_resposta_total_e_deduplicacao(self):
        total, itens = tratar_resposta({"num_found": 7, "docs": [DOCUMENTO, DOCUMENTO, {}]}, 3)
        self.assertEqual(total, 7)
        self.assertEqual(len(itens), 1)

    def test_08_resposta_invalida(self):
        for dados in (None, [], {"docs": None}, {"erro": "falhou"}):
            with self.subTest(dados=dados), self.assertRaises(ErroCatalogo) as erro:
                tratar_resposta(dados, 5)
            self.assertEqual(erro.exception.codigo, 502)

    def test_09_total_desconhecido_nao_vira_zero(self):
        total, _ = tratar_resposta({"docs": []}, 5)
        self.assertIsNone(total)

    def test_10_cache_evitar_requisicao_repetida(self):
        with patch.object(self.cliente, "_consultar", return_value=RESPOSTA) as consulta:
            primeiro = self.cliente.buscar("python", 5, 1)
            primeiro["itens"].clear()
            segundo = self.cliente.buscar("python", 5, 1)
            self.assertEqual(len(segundo["itens"]), 1)
            self.assertEqual(consulta.call_count, 1)
            ResultadoCatalogo(**segundo)

    def test_11_cache_expira(self):
        with patch("app.catalogo.time.monotonic", return_value=100) as relogio, \
             patch.object(self.cliente, "_consultar", return_value=RESPOSTA) as consulta:
            self.cliente.buscar("python", 5, 1)
            relogio.return_value = 401
            self.cliente.buscar("python", 5, 1)
            self.assertEqual(consulta.call_count, 2)

    def test_12_cache_paginas_distintas(self):
        with patch.object(self.cliente, "_consultar", return_value=RESPOSTA) as consulta:
            self.cliente.buscar("python", 5, 1)
            self.cliente.buscar("python", 5, 2)
            self.assertEqual(consulta.call_count, 2)

    def test_13_montagem_da_chamada_externa(self):
        with patch.object(self.cliente._opener, "open", return_value=io.BytesIO(json.dumps(RESPOSTA).encode())) as abrir:
            dados = self.cliente._consultar("álgebra & circuitos", 3, 2)
            self.assertEqual(dados["numFound"], 1)
            req = abrir.call_args.args[0]
            self.assertTrue(req.full_url.startswith("https://openlibrary.org/search.json?"))
            self.assertIn("%26", req.full_url)
            self.assertIn("page=2", req.full_url)
            self.assertTrue(req.get_header("User-agent").startswith("EstanteAcademica/"))

    def test_14_tratamento_http_externo(self):
        for status, esperado in ((429, 503), (503, 503), (500, 502), (302, 502)):
            erro_externo = urllib.error.HTTPError("https://openlibrary.org/search.json", status, "teste", {}, None)
            with self.subTest(status=status), \
                 patch.object(self.cliente._opener, "open", side_effect=erro_externo), \
                 self.assertRaises(ErroCatalogo) as erro:
                self.cliente._consultar("python", 5, 1)
            self.assertEqual(erro.exception.codigo, esperado)

    def test_15_timeout_e_conexao(self):
        for externo, esperado in ((TimeoutError(), 504), (urllib.error.URLError(TimeoutError()), 504), (urllib.error.URLError("dns"), 502)):
            with self.subTest(esperado=esperado), \
                 patch.object(self.cliente._opener, "open", side_effect=externo), \
                 self.assertRaises(ErroCatalogo) as erro:
                self.cliente._consultar("python", 5, 1)
            self.assertEqual(erro.exception.codigo, esperado)

    def test_16_json_invalido(self):
        with patch.object(self.cliente._opener, "open", return_value=io.BytesIO(b"<html>erro</html>")), \
             self.assertRaises(ErroCatalogo) as erro:
            self.cliente._consultar("python", 5, 1)
        self.assertEqual(erro.exception.codigo, 502)

    def test_17_limite_da_resposta(self):
        with patch("app.catalogo.MAX_BYTES", 10), \
             patch.object(self.cliente._opener, "open", return_value=io.BytesIO(b"x" * 11)), \
             self.assertRaises(ErroCatalogo) as erro:
            self.cliente._consultar("python", 5, 1)
        self.assertEqual(erro.exception.codigo, 502)

    def test_18_handler_busca_so_espacos(self):
        with self.assertRaises(HTTPException) as erro:
            buscar_catalogo("   ", 5, 1)
        self.assertEqual(erro.exception.status_code, 422)

    def test_19_handler_traduz_erro(self):
        with patch("app.catalogo.cliente.buscar", side_effect=ErroCatalogo(503, "Ocupado")), \
             self.assertRaises(HTTPException) as erro:
            buscar_catalogo("python", 5, 1)
        self.assertEqual(erro.exception.status_code, 503)
        self.assertEqual(erro.exception.headers, {"Retry-After": "5"})

    def test_20_busca_vazia_legitima(self):
        with patch.object(self.cliente, "_consultar", return_value={"numFound": 0, "docs": []}):
            resposta = self.cliente.buscar("inexistente", 5, 1)
        self.assertEqual(resposta["total"], 0)
        self.assertEqual(resposta["itens"], [])

    def test_21_espacamento_de_chamadas(self):
        self.cliente._ultima_chamada = 100
        with patch("app.catalogo.INTERVALO_SEGUNDOS", 1.1), \
             patch("app.catalogo.time.monotonic", return_value=100), \
             patch("app.catalogo.time.sleep") as pausa, \
             patch.object(self.cliente, "_consultar", return_value=RESPOSTA):
            self.cliente.buscar("python", 5, 1)
        pausa.assert_called_once_with(1.1)

    def test_22_cache_tamanho_limitado(self):
        with patch("app.catalogo.MAX_CACHE", 2), patch.object(self.cliente, "_consultar", return_value=RESPOSTA):
            for termo in ("um", "dois", "tres"):
                self.cliente.buscar(termo, 5, 1)
        self.assertEqual(len(self.cliente._cache), 2)
        self.assertNotIn(("um", 5, 1), self.cliente._cache)


if __name__ == "__main__":
    unittest.main(argv=["testar_catalogo_unit.py"], verbosity=2)

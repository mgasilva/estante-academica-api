#!/usr/bin/env python3
"""12 testes HTTP, usando somente a biblioteca padrão do Python.

Cria registros temporários e exclui SOMENTE os registros criados pelos testes.
Uso: python scripts/testar_api.py [--base-url http://127.0.0.1:8000]
"""

import argparse
import json
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE_URL = "http://127.0.0.1:8000"


def requisicao(metodo, caminho, dados=None):
    corpo = None if dados is None else json.dumps(dados).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + caminho, data=corpo, method=metodo,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resposta:
            codigo, bruto = resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        codigo, bruto = erro.code, erro.read()
    return codigo, json.loads(bruto) if bruto else None


class TestarAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for _ in range(15):
            try:
                codigo, corpo = requisicao("GET", "/")
                if codigo == 200 and corpo.get("service") == "estante-academica-api":
                    return
            except (OSError, ValueError, AttributeError):
                pass
            time.sleep(1)
        raise RuntimeError("API indisponível. Execute bash scripts/subir_api.sh e confira os logs.")

    def setUp(self):
        self.ids = []
        self.marca = f"teste-{uuid.uuid4().hex}"

    def tearDown(self):
        for livro_id in self.ids:
            codigo, _ = requisicao("DELETE", f"/livros/{livro_id}")
            self.assertIn(codigo, (204, 404), "Não foi possível limpar um registro do teste.")

    def dados(self, **alteracoes):
        dados = {
            "titulo": f"Eletrônica e programação {self.marca}",
            "autores": "Autor de teste",
            "ano_publicacao": 2024,
            "status": "quero_ler",
            "observacoes": "Registro temporário criado pelo teste automatizado.",
            "open_library_id": None,
        }
        dados.update(alteracoes)
        return dados

    def criar(self, **alteracoes):
        codigo, livro = requisicao("POST", "/livros", self.dados(**alteracoes))
        if codigo == 201 and isinstance(livro, dict) and "id" in livro:
            self.ids.append(livro["id"])
        self.assertEqual(codigo, 201, livro)
        return livro

    def test_01_disponibilidade(self):
        codigo, corpo = requisicao("GET", "/")
        self.assertEqual(codigo, 200)
        self.assertEqual(corpo["status"], "ok")

    def test_02_cadastro_e_unicode(self):
        livro = self.criar()
        self.assertIsInstance(livro["id"], int)
        self.assertEqual(livro["titulo"], self.dados()["titulo"])
        self.assertEqual(livro["status"], "quero_ler")

    def test_03_listagem(self):
        livro = self.criar()
        codigo, livros = requisicao("GET", "/livros")
        self.assertEqual(codigo, 200)
        self.assertIn(livro["id"], [item["id"] for item in livros])

    def test_04_filtro_status(self):
        desejado = self.criar(status="lendo")
        outro = self.criar(status="quero_ler")
        query = urllib.parse.urlencode({"status": "lendo", "busca": self.marca})
        codigo, livros = requisicao("GET", "/livros?" + query)
        self.assertEqual(codigo, 200)
        self.assertIn(desejado["id"], [item["id"] for item in livros])
        self.assertNotIn(outro["id"], [item["id"] for item in livros])

    def test_05_busca_por_autor(self):
        livro = self.criar(autores=f"Autor-{self.marca}")
        query = urllib.parse.urlencode({"busca": f"Autor-{self.marca}"})
        codigo, livros = requisicao("GET", "/livros?" + query)
        self.assertEqual(codigo, 200)
        self.assertEqual([item["id"] for item in livros], [livro["id"]])

    def test_06_atualizacao(self):
        livro = self.criar()
        payload = self.dados(status="concluido", observacoes="Leitura terminada.")
        codigo, alterado = requisicao("PUT", f"/livros/{livro['id']}", payload)
        self.assertEqual(codigo, 200, alterado)
        self.assertEqual(alterado["status"], "concluido")
        query = urllib.parse.urlencode({"busca": self.marca})
        _, livros = requisicao("GET", "/livros?" + query)
        salvo = next(item for item in livros if item["id"] == livro["id"])
        self.assertEqual(salvo["observacoes"], "Leitura terminada.")

    def test_07_exclusao(self):
        livro = self.criar()
        codigo, corpo = requisicao("DELETE", f"/livros/{livro['id']}")
        self.assertEqual(codigo, 204)
        self.assertIsNone(corpo)
        codigo, _ = requisicao("DELETE", f"/livros/{livro['id']}")
        self.assertEqual(codigo, 404)

    def test_08_titulo_vazio_invalido(self):
        codigo, _ = requisicao("POST", "/livros", self.dados(titulo="   "))
        self.assertEqual(codigo, 422)

    def test_09_status_invalido(self):
        codigo, _ = requisicao("POST", "/livros", self.dados(status="invalido"))
        self.assertEqual(codigo, 422)
        codigo, _ = requisicao("GET", "/livros?status=invalido")
        self.assertEqual(codigo, 422)

    def test_10_ano_invalido(self):
        codigo, _ = requisicao("POST", "/livros", self.dados(ano_publicacao=-1))
        self.assertEqual(codigo, 422)

    def test_11_atualizacao_inexistente(self):
        livro = self.criar()
        requisicao("DELETE", f"/livros/{livro['id']}")
        codigo, _ = requisicao("PUT", f"/livros/{livro['id']}", self.dados())
        self.assertEqual(codigo, 404)

    def test_12_identificador_duplicado(self):
        identificador = f"/works/OL{uuid.uuid4().int}W"
        self.criar(open_library_id=identificador)
        codigo, _ = requisicao("POST", "/livros", self.dados(open_library_id=identificador))
        self.assertEqual(codigo, 409)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    BASE_URL = args.base_url.rstrip("/")
    unittest.main(argv=[__file__], verbosity=2)

#!/usr/bin/env python3
"""Teste HTTP da rota /catalogo, com UMA busca externa real. Não altera o banco.

Uso: python scripts/testar_catalogo.py [--base-url http://127.0.0.1:8000]
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def consultar(base_url: str, caminho: str) -> tuple[int, object]:
    req = urllib.request.Request(base_url.rstrip("/") + caminho, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resposta:
            return resposta.status, json.loads(resposta.read())
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, json.loads(erro.read())
        finally:
            erro.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    # Estas quatro chamadas inválidas são rejeitadas antes do acesso externo.
    for caminho in ("/catalogo", "/catalogo?busca=x", "/catalogo?busca=python&limite=21", "/catalogo?busca=python&pagina=0"):
        codigo, corpo = consultar(args.base_url, caminho)
        if codigo != 422:
            print(f"FALHOU: {caminho} deveria retornar 422; recebido {codigo}: {corpo}")
            return 1
    print("OK: validação de busca, limite e página (4 verificações HTTP).")

    query = urllib.parse.urlencode({"busca": "python", "limite": 3, "pagina": 1})
    codigo, corpo = consultar(args.base_url, "/catalogo?" + query)
    if codigo != 200:
        print(f"Busca externa: HTTP {codigo}\n{json.dumps(corpo, ensure_ascii=False)}")
        print("Não repita cadastros nem recrie o banco. Verifique a mensagem e a conectividade externa.")
        return 1
    if not isinstance(corpo, dict) or corpo.get("fonte") != "Open Library" or not isinstance(corpo.get("itens"), list):
        print("FALHOU: formato inesperado:", corpo)
        return 1
    itens = corpo["itens"]
    if not itens:
        print("A busca funcionou, mas veio vazia. Precisamos inspecionar antes de confirmar o teste externo.")
        return 1
    campos = {"titulo", "autores", "ano_publicacao", "status", "observacoes", "open_library_id"}
    for livro in itens:
        if not isinstance(livro, dict) or not campos.issubset(livro) or not livro.get("open_library_id"):
            print("FALHOU: item incompatível com o cadastro:", livro)
            return 1
    if len(itens) > 3:
        print("FALHOU: a API excedeu o limite pedido.")
        return 1
    print(f"OK: GET /catalogo retornou HTTP 200 com {len(itens)} livro(s).")
    for i, livro in enumerate(itens, 1):
        print(f"  {i}. {livro['titulo']} — {livro['autores']} [{livro['open_library_id']}]")
    print("TESTE DO CATÁLOGO: OK. Nenhum livro foi cadastrado ou excluído.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as erro:
        print(f"FALHOU: {erro}", file=sys.stderr)
        raise SystemExit(1)

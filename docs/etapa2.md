# Etapa 2 — API com SQLite

Esta etapa implementa o cadastro local. A integração real com a Open Library,
a interface, o Compose e a documentação final ainda serão acrescentados.
O campo opcional `open_library_id` está reservado para a próxima etapa;
nenhuma chamada externa é feita nesta versão.

## Estrutura

- `app/main.py`: rotas REST e criação do banco no início da aplicação.
- `app/database.py`: tabela SQLite, conexões e transações.
- `app/schemas.py`: validação das entradas e formato das saídas.
- `Dockerfile`: execução como usuário não root.
- `scripts/subir_api.sh`: build e recriação da API com o mesmo volume de dados.
- `scripts/testar_api.py`: 12 testes HTTP com a biblioteca padrão do Python.

`requirements.txt` e o README já existente não são alterados pelo preparador.
A aplicação continua utilizando as dependências que já funcionaram na etapa 1.

## Executar no Codespace

```bash
bash scripts/subir_api.sh
python scripts/testar_api.py
```

Abra a porta encaminhada 8000 e acrescente `/docs`. Mantenha a porta privada.

## Operações

| Método | Caminho | Sucesso |
|---|---|---|
| GET | `/` | 200 |
| GET | `/livros` | 200 |
| POST | `/livros` | 201 |
| PUT | `/livros/{livro_id}` | 200 |
| DELETE | `/livros/{livro_id}` | 204, sem corpo |

Em GET `/livros`, `status` é opcional (`quero_ler`, `lendo`, `concluido`),
e `busca` procura um trecho de título ou autores. A busca utiliza LIKE do SQLite:
não é uma busca aproximada e não normaliza acentos.

O POST aceita cadastro manual, deixando `open_library_id` como `null`.
Um mesmo identificador externo não pode ser cadastrado duas vezes (409).
Títulos vazios, status desconhecidos, anos fora de 1–9999 e campos não previstos
são rejeitados. O ano é opcional, mas quando enviado deve ser inteiro.

**PUT substitui os dados editáveis.** Envie todos os valores que pretende manter;
campos opcionais omitidos voltam ao valor padrão. Não envie o campo `id` no corpo:
o identificador deve aparecer no caminho da requisição.

## Persistência e limites

O banco fica em `/data/estante.db` dentro do contêiner. O script monta o volume
nomeado `estante-academica-dados` em `/data`, reutilizando-o a cada execução.

Para verificar persistência de verdade, cadastre um livro manualmente, execute
novamente `bash scripts/subir_api.sh` (que remove e recria o contêiner) e consulte
GET `/livros`. O cadastro deve continuar presente. Não remova o volume.

O volume protege contra a substituição do contêiner da aplicação; NÃO é um backup
externo e não deve ser considerado proteção contra exclusão/recriação do Codespace.
Os testes automatizados criam e removem apenas seus próprios livros; eles não
executam a recriação do contêiner nem verificam o volume Docker.
Não há autenticação nesta etapa; mantenha o ambiente de demonstração privado.

## Diagnóstico

```bash
docker logs --tail 60 estante-api
docker ps -a --filter name=estante-api
docker volume inspect estante-academica-dados
```

## Conceitos para a apresentação

A interface (ainda não implementada) chamará a API por HTTP. A API valida o JSON e
executa consultas parametrizadas no SQLite. O GET consulta; POST cria; PUT altera;
DELETE remove. A tabela é criada no lifespan do FastAPI, antes de receber requisições.
As alterações do banco são confirmadas no sucesso e desfeitas no erro.

## Referências técnicas

- FastAPI: https://fastapi.tiangolo.com/advanced/events/
- SQLite/Python: https://docs.python.org/3.12/library/sqlite3.html
- Pydantic: https://docs.pydantic.dev/latest/api/config/
- Docker volumes: https://docs.docker.com/engine/storage/volumes/

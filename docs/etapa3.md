# Etapa 3 — Busca na Open Library

Esta etapa acrescenta `GET /catalogo` ao cadastro com SQLite da etapa 2.
A API recebe a busca, consulta o serviço externo, adapta seus metadados e devolve
JSON. Não redireciona o navegador e não grava livros automaticamente.
O front-end ainda será construído em seu próprio repositório.

## Instalar e executar

Na raiz de `estante-academica-api`, execute o preparador uma vez e reconstrua:

```bash
python preparar_etapa3.py
bash scripts/subir_api.sh
python scripts/testar_api.py
python scripts/testar_catalogo.py
```

Teste isolado com respostas simuladas, sem internet e sem alterações no banco:

```bash
docker exec -i estante-api python - < scripts/testar_catalogo_unit.py
```

O preparador preserva `README.md`, `requirements.txt`, `Dockerfile`, os modelos
SQLite e as rotas de cadastro. Antes de alterar arquivos faz cópias em
`../backups-estante-academica/etapa3-DATA-HORA/`. Não faz commit nem push.
Não remove o volume de dados. As cópias locais não substituem um backup remoto.

## API externa utilizada

- Serviço: Open Library Search API, consulta pública de metadados bibliográficos.
- Endpoint consumido: `GET https://openlibrary.org/search.json`.
- Não é necessário cadastro nem chave de API para esta consulta pública.
- A consulta implementada não usa plano pago, empréstimos nem download de livros.
- Parâmetros enviados: `q`, `fields`, `limit` e `page`.
- Campos solicitados: `key,title,author_name,first_publish_year`.
- Documentação: https://openlibrary.org/dev/docs/api/search
- Diretrizes de uso: https://openlibrary.org/developers/api
- Licenciamento: https://openlibrary.org/developers/licensing

A página de licenciamento declara que o Internet Archive não reivindica novos
direitos autorais ou proprietários sobre o material da base, mas ressalva que
podem existir direitos em algumas contribuições e jurisdições. Isso não é uma
autorização geral para reproduzir o conteúdo dos livros. Este projeto usa apenas
metadados e identifica sua fonte. As condições devem ser verificadas antes de
outros usos. Fontes consultadas em 25/09/2026.

Para uso regular, informe um email de contato em `User-Agent`, como recomenda o
provedor. Use um endereço seu que possa ser compartilhado com a Open Library;
não é senha nem token. O script de execução aceita:

```bash
export OPEN_LIBRARY_CONTACT='seu-email-de-contato'
bash scripts/subir_api.sh
```

Não é preciso colocar esse endereço no código ou publicá-lo no GitHub.
Sem a variável, o cabeçalho identifica somente o projeto. A configuração continua
limitada a uma chamada externa a cada 1,1 segundo por processo, abaixo do limite
padrão documentado de uma requisição por segundo. O MVP prevê uma única instância
do processo Uvicorn. Múltiplos processos/réplicas exigiriam limite compartilhado.

## Contrato da nossa rota

```http
GET /catalogo?busca=python&limite=3&pagina=1
```

`busca`: 2 a 120 caracteres; `limite`: 1 a 20; `pagina`: 1 a 100.
Campos da resposta:

| Campo | Significado |
|---|---|
| fonte | Sempre `Open Library` |
| busca | Termo usado na consulta |
| pagina / limite | Paginação pedida ao catálogo externo |
| total | Total informado pelo serviço, ou `null` se não disponível |
| itens | Lista de objetos compatíveis com POST `/livros` |

### Transformação dos dados

| Open Library | Nossa aplicação |
|---|---|
| `title` | `titulo`, com limite de 300 caracteres |
| `author_name` | `autores`, unidos por ponto e vírgula; até 500 caracteres |
| `first_publish_year` | `ano_publicacao`, inteiro válido ou `null` |
| `key` | `open_library_id`, normalizado para `/works/OL...W` |
| Não se aplica | `status = quero_ler`; `observacoes = ""` |

O ano da busca é a **primeira publicação da obra**, não necessariamente o ano
da edição que o usuário possui. Registros sem título ou ID de obra válido são
descartados; nomes/anos ausentes não são inventados. O total informado pela fonte
pode ser maior que a quantidade de itens recebidos, devido à paginação e ao filtro
de registros incompletos. Obras repetidas numa mesma resposta são deduplicadas.

Cada objeto dentro de `itens` pode ser copiado inteiro para POST `/livros`.
Copie somente o objeto escolhido, não o envelope com `fonte`, `total` e `itens`.
O cadastro retorna um ID **local** numérico; `open_library_id` é o ID **externo**.
O banco da etapa 2 impede repetir o mesmo ID externo, devolvendo 409.
A busca não muda se você excluir um livro local: as bases são distintas.

## Proteções e limites

A implementação inclui cache em memória por 5 minutos, até 100 buscas, uma URL
externa fixa, TLS com verificação padrão, limite de leitura de 1 MB, timeout de
10 segundos nas operações de rede e tratamento de falhas. O timeout da biblioteca
não é um cronômetro global para toda a requisição. Não há repetição automática nem
consulta a cada tecla; o futuro front-end usará um botão de busca.
Não segue redirecionamentos para destinos externos diferentes.

| Código | Significado nesta implementação |
|---|---|
| 200 | Busca realizada, eventualmente sem resultados |
| 422 | Parâmetro de entrada inválido |
| 502 | Falha de comunicação ou formato de resposta inesperado |
| 503 | Busca concorrente ocupada ou indisponibilidade/limite externo |
| 504 | Timeout do serviço externo |

Falhas externas não são transformadas silenciosamente em uma lista vazia. O CRUD
local não depende da Open Library para funcionar. Os erros não expõem o HTML ou
outros detalhes internos do provedor. Não há autenticação de usuários no MVP;
mantenha privadas as portas encaminhadas no Codespace.

## Conferência manual

```bash
curl -sS --get --max-time 25 \
  'http://127.0.0.1:8000/catalogo' \
  --data-urlencode 'busca=python' \
  --data 'limite=3' | python -m json.tool
```

Atualize `/docs`, abra GET `/catalogo`, clique em Try it out, preencha a busca e
Execute. Leia **Server response / Response body**, não **Example Value**.
Copie um objeto de `itens` para o POST `/livros`, confirme 201 e consulte GET
`/livros`. Os resultados reais podem mudar e não têm ordem garantida no projeto.

## O que os testes demonstram

- `testar_api.py`: regressão das 12 verificações de CRUD da etapa 2, com seus próprios registros temporários.
- `testar_catalogo_unit.py`: 22 testes locais de normalização, erros, cache e montagem de requisições; respostas externas simuladas.
- `testar_catalogo.py`: 4 entradas inválidas e uma busca HTTP válida no serviço em execução, sem gravar no banco. Pode reutilizar cache recente da busca.

Testes simulados não provam disponibilidade da Open Library. O teste HTTP não
recria o contêiner nem retesta a persistência do volume. A prova real da integração
no seu Codespace será uma consulta bem-sucedida após a nova versão subir.

## Para o README do front-end

A documentação da API externa também deve aparecer na documentação do componente
principal. Ao criar o front-end, leve para seu README as informações desta seção:
serviço, endpoint, ausência de chave/plano pago nesta consulta, fonte dos metadados,
limites de uso e referência ao licenciamento. Ainda faltam o front-end, o desenho
da arquitetura, a documentação final, o envio dos códigos e o vídeo.

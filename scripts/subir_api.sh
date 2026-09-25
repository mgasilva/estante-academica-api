#!/usr/bin/env bash
# Reconstrói SOMENTE a API deste projeto; reutiliza seu volume de dados.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="estante-academica-api:dev"
CONTAINER="estante-api"
VOLUME="estante-academica-dados"

echo "Construindo a nova imagem antes de parar a versão atual..."
docker build -t "$IMAGE" .

# Protege um possível banco em outro volume ou na camada interna do contêiner.
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
    current_mount="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$CONTAINER")"
    if [[ -n "$current_mount" && "$current_mount" != "$VOLUME" ]]; then
        echo "ERRO: /data usa outro volume. Pare e revise a configuração antes de continuar." >&2
        exit 1
    fi
    if [[ -z "$current_mount" ]] && docker exec "$CONTAINER" test -e /data/estante.db 2>/dev/null; then
        echo "ERRO: há um banco fora do volume esperado. Faça backup antes de recriar o contêiner." >&2
        exit 1
    fi
    echo "Parando e removendo apenas o contêiner $CONTAINER..."
    docker stop "$CONTAINER" >/dev/null
    docker rm "$CONTAINER" >/dev/null
fi

docker volume create "$VOLUME" >/dev/null

echo "Iniciando a API com o volume persistente $VOLUME..."
docker run -d \
    --name "$CONTAINER" \
    --env OPEN_LIBRARY_CONTACT="${OPEN_LIBRARY_CONTACT:-}" \
    -p 127.0.0.1:8000:8000 \
    --mount type=volume,source="$VOLUME",target=/data \
    "$IMAGE"

for attempt in {1..30}; do
    if curl -fsS http://127.0.0.1:8000/ >/dev/null 2>&1; then
        echo "API pronta na porta 8000."
        echo "Abra /docs pelo endereço encaminhado do Codespace."
        echo "Teste: python scripts/testar_api.py"
        exit 0
    fi
    sleep 1
done

echo "ERRO: a API não respondeu. Últimas mensagens:" >&2
docker logs --tail 60 "$CONTAINER" >&2
exit 1

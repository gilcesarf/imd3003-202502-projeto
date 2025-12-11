#!/bin/bash
set -euo pipefail

SEMANTIC_DIR="./semantic"
FAILURES_DIR="./failures"
OUT_FILE="invalid_json.txt"

# Cria diretório de falhas (caso não exista)
mkdir -p "$FAILURES_DIR"

# Zera o arquivo de saída
> "$OUT_FILE"

echo "📁 Diretório dos JSONs: $SEMANTIC_DIR"
echo "📁 Diretório de falhas: $FAILURES_DIR"
echo "📝 Lista de inválidos:  $OUT_FILE"
echo

COUNT=0
BAD=0

for FILE in "$SEMANTIC_DIR"/*.json; do
    [ -e "$FILE" ] || continue  # ignora caso não existam arquivos

    COUNT=$((COUNT + 1))
    BASENAME=$(basename "$FILE")

    echo -n "Validando $BASENAME ... "

    if jq . "$FILE" >/dev/null 2>&1; then
        echo "OK"
    else
        echo "FALHOU"

        # registra no txt
        echo "$FILE" >> "$OUT_FILE"

        # move para pasta failures
        mv "$FILE" "$FAILURES_DIR"/

        BAD=$((BAD + 1))
    fi
done

echo
echo "=============================================="
echo "  Arquivos verificados : $COUNT"
echo "  JSONs inválidos      : $BAD"
echo "  Lista salva em       : $OUT_FILE"
echo "  Arquivos movidos para: $FAILURES_DIR/"
echo "=============================================="

if [ "$BAD" -gt 0 ]; then
    echo "⚠️ Existem JSONs inválidos."
else
    echo "✔ Todos os JSONs são válidos!"
fi

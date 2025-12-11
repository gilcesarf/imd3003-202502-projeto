#!/bin/bash
set -euo pipefail

# ============================
# CONFIGURAÇÃO
# ============================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SEMANTIC_PY="${SCRIPT_DIR}/semantic_route_summary.py"
OUT_DIR="${SCRIPT_DIR}/semantic"
REMOVE_PREFIX="coopeuch-migracion-"

# ============================
# PARÂMETRO
# ============================

if [ $# -ne 1 ]; then
  echo "Uso: $0 <diretorio-raiz>"
  exit 1
fi

ROOT_DIR="$1"

if [ ! -d "$ROOT_DIR" ]; then
  echo "ERRO: diretório não encontrado: $ROOT_DIR"
  exit 1
fi

mkdir -p "$OUT_DIR"

if [ ! -f "$SEMANTIC_PY" ]; then
  echo "ERRO: semantic_route_summary.py não encontrado!"
  exit 1
fi


# ============================
# HEADER
# ============================

echo "==============================================="
echo "  GERADOR DE DESCRIÇÃO SEMÂNTICA (PARALELO)   "
echo "==============================================="
echo "Raiz:      $ROOT_DIR"
echo "Destino:   $OUT_DIR"
echo


# ============================
# LOCALIZAR ARQUIVOS DE ROTA
# ============================

echo "Localizando rotas Camel..."

ROUTES_TMP="$(mktemp)"

find "$ROOT_DIR" -type f -path "*/infrastructure/*" \
  \( -name "*Route.java" -o -name "*Router.java" -o -name "*Ruta.java" \) \
  > "$ROUTES_TMP"

TOTAL=$(wc -l < "$ROUTES_TMP" | tr -d ' ')

if [ "$TOTAL" -eq 0 ]; then
  echo "Nenhuma rota encontrada."
  rm -f "$ROUTES_TMP"
  exit 0
fi

echo "Encontradas $TOTAL rotas."
echo


# ============================
# PROCESSAMENTO PARALELO
# ============================

process_file() {
  FILE="$1"

  # ignorar arquivos que não são rotas com RouteBuilder
  if ! grep -q "extends RouteBuilder" "$FILE"; then
    echo "[IGNORADO] $FILE (não contém extends RouteBuilder)"
    exit 0
  fi

  # caminho relativo
  FILE_REL="${FILE#$ROOT_DIR/}"

  # remove prefixo coopeuch-migracion-
  FILE_REL="${FILE_REL//$REMOVE_PREFIX/}"

  # transformar path em nome seguro
  SAFE_NAME=$(echo "$FILE_REL" | sed 's#/#__#g')

  OUT_FILE="${OUT_DIR}/${SAFE_NAME%.java}.json"

  # ============================
  # NOVA REGRA:
  # Se o JSON já existe → ignorar
  # ============================
  if [ -f "$OUT_FILE" ]; then
    echo "[PULADA] $FILE → $OUT_FILE (já existe)"
    exit 0
  fi

  echo "[PROCESSANDO] $FILE → $OUT_FILE"

  if python3 "$SEMANTIC_PY" "$FILE" > "$OUT_FILE"; then
    echo "[OK] $OUT_FILE"
  else
    echo "[ERRO] Falha ao processar: $FILE"
  fi
}

export ROOT_DIR OUT_DIR REMOVE_PREFIX SEMANTIC_PY
export -f process_file

echo "Iniciando processamento paralelo..."

# -P 8 = processar até 8 rotas simultaneamente
cat "$ROUTES_TMP" | xargs -I {} -P 8 bash -c 'process_file "$@"' _ {}

echo
echo "==============================================="
echo "Processamento concluído!"
echo "JSONs gerados em: $OUT_DIR/"
echo "==============================================="

rm -f "$ROUTES_TMP"

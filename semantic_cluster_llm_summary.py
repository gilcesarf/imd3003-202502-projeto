import os
import json
from pathlib import Path
from collections import defaultdict
from typing import List

import pandas as pd
import requests

# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

BASE_ARTIFACTS_DIR = Path("semantic_artifacts")
CLUSTERS_FILE = BASE_ARTIFACTS_DIR / "clusters_final.parquet"

OUTPUT_ROOT = BASE_ARTIFACTS_DIR / "cluster_llm_analysis"

#TEST_ONLY_CLUSTER = "S8.2"   # None para rodar todos
TEST_ONLY_CLUSTER = None   # None para rodar todos

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

ENCODING = "utf-8"
REQUEST_TIMEOUT = 900

BATCH_SIZE = 10
MAX_ATTEMPTS_PER_BATCH = 3
FINAL_GROUP_SIZE = 5   # consolidação hierárquica

# ============================================================
# PROMPTS
# ============================================================

BATCH_PROMPT = """
Analise as descrições semânticas abaixo, todas pertencentes ao MESMO cluster
de rotas Apache Camel.

Objetivo:
- Identificar padrões arquiteturais e funcionais COMUNS
- Ignorar detalhes de rotas individuais
- Usar vocabulário técnico de integração (Camel, EIP, síncrono/assíncrono)

Formato OBRIGATÓRIO da resposta:

PARAGRAFO:
<1 parágrafo com 3 a 6 frases>

BULLETS:
- bullet técnico 1
- bullet técnico 2
- bullet técnico 3

NÃO use JSON.
NÃO use Markdown.
NÃO adicione explicações fora do formato.

Rotas analisadas (forma compacta):
"""

FINAL_PROMPT = """
Abaixo estão textos referentes a subconjuntos de rotas
do MESMO cluster Apache Camel.

Consolide essas informações eliminando redundâncias
e mantendo apenas padrões comuns.

Formato OBRIGATÓRIO da resposta:

PARAGRAFO:
<1 parágrafo com 3 a 6 frases>

BULLETS:
- bullet técnico 1
- bullet técnico 2
- bullet técnico 3

Textos:
"""

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def call_ollama(prompt: str) -> str:
    resp = requests.post(
        OLLAMA_HOST.rstrip("/") + "/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def is_valid_output(text: str) -> bool:
    return (
        text.startswith("PARAGRAFO:") and
        "\n\nBULLETS:\n-" in text
    )


def compact_route(route: dict) -> dict:
    return {
        "patterns": route.get("patterns_detected", [])[:5],
        "components": route.get("components_used", [])[:5],
        "endpoints": route.get("endpoints_called", [])[:5],
        "error_handling": route.get("error_handling", "")[:200],
        "fingerprint": route.get("fingerprint", "")[:120]
    }


def chunk_list(items: List[str], size: int) -> List[List[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]

# ============================================================
# PIPELINE PRINCIPAL
# ============================================================

def main():
    print("▶ Carregando clusters...")
    df = pd.read_parquet(CLUSTERS_FILE)

    clusters = defaultdict(list)
    for _, r in df.iterrows():
        with open(r["path"], encoding=ENCODING) as f:
            clusters[r["cluster_label"]].append(json.load(f))

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for cluster_label, routes in clusters.items():
        if TEST_ONLY_CLUSTER and cluster_label != TEST_ONLY_CLUSTER:
            continue

        print(f"\n▶ Cluster {cluster_label} ({len(routes)} rotas)")
        cluster_dir = OUTPUT_ROOT / f"cluster_{cluster_label}"
        cluster_dir.mkdir(parents=True, exist_ok=True)

        state_file = cluster_dir / "state.json"
        state = json.load(open(state_file)) if state_file.exists() else {}

        compact_routes = [compact_route(r) for r in routes]

        batches = chunk_list(compact_routes, BATCH_SIZE)
        total_batches = len(batches)

        pending = False

        # ====================================================
        # ETAPA 1 — PROCESSAMENTO DOS LOTES
        # ====================================================

        for idx, batch in enumerate(batches, 1):
            batch_id = f"{idx:03d}"

            ok_file = cluster_dir / f"batch_{batch_id}.ok.txt"
            manual_file = cluster_dir / f"batch_{batch_id}.manual.txt"
            error_file = cluster_dir / f"batch_{batch_id}.error.txt"

            if ok_file.exists() or manual_file.exists():
                print(f"  ✔ Lote {idx:03d}/{total_batches:03d} já resolvido")
                continue

            attempts = state.get(batch_id, 0)
            if attempts >= MAX_ATTEMPTS_PER_BATCH:
                print(f"  ✖ Lote {idx:03d}/{total_batches:03d} requer revisão manual")
                pending = True
                continue

            print(f"  → Lote {idx:03d}/{total_batches:03d} (tentativa {attempts + 1})")

            prompt = BATCH_PROMPT + json.dumps(batch, ensure_ascii=False, indent=2)

            try:
                output = call_ollama(prompt)
                if is_valid_output(output):
                    ok_file.write_text(output, encoding=ENCODING)
                else:
                    raise ValueError("Formato inválido")
            except Exception as e:
                state[batch_id] = attempts + 1
                error_file.write_text(
                    f"ERRO: {e}\n\n{output if 'output' in locals() else ''}",
                    encoding=ENCODING
                )
                pending = True

        json.dump(state, open(state_file, "w"), indent=2)

        if pending:
            print("\n⛔ Execução interrompida.")
            print("➡ Existem lotes pendentes ou inválidos.")
            print("➡ Corrija *.manual.txt e execute novamente.")
            return

        # ====================================================
        # ETAPA 2 — CONSOLIDAÇÃO HIERÁRQUICA
        # ====================================================

        print("\n▶ Consolidação hierárquica...")

        batch_texts = []
        for idx in range(1, total_batches + 1):
            batch_id = f"{idx:03d}"
            file = cluster_dir / f"batch_{batch_id}.ok.txt"
            if not file.exists():
                file = cluster_dir / f"batch_{batch_id}.manual.txt"
            batch_texts.append(file.read_text(encoding=ENCODING))

        intermediate_groups = chunk_list(batch_texts, FINAL_GROUP_SIZE)
        intermediate_texts = []

        for i, group in enumerate(intermediate_groups, 1):
            print(f"  → Consolidação intermediária {i}/{len(intermediate_groups)}")
            prompt = FINAL_PROMPT + "\n\n".join(group)
            text = call_ollama(prompt)
            intermediate_file = cluster_dir / f"final_intermediate_{i:02d}.txt"
            intermediate_file.write_text(text, encoding=ENCODING)
            intermediate_texts.append(text)

        print("  → Consolidação final")
        final_prompt = FINAL_PROMPT + "\n\n".join(intermediate_texts)
        final_text = call_ollama(final_prompt)

        cluster_dir.joinpath("final_summary.txt").write_text(
            final_text, encoding=ENCODING
        )

        print("✔ Cluster consolidado com sucesso.")


if __name__ == "__main__":
    main()

import os
import json
import torch
import numpy as np
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer

# ============================================
# CONFIGURAÇÃO
# ============================================

SEMANTIC_DIR = "./semantic"
OUT_CSV = "./embeddings.csv"
MAX_WORKERS = 8   # paralelização
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # modelo recomendado

# Detecta GPU MPS (Apple Silicon)
device = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"🔥 Carregando modelo: {MODEL_NAME}")
print(f"🎛 Device: {device}")

model = SentenceTransformer(MODEL_NAME, device=device)
EMBED_DIM = model.get_sentence_embedding_dimension()

print(f"📏 Dimensão do embedding: {EMBED_DIM}")


# ============================================
# FUNÇÃO: normalização L2
# ============================================

def normalize(vec):
    v = np.array(vec, dtype=float)
    norm = np.linalg.norm(v)
    return (v / norm).tolist() if norm > 0 else v.tolist()


# ============================================
# FUNÇÃO: gerar embedding para um JSON
# ============================================

def generate_embedding(json_path: str):
    """Lê o JSON, gera embedding via SentenceTransformer e normaliza."""

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": f"Erro ao ler JSON: {e}", "path": json_path}

    route_id = data.get("route_id", "")

    # texto base → usamos o JSON inteiro como string
    input_text = json.dumps(data, ensure_ascii=False)

    try:
        emb = model.encode(input_text, convert_to_numpy=True)
        emb_norm = normalize(emb)

        return {
            "route_id": route_id,
            "path": json_path,
            "embedding": emb_norm,
            "error": None
        }
    except Exception as e:
        return {"error": str(e), "path": json_path}


# ============================================
# FUNÇÃO PRINCIPAL
# ============================================

def main():
    print("⏳ Localizando arquivos JSON em:", SEMANTIC_DIR)

    json_files = [
        os.path.join(SEMANTIC_DIR, f)
        for f in os.listdir(SEMANTIC_DIR)
        if f.endswith(".json")
    ]

    print(f"📦 Encontrados {len(json_files)} arquivos semânticos.")
    print("🚀 Gerando embeddings em paralelo...\n")

    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(generate_embedding, path): path
            for path in json_files
        }

        for future in tqdm(as_completed(futures), total=len(futures)):
            results.append(future.result())

    print("\n📊 Convertendo para DataFrame...")

    df = pd.DataFrame(results)

    print("💾 Salvando embeddings normalizados em:", OUT_CSV)
    df.to_csv(OUT_CSV, index=False)

    print("\n📊 Shape do DataFrame:", df.shape)

    # Encontrar o primeiro embedding válido
    valid_vectors = df[df["error"].isna()]["embedding"]
    if len(valid_vectors) > 0:
        print("📏 Dimensão do primeiro embedding válido:", len(valid_vectors.iloc[0]))
    else:
        print("⚠ Nenhum embedding válido encontrado.")

    print("\n✅ Processamento concluído!")
    print(f"Arquivo salvo: {OUT_CSV}")


if __name__ == "__main__":
    main()

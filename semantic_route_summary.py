import argparse
import json
import os
import re
import sys

import requests

PROMPT_TEMPLATE = """
Analise a rota Camel Java DSL a seguir e gere uma descrição SEMÂNTICA estruturada, NÃO sintática.

Transforme o código em uma representação conceitual concisa, adequada para geração de embeddings e clusterização de rotas.

Siga estritamente este JSON:

{{
  "route_id": "",
  "route_start": "",
  "components_used": [],
  "patterns_detected": [],
  "flow_summary": [],
  "transformations": [],
  "endpoints_called": [],
  "internal_beans": [],
  "error_handling": "",
  "fingerprint": ""
}}

REGRAS:
- Responda SOMENTE o JSON, sem texto adicional.
- Toda a saida deve ser em Português Brasileiro.
- Descreva intenção, não sintaxe.
- Identifique padrões EIP (ex: request-response, content-based-router, error-policy, transformation pipeline).
- Capture o papel arquitetural da rota.
- Resuma o fluxo em 5–10 passos conceituais.
- Liste componentes Camel usados.
- Liste endpoints externos chamados.
- Liste beans internos usados.
- Descreva como exceções são manejadas.
- Gere uma fingerprint curta: "origem → transformação A → backend X → transformação B → saída".

Agora processe a rota abaixo:

```java
{route_code}
```
"""


def build_prompt(route_code: str) -> str:
    return PROMPT_TEMPLATE.format(route_code=route_code)


def call_ollama(prompt: str, model: str, host: str) -> str:
    url = host.rstrip('/') + '/api/generate'
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
    }
    resp = requests.post(url, json=payload, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data.get('response', '')


def extract_json(raw: str) -> dict:
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        raise ValueError('Nenhum JSON válido encontrado na resposta do modelo.')

    return json.loads(match.group(0))


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Gera descrição semântica estruturada de uma rota Camel Java DSL usando Ollama.'
    )
    parser.add_argument(
        'java_file',
        help='Caminho para o arquivo .java contendo a rota Camel Java DSL',
    )
    parser.add_argument(
        '--model',
        default=os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b'),
        help='Nome do modelo do Ollama (default: qwen2.5:7b ou OLLAMA_MODEL)',
    )
    parser.add_argument(
        '--host',
        default=os.environ.get('OLLAMA_HOST', 'http://localhost:11434'),
        help='Host da API do Ollama (default: http://localhost:11434 ou OLLAMA_HOST)',
    )

    args = parser.parse_args()

    try:
        with open(args.java_file, 'r', encoding='utf-8') as f:
            route_code = f.read()
    except OSError as e:
        print(f'ERRO: não foi possível ler o arquivo {args.java_file}: {e}', file=sys.stderr)
        sys.exit(1)

    prompt = build_prompt(route_code)

    try:
        raw_output = call_ollama(prompt, args.model, args.host)
    except requests.RequestException as e:
        print(f'ERRO: falha ao chamar a API do Ollama: {e}', file=sys.stderr)
        sys.exit(1)

    try:
        route_json = extract_json(raw_output)
    except Exception as e:
        print(f'ERRO: falha ao interpretar a resposta como JSON: {e}', file=sys.stderr)
        print(raw_output)
        sys.exit(2)

    json.dump(route_json, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()

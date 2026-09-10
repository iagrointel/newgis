"""Testa por HTTP as URLs de referência de `docs/urls_paridade.txt` (item L6-03-paridade-conectores) e grava
`tests/medidas/L6-03-paridade-conectores.json` com o código de cada uma na data — o portão diz "URLs testadas
(200) na data". Não usa a defesa de SSRF da aplicação de propósito: são páginas de documentação de terceiros,
lidas com `httpx` puro, cabeçalho de navegador (a doc da Esri devolve 403 a agentes vazios) e sem seguir mais
que 5 redirecionamentos. Uso: `venv/bin/python scripts/paridade_urls_testar.py`; sai com 1 se alguma não deu 200."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
from app.versao import git_sha_curto  # noqa: E402

ITEM = "L6-03-paridade-conectores"
ORIGEM = RAIZ / "docs" / "urls_paridade.txt"
DESTINO = RAIZ / "tests" / "medidas" / f"{ITEM}.json"
CABECALHOS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) plataforma-paridade/1.0", "Accept": "text/html,*/*"}


def ler_urls(caminho: Path = ORIGEM) -> list[tuple[str, str]]:
    saida = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        chave, url = linha.split("\t", 1)
        saida.append((chave.strip(), url.strip()))
    return saida


def main() -> int:
    urls = ler_urls()
    resultados = []
    with httpx.Client(headers=CABECALHOS, timeout=30, follow_redirects=True, max_redirects=5) as c:
        for chave, url in urls:
            try:
                r = c.get(url)
                codigo, final = r.status_code, str(r.url)
            except httpx.HTTPError as e:
                codigo, final = None, f"erro: {type(e).__name__}"
            resultados.append({"chave": chave, "url": url, "http": codigo, "url_final": final})
            print(f"{codigo!s:>4} {chave:22} {url}")
    agora = datetime.datetime.now(datetime.UTC)
    ok = [r for r in resultados if r["http"] == 200]
    comando = "venv/bin/python scripts/paridade_urls_testar.py (GET com httpx, até 5 redirecionamentos)"
    dados = {"item": ITEM, "medidas": {}}
    if DESTINO.exists():
        dados = json.loads(DESTINO.read_text(encoding="utf-8"))
    dados["medidas"]["urls_referencia"] = {"valor": len(urls), "unidade": "URLs", "comando": comando}
    dados["medidas"]["urls_200_na_data"] = {"valor": len(ok), "unidade": "URLs", "comando": comando}
    dados["urls"] = resultados
    dados["gerado_em"] = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
    dados["git_sha"] = git_sha_curto()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(ok)} de {len(urls)} com 200 -> {DESTINO}")
    return 0 if len(ok) == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main())

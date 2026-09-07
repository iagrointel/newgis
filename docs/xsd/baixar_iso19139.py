"""Baixa e põe em cache local a árvore de XSD do perfil ISO 19139 hospedado em schemas.opengis.net (revisão
2007-04-17, a mesma que GeoNetwork/INDE usam para o schema "iso19139") — item L0-09-metadado-catalogo.

Por que baixar em vez de validar contra a URL remota a cada chamada: a validação de `GET /api/itens/{id}/
metadado.xml` roda a cada requisição (app/catalogo/metadado.py); depender de rede ali violaria o portão P5
(reprodutível, nada manual fora de script) e acrescentaria latência e um ponto de falha externo a uma rota
interna. O cache é reescrito para ser AUTOSSUFICIENTE: todo atributo `schemaLocation` absoluto (http:// ou
https://, `schemas.opengis.net`, `www.w3.org`) é reescrito para caminho relativo dentro do próprio cache antes
de gravar — depois de rodado este script, `app/catalogo/metadado.py` nunca mais toca a rede para validar.

Idempotente: pula arquivo já presente no cache, a menos que --forcar. Cada execução (mesmo sem baixar nada
novo) reescreve `MANIFESTO.json` com sha256 e data de acesso do que está no disco.

Uso: venv/bin/python docs/xsd/baixar_iso19139.py [--forcar]
"""

import argparse
import collections
import datetime
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

RAIZ = Path(__file__).resolve().parent
CACHE = RAIZ / "cache"
MANIFESTO = CACHE / "MANIFESTO.json"
SEMENTES = ("https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd",)
SCHEMA_LOCATION = re.compile(r'schemaLocation\s*=\s*"([^"]+)"')
TIMEOUT_S = 20


def chave(url: str) -> str:
    """netloc+path, sem esquema (http e https do mesmo host são o MESMO arquivo — a árvore real mistura os dois:
    gmd.xsd é servido por https, mas importa o resto por http:// absoluto)."""
    p = urlparse(url)
    return f"{p.netloc}{p.path}"


def caminho_local(url: str) -> Path:
    return CACHE / chave(url)


def relativo(de_url: str, para_url: str) -> str:
    import os

    de = caminho_local(de_url).parent
    para = caminho_local(para_url)
    return os.path.relpath(para, de)


def buscar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "iAgroIntel-plataforma-enterprise/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - URL fixa do OGC, só neste script
        return r.read()


def baixar(forcar: bool) -> dict:
    fila = collections.deque(SEMENTES)
    vistos: set[str] = set()
    conteudo: dict[str, bytes] = {}
    origem_url: dict[str, str] = {}
    while fila:
        url = fila.popleft()
        k = chave(url)
        if k in vistos:
            continue
        vistos.add(k)
        origem_url[k] = url
        destino = CACHE / k
        if destino.exists() and not forcar:
            dados = destino.read_bytes()
        else:
            try:
                dados = buscar(url)
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"ERRO baixando {url}: {e}", file=sys.stderr)
                raise
            print(f"baixado: {url} ({len(dados)} bytes)")
        conteudo[k] = dados
        for m in SCHEMA_LOCATION.finditer(dados.decode("utf-8", "replace")):
            loc = m.group(1)
            if loc.startswith("http://") or loc.startswith("https://"):
                alvo_url = loc
            elif loc.startswith("../") or "/" in loc or loc.endswith(".xsd"):
                # cache JÁ reescrito (2ª execução em diante): a referência relativa aponta para outro
                # arquivo do PRÓPRIO cache — resolver urljoin contra a URL de origem compõe um endereço
                # falso (https://schemas.opengis.net/www.w3.org/1999/xlink.xsd, 404 medido em 07/09 e o
                # install.sh morria aqui). Se o arquivo local existe, nada a baixar.
                alvo_local = (destino.parent / loc).resolve()
                if str(alvo_local).startswith(str(CACHE.resolve())) and alvo_local.exists():
                    continue
                alvo_url = urljoin(url, loc)
            else:
                continue
            if chave(alvo_url) not in vistos:
                fila.append(alvo_url)
    # reescreve todo schemaLocation absoluto para caminho relativo dentro do cache (autossuficiente, sem rede)
    saida: dict[str, bytes] = {}
    for k, dados in conteudo.items():
        url = origem_url[k]
        texto = dados.decode("utf-8", "replace")

        def _troca(m, url=url):
            loc = m.group(1)
            if loc.startswith("http://") or loc.startswith("https://"):
                novo = relativo(url, loc)
                return f'schemaLocation="{novo}"'
            return m.group(0)

        texto2 = SCHEMA_LOCATION.sub(_troca, texto)
        saida[k] = texto2.encode("utf-8")
    for k, dados in saida.items():
        destino = CACHE / k
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
    return {k: origem_url[k] for k in saida}


def gravar_manifesto(mapa_url: dict[str, str]) -> None:
    agora = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # o manifesto cobre TODO o cache (rglob), não só o que esta execução baixou/leu: numa execução
    # idempotente (cache completo) quase nada passa pela fila, e o manifesto encolheria a cada run —
    # medido 07/09: 57 arquivos viraram 1. url_origem vem desta execução ou do manifesto anterior;
    # arquivo sem origem conhecida nas duas fontes fica de fora (URL nunca se inventa).
    antigo: dict[str, str] = {}
    if MANIFESTO.exists():
        try:
            antigo = {
                i["arquivo"]: i["url_origem"]
                for i in json.loads(MANIFESTO.read_text(encoding="utf-8"))["arquivos"]
            }
        except (json.JSONDecodeError, KeyError, TypeError):
            antigo = {}
    itens = []
    for caminho in sorted(CACHE.rglob("*.xsd")):
        k = str(caminho.relative_to(CACHE))
        url = mapa_url.get(k) or antigo.get(k)
        if not url:
            continue
        dados = caminho.read_bytes()
        itens.append(
            {
                "arquivo": k,
                "url_origem": url,
                "sha256": hashlib.sha256(dados).hexdigest(),
                "bytes": len(dados),
            }
        )
    MANIFESTO.write_text(
        json.dumps(
            {
                "gerado_em": agora,
                "entrada": chave(SEMENTES[0]),
                "perfil": "ISO 19139 (schemas.opengis.net, revisão 2007-04-17) — o que GeoNetwork/INDE chamam de "
                "schema iso19139; usado pelo Perfil MGB 2.0 (D17)",
                "arquivos": itens,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"MANIFESTO.json: {len(itens)} arquivos")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true", help="rebaixa mesmo o que já está em cache")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    mapa = baixar(args.forcar)
    gravar_manifesto(mapa)


if __name__ == "__main__":
    main()

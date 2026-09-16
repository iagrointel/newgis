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

Uso: venv/bin/python docs/xsd/baixar_iso19139.py [--perfil iso19139|wfs20|iso19115-3] [--forcar]

Perfis (mesma mecânica, sementes diferentes; o manifesto acumula todos): `iso19139` (metadado do
catálogo, L0-09) e `wfs20` (WFS 2.0/1.1 + FES 2.0 + OWS + GML, para validar a saída XML do
item L2-04-h sem tocar a rede em teste) e `iso19115-3` (mdb:MD_Metadata, L0-09 cláusula 2/D42;
reaproveita a árvore GML 3.2 do `wfs20` porque o import de GML do pacote `gmw` do 19115-3 aponta
para uma URL do ISO que nunca respondeu — ver REDIRECIONAMENTOS abaixo).
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
PERFIS = {
    "iso19139": {
        "sementes": ("https://schemas.opengis.net/iso/19139/20070417/gmd/gmd.xsd",),
        "descricao": "ISO 19139 (schemas.opengis.net, revisão 2007-04-17) — o que GeoNetwork/INDE chamam de "
        "schema iso19139; usado pelo Perfil MGB 2.0 (D17)",
    },
    "wfs20": {
        "sementes": (
            "https://schemas.opengis.net/wfs/2.0/wfs.xsd",
            "https://schemas.opengis.net/wfs/1.1.0/wfs.xsd",
        ),
        "descricao": "WFS 2.0.0 (OGC 09-025r2) e WFS 1.1.0, com as árvores que eles importam "
        "(FES 2.0, OWS 1.1/1.0, GML 3.2.1 e 3.1.1) — validação do GetCapabilities/GetFeature do "
        "item L2-04-h, sempre offline",
    },
    "iso19115-3": {
        "sementes": (
            "https://standards.iso.org/iso/19115/-3/mdb/2.0/mdb.xsd",
            "https://standards.iso.org/iso/19115/-3/cit/2.0/cit.xsd",
            "https://standards.iso.org/iso/19115/-3/gco/1.0/gco.xsd",
            "https://standards.iso.org/iso/19115/-3/gex/1.0/gex.xsd",
            "https://standards.iso.org/iso/19115/-3/lan/1.0/lan.xsd",
            "https://standards.iso.org/iso/19115/-3/mcc/1.0/mcc.xsd",
            "https://standards.iso.org/iso/19115/-3/mri/1.0/mri.xsd",
            "https://standards.iso.org/iso/19115/-3/mrs/1.0/mrs.xsd",
            "https://standards.iso.org/iso/19115/-3/msr/1.0/msr.xsd",
            "https://standards.iso.org/iso/19115/-3/mmi/1.0/mmi.xsd",
            "https://standards.iso.org/iso/19115/-3/mco/1.0/mco.xsd",
            "https://standards.iso.org/iso/19115/-3/mrd/1.0/mrd.xsd",
            "https://standards.iso.org/iso/19157/-2/mdq/1.0/mdq.xsd",
            "https://standards.iso.org/iso/19115/-3/mrl/2.0/mrl.xsd",
        ),
        "descricao": "ISO 19115-3 (mdb:MD_Metadata, XML Schema Implementation, standards.iso.org) — L0-09 "
        "cláusula 2 (D42); sementes = mdb (base) + cit/gco/gex/lan/mcc (comuns) + mri (identificação) + "
        "mrs (sistema de referência) + msr (representação espacial) + mmi (manutenção) + mco (restrições/"
        "licença) + mrd (distribuição) + 19157-2/mdq (qualidade) + mrl (linhagem); dqc (19157-2), gcx e a "
        "árvore GML 3.2 (gmw:*) entram por import transitivo. Ver REDIRECIONAMENTOS: o espelho oficial do "
        "GML citado por gmw (standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19136_Schemas/gml.xsd) "
        "responde 404 (medido 16/09/2026) — reaproveita a árvore GML 3.2.1 já cacheada pelo perfil wfs20 "
        "em vez de inventar conteúdo (é o mesmo schema, hospedado pelo OGC).",
    },
}
SEMENTES = PERFIS["iso19139"]["sementes"]
SCHEMA_LOCATION = re.compile(r'schemaLocation\s*=\s*"([^"]+)"')
COMENTARIO_XML = re.compile(r"<!--.*?-->", re.S)
# `extent.xsd` (gex 1.0) traz um <import> de `19111/rce/1.0/rce.xsd` DENTRO de um comentário XML (nunca usado
# por nenhum tipo do arquivo — conferido: nenhuma referência "rce:" fora do comentário) e essa URL nunca foi
# publicada pelo ISO (404 medido nos 6 caminhos plausíveis em 16/09/2026). Sem tirar comentário antes de
# procurar schemaLocation, o rastreador tentava baixar um import morto que nem o validador real (libxml2)
# precisa resolver. Ler o texto sem comentário SÓ decide o que entra na fila; o arquivo gravado no cache
# continua sendo o texto oficial completo, comentário incluído.
REDIRECIONAMENTOS = {
    # standards.iso.org/ittf/.../ISO_19136_Schemas/gml.xsd: import ATIVO (não comentado) em gmw.xsd
    # (19115-3), usado por gex/mri/msr/mdq — e nunca respondeu (404 medido nos dois esquemas em 16/09/2026).
    # GML 3.2 é o MESMO schema (OGC 07-036) que o perfil wfs20 já baixa de schemas.opengis.net; redirecionar
    # para lá evita rede extra e evita inventar conteúdo para uma URL que o ISO nunca publicou.
    "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19136_Schemas/gml.xsd":
        "https://schemas.opengis.net/gml/3.2.1/gml.xsd",
    "https://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19136_Schemas/gml.xsd":
        "https://schemas.opengis.net/gml/3.2.1/gml.xsd",
}
TIMEOUT_S = 20


def redirecionar(url: str) -> str:
    return REDIRECIONAMENTOS.get(url, url)


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


def baixar(forcar: bool, sementes: tuple[str, ...] = SEMENTES) -> dict:
    fila = collections.deque(sementes)
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
        texto_sem_comentario = COMENTARIO_XML.sub("", dados.decode("utf-8", "replace"))
        for m in SCHEMA_LOCATION.finditer(texto_sem_comentario):
            loc = m.group(1)
            if loc.startswith("http://") or loc.startswith("https://"):
                alvo_url = redirecionar(loc)
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
                novo = relativo(url, redirecionar(loc))
                return f'schemaLocation="{novo}"'
            return m.group(0)

        texto2 = SCHEMA_LOCATION.sub(_troca, texto)
        saida[k] = texto2.encode("utf-8")
    for k, dados in saida.items():
        destino = CACHE / k
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
    return {k: origem_url[k] for k in saida}


def gravar_manifesto(mapa_url: dict[str, str], perfil: str = "iso19139") -> None:
    agora = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # o manifesto cobre o cache inteiro (rglob), não só o que esta execução baixou/leu: numa execução
    # idempotente (cache completo) quase nada passa pela fila, e o manifesto encolheria a cada run —
    # medido 07/09: 57 arquivos viraram 1. url_origem vem desta execução ou do manifesto anterior;
    # arquivo sem origem conhecida nas duas fontes fica de fora (URL nunca se inventa).
    antigo: dict[str, str] = {}
    perfis_antigos: dict[str, dict] = {}
    if MANIFESTO.exists():
        try:
            anterior = json.loads(MANIFESTO.read_text(encoding="utf-8"))
            antigo = {i["arquivo"]: i["url_origem"] for i in anterior["arquivos"]}
            perfis_antigos = dict(anterior.get("perfis") or {})
        except (json.JSONDecodeError, KeyError, TypeError):
            antigo = {}
            perfis_antigos = {}
    perfis = dict(perfis_antigos)
    perfis[perfil] = {
        "entradas": [chave(u) for u in PERFIS[perfil]["sementes"]],
        "descricao": PERFIS[perfil]["descricao"],
    }
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
                "perfis": perfis,
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
    ap.add_argument("--perfil", choices=sorted(PERFIS), default="iso19139",
                    help="qual árvore de XSD baixar (o manifesto acumula os perfis já baixados)")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    mapa = baixar(args.forcar, PERFIS[args.perfil]["sementes"])
    gravar_manifesto(mapa, args.perfil)


if __name__ == "__main__":
    main()

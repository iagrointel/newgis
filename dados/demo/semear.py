"""Semeadura do pacote de dado de demonstração (item L7-01-c-dado-demonstracao).

Reusa o desenho do item L0-13-dado-demonstracao (mesma casa, ramo `wt/t13`, ainda não integrado):
entra como administrador do inquilino, sobe cada arquivo pela própria API (POST /api/arquivos),
registra o item (POST /api/itens), pede a importação quando o arquivo é uma camada vetorial
(POST /api/importacoes) e espera o job de carga. Nada é escrito direto no banco e nada é baixado
da rede em tempo de instalação: os arquivos e a proveniência de cada um vêm de
`dados/demo/catalogo.json`, comitado no repositório.

Além dos arquivos, semeia as QUATRO peças que o item pede e o L0-13 não tinha: 1 mapa (compõe as
camadas do IBGE), 1 painel (indicador sobre a camada do INMET), 1 formulário (ficha de campo, sem
dado nenhum atrás) e 1 rede (nós + arestas = o grafo de vias do OpenStreetMap recém-carregado —
é um grafo de verdade, não uma rede elétrica/hídrica: o resumo do item já diz isso).

Idempotente: reconhece o que já semeou pelo título do item dentro do inquilino (inclusive na
lixeira) e só cria o que falta. Rodar duas vezes não duplica nada.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import httpx

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def gerar_ulid() -> str:
    """Mesmo formato de app/catalogo/documento.py::gerar_ulid (ULID_RE), duplicado aqui de propósito:
    este script fala com a plataforma só por HTTP e nunca importa app.* (evita arrastar app.settings,
    que exige PLAT_DSN mesmo fora de um processo de servidor)."""
    ts = int(time.time() * 1000) & ((1 << 48) - 1)
    valor = (ts << 80) | int.from_bytes(os.urandom(10), "big")
    caracteres = []
    for _ in range(26):
        caracteres.append(_CROCKFORD[valor & 0x1F])
        valor >>= 5
    return "".join(reversed(caracteres))


RAIZ = Path(__file__).resolve().parents[2]
DIR_DEMO = RAIZ / "dados" / "demo"
CATALOGO = DIR_DEMO / "catalogo.json"
ARQUIVOS = DIR_DEMO / "arquivos"
TOKEN_NOME = "semente-dado-demo-l7"
ESPERA_JOB_S = 180.0

CATEGORIAS_DEMO = [
    "Limites administrativos",
    "Transporte",
    "Recursos hídricos",
    "Clima",
    "Sensoriamento remoto",
    "Demonstração",
]

TITULO_MAPA = "Mapa de demonstração — limites e rodovias (Amapá e Roraima)"
TITULO_PAINEL = "Painel de demonstração — estações do INMET na região Norte"
TITULO_FORMULARIO = "Formulário de demonstração — ficha de visita de campo"
TITULO_REDE = "Rede de demonstração — grafo de vias de Fernando de Noronha (OSM)"


class Erro(RuntimeError):
    pass


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def carregar_catalogo() -> dict:
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


def credenciais(caminho: Path) -> dict[str, tuple[str, str]]:
    saida: dict[str, tuple[str, str]] = {}
    if not caminho.exists():
        raise Erro(f"arquivo de credenciais inexistente: {caminho} (rode o install.sh ou semeie os admins de teste)")
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) >= 3:
            saida[partes[0]] = (partes[1], " ".join(partes[2:]))
    return saida


class Cliente:
    """Sessão de administrador de um inquilino, com um token de serviço para o envio de arquivo (o
    upload manda bytes crus, que a defesa de CSRF sob cookie recusa por não ser application/json)."""

    def __init__(self, base_url: str, slug: str, login: str, senha: str, verboso: bool = True):
        self.slug = slug
        self.verboso = verboso
        self.http = httpx.Client(base_url=base_url.rstrip("/"), timeout=120.0)
        self.http_token = httpx.Client(base_url=base_url.rstrip("/"), timeout=300.0)
        r = self.http.post("/api/login", json={"inquilino": slug, "login": login, "senha": senha})
        if r.status_code != 200 or not r.json().get("ok"):
            raise Erro(f"login de {slug} falhou: {r.status_code} {r.text[:300]}")
        if r.json().get("exige_2fa"):
            raise Erro(f"o administrador de {slug} exige 2FA; a semeadura só cobre os inquilinos de demonstração")
        self._token: str | None = None
        self._token_id: str | None = None

    def fechar(self) -> None:
        if self._token_id:
            self.http.delete(f"/api/tokens/{self._token_id}")
            self._token_id = None
        self.http.close()
        self.http_token.close()

    def token(self) -> str:
        if self._token is None:
            r = self.http.post("/api/tokens", json={"nome": TOKEN_NOME, "escopos": ["admin:inquilino"]})
            if r.status_code != 201:
                raise Erro(f"não criou token em {self.slug}: {r.status_code} {r.text[:300]}")
            self._token = r.json()["token"]
            self._token_id = r.json()["id"]
        return self._token

    def dizer(self, msg: str) -> None:
        if self.verboso:
            print(f"  [{self.slug}] {msg}", flush=True)

    def titulos(self) -> dict[str, str]:
        saida: dict[str, str] = {}
        for rota in ("/api/itens", "/api/lixeira"):
            deslocamento = 0
            while True:
                r = self.http.get(rota, params={"limite": 200, "deslocamento": deslocamento})
                if r.status_code != 200:
                    raise Erro(f"listagem de {rota} falhou: {r.status_code} {r.text[:300]}")
                corpo = r.json()
                for it in corpo["itens"]:
                    saida[it["titulo"]] = it["id"]
                deslocamento += len(corpo["itens"])
                if not corpo["itens"] or deslocamento >= corpo["total"]:
                    break
        return saida

    def categorias(self, nomes: list[str]) -> dict[str, str]:
        r = self.http.get("/api/categorias")
        if r.status_code != 200:
            raise Erro(f"leitura de categorias falhou: {r.status_code} {r.text[:300]}")
        arvore = r.json()["arvore"]
        existentes = {no["nome"]: no for no in arvore}
        faltam = [n for n in nomes if n not in existentes]
        if faltam:
            nova = [{"id": no["id"], "nome": no["nome"], "codigo": no.get("codigo"), "filhas": []} for no in arvore]
            nova += [{"nome": n, "filhas": []} for n in faltam]
            r = self.http.put("/api/categorias", json={"arvore": nova})
            if r.status_code != 200:
                raise Erro(f"gravação de categorias falhou: {r.status_code} {r.text[:300]}")
            arvore = r.json()["arvore"]
        return {no["nome"]: no["id"] for no in arvore}

    def enviar_arquivo(self, caminho: Path, classe: str) -> dict:
        dados = caminho.read_bytes()
        r = self.http_token.post(
            "/api/arquivos",
            params={"classe": classe},
            content=dados,
            headers={"authorization": f"Bearer {self.token()}", "content-type": "application/octet-stream"},
        )
        if r.status_code != 201:
            raise Erro(f"envio de {caminho.name} falhou: {r.status_code} {r.text[:300]}")
        return r.json()

    def criar_item(self, corpo: dict) -> str:
        r = self.http.post("/api/itens", json=corpo)
        if r.status_code != 201:
            raise Erro(f"criação do item {corpo['titulo']!r} falhou: {r.status_code} {r.text[:300]}")
        return r.json()["id"]

    def esperar_job(self, job_id: str) -> dict:
        fim = time.monotonic() + ESPERA_JOB_S
        ultimo = None
        while time.monotonic() < fim:
            r = self.http.get(f"/api/jobs/{job_id}")
            if r.status_code != 200:
                raise Erro(f"consulta do job {job_id} falhou: {r.status_code} {r.text[:300]}")
            ultimo = r.json()
            if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
                return ultimo
            time.sleep(0.3)
        raise Erro(f"job {job_id} não terminou em {ESPERA_JOB_S:.0f} s: {ultimo}")

    def importar(self, arquivo_item_id: str, formato: str, titulo: str, metadado: dict) -> str:
        r = self.http.post("/api/importacoes", json={"arquivo_id": arquivo_item_id, "formato": formato})
        if r.status_code != 202:
            raise Erro(f"importação de {titulo!r} recusada: {r.status_code} {r.text[:300]}")
        importacao_id = r.json()["importacao_id"]
        job = self.esperar_job(r.json()["job_id"])
        if job["estado"] != "concluido":
            raise Erro(f"inspeção de {titulo!r} falhou: {job.get('erro')}")
        r = self.http.get(f"/api/importacoes/{importacao_id}")
        proposta = r.json()["proposta"] or {}
        corpo: dict = {"titulo": titulo}
        perguntas = proposta.get("perguntas") or []
        if "crs" in perguntas:
            sugestao = (proposta.get("crs") or {}).get("sugestao") or 4674
            corpo["crs"] = {"srid": sugestao}
        if "codificacao" in perguntas:
            corpo["codificacao"] = {"valor": "UTF-8"}
        r = self.http.put(f"/api/importacoes/{importacao_id}/confirmar", json=corpo)
        if r.status_code != 202:
            raise Erro(f"confirmação de {titulo!r} recusada: {r.status_code} {r.text[:300]}")
        job = self.esperar_job(r.json()["job_id"])
        if job["estado"] != "concluido":
            raise Erro(f"carga de {titulo!r} falhou: {job.get('erro')}")
        r = self.http.get(f"/api/importacoes/{importacao_id}")
        final = r.json()
        if final["estado"] != "concluida":
            raise Erro(f"importação de {titulo!r} terminou em {final['estado']}: {final.get('erro')}")
        item_id = final["item_id"]
        r = self.http.patch(f"/api/itens/{item_id}", json=metadado)
        if r.status_code != 200:
            raise Erro(f"metadado da camada {titulo!r} falhou: {r.status_code} {r.text[:300]}")
        return item_id


def metadado_de(it: dict, categoria_id: str | None) -> dict:
    corpo = {
        "resumo": it["resumo"],
        "descricao": (
            f"Fonte: {it['fonte']} ({it['orgao']}).\n\n"
            f"Endereço: {it['url']}\n\n"
            f"Licença: {it['licenca']}\n\n"
            f"Data de acesso: {it['data_acesso']}\n\n"
            f"Arquivo de origem: `dados/demo/arquivos/{it['arquivo']}` (sha256 {it['sha256'][:16]}...)."
        ),
        "tags": it["tags"],
        "creditos": f"{it['orgao']} — {it['fonte']}",
        "termos_de_uso": it["licenca"],
        "origem": "hospedado",
        "url": it["url"],
    }
    if categoria_id:
        corpo["categorias"] = [categoria_id]
    return corpo


def semear_inquilino(base_url: str, slug: str, login: str, senha: str, itens: list[dict], verboso: bool = True) -> dict:
    cli = Cliente(base_url, slug, login, senha, verboso)
    try:
        criados = {"arquivo": 0, "camada": 0, "composicao": 0, "reaproveitados": 0}
        tempos: dict[str, float] = {}
        cats = cli.categorias(sorted({it["categoria"] for it in itens}))
        titulos = cli.titulos()
        ids_por_papel: dict[str, str] = {}
        for it in itens:
            t0 = time.monotonic()
            titulo_arquivo = f"{it['titulo']} (arquivo de origem)"
            meta = metadado_de(it, cats.get(it["categoria"]))
            if titulo_arquivo in titulos:
                arquivo_item = titulos[titulo_arquivo]
                criados["reaproveitados"] += 1
            else:
                obj = cli.enviar_arquivo(ARQUIVOS / it["arquivo"], "camada_arquivo" if it["ingerir"] else "objeto")
                corpo = dict(meta)
                corpo.update(
                    {
                        "tipo": "arquivo",
                        "titulo": titulo_arquivo,
                        "dados": {
                            "chave": obj["chave"],
                            "sha256": obj["sha256"],
                            "bytes": obj["bytes"],
                            "content_type": obj["content_type"],
                            "nome_original": it["arquivo"],
                        },
                    }
                )
                arquivo_item = cli.criar_item(corpo)
                criados["arquivo"] += 1
                cli.dizer(f"arquivo {it['arquivo']} ({obj['bytes']} bytes)")
            item_final = arquivo_item
            if it["ingerir"]:
                if it["titulo"] in titulos:
                    item_final = titulos[it["titulo"]]
                    criados["reaproveitados"] += 1
                else:
                    item_final = cli.importar(arquivo_item, it["formato"], it["titulo"], meta)
                    criados["camada"] += 1
                    cli.dizer(f"camada {it['titulo']!r} carregada pela ingestão")
            papel = it.get("papel")
            if papel:
                ids_por_papel[papel] = item_final
            tempos[it["arquivo"]] = round(time.monotonic() - t0, 2)
        if slug == "demo":
            criados["composicao"] += semear_composicoes(cli, titulos, ids_por_papel, cats)
        return {"inquilino": slug, **criados, "segundos_por_arquivo": tempos}
    finally:
        cli.fechar()


def semear_composicoes(
    cli: Cliente, titulos_iniciais: dict[str, str], ids_por_papel: dict[str, str], cats: dict[str, str]
) -> int:
    """As 4 peças que o item pede além dos arquivos: 1 mapa, 1 painel, 1 formulário, 1 rede."""
    titulos = dict(titulos_iniciais)
    titulos.update(cli.titulos())
    criadas = 0
    cat_demo = cats.get("Demonstração")

    if TITULO_MAPA not in titulos:
        corpo = {
            "titulo": TITULO_MAPA,
            "tipo": "mapa",
            "resumo": "Mapa de demonstração com as camadas do IBGE (limites e ponto municipal) e a "
            "rodovia federal de Roraima, semeado por plat demo semear.",
            "tags": ["demonstracao", "mapa"],
            "dados": {
                "esquema_versao": 1,
                "corpo": {
                    "camadas": [
                        {"titulo": t, "item_id": i}
                        for t, i in titulos.items()
                        if t
                        in (
                            "Limites municipais do Amapá e de Roraima",
                            "Ponto representativo dos municípios do Amapá e de Roraima",
                            "Rodovias federais de Roraima",
                        )
                    ],
                    "centro": [-61.5, 2.0],
                    "zoom": 6,
                },
            },
        }
        if cat_demo:
            corpo["categorias"] = [cat_demo]
        mapa_id = cli.criar_item(corpo)
        titulos[TITULO_MAPA] = mapa_id
        criadas += 1
        cli.dizer("mapa de demonstração criado")

    if TITULO_PAINEL not in titulos:
        # 'painel' é uma família de GRAFO (app/catalogo/documento.py FAMILIAS_GRAFO): corpo = {nos, ligacoes,
        # mapa_id, mapas}, cada nó com id ULID. Um único nó de indicador, ligado ao mapa recém-criado.
        # ULID gerado aqui (não importamos app.* neste script: ele fala com a plataforma só por HTTP e
        # importar app.catalogo.documento arrastaria app.settings, que exige PLAT_DSN mesmo fora de processo
        # de servidor) — mesmo formato validado por app/catalogo/documento.py::ULID_RE.
        corpo = {
            "titulo": TITULO_PAINEL,
            "tipo": "painel",
            "resumo": "Painel de demonstração com um indicador de contagem sobre a camada de "
            "estações do INMET, semeado por plat demo semear.",
            "tags": ["demonstracao", "painel"],
            "dados": {
                "tipo": "painel",
                "esquema_versao": 1,
                "corpo": {
                    "mapa_id": titulos.get(TITULO_MAPA),
                    "nos": [
                        {
                            "id": gerar_ulid(),
                            "tipo": "indicador_contagem",
                            "titulo": "Estações do INMET na região Norte",
                            "camada_id": titulos.get("Estações meteorológicas do INMET na região Norte"),
                        },
                    ],
                    "ligacoes": [],
                },
            },
        }
        if cat_demo:
            corpo["categorias"] = [cat_demo]
        cli.criar_item(corpo)
        criadas += 1
        cli.dizer("painel de demonstração criado")

    if TITULO_FORMULARIO not in titulos:
        corpo = {
            "titulo": TITULO_FORMULARIO,
            "tipo": "formulario",
            "resumo": "Ficha de visita de campo, sem dado nenhum atrás — só demonstra o construtor "
            "de formulário, semeada por plat demo semear.",
            "tags": ["demonstracao", "formulario"],
            "dados": {
                "tipo": "formulario",
                "esquema_versao": 1,
                "corpo": {
                    "titulo": "Ficha de visita de campo (demonstração)",
                    "campos": [
                        {"nome": "data_visita", "rotulo": "Data da visita", "tipo": "data", "obrigatorio": True},
                        {"nome": "observacao", "rotulo": "Observação", "tipo": "texto", "obrigatorio": False},
                        {"nome": "foto", "rotulo": "Foto", "tipo": "arquivo", "obrigatorio": False},
                    ],
                },
            },
        }
        if cat_demo:
            corpo["categorias"] = [cat_demo]
        cli.criar_item(corpo)
        criadas += 1
        cli.dizer("formulário de demonstração criado")

    if TITULO_REDE not in titulos:
        nos_id = ids_por_papel.get("rede_nos")
        arestas_id = ids_por_papel.get("rede_arestas")
        if not (nos_id and arestas_id):
            raise Erro("rede de demonstração exige as camadas rede_nos e rede_arestas já carregadas")
        corpo = {
            "titulo": TITULO_REDE,
            "tipo": "rede",
            "resumo": "Grafo de vias de Fernando de Noronha (OpenStreetMap): 576 nós e 411 arestas. "
            "É um grafo de demonstração do tipo `rede`, não uma rede de utilidade elétrica "
            "ou hídrica — o item L4 dessa linha ainda não foi construído.",
            "tags": ["demonstracao", "rede", "osm"],
            "dados": {"camadas": {"nos": nos_id, "arestas": arestas_id}, "regras_versao": 1},
        }
        if cat_demo:
            corpo["categorias"] = [cat_demo]
        cli.criar_item(corpo)
        criadas += 1
        cli.dizer("rede de demonstração criada")

    return criadas


def semear(base_url: str, credenciais_arquivo: Path, medida: Path | None = None, verboso: bool = True) -> dict:
    catalogo = carregar_catalogo()
    cred = credenciais(credenciais_arquivo)
    inicio = time.monotonic()
    resultados = []
    for slug in ("demo", "demo2"):
        itens = [it for it in catalogo["itens"] if it["inquilino"] == slug]
        if not itens:
            continue
        if slug not in cred:
            raise Erro(f"{credenciais_arquivo} não tem a linha de {slug}")
        login, senha = cred[slug]
        resultados.append(semear_inquilino(base_url, slug, login, senha, itens, verboso))
    segundos = time.monotonic() - inicio
    resumo = {"segundos": round(segundos, 2), "inquilinos": resultados, "arquivos_no_catalogo": len(catalogo["itens"])}
    if medida:
        medida.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def verificar(base_url: str, credenciais_arquivo: Path, verboso: bool = True) -> dict:
    """`plat demo verificar`: confere que o hash de cada arquivo do catálogo bate com o disco e que
    cada inquilino de demonstração tem o item correspondente (arquivo, camada e as 4 composições).
    Não semeia nada; só lê."""
    catalogo = carregar_catalogo()
    problemas: list[str] = []
    contagens: dict[str, dict] = {}

    for it in catalogo["itens"]:
        caminho = ARQUIVOS / it["arquivo"]
        if not caminho.exists():
            problemas.append(f"arquivo ausente no disco: {it['arquivo']}")
            continue
        real = sha256_arquivo(caminho)
        if real != it["sha256"]:
            problemas.append(
                f"sha256 divergente em {it['arquivo']}: catálogo {it['sha256'][:16]}... disco {real[:16]}..."
            )
        tamanho_real = caminho.stat().st_size
        if tamanho_real != it["bytes"]:
            problemas.append(f"tamanho divergente em {it['arquivo']}: catálogo {it['bytes']} disco {tamanho_real}")

    total_bytes = sum(
        (ARQUIVOS / it["arquivo"]).stat().st_size for it in catalogo["itens"] if (ARQUIVOS / it["arquivo"]).exists()
    )
    teto = 300 * 1024 * 1024
    if total_bytes > teto:
        problemas.append(f"pacote com {total_bytes} bytes, acima do teto de {teto} bytes (300 MB)")

    cred = credenciais(credenciais_arquivo)
    esperados_por_slug: dict[str, set[str]] = {}
    for it in catalogo["itens"]:
        esperados_por_slug.setdefault(it["inquilino"], set()).add(f"{it['titulo']} (arquivo de origem)")
        if it["ingerir"]:
            esperados_por_slug[it["inquilino"]].add(it["titulo"])
    esperados_por_slug.setdefault("demo", set()).update({TITULO_MAPA, TITULO_PAINEL, TITULO_FORMULARIO, TITULO_REDE})

    for slug, esperados in esperados_por_slug.items():
        if slug not in cred:
            problemas.append(f"sem credencial para conferir o inquilino {slug}")
            continue
        login, senha = cred[slug]
        cli = Cliente(base_url, slug, login, senha, verboso=False)
        try:
            titulos = cli.titulos()
        finally:
            cli.fechar()
        faltam = sorted(t for t in esperados if t not in titulos)
        contagens[slug] = {"esperados": len(esperados), "encontrados": len(esperados) - len(faltam), "faltando": faltam}
        if faltam:
            problemas.append(f"{slug}: faltam {len(faltam)} item(ns): {faltam}")

    resultado = {
        "ok": not problemas,
        "problemas": problemas,
        "contagens": contagens,
        "bytes_total": total_bytes,
        "arquivos": len(catalogo["itens"]),
    }
    return resultado

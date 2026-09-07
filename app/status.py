"""GET /api/status e a página /status (item L0-06-e-status): retrato operacional da instalação, aberto, sem
sessão e sem nome de inquilino.

Três decisões que valem a leitura:

1. **Cache de 30 s no processo.** A página é pública e um só cliente pode pedi-la mil vezes por minuto; o
   conteúdo vale para todo mundo igual, então o retrato é calculado uma vez e servido do cache até vencer.
   Sem isso cada pedido abriria conexão de banco e sondaria seis serviços — o oposto de uma página de saúde.
2. **Só agregado.** A resposta nunca carrega slug de inquilino, caminho de disco, alvo de serviço, versão de
   biblioteca ou o número de versão da aplicação. Estado, contagem, data e percentual — nada que descreva a
   máquina. `/saude/profunda` (L7-34) continua sendo o lugar onde o superadmin vê alvo e motivo.
3. **O histórico vem do banco, não da memória.** O periódico `status.amostrar` grava uma linha por serviço a
   cada 5 minutos em `plat.status_amostra`; o percentual do mês é recalculado dessas linhas a cada pedido
   (função `plat.status_disponibilidade`). Nada é acumulado em contador que ninguém consegue auditar.
"""

from __future__ import annotations

import datetime
import logging
import re
import threading
import time
from pathlib import Path

import psycopg2
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import db
from app.garage import ClienteAdmin, ErroGarage
from app.saude import agora_iso
from app.saude_profunda import _certificado, _disco, _sondar, pior_estado
from app.saude_profunda import _servico_simples as _servico
from app.settings import settings

router = APIRouter()
log = logging.getLogger("plat.status")

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
CACHE_S = 30.0
DIAS_HISTORICO = 90
MAX_CORRECOES = 20
NOINDEX = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"}
# serviços cujo estado entra em plat.status_amostra e no histórico de 90 dias
SERVICOS_AMOSTRADOS = ("api", "banco", "worker", "martin", "titiler", "garage")
_RE_CORRECAO = re.compile(r"corre[çc][ãa]o|corrig", re.IGNORECASE)
_RE_VERSAO = re.compile(r"^##+\s+(.+?)\s*$")
_RE_ITEM = re.compile(r"^\s*[-*]\s+")
_RE_FRASE = re.compile(r"(?<=[.;])\s+")

_trava = threading.Lock()
_cache: tuple[float, dict] | None = None


# ---------------------------------------------------------------- leituras de banco (uma conexão por retrato)


def _do_banco() -> dict:
    """Banco, migrações, fila, backup, ensaio de restauração, histórico e disponibilidade do mês numa conexão
    só: o pool da trilha nasce com PLAT_POOL_MAX=2 (mesma razão registrada em app/saude_profunda.py)."""
    inicio = datetime.datetime.now(datetime.UTC)
    primeiro_do_mes = inicio.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.db() as cur:
        aplicadas, pendentes, ultima = db.migracoes_estado()

        cur.execute("SELECT * FROM plat.status_fila()")
        f = cur.fetchone()

        cur.execute("SELECT * FROM plat.status_backup()")
        b = cur.fetchone()

        drill = _ensaio(cur)

        cur.execute("SELECT * FROM plat.status_historico(%s)", (DIAS_HISTORICO,))
        historico: dict[str, list[dict]] = {}
        for r in cur.fetchall():
            historico.setdefault(r["servico"], []).append(
                {"dia": r["dia"].isoformat(), "amostras": r["amostras"], "ok": r["ok"], "ausentes": r["ausentes"]}
            )

        cur.execute("SELECT * FROM plat.status_disponibilidade(%s)", (primeiro_do_mes,))
        disponibilidade = {
            r["servico"]: {
                "amostras": r["amostras"],
                "ok": r["ok"],
                "pct": float(r["pct"]) if r["pct"] is not None else None,
            }
            for r in cur.fetchall()
        }

    return {
        "banco": {"estado": "degradado" if pendentes else "ok"},
        "migracoes": {"aplicadas": aplicadas, "pendentes": pendentes, "ultima": ultima},
        "fila": {"na_fila": f["na_fila"], "executando": f["executando"], "falhas_24h": f["falhas_24h"]},
        "backup": {
            "ultimo_em": _iso(b["ultimo_em"]),
            "esquemas": b["esquemas"],
            "bytes": int(b["bytes"] or 0),
            "idade_h": _idade_h(b["ultimo_em"], inicio),
        },
        "ensaio_restauracao": drill,
        "historico": {"dias": DIAS_HISTORICO, "servicos": historico},
        "disponibilidade_mes": {"desde": _iso(primeiro_do_mes), "servicos": disponibilidade},
    }


def _ensaio(cur) -> dict:
    """Último ensaio de restauração pela função `plat.backup_drill_status()` do item L0-06-c. Esse item ainda
    não entrou em master: enquanto a função não existir, o campo diz `indisponivel` com a razão, em vez de
    fingir que o ensaio nunca falhou. Quando o L0-06-c juntar, a mesma chamada passa a responder sozinha."""
    try:
        cur.execute("SELECT * FROM plat.backup_drill_status()")
        r = cur.fetchone()
    except psycopg2.errors.UndefinedFunction:
        cur.connection.rollback()
        return {"indisponivel": "rotina de ensaio de restauração ainda não instalada (item L0-06-c)"}
    if r is None or r["ultimo_em"] is None:
        return {"ultimo_em": None}
    return {
        "ultimo_em": _iso(r["ultimo_em"]),
        "ok": r["ok"],
        "esquemas": r["esquemas"],
        "divergencias": r["divergencias"],
        "idade_h": _idade_h(r["ultimo_em"], datetime.datetime.now(datetime.UTC)),
    }


def _iso(v) -> str | None:
    return v.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if v else None


def _idade_h(v, agora) -> float | None:
    return round((agora - v).total_seconds() / 3600.0, 2) if v else None


# ---------------------------------------------------------------- espaço no bucket (Garage)


def _bucket() -> dict:
    """Espaço no armazenamento de objetos, pela Admin API v2 do Garage (GetClusterStatistics): buckets, objetos,
    tamanho total e espaço livre estimado. Só os números — o relatório do Garage traz o nome da máquina de
    armazenamento junto, e esse não sai daqui. Sem Admin API configurada -> ausente."""
    if not settings.PLAT_GARAGE_ADMIN_URL or not settings.PLAT_GARAGE_ADMIN_TOKEN:
        return {"estado": "ausente", "motivo": "Admin API do Garage não configurada nesta instalação"}
    try:
        relatorio = ClienteAdmin(
            settings.PLAT_GARAGE_ADMIN_URL, settings.PLAT_GARAGE_ADMIN_TOKEN
        ).estatisticas_cluster()
    except (ErroGarage, OSError, ValueError, KeyError) as e:
        return {"estado": "erro", "motivo": type(e).__name__}
    return {"estado": "ok", **medir_bucket((relatorio or {}).get("freeform") or "")}


_RE_BUCKETS = re.compile(r"^Number of buckets:\s+(\d+)", re.MULTILINE)
_RE_OBJETOS = re.compile(r"^Total number of objects:\s+(\d+)", re.MULTILINE)
_RE_TAMANHO = re.compile(r"^Total size of objects:\s+([\d.]+\s*\w+)", re.MULTILINE)
_RE_LIVRE = re.compile(r"^\s+data:\s+([\d.]+\s*\w+)", re.MULTILINE)
_UNIDADES = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4, "PiB": 1024**5}


def medir_bucket(freeform: str) -> dict:
    """Extrai os números do relatório do Garage. O que não vier no formato esperado fica NULL — nunca zero
    fingido — e o texto original não é repassado (carrega o nome da máquina de armazenamento)."""
    buckets = _RE_BUCKETS.search(freeform)
    objetos = _RE_OBJETOS.search(freeform)
    tamanho = _RE_TAMANHO.search(freeform)
    livre = _RE_LIVRE.search(freeform)
    return {
        "buckets": int(buckets.group(1)) if buckets else None,
        "objetos": int(objetos.group(1)) if objetos else None,
        "bytes_aprox": _para_bytes(tamanho.group(1)) if tamanho else None,
        "livre_bytes_aprox": _para_bytes(livre.group(1)) if livre else None,
    }


def _para_bytes(texto: str) -> int | None:
    """'7.1 GiB' -> 7623566950. Aproximado de propósito: o Garage arredonda o relatório em uma casa decimal."""
    partes = texto.split()
    if len(partes) != 2 or partes[1] not in _UNIDADES:
        return None
    try:
        return int(float(partes[0]) * _UNIDADES[partes[1]])
    except ValueError:
        return None


# ---------------------------------------------------------------- log de correções (CHANGELOG)


def correcoes(texto: str, limite: int = MAX_CORRECOES) -> list[dict]:
    """Frases do CHANGELOG que descrevem correção, com o título da seção (o item) em que estão.

    O CHANGELOG da casa é escrito em prosa, um parágrafo por assunto, não em lista de linhas curtas — ler
    linha física devolvia meia frase, e ler o parágrafo inteiro devolvia meia página. Então: o texto é
    reunido por parágrafo, o parágrafo é partido em frases e ficam as frases que falam de correção
    ('correção'/'corrigido', o filtro literal da cláusula do portão). Nada mais é interpretado.
    """
    achadas: list[dict] = []
    secao = ""
    paragrafo: list[str] = []

    def fechar() -> None:
        if paragrafo:
            for frase in _RE_FRASE.split(" ".join(paragrafo).strip()):
                frase = frase.strip()
                if frase and _RE_CORRECAO.search(frase):
                    limpa = higienizar(frase)
                    if limpa.count(OMITIDO) <= MAX_OMISSOES:  # frase que só sobrevive em pedaços não informa nada
                        achadas.append({"secao": higienizar(secao), "texto": _cortar(limpa)})
            paragrafo.clear()

    for linha in texto.splitlines():
        cabecalho = _RE_VERSAO.match(linha)
        if cabecalho:
            fechar()
            secao = cabecalho.group(1).strip()
            continue
        if linha.lstrip().startswith("|"):
            fechar()  # linha de tabela (a lista de commits do turno): não é prosa, não entra
            continue
        if linha.strip():
            paragrafo.append(_RE_ITEM.sub("", linha, count=1).strip())
        else:
            fechar()
    fechar()
    return achadas[-limite:]  # as últimas registradas no arquivo, na ordem em que estão escritas


_RE_VERSAO_NUM = re.compile(r"\b\d+\.\d+(?:\.\d+)+\b")
_RE_CAMINHO = re.compile(r"(?:\.?/[\w.\-]+){2,}|\b\w+\.(?:py|sql|js|html|css|json|sh|md|conf|txt)\b")
_RE_CODIGO = re.compile(r"`[^`]*`")
OMITIDO = "…"


def _dependencias() -> frozenset[str]:
    """Nomes dos pacotes de requirements.txt, em minúscula. Servem de lista de redação: uma frase do CHANGELOG
    que cite a biblioteca por nome revelaria a pilha numa página aberta, e a cláusula do portão veda isso."""
    nomes = set()
    try:
        for linha in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#"):
                nomes.add(re.split(r"[=<>\[; ]", linha, maxsplit=1)[0].strip().lower())
    except OSError:
        return frozenset()
    return frozenset(n for n in nomes if len(n) >= 4)


# nomes da pilha que não estão em requirements.txt porque vêm de pacote do sistema (dpkg) ou não são pacote
# Python nenhum; a página é aberta e a cláusula do portão veda revelar a pilha.
PILHA = frozenset({"psycopg2", "postgres", "postgresql", "nginx", "uvicorn", "python", "playwright", "pytest",
                   "systemd", "gunicorn", "chromium"})
MAX_OMISSOES = 3

_DEPENDENCIAS = _dependencias() | PILHA


def higienizar(frase: str) -> str:
    """Tira da frase o que a cláusula do portão proíbe numa resposta aberta: trecho de código, caminho de
    arquivo, número de versão e nome de dependência. O resto do texto do CHANGELOG fica como está — a página
    mostra a correção que houve, não o interior da máquina."""
    frase = _RE_CODIGO.sub(OMITIDO, frase)
    frase = _RE_CAMINHO.sub(OMITIDO, frase)
    frase = _RE_VERSAO_NUM.sub(OMITIDO, frase)
    if _DEPENDENCIAS:
        frase = re.sub(r"\b[\w.\-]+\b",
                       lambda m: OMITIDO if m.group(0).lower() in _DEPENDENCIAS else m.group(0), frase)
    return re.sub(r"(?:… ?)+", "… ", frase).strip()


def _cortar(texto: str, limite: int = 400) -> str:
    """Corta no espaço anterior ao limite (a linha do CHANGELOG às vezes é um parágrafo inteiro): cortar no
    meio da palavra faz a página parecer defeito de renderização."""
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0]
    return (corte or texto[:limite]).rstrip(",;:. ") + "…"


def _correcoes_do_arquivo() -> list[dict]:
    try:
        return correcoes(CHANGELOG.read_text(encoding="utf-8"))
    except OSError:
        return []


# ---------------------------------------------------------------- retrato


def retrato() -> dict:
    """Calcula o retrato inteiro (sem cache). Também é o que o periódico `status.amostrar` usa para gravar a
    amostra — a página e o histórico medem exatamente a mesma coisa."""
    inicio = time.perf_counter()
    servicos = {
        "api": {"estado": "ok", "tempo_ms": 0.0},  # se esta função responde, a API está de pé
        "worker": _sondar(lambda: _servico(settings.PLAT_WORKER_URL)),
        "martin": _sondar(lambda: _servico(settings.PLAT_MARTIN_URL)),
        "titiler": _sondar(lambda: _servico(settings.PLAT_TITILER_URL)),
        "garage": _sondar(lambda: _servico(settings.PLAT_GARAGE_URL)),
    }
    for s in servicos.values():
        s.pop("alvo", None)  # host:porta é detalhe de máquina: fica no /saude/profunda do superadmin
    banco = _sondar(_do_banco)
    if "banco" in banco:
        corpo = dict(banco)
        servicos["banco"] = {"estado": corpo["banco"]["estado"], "tempo_ms": banco["tempo_ms"]}
    else:
        corpo = {}
        servicos["banco"] = {"estado": "erro", "tempo_ms": banco["tempo_ms"]}
    disco = _sondar(_disco)
    certificado = _sondar(_certificado)

    saida = {
        "estado": pior_estado([s["estado"] for s in servicos.values()]),
        "servicos": {n: servicos[n] for n in SERVICOS_AMOSTRADOS},
        "migracoes": corpo.get("migracoes", {"erro": True}),
        "fila": corpo.get("fila", {"erro": True}),
        "backup": corpo.get("backup", {"erro": True}),
        "ensaio_restauracao": corpo.get("ensaio_restauracao", {"erro": True}),
        "disco": _disco_agregado(disco),
        "bucket": _bucket(),
        "certificado": {"estado": certificado["estado"], "dias_restantes": certificado.get("dias_restantes")},
        "historico": corpo.get("historico", {"dias": DIAS_HISTORICO, "servicos": {}}),
        "disponibilidade_mes": corpo.get("disponibilidade_mes", {"desde": None, "servicos": {}}),
        "correcoes": _correcoes_do_arquivo(),
        "cache_s": int(CACHE_S),
        "tempo_ms": round((time.perf_counter() - inicio) * 1000, 1),
        "em": agora_iso(),
    }
    return saida


def _disco_agregado(disco: dict) -> dict:
    """O nome do volume é caminho de disco e não sai daqui (cláusula do portão): só o estado e o pior
    percentual livre entre os volumes que a instalação tem."""
    volumes = disco.get("volumes") or {}
    livres = [v["livre_pct"] for v in volumes.values()]
    return {
        "estado": disco["estado"],
        "volumes": len(volumes),
        "menor_livre_pct": min(livres) if livres else None,
    }


def retrato_com_cache() -> tuple[dict, bool]:
    """Devolve (retrato, veio_do_cache). Um pedido calcula; os outros dos 30 s seguintes leem o mesmo dicionário
    (a trava é segurada durante o cálculo de propósito: mil pedidos no mesmo segundo fazem UM cálculo)."""
    global _cache
    with _trava:
        agora = time.monotonic()
        if _cache is not None and agora < _cache[0]:
            return _cache[1], True
        novo = retrato()
        _cache = (agora + CACHE_S, novo)
        return novo, False


def limpar_cache() -> None:
    global _cache
    with _trava:
        _cache = None


# rota aberta, como /saude e /saude/profunda: x-auth/x-privilegio declarados para os portões transversais
@router.get("/api/status", openapi_extra={"x-auth": "-", "x-privilegio": "publico"})
def api_status():
    corpo, do_cache = retrato_com_cache()
    codigo = 200 if corpo["estado"] in ("ok", "ausente") else 503
    return JSONResponse(corpo, status_code=codigo, headers={**NOINDEX, "X-Cache": "hit" if do_cache else "miss"})


router.add_api_route("/api/status", api_status, methods=["HEAD"], include_in_schema=False)

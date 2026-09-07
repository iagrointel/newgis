"""Popup em tempo de execução (item L2-01-d-popup-runtime).

O visualizador (L2-01-mapa-web) já clica no mapa e monta uma janela simples a partir do que veio no
tile vetorial (`app/mapa/rotas.py::_ficha`, `web/js/mapa/atributos.js`). Este item COMPLETA aquele
motor sem duplicá-lo:

1. **Fixa a forma de `plat.item.dados.popup`** (a mesma lacuna que o handoff do L2-01-a deixou
   registrada para "estilo.embutido / popup.embutido"; naquela lineage o documento de mapa mora em
   `app/mapas/documento.py` — nesta, mais simples, o popup é configuração da própria camada,
   `dados.popup`, normalizada aqui por `normalizar()`). Título com `{campo}`, lista de campos com
   rótulo e formato (número com casas + separador pt-BR, moeda, data no fuso do inquilino, URL
   clicável, imagem por URL), campo `servidor: true` (não é lido do tile — sempre buscado no servidor)
   e `expressoes` (avaliadas aqui, reusando POR INTEIRO o núcleo de `app/expressao/avaliador_py.py`
   do item L2-10-c — nenhuma gramática nova).
2. **A rota `GET /api/camadas/{id}/feicoes/{fid}/popup`**: consulta a UMA feição por `fid` (a mesma
   tabela hospedada que o tile lê) e devolve só o que o cliente não tem: os campos marcados
   `servidor` (lidos de uma tabela COMPANHEIRA `<tabela>_x`, quando existe — nunca da tabela tilada:
   é assim que um campo fica "não incluído no tile" sem mexer no gerador de tile do L2-01-b, que
   inclui toda coluna da tabela principal) e as `expressoes`, com `$area_m2`/`$perimetro_m2`
   calculados por PostGIS geográfico (`ST_Area`/`ST_Perimeter` sobre `geography(geom)`) postos no
   CONTEXTO da expressão — a função geométrica em si (`Area()`/`AreaGeodetic()` do Arcade) é
   pendência nomeada do L2-10-c (`docs/EXPRESSAO.md` linha "geometria... é pendência nomeada"); aqui
   a expressão só usa aritmética (`$area_m2 / 10000`), que o núcleo já resolve.

Fora deste item, com o motivo (fronteira honesta, não fingida):
  * **anexos** (lista) — não existe armazenamento de anexo POR FEIÇÃO na casa; a plataforma tem
    upload por ITEM do catálogo (L0-04), não por linha de tabela hospedada.
  * **registros relacionados** — item L2-10-b-relacionamentos está `pendente` no backlog
    (`laco/estado.json`); sem relação declarada não há o que listar.
  * **popup de raster com valor de pixel** — item L1-02-h está `pendente`; esta camada (`/api/mapa/
    camadas`) só serve vetor.
  * **ações "selecionar" e "editar"** — dependem de L2-01-h/L2-03, que não existem nesta lineage
    (`app/mapa`, família L2-01-mapa-web); zoom-para-a-feição é cliente puro e ENTRA (não depende de
    nada disso).
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from fastapi import APIRouter, Path
from psycopg2 import sql

from app import db
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI
from app.expressao.avaliador_py import ErroExpressao, avaliar_texto
from app.mapa.consultas import SQL_CAMADA

router = APIRouter(tags=["mapa-popup"])
X = {"x-auth": "S/T", "x-privilegio": "proprio"}

ESQUEMA_RE = re.compile(r"^d_[a-z0-9_]{1,60}$")
TABELA_RE = re.compile(r"^c_[0-9a-f]{16}$")
FORMATOS = {"texto", "numero", "moeda", "data", "url", "imagem"}
FUSO_PADRAO = "America/Sao_Paulo"


# ------------------------------------------------------------------ normalização de dados.popup
def _campo(c: Any, indice_campos: dict[str, dict]) -> dict | None:
    if isinstance(c, str):
        c = {"nome": c}
    if not isinstance(c, dict) or not c.get("nome"):
        return None
    nome = str(c["nome"])
    formato = c.get("formato") if isinstance(c.get("formato"), dict) else {}
    tipo = formato.get("tipo") if formato.get("tipo") in FORMATOS else "texto"
    decimais = formato.get("decimais")
    if not isinstance(decimais, int) or decimais < 0 or decimais > 6:
        decimais = 2 if tipo in ("numero", "moeda") else None
    return {
        "nome": nome,
        "rotulo": str(c.get("rotulo") or indice_campos.get(nome, {}).get("rotulo") or nome),
        "tipo": tipo,
        "decimais": decimais,
        "servidor": bool(c.get("servidor")),
    }


def _expressao(e: Any) -> dict | None:
    if not isinstance(e, dict):
        return None
    nome, expressao = e.get("nome"), e.get("expressao")
    if not nome or not isinstance(expressao, str) or not expressao.strip():
        return None
    formato = e.get("formato") if isinstance(e.get("formato"), dict) else {}
    tipo = formato.get("tipo") if formato.get("tipo") in FORMATOS else "numero"
    decimais = formato.get("decimais")
    if not isinstance(decimais, int) or decimais < 0 or decimais > 6:
        decimais = 2
    return {"nome": str(nome), "rotulo": str(e.get("rotulo") or nome), "expressao": expressao,
            "tipo": tipo, "decimais": decimais}


def normalizar(dados: dict) -> dict:
    """`dados` é `plat.item.dados` da camada. Nunca falha: configuração ausente ou incoerente vira o
    padrão (mostrar tudo como texto), igual ao comportamento anterior do item L2-01-mapa-web — este
    item ACRESCENTA formato e paginação, não torna a camada sem popup nenhum quando não configurada."""
    campos_catalogo = dados.get("campos") if isinstance(dados.get("campos"), list) else []
    indice = {c.get("nome"): c for c in campos_catalogo if isinstance(c, dict) and c.get("nome")}
    cfg = dados.get("popup") if isinstance(dados.get("popup"), dict) else {}

    campos_cfg = cfg.get("campos") if isinstance(cfg.get("campos"), list) else None
    if campos_cfg:
        campos = [c for c in (_campo(c, indice) for c in campos_cfg) if c]
    else:
        campos = [{"nome": nome, "rotulo": nome, "tipo": "texto", "decimais": None, "servidor": False}
                  for nome in indice]

    expressoes = [e for e in (_expressao(e) for e in (cfg.get("expressoes") or [])) if e]
    titulo = cfg.get("titulo") if isinstance(cfg.get("titulo"), str) and cfg.get("titulo").strip() else None

    return {"titulo": titulo, "campos": campos, "expressoes": expressoes,
            "tem_servidor": any(c["servidor"] for c in campos) or bool(expressoes)}


# ------------------------------------------------------------------ formatação (mesmas regras do cliente,
# aqui só para o que o SERVIDOR calcula: expressão e campo marcado "servidor" — o campo lido direto do
# tile é formatado no navegador, sem round-trip, pelo motivo dito no docstring do módulo)
def formatar_numero_ptbr(valor: float, decimais: int) -> str:
    """`1234567.891` com 2 casas -> `'1.234.567,89'`. Sem `locale` do SO (não confiável entre processos):
    formata em inglês e troca `,`/`.` de lugar — truque determinístico, sem dependência nova."""
    texto = f"{valor:,.{decimais}f}"
    return texto.translate(str.maketrans({",": "\x00", ".": ","})).replace("\x00", ".")


def formatar_moeda_brl(valor: float) -> str:
    return "R$ " + formatar_numero_ptbr(valor, 2)


def formatar_data(valor_ms: float, fuso: str) -> str:
    """`valor_ms` é a convenção do L2-10-c (milissegundos desde a época, sempre UTC). `zoneinfo` é
    biblioteca padrão (já usado em `app/jobs/agenda.py`) — nenhuma dependência nova."""
    import zoneinfo

    try:
        tz = zoneinfo.ZoneInfo(fuso)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        tz = zoneinfo.ZoneInfo(FUSO_PADRAO)
    dt = datetime.datetime.fromtimestamp(valor_ms / 1000.0, tz=datetime.UTC).astimezone(tz)
    return dt.strftime("%d/%m/%Y %H:%M")


def formatar(valor: Any, tipo: str, decimais: int | None, fuso: str) -> str | None:
    if valor is None:
        return None
    if tipo == "numero":
        return formatar_numero_ptbr(float(valor), decimais if decimais is not None else 2)
    if tipo == "moeda":
        return formatar_moeda_brl(float(valor))
    if tipo == "data":
        return formatar_data(float(valor), fuso)
    return str(valor)


# ------------------------------------------------------------------ a rota
def _camada_ou_404(cur, id_: str) -> dict:
    cur.execute(SQL_CAMADA + " AND i.id = %s::uuid", (id_,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "camada_inexistente", "camada inexistente ou sem permissão de leitura")
    return linha


def _fuso_do_inquilino(cur) -> str:
    cur.execute("SELECT config->>'fuso' AS fuso FROM plat.tenant WHERE id = plat.tenant_atual()")
    linha = cur.fetchone()
    fuso = linha["fuso"] if linha else None
    return fuso or FUSO_PADRAO


@router.get("/api/mapa/fuso", openapi_extra=X)
def fuso_do_mapa(auth: Auth = autenticado(escopo_token="catalogo:ler")):
    """O visualizador chama isto UMA vez ao abrir a tela para formatar data no fuso do inquilino sem
    round-trip por campo (`tenant.config.fuso`, mesma leitura que a rota do popup usa)."""
    with db.db(auth.contexto()) as cur:
        return {"fuso": _fuso_do_inquilino(cur)}


@router.get("/api/camadas/{id}/feicoes/{fid}/popup", openapi_extra=X)
def popup_da_feicao(
    id: str,
    fid: int = Path(ge=1),
    fuso: str | None = None,
    auth: Auth = autenticado(escopo_token="catalogo:ler"),
):
    """Só o que o cliente NÃO tem: campos `servidor` (tabela companheira) e expressões (avaliadas
    aqui). `fuso`, se dado na query, sobrepõe o do inquilino só nesta chamada (é assim que o e2e prova
    a mesma data em dois fusos sem precisar reconfigurar o inquilino a cada teste; o padrão de produto
    é o fuso do inquilino, lido de `tenant.config.fuso`)."""
    with db.db(auth.contexto()) as cur:
        linha = _camada_ou_404(cur, id)
        dados = linha["dados"] or {}
        esquema, tabela = dados.get("schema"), dados.get("tabela")
        if not esquema or not tabela or not ESQUEMA_RE.match(esquema) or not TABELA_RE.match(tabela):
            raise ErroAPI(422, "camada_sem_tabela", "esta camada não é hospedada: não há feição a consultar")
        cfg = normalizar(dados)
        fuso_efetivo = fuso or _fuso_do_inquilino(cur)

        tabela_x = tabela + "_x"
        cur.execute(
            "SELECT to_regclass(%s) IS NOT NULL AS existe",
            (f"{esquema}.{tabela_x}",),
        )
        tem_tabela_x = bool(cur.fetchone()["existe"])

        if tem_tabela_x:
            consulta = sql.SQL(
                "SELECT t.*, x.*, ST_Area(geography(t.geom)) AS area_m2, "
                "ST_Perimeter(geography(t.geom)) AS perimetro_m2 "
                "FROM {esquema}.{tabela} t LEFT JOIN {esquema}.{tabela_x} x ON x.fid = t.fid "
                "WHERE t.fid = %s"
            ).format(esquema=sql.Identifier(esquema), tabela=sql.Identifier(tabela),
                     tabela_x=sql.Identifier(tabela_x))
        else:
            consulta = sql.SQL(
                "SELECT t.*, ST_Area(geography(t.geom)) AS area_m2, "
                "ST_Perimeter(geography(t.geom)) AS perimetro_m2 "
                "FROM {esquema}.{tabela} t WHERE t.fid = %s"
            ).format(esquema=sql.Identifier(esquema), tabela=sql.Identifier(tabela))
        cur.execute(consulta, (fid,))
        feicao = cur.fetchone()
        if feicao is None:
            raise ErroAPI(404, "feicao_inexistente", "feição inexistente ou sem permissão de leitura")

        contexto_expr: dict[str, Any] = {}
        for chave, valor in feicao.items():
            if chave in ("geom",):
                continue
            contexto_expr[chave] = float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else valor

        campos_servidor = {}
        for c in cfg["campos"]:
            if not c["servidor"]:
                continue
            bruto = feicao.get(c["nome"])
            campos_servidor[c["nome"]] = {
                "bruto": bruto,
                "formatado": formatar(bruto, c["tipo"], c["decimais"], fuso_efetivo) if bruto is not None else None,
            }

        expressoes_saida = {}
        for e in cfg["expressoes"]:
            try:
                valor = avaliar_texto(e["expressao"], contexto_expr)
            except ErroExpressao as exc:
                expressoes_saida[e["nome"]] = {"erro": exc.codigo, "mensagem": exc.mensagem}
                continue
            expressoes_saida[e["nome"]] = {
                "bruto": valor,
                "formatado": formatar(valor, e["tipo"], e["decimais"], fuso_efetivo) if valor is not None else None,
            }

        return {
            "camada_id": id,
            "fid": fid,
            "fuso": fuso_efetivo,
            "campos_servidor": campos_servidor,
            "expressoes": expressoes_saida,
            "relacionados": None,
            "relacionados_motivo": "item L2-10-b-relacionamentos pendente no backlog",
        }

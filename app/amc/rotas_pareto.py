"""Rotas /api/amc/pareto (item L3-08-pareto): análise sem agregação sobre uma execução do motor.

A conta é a de `app/amc/pareto.py` (módulo puro). Estas rotas só fazem três coisas: escolher de 2 a 4
fatores de uma execução do motor multicritério em grades aninhadas (`plat.escala_execucao`, item
L3-19-multiescala) como OBJETIVOS, entregar a ordenação não dominada por unidade, e devolver a
fronteira como camada GeoJSON — que é o que o mapa desenha e o que o usuário baixa.

Por que a execução do motor de grades é a fonte: é o único conjunto de unidades com geometria, fator
por unidade e RLS por inquilino que já existe em master. Quando o conjunto de unidades genérico
(L3-01-b) entrar, a mesma rota ganha a segunda fonte; nada aqui depende do formato da grade além de
"uma unidade tem id, geometria e um valor por fator".

As duas rotas são LEITURA (usam POST só porque a lista de objetivos não cabe em query string): não
escrevem nada e por isso não registram evento de domínio. Escopo de token reusado: `multiescala:usar`,
o mesmo que dá acesso à execução que está sendo lida — um token que não pode ler a execução também não
pode analisá-la, e nenhum vocabulário novo é preciso.
"""

import json
import uuid as uuid_mod

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app import db, limites
from app.amc import pareto
from app.auth.escopos import exigir_escopo
from app.auth.sessao import Auth, autenticado
from app.erros import ErroAPI

router = APIRouter(prefix="/api/amc/pareto", tags=["amc"])
LER = {"x-auth": "S/T", "x-privilegio": "rls:visibilidade"}
ESCOPO = "multiescala:usar"

BASES = ("favorabilidade", "valor")


class Objetivo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fator_id: str = Field(..., description="fator da execução (plat.escala_execucao_fator)")
    direcao: str = Field("maximizar", description="maximizar ou minimizar")
    base: str = Field("favorabilidade", description="favorabilidade 0-100 transformada, ou valor bruto do fator")


class PedidoPareto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execucao_id: str
    objetivos: list[Objetivo] = Field(..., min_length=pareto.MIN_OBJETIVOS, max_length=pareto.MAX_OBJETIVOS)
    ordens: int = Field(3, ge=1, le=pareto.MAX_ORDENS)


class PedidoCamada(PedidoPareto):
    ordens_incluidas: list[int] = Field(
        default_factory=lambda: [1],
        description="quais ordens entram na camada; [1] é só a fronteira",
    )


class Saida(BaseModel):
    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------ apoio


def _uuid(valor: str, codigo: str, mensagem: str) -> str:
    try:
        return str(uuid_mod.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError) as e:
        raise ErroAPI(422, codigo, mensagem) from e


def _validar_pedido(corpo: PedidoPareto) -> None:
    _uuid(corpo.execucao_id, "execucao_id_invalido", "execucao_id não é um uuid")
    vistos = set()
    for o in corpo.objetivos:
        _uuid(o.fator_id, "fator_id_invalido", "fator_id não é um uuid")
        if o.direcao not in pareto.DIRECOES:
            raise ErroAPI(422, "direcao_desconhecida", "direção tem de ser maximizar ou minimizar")
        if o.base not in BASES:
            raise ErroAPI(422, "base_desconhecida", "base tem de ser favorabilidade ou valor")
        if (o.fator_id, o.base) in vistos:
            raise ErroAPI(422, "objetivo_repetido", "o mesmo fator na mesma base não pode ser dois objetivos")
        vistos.add((o.fator_id, o.base))


def _execucao(cur, execucao_id: str) -> dict:
    """Execução do motor de grades, já filtrada pela RLS do inquilino: de outro inquilino é 404."""
    cur.execute(
        "SELECT e.id, e.grade_id, e.nivel, g.resolucao_m, g.celulas "
        "FROM plat.escala_execucao e JOIN plat.escala_grade g ON g.id = e.grade_id "
        "WHERE e.id = %s::uuid",
        (execucao_id,),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "execucao_inexistente", "execução inexistente")
    return r


def _fatores(cur, execucao_id: str, pedidos: list[Objetivo]) -> dict[str, dict]:
    cur.execute(
        "SELECT ef.fator_id, f.nome, f.unidade "
        "FROM plat.escala_execucao_fator ef JOIN plat.escala_fator f ON f.id = ef.fator_id "
        "WHERE ef.execucao_id = %s::uuid",
        (execucao_id,),
    )
    tem = {str(r["fator_id"]): {"nome": r["nome"], "unidade": r["unidade"]} for r in cur.fetchall()}
    for o in pedidos:
        if o.fator_id not in tem:
            raise ErroAPI(422, "fator_fora_da_execucao", f"o fator {o.fator_id} não faz parte desta execução")
    return tem


def _matriz(cur, execucao: dict, objetivos: list[Objetivo]) -> tuple[list[int], list[list[float | None]]]:
    """Universo = TODAS as células da grade da execução (não só as que têm linha de fator).

    Célula sem linha para um fator entra como NULL, nunca como zero: é a diferença entre "não medimos"
    e "medimos e deu nada", e é o que tira a unidade da ordenação em vez de premiá-la.
    """
    total = int(execucao["celulas"] or 0)
    if total > limites.PARETO_UNIDADES_MAX:
        raise ErroAPI(
            422,
            "unidades_demais",
            f"a análise aceita até {limites.PARETO_UNIDADES_MAX} unidades; esta execução tem {total}",
            {"unidades": total, "teto": limites.PARETO_UNIDADES_MAX},
        )
    ids = [o.fator_id for o in objetivos]
    cur.execute(
        "SELECT c.id AS celula_id, fc.fator_id, fc.valor, fc.favorabilidade "
        "FROM plat.escala_celula c "
        "LEFT JOIN plat.escala_fator_celula fc "
        "  ON fc.celula_id = c.id AND fc.execucao_id = %s::uuid AND fc.fator_id = ANY(%s::uuid[]) "
        "WHERE c.grade_id = %s::uuid ORDER BY c.id",
        (str(execucao["id"]), ids, str(execucao["grade_id"])),
    )
    por_celula: dict[int, dict[tuple[str, str], float | None]] = {}
    for r in cur.fetchall():
        cid = int(r["celula_id"])
        alvo = por_celula.setdefault(cid, {})
        if r["fator_id"] is None:
            continue
        fid = str(r["fator_id"])
        alvo[(fid, "valor")] = None if r["valor"] is None else float(r["valor"])
        alvo[(fid, "favorabilidade")] = (
            None if r["favorabilidade"] is None else float(r["favorabilidade"])
        )
    celulas = sorted(por_celula)
    linhas = [[por_celula[c].get((o.fator_id, o.base)) for o in objetivos] for c in celulas]
    return celulas, linhas


def _ordenar(linhas: list[list[float | None]], objetivos: list[Objetivo], ordens: int) -> pareto.Ordenacao:
    if not linhas:
        raise ErroAPI(422, "sem_unidades", "a execução não tem célula nenhuma para ordenar")
    matriz = [[float("nan") if v is None else v for v in linha] for linha in linhas]
    try:
        return pareto.ordenar(matriz, [o.direcao for o in objetivos], ordens)
    except pareto.ErroPareto as e:
        raise ErroAPI(422, e.codigo, e.mensagem, e.detalhe) from e


def _objetivos_json(objetivos: list[Objetivo], fatores: dict[str, dict]) -> list[dict]:
    return [
        {
            "fator_id": o.fator_id,
            "nome": fatores[o.fator_id]["nome"],
            "unidade": fatores[o.fator_id]["unidade"],
            "direcao": o.direcao,
            "base": o.base,
        }
        for o in objetivos
    ]


# ------------------------------------------------------------------ rotas


@router.post("", response_model=Saida, openapi_extra=LER)
def ordenacao(corpo: PedidoPareto, auth: Auth = autenticado()):
    """Ordenação não dominada das unidades de uma execução, com 2 a 4 objetivos e sem peso nenhum."""
    exigir_escopo(auth, ESCOPO)
    _validar_pedido(corpo)
    with db.db(auth.contexto()) as cur:
        execucao = _execucao(cur, corpo.execucao_id)
        fatores = _fatores(cur, corpo.execucao_id, corpo.objetivos)
        celulas, linhas = _matriz(cur, execucao, corpo.objetivos)
    o = _ordenar(linhas, corpo.objetivos, corpo.ordens)
    saida = o.como_dicionario()
    saida.update(
        {
            "execucao_id": corpo.execucao_id,
            "objetivos": _objetivos_json(corpo.objetivos, fatores),
            "unidades_avaliadas": len(celulas),
            "unidades": [
                {
                    "unidade_id": cid,
                    "ordem": int(o.ordem[i]),
                    "motivo": o.motivo[i],
                    "valores": linhas[i],
                }
                for i, cid in enumerate(celulas)
            ],
        }
    )
    return saida


@router.post("/camada", response_model=Saida, openapi_extra=LER)
def camada(corpo: PedidoCamada, auth: Auth = autenticado()):
    """A fronteira (ou as ordens pedidas) como camada GeoJSON: é o que o mapa desenha e o que se baixa."""
    exigir_escopo(auth, ESCOPO)
    _validar_pedido(corpo)
    ordens_incluidas = sorted(set(corpo.ordens_incluidas))
    if not ordens_incluidas or any(k < 1 or k > corpo.ordens for k in ordens_incluidas):
        raise ErroAPI(
            422,
            "ordens_incluidas_invalidas",
            f"ordens_incluidas tem de ser um subconjunto não vazio de 1..{corpo.ordens}",
        )
    with db.db(auth.contexto()) as cur:
        execucao = _execucao(cur, corpo.execucao_id)
        fatores = _fatores(cur, corpo.execucao_id, corpo.objetivos)
        celulas, linhas = _matriz(cur, execucao, corpo.objetivos)
        o = _ordenar(linhas, corpo.objetivos, corpo.ordens)
        escolhidas = [c for i, c in enumerate(celulas) if int(o.ordem[i]) in ordens_incluidas]
        geometrias = _geometrias(cur, escolhidas)
    nomes = [f["nome"] for f in _objetivos_json(corpo.objetivos, fatores)]
    posicao = {c: i for i, c in enumerate(celulas)}
    feicoes = []
    for cid in escolhidas:
        i = posicao[cid]
        propriedades = {"unidade_id": cid, "ordem": int(o.ordem[i])}
        for nome, valor in zip(nomes, linhas[i], strict=True):
            propriedades[nome] = valor
        feicoes.append({"type": "Feature", "id": cid, "geometry": geometrias[cid], "properties": propriedades})
    return {
        "type": "FeatureCollection",
        "features": feicoes,
        "metadados": {
            "execucao_id": corpo.execucao_id,
            "objetivos": _objetivos_json(corpo.objetivos, fatores),
            "ordens_incluidas": ordens_incluidas,
            "unidades_avaliadas": len(celulas),
            **o.como_dicionario(),
        },
    }


def _geometrias(cur, celulas: list[int]) -> dict[int, dict]:
    if not celulas:
        return {}
    cur.execute(
        "SELECT id, ST_AsGeoJSON(geom) AS g FROM plat.escala_celula WHERE id = ANY(%s)",
        (celulas,),
    )
    return {int(r["id"]): json.loads(r["g"]) for r in cur.fetchall()}

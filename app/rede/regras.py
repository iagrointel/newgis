"""Motor de regras de atributo de rede (item L4-29-regras-de-atributo-de-rede).

Três perfis de regra sobre `plat.rede_objeto` (migração 20260908T1934_regras_atributo_rede.sql),
com o mesmo vocabulário dos perfis de regra de atributo do Arcade (ver
docs/PARIDADE_REGRAS_ATRIBUTO.md):

  calculo    — escreve um atributo (`atributo_alvo`) no objeto com o valor da expressão;
  restricao  — RECUSA uma operação sobre o objeto quando a expressão é verdadeira
               (aqui: "fechar chave" — o chamador pergunta `checar_restricao` antes de fechar);
  validacao  — em lote, lista os objetos que infringem a regra (expressão verdadeira).

Semântica de tempo declarada (é a refutação do item: o adversário escreve "jusante de jusante" e
o motor não entra em laço): uma RODADA avalia cada regra UMA vez por objeto e grava; não existe
ponto fixo nem iteração até estabilizar. Uma regra que lê o próprio atributo que escreve
(`AtributoRede('x') + 1`) avança exatamente 1 por rodada; a rodada seguinte é uma ação nova e
explícita de quem opera. O orçamento de passos e o relógio do avaliador (`limite_passos`/
`limite_ms`, parâmetros documentados para teste) cortam expressão cara com erro NOMEADO, e um erro
de regra em restrição RECUSA (falha fechada) com o código nomeado na resposta — regra que não
consegue avaliar não pode autorizar.

Ausência é dado, não erro: `TensaoAlimentador()` de um trecho sem alimentador é NULO, e `nulo`
nunca recusa (lógica de três valores, igual ao SQL — `docs/EXPRESSAO.md` §5).
"""

import json
from typing import Any

from app import limites
from app.erros import ErroAPI
from app.expressao.avaliador_py import (
    PROIBIDOS,
    ErroExpressao,
    analisar,
    avaliar,
)

PERFIS = ("calculo", "restricao", "validacao")
CHAVE_REDE = "rede"  # reservada no contexto: um atributo chamado `rede` nunca a substitui
ATRIBUTO_JUSANTE = "clientes_jusante"  # atributo que alimenta ContarJusante()
ATRIBUTO_TENSAO_ALIMENTADOR = "tensao_kv"  # atributo do ALIMENTADOR que alimenta TensaoAlimentador()

# chaves do dicionário `rede` (contexto["rede"]), uma por função de rede — ver docs/EXPRESSAO.md §5
_CAMINHO_JUSANTE = "jusante"
_CAMINHO_TENSAO = "tensao_alimentador_kv"


def montar_contexto(objeto: dict, alimentador: dict | None = None) -> dict:
    """Contexto de avaliação de UM objeto de rede: os atributos do objeto achatados no topo (o que
    deixa `$tensao_kv` funcionar) mais a chave RESERVADA `rede` com o que vem da topologia —
    nível, subrede, alimentador, a jusante já calculada pelo motor e a tensão herdada do
    alimentador em um salto. A chave `rede` é gravada POR ÚLTIMO de propósito: se um atributo do
    objeto se chamar `rede`, a reserva vence."""
    atributos = objeto.get("atributos")
    if atributos is None:
        atributos = {}
    if type(atributos) is not dict:  # jsonb garante objeto; defesa barata contra uso errado da API
        raise ErroAPI(422, "tipo_invalido", "atributos do objeto de rede precisam ser um objeto JSON")
    contexto: dict[str, Any] = dict(atributos)
    jusante = atributos.get(ATRIBUTO_JUSANTE)
    tensao = None
    if alimentador is not None and type(alimentador.get("atributos")) is dict:
        tensao = alimentador["atributos"].get(ATRIBUTO_TENSAO_ALIMENTADOR)
    contexto[CHAVE_REDE] = {
        "nivel": objeto.get("nivel"),
        "subrede": objeto.get("subrede"),
        "alimentador": objeto.get("alimentador"),
        _CAMINHO_TENSAO: tensao,
        _CAMINHO_JUSANTE: jusante,
        "atributos": atributos,
    }
    return contexto


# ------------------------------------------------------------------ validação de regra (pura)


def validar_regra(
    *,
    perfil: str,
    nome: str,
    alvo_tipo: str,
    expressao: str,
    atributo_alvo: str | None = None,
) -> None:
    """Valida UMA regra sem tocar no banco (as mesmas checagens do CHECK da migração mais a
    sintaxe da expressão). Levanta ErroAPI 422 com código curto; não devolve nada."""
    if perfil not in PERFIS:
        raise ErroAPI(422, "perfil_invalido", f"perfil precisa ser um de: {', '.join(PERFIS)}")
    if not isinstance(nome, str) or not nome.strip():
        raise ErroAPI(422, "nome_invalido", "a regra precisa de um nome")
    if not isinstance(alvo_tipo, str) or not alvo_tipo.strip():
        raise ErroAPI(422, "alvo_tipo_invalido", "a regra precisa de um tipo de objeto alvo")
    if not isinstance(expressao, str) or not expressao.strip():
        raise ErroAPI(422, "expressao_invalida", "a regra precisa de uma expressão")
    if perfil == "calculo":
        if not isinstance(atributo_alvo, str) or not atributo_alvo.strip():
            raise ErroAPI(422, "atributo_alvo_obrigatorio", "regra de cálculo precisa de atributo_alvo")
        if atributo_alvo in PROIBIDOS:
            raise ErroAPI(422, "campo_nao_permitido", f"campo não permitido: {atributo_alvo}")
    elif atributo_alvo is not None:
        raise ErroAPI(422, "atributo_alvo_proibido", "só regra de cálculo tem atributo_alvo")
    try:
        analisar(expressao)
    except ErroExpressao as e:
        raise ErroAPI(422, "expressao_invalida", f"{e.codigo}: {e}") from e


# ------------------------------------------------------------------ banco


def criar_regra(cur, tenant_id: int, *, perfil, nome, alvo_tipo, expressao, atributo_alvo=None,
                mensagem: str | None = None, prioridade: int = 0) -> dict:
    """Grava a regra (RLS do inquilino valendo pelo cursor). Teto de REDE_REGRA_MAX regras ativas
    por (inquilino, perfil) — desativar regra antiga é ação do operador, não poda automática."""
    validar_regra(
        perfil=perfil, nome=nome, alvo_tipo=alvo_tipo, expressao=expressao, atributo_alvo=atributo_alvo
    )
    cur.execute(
        "SELECT count(*) AS n FROM plat.rede_regra WHERE perfil = %s AND ativa", (perfil,)
    )
    n = int(cur.fetchone()["n"])
    if n >= limites.REDE_REGRA_MAX:
        raise ErroAPI(
            422, "regras_demais",
            f"{n} regras ativas no perfil '{perfil}'; o teto é {limites.REDE_REGRA_MAX}",
        )
    cur.execute(
        "INSERT INTO plat.rede_regra(tenant_id, perfil, nome, alvo_tipo, expressao, atributo_alvo, "
        "mensagem, prioridade) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id, perfil, nome, alvo_tipo, expressao, atributo_alvo, mensagem, prioridade, ativa",
        (tenant_id, perfil, nome, alvo_tipo, expressao, atributo_alvo, mensagem, int(prioridade)),
    )
    return cur.fetchone()


def _regras_ativas(cur, perfil: str, alvo_tipo: str) -> list[dict]:
    cur.execute(
        "SELECT id, perfil, nome, alvo_tipo, expressao, atributo_alvo, mensagem, prioridade "
        "FROM plat.rede_regra WHERE ativa AND perfil = %s AND alvo_tipo = %s "
        "ORDER BY prioridade DESC, nome LIMIT %s",
        (perfil, alvo_tipo, limites.REDE_REGRA_MAX),
    )
    return cur.fetchall()


def _objetos_do_tipo(cur, tipo: str) -> list[dict]:
    cur.execute(
        "SELECT id, tipo, codigo, nivel, subrede, alimentador, atributos FROM plat.rede_objeto "
        "WHERE tipo = %s ORDER BY codigo LIMIT %s",
        (tipo, limites.REDE_REGRAS_OBJETOS_MAX),
    )
    return cur.fetchall()


class _Alimentadores:
    """Memória de rodada para o salto alimentador → atributos (uma consulta por código distinto,
    não uma por objeto). Alimentador sem linha é NULO — ausência é dado."""

    def __init__(self, cur):
        self._cur = cur
        self._cache: dict[str, dict | None] = {}

    def de(self, objeto: dict) -> dict | None:
        codigo = objeto.get("alimentador")
        if not codigo:
            return None
        if codigo not in self._cache:
            self._cur.execute(
                "SELECT id, tipo, codigo, nivel, subrede, alimentador, atributos FROM plat.rede_objeto "
                "WHERE tipo = 'alimentador' AND codigo = %s",
                (codigo,),
            )
            self._cache[codigo] = self._cur.fetchone()
        return self._cache[codigo]


def _avaliar(regra: dict, contexto: dict, *, limite_passos: int | None, limite_ms: float | None) -> Any:
    kwargs: dict[str, Any] = {}
    if limite_passos is not None:
        kwargs["limite_passos"] = limite_passos
    if limite_ms is not None:
        kwargs["limite_ms"] = limite_ms
    return avaliar(analisar(regra["expressao"]), contexto, **kwargs)


# ------------------------------------------------------------------ restrição


def checar_restricao(cur, objeto: dict, *, limite_passos: int | None = None,
                     limite_ms: float | None = None) -> dict:
    """A pergunta "posso fechar esta chave?" de um objeto de rede. Recusa quando alguma regra de
    restrição ativa é VERDADEIRA para o objeto — e também quando a regra ERRA (falha fechada: o
    erro vem nomeado na recusa, nunca silencioso). Nulo não recusa (três valores, como o SQL)."""
    alimentadores = _Alimentadores(cur)
    contexto = montar_contexto(objeto, alimentadores.de(objeto))
    recusas: list[dict] = []
    for regra in _regras_ativas(cur, "restricao", objeto["tipo"]):
        try:
            valor = _avaliar(regra, contexto, limite_passos=limite_passos, limite_ms=limite_ms)
        except ErroExpressao as e:
            recusas.append({"regra": regra["nome"], "erro": e.codigo, "mensagem": str(e)})
            continue
        if valor is True:
            recusas.append({"regra": regra["nome"], "mensagem": regra["mensagem"]})
    return {"permitido": not recusas, "recusas": recusas}


# ------------------------------------------------------------------ cálculo (uma rodada, sem fixpoint)


def aplicar_calculo(cur, *, limite_passos: int | None = None, limite_ms: float | None = None) -> dict:
    """UMA rodada de cálculo: cada regra ativa do perfil cálculo avalia UMA vez por objeto do seu
    tipo e grava `atributo_alvo` quando o valor não é nulo. Reavaliar é rodar de novo (ação
    explícita) — é isto que mata o laço "jusante de jusante" da refutação."""
    alimentadores = _Alimentadores(cur)
    cur.execute(
        "SELECT id, perfil, nome, alvo_tipo, expressao, atributo_alvo, mensagem, prioridade "
        "FROM plat.rede_regra WHERE ativa AND perfil = 'calculo' "
        "ORDER BY prioridade DESC, nome LIMIT %s",
        (limites.REDE_REGRA_MAX,),
    )
    regras = cur.fetchall()
    escritos = 0
    erros: list[dict] = []
    total_erros = 0
    objetos_vistos: set[str] = set()
    for regra in regras:
        for objeto in _objetos_do_tipo(cur, regra["alvo_tipo"]):
            objetos_vistos.add(objeto["codigo"])
            contexto = montar_contexto(objeto, alimentadores.de(objeto))
            try:
                valor = _avaliar(regra, contexto, limite_passos=limite_passos, limite_ms=limite_ms)
            except ErroExpressao as e:
                total_erros += 1
                if len(erros) < limites.REDE_REGRAS_ERROS_MAX:
                    erros.append({"regra": regra["nome"], "objeto": objeto["codigo"], "erro": e.codigo})
                continue
            if valor is None:
                continue  # ausência não sobrescreve dado existente
            cur.execute(
                "UPDATE plat.rede_objeto SET atributos = jsonb_set(atributos, ARRAY[%s], %s::jsonb), "
                "atualizado_em = now() WHERE id = %s::uuid",
                (regra["atributo_alvo"], json.dumps(valor), str(objeto["id"])),
            )
            escritos += 1
    return {"regras": len(regras), "objetos": len(objetos_vistos), "escritos": escritos,
            "erros": erros, "erros_total": total_erros}


# ------------------------------------------------------------------ validação em lote


def rodar_validacao(cur, *, limite_passos: int | None = None, limite_ms: float | None = None) -> dict:
    """UMA rodada de validação: item por (regra, objeto) cuja expressão é VERDADEIRA. Erro de
    regra vira item com o código nomeado e a rodada CONTINUA (validação lista, não trava). Acima
    de REDE_REGRAS_ITENS_MAX a lista sai `truncado` — o teto é declarado, não escondido."""
    alimentadores = _Alimentadores(cur)
    cur.execute(
        "SELECT id, perfil, nome, alvo_tipo, expressao, atributo_alvo, mensagem, prioridade "
        "FROM plat.rede_regra WHERE ativa AND perfil = 'validacao' "
        "ORDER BY prioridade DESC, nome LIMIT %s",
        (limites.REDE_REGRA_MAX,),
    )
    regras = cur.fetchall()
    itens: list[dict] = []
    truncado = False
    for regra in regras:
        for objeto in _objetos_do_tipo(cur, regra["alvo_tipo"]):
            if len(itens) >= limites.REDE_REGRAS_ITENS_MAX:
                truncado = True
                break
            contexto = montar_contexto(objeto, alimentadores.de(objeto))
            try:
                valor = _avaliar(regra, contexto, limite_passos=limite_passos, limite_ms=limite_ms)
            except ErroExpressao as e:
                itens.append({"regra": regra["nome"], "objeto": objeto["codigo"], "erro": e.codigo})
                continue
            if valor is True:
                itens.append({"regra": regra["nome"], "objeto": objeto["codigo"],
                              "mensagem": regra["mensagem"]})
        if truncado:
            break
    return {"regras": len(regras), "itens": itens, "total": len(itens), "truncado": truncado}

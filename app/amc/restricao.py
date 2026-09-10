"""Restrição como objeto próprio do motor multicritério (item L3-04-restricoes; equivalente ao
Restricted/NoData do Weighted Overlay do ArcGIS, com o rigor de proveniência do motor de LT).

Decisões de conceito (laco/decomposicao/L3L6_CONCEITO.md, A6, e o esquema `docs/esquemas/amc_modelo.v1.json`,
`$defs.restricao`):

- restrição é objeto SEPARADO do peso: nunca é sorteada na robustez (`app.amc.robustez` já trata
  `fracao_vetada` como fixa em todo sorteio — este módulo só PRODUZ essa fração e o motivo, não muda a
  robustez nem a combinação);
- toda restrição carrega metadado obrigatório: `base` (`norma` — a lei veda — ou `precaucao` — vetamos por
  precaução, nunca dizendo que a lei proíbe), `fonte`, `camada`, `buffer_m` opcional; a versão da camada é a
  mesma ficha de proveniência que `app.amc.camadas.resolver` já congela por execução (este módulo não a
  duplica, só a referencia no relatório);
- a regra de veto é um objeto próprio (`regra.tipo`): `intersecta` (com ou sem `buffer_m`),
  `fracao_area_minima` (fração da área da unidade coberta pela camada, comparada a `fracao_minima`) e
  `atributo_igual` (a feição mais próxima/intersectante tem um atributo num conjunto de valores). O tipo
  `valor_raster` do esquema fica DECLARADAMENTE fora do escopo deste item — levanta erro claro, nunca finge
  suportar;
- buffer é sempre GEOGRÁFICO: a distância declarada em metros é testada com `ST_DWithin` sobre `geography`
  (GRS80), nunca sobre graus nem sobre uma projeção plana escolhida por acaso — é o mesmo padrão de área
  geodésica que `app.amc.crs` já documenta ("área das unidades sempre geodésica (ST_Area(geography))");
- composição de várias restrições é por OU: a unidade fica vetada se QUALQUER restrição da lista a vetar.
  A fração vetada final que `app.amc.combinacao.combinar` recebe é sempre 0,0 ou 1,0 — restrição veta,
  não pesa; não existe veto parcial que deixe passar metade da nota;
- unidade restrita sai com favorabilidade 0, motivo (a frase de `frase_motivo`, construída do metadado
  declarado no modelo — nunca inventada) e contagem separada POR restrição, para que o relatório diga
  qual das N restrições vetou cada unidade, não só "vetada";
- camada sem nenhuma feição na área de estudo NUNCA veta zero unidades em silêncio: `avaliar` levanta
  `ErroRestricao('camada_vazia', ...)` — quem chama decide se aborta o modelo inteiro ou registra o aviso,
  mas o silêncio (zero vetos por falta de dado, indistinguível de zero vetos por ausência real de
  sobreposição) é a falha que o adversário deste item cobra.

O módulo fala com o banco só pelo `cur` recebido (o mesmo cursor de dicionário do resto do `app.amc`,
`app.db.db(ctx)` em produção ou uma conexão de teste crua) — nunca abre pool próprio. As geometrias de
entrada são GeoJSON em EPSG:4326, como todo o resto do motor (`app.amc.vetorial`, `app.amc.zonal`).
"""

from __future__ import annotations

import json

TIPOS_REGRA = ("intersecta", "fracao_area_minima", "atributo_igual", "valor_raster")
BASES = ("norma", "precaucao")
_REGRAS_SUPORTADAS = ("intersecta", "fracao_area_minima", "atributo_igual")


class ErroRestricao(Exception):
    """Erro de contrato da avaliação de restrição. `codigo` é curto e estável; `mensagem` é a frase em
    português que vai para o 422/handoff; `detalhe` é o dicionário extra para depuração."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe or {}


def validar_restricao(restricao: dict) -> None:
    """Confere o que o JSON Schema do modelo não trava sozinho antes de qualquer consulta ao banco: buffer
    não-negativo, regra conhecida e com os parâmetros que ela exige, base declarada. Chamado por `avaliar`
    e reaproveitável por quem valida o modelo inteiro antes de rodar."""
    if not isinstance(restricao, dict):
        raise ErroRestricao("restricao_invalida", "a restrição precisa ser um objeto")
    rid = restricao.get("id")
    base = restricao.get("base")
    if base not in BASES:
        raise ErroRestricao("base_desconhecida",
                             f"restrição {rid!r}: base desconhecida {base!r} (precisa ser 'norma' ou "
                             f"'precaucao')", {"restricao": rid})
    buffer_m = restricao.get("buffer_m")
    if buffer_m is not None:
        if isinstance(buffer_m, bool) or not isinstance(buffer_m, (int, float)):
            raise ErroRestricao("buffer_invalido", f"restrição {rid!r}: buffer_m precisa ser número, veio "
                                 f"{buffer_m!r}", {"restricao": rid})
        if buffer_m < 0:
            raise ErroRestricao("buffer_negativo",
                                 f"restrição {rid!r}: buffer_m negativo ({buffer_m:g}); a faixa de estudo não "
                                 f"pode ter distância negativa — use 0 para 'sem buffer' (só interseção)",
                                 {"restricao": rid, "buffer_m": buffer_m})
    regra = restricao.get("regra")
    if not isinstance(regra, dict) or regra.get("tipo") not in TIPOS_REGRA:
        raise ErroRestricao("regra_desconhecida",
                             f"restrição {rid!r}: tipo de regra desconhecido "
                             f"{(regra or {}).get('tipo')!r} (admitidos: {', '.join(TIPOS_REGRA)})",
                             {"restricao": rid})
    tipo = regra["tipo"]
    if tipo not in _REGRAS_SUPORTADAS:
        raise ErroRestricao("regra_nao_suportada",
                             f"restrição {rid!r}: regra {tipo!r} está fora do escopo deste item (só "
                             f"{', '.join(_REGRAS_SUPORTADAS)}; 'valor_raster' fica para item futuro, "
                             f"declarado, nunca fingido)", {"restricao": rid, "tipo": tipo})
    if tipo == "fracao_area_minima":
        fm = regra.get("fracao_minima")
        if isinstance(fm, bool) or not isinstance(fm, (int, float)) or not (0.0 <= fm <= 1.0):
            raise ErroRestricao("fracao_minima_invalida",
                                 f"restrição {rid!r}: fracao_minima precisa estar entre 0 e 1, veio {fm!r}",
                                 {"restricao": rid})
    if tipo == "atributo_igual":
        if not regra.get("atributo"):
            raise ErroRestricao("atributo_ausente", f"restrição {rid!r}: regra 'atributo_igual' exige "
                                 f"'atributo' (nome do campo na camada)", {"restricao": rid})
        if not regra.get("valores"):
            raise ErroRestricao("valores_ausentes", f"restrição {rid!r}: regra 'atributo_igual' exige "
                                 f"'valores' (lista não vazia)", {"restricao": rid})


def frase_motivo(restricao: dict, motivo_especifico: str | None = None) -> str:
    """Frase do relatório a partir SÓ do metadado declarado no modelo (nunca uma alegação nova): 'a norma
    veda' quando `base == 'norma'`, 'vetamos por precaução' quando `base == 'precaucao'` — a regra de
    linguagem da casa é dura: nunca dizer que a lei proíbe quando o veto é por precaução da casa."""
    base = restricao.get("base")
    if base not in BASES:
        raise ErroRestricao("base_desconhecida", f"base de restrição desconhecida: {base!r}")
    nome = restricao.get("nome") or restricao.get("id") or "restrição sem nome"
    corpo = motivo_especifico or restricao.get("motivo") or nome
    if base == "norma":
        base_legal = restricao.get("base_legal")
        sufixo = f" ({base_legal})" if base_legal else ""
        return f"a norma veda: {corpo}{sufixo}"
    return f"vetamos por precaução: {corpo}"


def _feicoes_para_sql(feicoes: list) -> tuple[list[str], list[str | None]]:
    geoms = [json.dumps(f[1]) for f in feicoes]
    atributos = [str(f[2]) if len(f) > 2 and f[2] is not None else None for f in feicoes]
    return geoms, atributos


def _avaliar_intersecta(cur, unidades: list[tuple[str, dict]], feicoes: list, regra: dict,
                         buffer_m: float) -> dict[str, dict]:
    uids = [u[0] for u in unidades]
    ugeoms = [json.dumps(u[1]) for u in unidades]
    cgeoms, cattrs = _feicoes_para_sql(feicoes)
    atributo_igual = regra["tipo"] == "atributo_igual"
    valores = [str(v) for v in regra.get("valores", [])] if atributo_igual else None
    cur.execute(
        """
        WITH u AS (
            SELECT ord, uid, ST_SetSRID(ST_GeomFromGeoJSON(g), 4326) AS geom
            FROM unnest(%(uids)s::text[], %(ugeoms)s::text[]) WITH ORDINALITY AS t(uid, g, ord)
        ), c AS (
            SELECT ST_SetSRID(ST_GeomFromGeoJSON(g), 4326) AS geom, attr
            FROM unnest(%(cgeoms)s::text[], %(cattrs)s::text[]) WITH ORDINALITY AS t(g, attr, ord)
        ), pareado AS (
            SELECT u.uid,
                   CASE WHEN %(buffer)s > 0
                        THEN ST_DWithin(u.geom::geography, c.geom::geography, %(buffer)s)
                        ELSE ST_Intersects(u.geom, c.geom)
                   END AS toca,
                   c.attr
            FROM u LEFT JOIN c ON true
        )
        SELECT uid,
               bool_or(toca AND (%(valores)s::text[] IS NULL OR attr = ANY(%(valores)s::text[]))) AS vetada
        FROM pareado
        GROUP BY uid
        """,
        {"uids": uids, "ugeoms": ugeoms, "cgeoms": cgeoms, "cattrs": cattrs,
         "buffer": float(buffer_m), "valores": valores},
    )
    por_uid = {r["uid"]: bool(r["vetada"]) for r in cur.fetchall()}
    return {uid: {"vetada": por_uid.get(uid, False), "fracao_intersectada": None} for uid in uids}


def _avaliar_fracao(cur, unidades: list[tuple[str, dict]], feicoes: list, regra: dict,
                     buffer_m: float) -> dict[str, dict]:
    uids = [u[0] for u in unidades]
    ugeoms = [json.dumps(u[1]) for u in unidades]
    cgeoms, _ = _feicoes_para_sql(feicoes)
    fracao_minima = float(regra["fracao_minima"])
    # a camada some com buffer_m > 0 ANTES da interseção — a faixa de exclusão cresce, o critério continua
    # sendo fração de área, calculada sempre em ST_Area(geography), o mesmo padrão de app.amc.crs.
    cur.execute(
        """
        WITH u AS (
            SELECT ord, uid, ST_SetSRID(ST_GeomFromGeoJSON(g), 4326) AS geom
            FROM unnest(%(uids)s::text[], %(ugeoms)s::text[]) WITH ORDINALITY AS t(uid, g, ord)
        ), c AS (
            SELECT ST_SetSRID(ST_GeomFromGeoJSON(g), 4326) AS geom
            FROM unnest(%(cgeoms)s::text[]) AS t(g)
        ), c_ajustada AS (
            SELECT CASE WHEN %(buffer)s > 0
                        THEN ST_Buffer(geom::geography, %(buffer)s)::geometry
                        ELSE geom
                   END AS geom
            FROM c
        ), uniao AS (
            SELECT ST_Union(geom) AS geom FROM c_ajustada
        )
        SELECT u.uid,
               COALESCE(
                   ST_Area(ST_Intersection(u.geom, uniao.geom)::geography)
                   / NULLIF(ST_Area(u.geom::geography), 0),
                   0.0
               ) AS fracao
        FROM u, uniao
        """,
        {"uids": uids, "ugeoms": ugeoms, "cgeoms": cgeoms, "buffer": float(buffer_m)},
    )
    saida = {}
    for r in cur.fetchall():
        fracao = float(r["fracao"])
        saida[r["uid"]] = {"vetada": fracao >= fracao_minima, "fracao_intersectada": fracao}
    for uid in uids:
        saida.setdefault(uid, {"vetada": False, "fracao_intersectada": 0.0})
    return saida


def avaliar(cur, unidades: list[tuple[str, dict]], feicoes: list, restricao: dict) -> dict[str, dict]:
    """Avalia UMA restrição sobre a grade `unidades` = [(unidade_id, geojson 4326)] contra a camada já lida
    em `feicoes` = [(feicao_id, geojson 4326, atributo|None)] (a mesma forma que `app.amc.vetorial.extrair`
    usa — quem chama já resolveu a camada do modelo, seja do acervo seja do catálogo do inquilino).

    Devolve ``{unidade_id: {"vetada": bool, "fracao_intersectada": float|None}}``. Camada vazia levanta
    ``ErroRestricao('camada_vazia', ...)`` — nunca devolve vetada=False para todas por falta de dado sem
    avisar (a refutação exigida pelo item)."""
    validar_restricao(restricao)
    if not feicoes:
        raise ErroRestricao(
            "camada_vazia",
            f"a camada da restrição {restricao.get('id')!r} não tem nenhuma feição na área de estudo: "
            f"camada sem feições na área — a avaliação é abortada, nunca vira zero unidades vetadas em "
            f"silêncio",
            {"restricao": restricao.get("id")},
        )
    if not unidades:
        raise ErroRestricao("sem_unidades", "não há nenhuma unidade de análise para avaliar a restrição")
    buffer_m = float(restricao.get("buffer_m") or 0.0)
    regra = restricao["regra"]
    if regra["tipo"] == "fracao_area_minima":
        return _avaliar_fracao(cur, unidades, feicoes, regra, buffer_m)
    return _avaliar_intersecta(cur, unidades, feicoes, regra, buffer_m)


def compor(unidades_ids: list[str], avaliacoes: list[tuple[dict, dict[str, dict]]]) -> dict:
    """Composição por OU de várias restrições já avaliadas (`avaliacoes` = [(restricao, resultado_de_avaliar)],
    na ordem declarada no modelo). Restrição nunca pesa: a fração vetada final de cada unidade é sempre 0,0
    ou 1,0 — 0,0 quando nenhuma restrição a vetou, 1,0 quando ao menos uma vetou.

    Devolve:
    - ``fracao_vetada``: lista alinhada a `unidades_ids`, pronta para `app.amc.combinacao.combinar` e
      `app.amc.robustez.simular_robustez` (que já tratam essa fração como fixa, nunca sorteada);
    - ``motivo``: a frase (`frase_motivo`) da PRIMEIRA restrição, na ordem declarada, que vetou cada
      unidade — nunca empilha motivos de restrições diferentes na mesma unidade;
    - ``contagem_por_restricao``: uma entrada por restrição com quantas unidades ELA vetou (independente
      de outra restrição já ter vetado a mesma unidade), para o relatório dizer "a restrição X vetou N
      unidades" sem se confundir com o total após o OU.
    """
    fracao_vetada = [0.0] * len(unidades_ids)
    motivo: list[str | None] = [None] * len(unidades_ids)
    contagem_por_restricao = []
    for restricao, resultado in avaliacoes:
        rid = restricao.get("id")
        n_vetadas = 0
        for i, uid in enumerate(unidades_ids):
            r = resultado.get(uid, {"vetada": False})
            if not r.get("vetada"):
                continue
            n_vetadas += 1
            if fracao_vetada[i] < 1.0:
                fracao_vetada[i] = 1.0
                motivo[i] = frase_motivo(restricao)
        contagem_por_restricao.append({
            "id": rid,
            "nome": restricao.get("nome"),
            "base": restricao.get("base"),
            "unidades_vetadas": n_vetadas,
            "total_unidades": len(unidades_ids),
        })
    return {
        "fracao_vetada": fracao_vetada,
        "motivo": motivo,
        "contagem_por_restricao": contagem_por_restricao,
        "unidades_vetadas_total": sum(1 for f in fracao_vetada if f >= 1.0),
    }

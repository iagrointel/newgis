"""Dividir/unir feição (item L2-03-edicao, hipótese "dividir, unir"). Geometria estrutural precisa do motor
geométrico do PostGIS — as fichas do mapa carregam geometria RECORTADA por tile (MVT), nunca a exata —, por
isso estas duas operações leem a geometria de verdade do banco e escrevem pela MESMA porta (`_inserir`/
`_apagar` de `app.edicao.servico`, C5 do conceito: uma porta só), nunca um `INSERT`/`DELETE` cru fora dela.

Escopo desta passagem: `unir` funciona para qualquer família de geometria (`ST_Union`, com `ST_LineMerge`
extra quando a camada é de linha, para não devolver uma coleção fragmentada quando as partes se tocam).
`dividir` está escopado a LineString/MultiLineString de UMA parte só — dividir polígono por uma linha de
corte é geometria mais cara (ST_Split exige a linha de corte inteira, não um ponto) e fica de fora, registrado
no handoff, não escondido."""

from __future__ import annotations

import json
from typing import Any

from app.catalogo import comum
from app.edicao.modelos import EdicoesEntrada, FeicaoAdicionar, FeicaoApagar
from app.edicao.servico import (
    _apagar,
    _exigir_dono_ou_admin,
    _inserir,
    _schema_tabela,
    camada_ou_404,
    exigir_camada_editavel,
)
from app.erros import ErroAPI

_CORPO_PADRAO = EdicoesEntrada()  # modo=transacao, sem crs (já está no SRID da camada), sem corrigir


def _linha_ou_404(cur, schema: str, tabela: str, globalid: str) -> dict:
    cur.execute(f'SELECT * FROM "{schema}"."{tabela}" WHERE globalid = %s FOR UPDATE', (globalid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"id": globalid})
    return r


def _conferir_versao(linha: dict, esperada: int | None) -> None:
    if esperada is not None and linha["versao"] != esperada:
        raise ErroAPI(
            409, "conflito_versao", "a feição foi alterada por outra sessão desde a versão lida",
            {"id": str(linha["globalid"]), "versao_enviada": esperada, "versao_atual": linha["versao"]},
        )


def unir(cur, auth, request, camada_id: str, ids: list[str], versoes: dict[str, int],
         atributos: dict | None = None) -> dict:
    if len(ids) < 2:
        raise ErroAPI(422, "uniao_minimo_dois", "união exige ao menos duas feições")
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    if dados.get("geometria") in (None, "nenhuma"):
        raise ErroAPI(422, "camada_sem_geometria", "esta camada não tem geometria para unir")
    schema, tabela = _schema_tabela(dados)

    # duas passagens deliberadas (achado desta rodada, ao rodar a suíte de novo após o achado do
    # adversário abaixo): existência/acesso (404) de todos os ids primeiro, só depois versão (422/409) de
    # todos — numa passagem só, o primeiro id da lista que existisse mas não tivesse versão declarada
    # disparava 422 antes de a lista chegar ao id inexistente/de outro inquilino, escondendo o 404 que os
    # dois testes de refutação (`feição inexistente`, `feição de outro inquilino`) exigem ver primeiro.
    linhas = [_linha_ou_404(cur, schema, tabela, gid) for gid in ids]
    for gid, r in zip(ids, linhas, strict=True):
        if gid not in versoes:
            # achado do adversário 07/09: sem exigir uma entrada por id, `versoes` incompleto (ou {})
            # deixava a checagem de concorrência rodar só para os ids presentes — a de origem sem
            # versão nunca era conferida contra uma edição concorrente, e o descarte era silencioso.
            raise ErroAPI(
                422, "versao_ausente", f"declare a versão lida de cada feição unida (faltou {gid})",
                {"id": gid},
            )
        _conferir_versao(r, versoes[gid])
        _exigir_dono_ou_admin(auth, dados, r)

    e_linha = "LineString" in str(dados.get("geometria"))
    expr = "ST_LineMerge(ST_Union(geom))" if e_linha else "ST_Union(geom)"
    cur.execute(
        f'SELECT ST_AsGeoJSON({expr}) AS g FROM "{schema}"."{tabela}" WHERE globalid = ANY(%s::uuid[])',
        ([str(g) for g in ids],),
    )
    geojson = json.loads(cur.fetchone()["g"])

    # atributos: o que o chamador mandar explicitamente, senão o da PRIMEIRA feição da lista (política
    # simples e declarada — nunca inventa um valor médio)
    atributos_base = atributos if atributos is not None else {
        c["nome"]: linhas[0].get(c["nome"]) for c in (dados.get("campos") or [])
    }

    for gid in ids:
        _apagar(cur, auth, dados, _CORPO_PADRAO, FeicaoApagar(id=gid, versao=None))

    resultado, avisos = _inserir(
        cur, auth, dados, _CORPO_PADRAO, FeicaoAdicionar(atributos=atributos_base, geometria=geojson)
    )
    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
        "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid",
        (item["id"],),
    )
    comum.registrar_evento(cur, request, "camadas/unir", "item", item["id"],
                            {"ids_origem": ids, "id_novo": resultado.id})
    return {"sucesso": True, "id": resultado.id, "fid": resultado.fid, "versao": resultado.versao,
            "ids_apagados": ids, "avisos": avisos}


def dividir(cur, auth, request, camada_id: str, globalid: str, versao: int | None,
            ponto: list[float]) -> dict:
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    geom_tipo = str(dados.get("geometria") or "")
    if "LineString" not in geom_tipo:
        raise ErroAPI(
            422, "divisao_nao_suportada",
            "esta passagem só divide linha (LineString/MultiLineString de uma parte); "
            f"a camada é {geom_tipo!r}",
        )
    schema, tabela = _schema_tabela(dados)
    atual = _linha_ou_404(cur, schema, tabela, globalid)
    _conferir_versao(atual, versao)
    _exigir_dono_ou_admin(auth, dados, atual)

    cur.execute(
        f'SELECT ST_NumGeometries(geom) AS n FROM "{schema}"."{tabela}" WHERE globalid = %s', (globalid,)
    )
    if geom_tipo == "MultiLineString" and cur.fetchone()["n"] != 1:
        raise ErroAPI(422, "divisao_nao_suportada", "só divide MultiLineString com uma única parte")

    cur.execute(
        f'SELECT ST_LineLocatePoint(ST_LineMerge(geom), ST_SetSRID(ST_MakePoint(%s, %s), %s)) AS fracao '
        f'FROM "{schema}"."{tabela}" WHERE globalid = %s',
        (ponto[0], ponto[1], int(dados["srid"]), globalid),
    )
    fracao = cur.fetchone()["fracao"]
    if fracao is None or fracao <= 0.0 or fracao >= 1.0:
        raise ErroAPI(
            422, "ponto_de_divisao_invalido",
            "o ponto informado cai numa ponta da linha (ou fora dela) — escolha um ponto no meio",
            {"fracao": fracao},
        )
    cur.execute(
        f'SELECT ST_AsGeoJSON(ST_LineSubstring(ST_LineMerge(geom), 0, %s)) AS a, '
        f'ST_AsGeoJSON(ST_LineSubstring(ST_LineMerge(geom), %s, 1)) AS b '
        f'FROM "{schema}"."{tabela}" WHERE globalid = %s',
        (fracao, fracao, globalid),
    )
    partes = cur.fetchone()
    atributos_base = {c["nome"]: atual.get(c["nome"]) for c in (dados.get("campos") or [])}

    _apagar(cur, auth, dados, _CORPO_PADRAO, FeicaoApagar(id=globalid, versao=None))
    resultados: list[dict[str, Any]] = []
    for chave in ("a", "b"):
        r, _av = _inserir(
            cur, auth, dados, _CORPO_PADRAO,
            FeicaoAdicionar(atributos=dict(atributos_base), geometria=json.loads(partes[chave])),
        )
        resultados.append({"id": r.id, "fid": r.fid, "versao": r.versao})

    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
        "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid",
        (item["id"],),
    )
    comum.registrar_evento(cur, request, "camadas/dividir", "item", item["id"],
                            {"id_origem": globalid, "novas": [r["id"] for r in resultados]})
    return {"sucesso": True, "id_apagado": globalid, "novas": resultados}

"""Histórico por feição e restauração (item L2-03-edicao, complemento do L2-03-a): lê `plat.feicao_historico`
(gravado por gatilho — item 20260907T1025, vale para QUALQUER escrita na tabela de camada, não só a que passa
pela API) e restaura um estado anterior aplicando-o pela MESMA porta de escrita (`_inserir`/`_atualizar` de
`app.edicao.servico`, C5: uma porta só) — a restauração em si também fica gravada no histórico, com
`operacao='restaurar'`, porque passa pelos MESMOS gatilhos `tg_versao`/`tg_historico` da tabela.

Restaurar quando a feição ainda existe = UPDATE para o estado gravado em `atributos_depois`/`geom_depois` da
linha de histórico escolhida (a versão otimista do INSERT/UPDATE atual continua valendo — outra sessão pode ter
mexido desde então, e a restauração não ignora isso). Restaurar quando a feição foi apagada = re-INSERT com o
MESMO globalid (senão qualquer referência externa a esse id — anexo, seleção salva, link — quebra em silêncio)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import psycopg2

from app.catalogo import comum
from app.edicao.modelos import UUID_PADRAO
from app.edicao.servico import (
    RESERVADOS,
    _exigir_dono_ou_admin,
    _ident,
    _preparar_geometria,
    _schema_tabela,
    camada_ou_404,
    exigir_camada_editavel,
    validar_atributos,
)
from app.erros import ErroAPI
from app.limites import HISTORICO_LISTA_MAX

_ = UUID_PADRAO  # reexportado para quem valida globalid nas rotas (mesmo padrão de FeicaoAtualizar.id)


def _linha_json(r: dict) -> dict:
    return {
        "id": r["id"],
        "operacao": r["operacao"],
        "versao": r["versao"],
        "atributos_antes": r["atributos_antes"],
        "atributos_depois": r["atributos_depois"],
        "geometria_antes": json.loads(r["geom_antes"]) if r["geom_antes"] else None,
        "geometria_depois": json.loads(r["geom_depois"]) if r["geom_depois"] else None,
        "usuario_id": r["usuario_id"],
        "momento": r["momento"].isoformat() if r["momento"] else None,
    }


def _cursor_par(cursor: str | None) -> tuple[datetime, int] | None:
    """Cursor chaveset "<epoch com microssegundos>|<id>" da página anterior — epoch (não ISO) porque o
    cursor viaja em query string, onde o '+' do fuso vira espaço e corromperia o valor. Inválido = 400,
    nunca silêncio: um cursor quebrado que virasse "primeira página" faria o cliente varrer o histórico
    duas vezes sem perceber."""
    if not cursor:
        return None
    try:
        momento_txt, id_txt = cursor.rsplit("|", 1)
        return datetime.fromtimestamp(float(momento_txt), tz=timezone.utc), int(id_txt)
    except (ValueError, TypeError, OverflowError, OSError) as e:
        raise ErroAPI(400, "cursor_invalido", "cursor de paginação inválido") from e


def _dif_atributos(antes: dict | None, depois: dict | None) -> dict:
    """Diff campo a campo (sem os campos de rastreio/sistema, que mudam em TODA escrita e não são decisão
    do editor). `mudou` por valor — o mesmo padrão do diff de reconciliação de ramos (L2-13-a), para que
    exista UMA resposta só para "o que mudou"."""
    a, d = antes or {}, depois or {}
    campos = sorted((set(a) | set(d)) - set(RESERVADOS))
    return {c: {"antes": a.get(c), "depois": d.get(c), "mudou": a.get(c) != d.get(c)} for c in campos}


def _dif_geometria(cur, r: dict, srid: int | None) -> dict | None:
    """Área/comprimento antes e depois em METROS (geography sobre o geom reprojetado para 4326 — o GeoJSON
    do histórico está no SRID da camada). NULL quando a camada não tem geometria ou a operação não a toca."""
    if not srid or (r["geom_antes"] is None and r["geom_depois"] is None):
        return None
    cur.execute(
        "SELECT "
        " CASE WHEN %(ga)s IS NOT NULL THEN ST_Area((ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(ga)s), %(srid)s), 4326))::geography) END AS area_antes_m2,"
        " CASE WHEN %(gd)s IS NOT NULL THEN ST_Area((ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(gd)s), %(srid)s), 4326))::geography) END AS area_depois_m2,"
        " CASE WHEN %(ga)s IS NOT NULL THEN ST_Length((ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(ga)s), %(srid)s), 4326))::geography) END AS comp_antes_m,"
        " CASE WHEN %(gd)s IS NOT NULL THEN ST_Length((ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(gd)s), %(srid)s), 4326))::geography) END AS comp_depois_m",
        {"ga": r["geom_antes"], "gd": r["geom_depois"], "srid": int(srid)},
    )
    m = cur.fetchone()
    return {
        "mudou": r["geom_antes"] != r["geom_depois"],
        "area_antes_m2": m["area_antes_m2"],
        "area_depois_m2": m["area_depois_m2"],
        "comprimento_antes_m": m["comp_antes_m"],
        "comprimento_depois_m": m["comp_depois_m"],
    }


def listar(
    cur, camada_id: str, globalid: str, cursor: str | None = None,
    limite: int | None = None, dif: bool = False,
) -> dict:
    """Portão: "histórico consultável" — quem, quando, o quê, mais recente primeiro. Só exige que a camada seja
    legível (a mesma RLS de `plat.item`); não exige privilégio de edição (consultar histórico não é editar).

    Paginação chaveset por (momento, id) — refutação do adversário: 100 mil versões de uma feição têm de ser
    percorríveis SEM deslocamento (OFFSET varre de novo o que já foi lido e mistura páginas se uma escrita
    acontece no meio do percurso; o chaveset é estável nos dois casos). `proximo_cursor` ausente = acabou.
    `dif=1` anexa o diff campo a campo e da geometria já calculado (área/comprimento antes/depois), para a
    tela não recalcular nada."""
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    limite = min(limite or HISTORICO_LISTA_MAX, HISTORICO_LISTA_MAX)
    par = _cursor_par(cursor)
    cur.execute(
        "SELECT count(*) AS n FROM plat.feicao_historico "
        "WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s",
        (schema, tabela, globalid),
    )
    total = cur.fetchone()["n"]
    cur.execute(
        "SELECT id, operacao, versao, atributos_antes, atributos_depois, geom_antes, geom_depois, usuario_id, "
        "momento FROM plat.feicao_historico "
        "WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s "
        "AND (%s::timestamptz IS NULL OR (momento, id) < (%s::timestamptz, %s::bigint)) "
        "ORDER BY momento DESC, id DESC LIMIT %s",
        (schema, tabela, globalid, par[0] if par else None, par[0] if par else None,
         par[1] if par else None, limite + 1),
    )
    linhas = cur.fetchall()
    tem_mais = len(linhas) > limite
    linhas = linhas[:limite]
    srid = dados.get("srid")
    entradas = []
    for r in linhas:
        e = _linha_json(r)
        if dif:
            e["dif"] = {
                "atributos": _dif_atributos(r["atributos_antes"], r["atributos_depois"]),
                "geometria": _dif_geometria(cur, r, srid),
            }
        entradas.append(e)
    proximo = None
    if tem_mais and linhas:
        ultimo = linhas[-1]
        proximo = f"{ultimo['momento'].timestamp():.6f}|{ultimo['id']}"
    return {"entradas": entradas, "total": total, "proximo_cursor": proximo}


def como_era(
    cur, camada_id: str, em: datetime, cursor: str | None = None, limite: int | None = None,
) -> dict:
    """"Como era a camada em <em>" (o historicMoment do FeatureServer, portão L2-03-d): a view temporal é
    MONTADA DO HISTÓRICO — para cada globalid, a entrada mais recente até `em`; quem terminou apagado não
    aparece. Não toca a tabela viva: feição sem NENHUMA linha de histórico (criada antes de o gatilho existir
    e nunca editada) não é reconstruível e não entra — fronteira declarada no relatório do item."""
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    limite = min(limite or HISTORICO_LISTA_MAX, HISTORICO_LISTA_MAX)
    cur.execute(
        "WITH ultima AS ("
        " SELECT DISTINCT ON (globalid) globalid, operacao, versao, atributos_depois, geom_depois"
        " FROM plat.feicao_historico"
        " WHERE schema_dado = %(s)s AND tabela_dado = %(t)s AND momento <= %(em)s"
        " ORDER BY globalid, momento DESC, id DESC"
        ") SELECT count(*) AS n FROM ultima WHERE operacao <> 'apagar'",
        {"s": schema, "t": tabela, "em": em},
    )
    total = cur.fetchone()["n"]
    cur.execute(
        "WITH ultima AS ("
        " SELECT DISTINCT ON (globalid) globalid, operacao, versao, atributos_depois, geom_depois"
        " FROM plat.feicao_historico"
        " WHERE schema_dado = %(s)s AND tabela_dado = %(t)s AND momento <= %(em)s"
        " ORDER BY globalid, momento DESC, id DESC"
        ") SELECT globalid, versao, atributos_depois, geom_depois FROM ultima"
        " WHERE operacao <> 'apagar' AND (%(cursor)s::uuid IS NULL OR globalid > %(cursor)s::uuid)"
        " ORDER BY globalid LIMIT %(lim)s",
        {"s": schema, "t": tabela, "em": em, "cursor": cursor, "lim": limite + 1},
    )
    linhas = cur.fetchall()
    tem_mais = len(linhas) > limite
    linhas = linhas[:limite]
    feicoes = [
        {
            "id": str(r["globalid"]),
            "versao": r["versao"],
            "atributos": {
                c: v for c, v in (r["atributos_depois"] or {}).items() if c not in RESERVADOS
            },
            "geometria": json.loads(r["geom_depois"]) if r["geom_depois"] else None,
        }
        for r in linhas
    ]
    return {
        "em": em.isoformat(),
        "total": total,
        "feicoes": feicoes,
        "proximo_cursor": str(linhas[-1]["globalid"]) if tem_mais and linhas else None,
    }


def _historico_ou_404(cur, schema: str, tabela: str, globalid: str, historico_id: int) -> dict:
    cur.execute(
        "SELECT id, operacao, versao, atributos_depois, geom_depois FROM plat.feicao_historico "
        "WHERE id = %s AND schema_dado = %s AND tabela_dado = %s AND globalid = %s",
        (historico_id, schema, tabela, globalid),
    )
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "historico_inexistente", "entrada de histórico inexistente para esta feição")
    return r


def restaurar(cur, auth, request, camada_id: str, globalid: str, historico_id: int) -> dict:
    """Restaura a feição para o estado gravado em `atributos_depois`/`geom_depois` da entrada escolhida.
    Reaplica pela mesma validação de domínio/tipo/geometria de uma edição normal (uma regra que valia quando o
    estado foi gravado pode ter mudado desde então — restaurar não é um caminho que pula validação atual)."""
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)
    schema, tabela = _schema_tabela(dados)
    hist = _historico_ou_404(cur, schema, tabela, globalid, historico_id)
    if hist["operacao"] == "apagar":
        raise ErroAPI(
            409, "nada_a_restaurar",
            "esta entrada é o registro de uma exclusão (sem estado 'depois' para restaurar); escolha a "
            "entrada anterior a ela",
        )
    atributos_alvo = dict(hist["atributos_depois"] or {})
    for campo in RESERVADOS:
        atributos_alvo.pop(campo, None)
    geometria_alvo = json.loads(hist["geom_depois"]) if hist["geom_depois"] else None
    tem_geom = dados.get("geometria") not in (None, "nenhuma")

    cur.execute(f'SELECT * FROM "{schema}"."{tabela}" WHERE globalid = %s FOR UPDATE', (globalid,))
    atual = cur.fetchone()

    atributos_limpos, avisos = validar_atributos(atributos_alvo, dados, "adicionar" if atual is None else "atualizar")

    if atual is None:
        # feição apagada: re-INSERT com o MESMO globalid (referências externas continuam válidas)
        colunas = ["globalid", *atributos_limpos.keys()]
        valores: list[Any] = [globalid, *atributos_limpos.values()]
        campos_sql = ["%s", *(["%s"] * len(atributos_limpos))]
        if tem_geom and geometria_alvo is not None:
            wkb, _aviso = _preparar_geometria(cur, geometria_alvo, None, dados, True)
            colunas.append("geom")
            campos_sql.append("ST_SetSRID(ST_GeomFromWKB(%s), %s)")
            valores += [psycopg2.Binary(wkb), int(dados["srid"])]
        cols_sql = ", ".join(_ident(c) if c not in ("globalid", "geom") else c for c in colunas)
        cur.execute(
            f'INSERT INTO "{schema}"."{tabela}" ({cols_sql}) VALUES ({", ".join(campos_sql)}) '
            f"RETURNING fid, globalid, versao",
            valores,
        )
        r = cur.fetchone()
        resultado = {"sucesso": True, "id": str(r["globalid"]), "fid": r["fid"], "versao": r["versao"],
                     "recriada": True}
    else:
        _exigir_dono_ou_admin(auth, dados, atual)
        sets = [f"{_ident(c)} = %s" for c in atributos_limpos]
        valores = list(atributos_limpos.values())
        if tem_geom and geometria_alvo is not None and not (dados.get("edicao") or {}).get("geometria_travada"):
            wkb, _aviso = _preparar_geometria(cur, geometria_alvo, None, dados, True)
            sets.append("geom = ST_SetSRID(ST_GeomFromWKB(%s), %s)")
            valores += [psycopg2.Binary(wkb), int(dados["srid"])]
        if sets:
            valores.append(globalid)
            cur.execute(
                f'UPDATE "{schema}"."{tabela}" SET {", ".join(sets)} WHERE globalid = %s '
                f"RETURNING fid, versao",
                valores,
            )
            r = cur.fetchone()
            resultado = {"sucesso": True, "id": globalid, "fid": r["fid"], "versao": r["versao"], "recriada": False}
        else:
            resultado = {"sucesso": True, "id": globalid, "fid": atual["fid"], "versao": atual["versao"],
                         "recriada": False}

    # marca a própria restauração no histórico com um registro A MAIS (operacao='restaurar'); o que tg_historico
    # já gravou sozinho para o INSERT/UPDATE acima ('inserir'/'atualizar') NUNCA é reescrito — histórico só cresce
    cur.execute(
        "INSERT INTO plat.feicao_historico (tenant_id, schema_dado, tabela_dado, fid, globalid, operacao, "
        "versao, atributos_depois, geom_depois, usuario_id) VALUES (plat.tenant_atual(), %s, %s, %s, %s, "
        "'restaurar', %s, %s, %s, %s)",
        (schema, tabela, resultado["fid"], globalid, resultado["versao"],
         comum.jsonb(atributos_limpos), json.dumps(geometria_alvo) if geometria_alvo else None,
         auth.usuario_id),
    )
    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
        "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid",
        (item["id"],),
    )
    comum.registrar_evento(
        cur, request, "camadas/restaurar", "item", item["id"],
        {"globalid": globalid, "historico_id": historico_id, "recriada": resultado["recriada"]},
    )
    resultado["avisos"] = avisos
    return resultado

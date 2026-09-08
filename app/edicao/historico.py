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


def listar(cur, camada_id: str, globalid: str) -> list[dict]:
    """Portão: "histórico consultável" — quem, quando, o quê, mais recente primeiro. Só exige que a camada seja
    legível (a mesma RLS de `plat.item`); não exige privilégio de edição (consultar histórico não é editar)."""
    _item, dados = camada_ou_404(cur, camada_id)
    schema, tabela = _schema_tabela(dados)
    cur.execute(
        "SELECT id, operacao, versao, atributos_antes, atributos_depois, geom_antes, geom_depois, usuario_id, "
        "momento FROM plat.feicao_historico WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s "
        "ORDER BY momento DESC, id DESC LIMIT %s",
        (schema, tabela, globalid, HISTORICO_LISTA_MAX),
    )
    return [_linha_json(r) for r in cur.fetchall()]


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

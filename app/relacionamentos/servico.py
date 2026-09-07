"""Regras de classe de relacionamento entre camadas do inquilino (item L2-10-b-relacionamentos).

Chave estrangeira real (1:N/1:1 composto ou simples) e gatilho de junção (N:M) são escritos pelo BANCO
(migração `20260907T1244_relacionamentos.sql`, funções `plat.relacionamento_fk_aplicar`/`_fk_remover`/
`_cardinalidade_aplicar`); esta camada só chama essas funções depois de gravar/apagar a linha de
`plat.relacionamento`. Nenhuma rota monta DDL — o mesmo padrão do L2-10-a."""

from __future__ import annotations

import psycopg2

from app.auth import comum as auth_comum
from app.catalogo.comum import uuid_ok
from app.dominios.servico import camada_ou_404
from app.erros import ErroAPI

ERROS = {
    "camada_sem_tabela": (404, "camada sem tabela associada"),
    "sem_tenant_no_contexto": (403, "operação fora do inquilino da sessão"),
    "relacionamento_invalido": (404, "relacionamento inexistente ou não é N:M"),
    "cardinalidade_maxima_excedida": (422, "cardinalidade máxima excedida"),
    "cardinalidade_minima_violada": (422, "a remoção deixaria a cardinalidade mínima violada"),
}


def erro_do_banco(e: Exception) -> ErroAPI:
    if isinstance(e, psycopg2.errors.RaiseException):
        codigo = (e.diag.message_primary or "").strip()
        detalhe = (e.diag.message_detail or "").strip()
        if codigo == "relacionamento_valor_inexistente":
            return ErroAPI(404, "relacionamento_valor_inexistente",
                           f"valor inexistente do lado {(e.diag.column_name or '?')!r}: {detalhe}",
                           {"lado": e.diag.column_name, "valor": detalhe})
        if codigo in ERROS:
            status, mensagem = ERROS[codigo]
            return ErroAPI(status, codigo, f"{mensagem} ({detalhe})" if detalhe else mensagem)
    return auth_comum.erro_do_banco(e)


def relacionamento_ou_404(cur, rel_id: str) -> dict:
    rid = uuid_ok(rel_id, "relacionamento_inexistente", "relacionamento inexistente")
    cur.execute("SELECT * FROM plat.relacionamento WHERE id = %s::uuid", (rid,))
    r = cur.fetchone()
    if r is None:
        raise ErroAPI(404, "relacionamento_inexistente", "relacionamento inexistente")
    return r


def relacionamento_json(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "origem_item_id": str(r["origem_item_id"]),
        "destino_item_id": str(r["destino_item_id"]),
        "cardinalidade": r["cardinalidade"],
        "chave_origem": r["chave_origem"],
        "chave_destino": r["chave_destino"],
        "composto": r["composto"],
        "nome_direto": r["nome_direto"],
        "nome_inverso": r["nome_inverso"],
        "cardinalidade_min": r["cardinalidade_min"],
        "cardinalidade_max": r["cardinalidade_max"],
        "limite_relacionados": r["limite_relacionados"],
        "criado_em": r["criado_em"].isoformat() if r.get("criado_em") else None,
    }


def criar(cur, entrada, usuario_id: int) -> dict:
    origem = camada_ou_404(cur, entrada.origem_item_id)
    destino = camada_ou_404(cur, entrada.destino_item_id)
    try:
        cur.execute(
            "INSERT INTO plat.relacionamento (tenant_id, origem_item_id, destino_item_id, cardinalidade, "
            "chave_origem, chave_destino, composto, nome_direto, nome_inverso, cardinalidade_min, "
            "cardinalidade_max, limite_relacionados, criado_por) "
            "VALUES (plat.tenant_atual(), %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING *",
            (str(origem["id"]), str(destino["id"]), entrada.cardinalidade, entrada.chave_origem,
             entrada.chave_destino, entrada.composto, entrada.nome_direto, entrada.nome_inverso,
             entrada.cardinalidade_min, entrada.cardinalidade_max, entrada.limite_relacionados, usuario_id),
        )
        r = cur.fetchone()
        cur.execute("SELECT plat.relacionamento_fk_aplicar(%s::uuid)", (str(r["id"]),))
        return r
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


def apagar(cur, rel_id: str) -> None:
    r = relacionamento_ou_404(cur, rel_id)
    try:
        cur.execute("SELECT plat.relacionamento_fk_remover(%s::uuid)", (str(r["id"]),))
        cur.execute("DELETE FROM plat.relacionamento WHERE id = %s::uuid", (str(r["id"]),))
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


def _tabela_de(cur, item_id) -> tuple[str, str]:
    cur.execute("SELECT esquema, tabela FROM plat.relacionamento_tabela_de(%s::uuid, plat.tenant_atual())",
                (str(item_id),))
    r = cur.fetchone()
    if not r or not r["esquema"]:
        raise ErroAPI(404, "camada_sem_tabela", "camada sem tabela associada")
    return r["esquema"], r["tabela"]


def relacionamentos_da_camada(cur, item: dict) -> list[dict]:
    """Lista as classes de relacionamento em que a camada aparece, do lado que ELA enxerga: `nome_direto`
    quando é a origem, `nome_inverso` quando é o destino. A tela usa isto para montar o popup de
    relacionados sem precisar conhecer o nome de antemão (P1: função visível não pode depender de um
    nome digitado à mão no front)."""
    cur.execute(
        "SELECT id, nome_direto AS nome, destino_item_id AS alvo_item_id, cardinalidade, "
        "limite_relacionados FROM plat.relacionamento WHERE origem_item_id = %s::uuid ORDER BY criado_em",
        (str(item["id"]),),
    )
    saida = [{**r, "sentido": "direto"} for r in cur.fetchall()]
    cur.execute(
        "SELECT id, nome_inverso AS nome, origem_item_id AS alvo_item_id, cardinalidade, "
        "limite_relacionados FROM plat.relacionamento WHERE destino_item_id = %s::uuid ORDER BY criado_em",
        (str(item["id"]),),
    )
    saida.extend({**r, "sentido": "inverso"} for r in cur.fetchall())
    return saida


def rel_da_camada_ou_404(cur, item: dict, nome_rel: str) -> tuple[dict, str]:
    """Acha a classe de relacionamento que a camada `item` enxerga sob o nome `nome_rel`, olhando os dois
    lados (nome_direto quando a camada é origem, nome_inverso quando é destino). Devolve (linha, sentido),
    sentido em {'direto', 'inverso'}. Camada de outro inquilino já caiu em 404 antes de chegar aqui
    (`camada_ou_404`), então um nome que só existe do lado de outro inquilino também dá 404 aqui."""
    cur.execute(
        "SELECT * FROM plat.relacionamento WHERE origem_item_id = %s::uuid AND lower(nome_direto) = lower(%s)",
        (str(item["id"]), nome_rel),
    )
    r = cur.fetchone()
    if r:
        return r, "direto"
    cur.execute(
        "SELECT * FROM plat.relacionamento WHERE destino_item_id = %s::uuid AND lower(nome_inverso) = lower(%s)",
        (str(item["id"]), nome_rel),
    )
    r = cur.fetchone()
    if r:
        return r, "inverso"
    raise ErroAPI(404, "relacionamento_inexistente", "a camada não tem relacionamento com esse nome")


def relacionados(cur, item: dict, nome_rel: str, fids: list[int], limite: int | None, deslocamento: int) -> dict:
    """Registros relacionados a cada fid de origem (via a classe achada por `nome_rel`), agrupados por fid,
    com paginação por classe (`limite_relacionados` é o teto; `limite` da consulta não passa dele)."""
    rel, sentido = rel_da_camada_ou_404(cur, item, nome_rel)
    if sentido == "direto":
        e_partida, t_partida, chave_partida = _tabela_de(cur, rel["origem_item_id"]) + (rel["chave_origem"],)
        e_alvo, t_alvo, chave_alvo = _tabela_de(cur, rel["destino_item_id"]) + (rel["chave_destino"],)
    else:
        e_partida, t_partida, chave_partida = _tabela_de(cur, rel["destino_item_id"]) + (rel["chave_destino"],)
        e_alvo, t_alvo, chave_alvo = _tabela_de(cur, rel["origem_item_id"]) + (rel["chave_origem"],)
    teto = min(limite or rel["limite_relacionados"], rel["limite_relacionados"])

    if rel["cardinalidade"] == "N:M":
        grupos: dict[int, list[dict]] = {}
        for fid in fids:
            cur.execute(
                f'SELECT {chave_partida} AS valor FROM {e_partida}.{t_partida} '
                f'WHERE tenant_id = plat.tenant_atual() AND fid = %s',
                (fid,),
            )
            linha = cur.fetchone()
            if not linha:
                grupos[fid] = []
                continue
            lado_partida = "origem_valor" if sentido == "direto" else "destino_valor"
            lado_alvo = "destino_valor" if sentido == "direto" else "origem_valor"
            cur.execute(
                f"SELECT j.{lado_alvo} AS chave FROM plat.relacionamento_junc j "
                f"WHERE j.rel_id = %s::uuid AND j.{lado_partida} = %s ORDER BY j.criado_em "
                f"LIMIT %s OFFSET %s",
                (str(rel["id"]), str(linha["valor"]), teto, deslocamento),
            )
            chaves = [r["chave"] for r in cur.fetchall()]
            grupos[fid] = _buscar_alvo(cur, e_alvo, t_alvo, chave_alvo, chaves)
        return {"nome": nome_rel, "cardinalidade": rel["cardinalidade"], "grupos": grupos}

    grupos = {}
    for fid in fids:
        cur.execute(
            f'SELECT {chave_partida} AS valor FROM {e_partida}.{t_partida} '
            f'WHERE tenant_id = plat.tenant_atual() AND fid = %s',
            (fid,),
        )
        linha = cur.fetchone()
        if not linha or linha["valor"] is None:
            grupos[fid] = []
            continue
        cur.execute(
            f'SELECT fid, {chave_alvo} AS chave FROM {e_alvo}.{t_alvo} '
            f'WHERE tenant_id = plat.tenant_atual() AND {chave_alvo} = %s '
            f'ORDER BY fid LIMIT %s OFFSET %s',
            (str(linha["valor"]), teto, deslocamento),
        )
        grupos[fid] = [{"fid": r["fid"]} for r in cur.fetchall()]
    return {"nome": nome_rel, "cardinalidade": rel["cardinalidade"], "grupos": grupos}


def _buscar_alvo(cur, esquema: str, tabela: str, chave: str, valores: list[str]) -> list[dict]:
    if not valores:
        return []
    cur.execute(
        f'SELECT fid, {chave} AS chave FROM {esquema}.{tabela} '
        f'WHERE tenant_id = plat.tenant_atual() AND {chave}::text = ANY(%s)',
        (valores,),
    )
    return [{"fid": r["fid"]} for r in cur.fetchall()]


def ligar(cur, rel: dict, par, usuario_id: int) -> None:
    try:
        cur.execute(
            "INSERT INTO plat.relacionamento_junc (rel_id, tenant_id, origem_valor, destino_valor, criado_por) "
            "VALUES (%s::uuid, plat.tenant_atual(), %s, %s, %s) ON CONFLICT DO NOTHING",
            (str(rel["id"]), par.origem_valor, par.destino_valor, usuario_id),
        )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e


def desligar(cur, rel: dict, par) -> None:
    try:
        cur.execute(
            "DELETE FROM plat.relacionamento_junc WHERE rel_id = %s::uuid AND origem_valor = %s "
            "AND destino_valor = %s",
            (str(rel["id"]), par.origem_valor, par.destino_valor),
        )
    except psycopg2.Error as e:
        raise erro_do_banco(e) from e

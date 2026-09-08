"""Núcleo do versionamento por ramo (item L2-13-a): marcar a camada como versionada, criar/listar/apagar
ramo, reconciliar contra o padrão, resolver conflito e publicar (post).

Vocabulário, uma vez só: **padrão** é a versão pública da camada (o `SDE.DEFAULT` da Esri) e mora na
própria tabela da camada; **ramo** é uma linha de trabalho paralela, com as suas edições numa tabela
companheira; **momento base** é o instante do padrão contra o qual o ramo é lido e comparado;
**reconciliar** é comparar ramo e padrão desde o momento base e listar as feições alteradas dos dois
lados; **publicar** (post) é levar as edições do ramo para o padrão.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2.extras
from fastapi import Request

from app import limites
from app.auth.sessao import Auth
from app.catalogo import comum
from app.erros import ErroAPI
from app.versionamento import leitura

ACESSOS = ("privado", "protegido", "publico")
ESTADOS_VIVOS = ("aberta",)


def _json(valor: Any) -> psycopg2.extras.Json:
    return psycopg2.extras.Json(valor, dumps=lambda v: json.dumps(v, ensure_ascii=False, default=str))


# ---------------------------------------------------------------- camada versionada
def camada_versionada_ou_erro(cur, camada_id: str) -> tuple[dict, dict]:
    """Item da camada + metadado, exigindo que o versionamento por ramo esteja ligado nela."""
    item = comum.item_ou_404(cur, camada_id)
    if item["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    dados = item["dados"] or {}
    if not (dados.get("versionamento") or {}).get("habilitado"):
        raise ErroAPI(
            409, "camada_nao_versionada",
            "camada sem versionamento por ramo; ligue em POST /api/camadas/{id}/versionar",
        )
    leitura.nomes_ok(dados.get("schema"), dados.get("tabela"))
    return item, dados


def versionar_camada(cur, request: Request, auth: Auth, camada_id: str, ramos_max: int | None) -> dict:
    """Liga o versionamento por ramo numa camada hospedada: cria a tabela companheira e grava o
    metadado. Idempotente — chamar de novo só reafirma (e permite mudar o teto de ramos)."""
    item = comum.item_ou_404(cur, camada_id)
    if item["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    dados = item["dados"] or {}
    if dados.get("fonte") != "hospedada":
        raise ErroAPI(409, "camada_nao_versionavel", "só camada hospedada aceita versionamento por ramo")
    schema, tabela = leitura.nomes_ok(dados.get("schema"), dados.get("tabela"))
    if ramos_max is not None and not 1 <= ramos_max <= limites.VERSOES_POR_CAMADA_MAX:
        raise ErroAPI(
            422, "ramos_max_fora",
            f"ramos_max precisa estar entre 1 e {limites.VERSOES_POR_CAMADA_MAX}",
            {"maximo": limites.VERSOES_POR_CAMADA_MAX},
        )
    cur.execute("SELECT plat.camada_versionar(%s, %s) AS ramo", (schema, tabela))
    nome_ramo = cur.fetchone()["ramo"]
    versionamento = {"habilitado": True, "tabela_ramo": nome_ramo}
    if ramos_max is not None:
        versionamento["ramos_max"] = int(ramos_max)
    elif (dados.get("versionamento") or {}).get("ramos_max"):
        versionamento["ramos_max"] = dados["versionamento"]["ramos_max"]
    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object('versionamento', %s::jsonb) "
        "WHERE id = %s::uuid",
        (json.dumps(versionamento), camada_id),
    )
    comum.registrar_evento(cur, request, "camadas/versionar", "item", camada_id, versionamento)
    return versionamento


def teto_de_ramos(dados: dict) -> int:
    declarado = (dados.get("versionamento") or {}).get("ramos_max")
    return int(declarado) if declarado else limites.VERSOES_POR_CAMADA_MAX


# ---------------------------------------------------------------- acesso ao ramo
def _pode_editar_qualquer(auth: Auth) -> bool:
    return auth.tem("feicoes.editar_total")


def exigir_acesso(auth: Auth, versao: dict, escrita: bool) -> None:
    """`privado`: só o dono lê e escreve. `protegido`: todos leem, só o dono escreve (é o padrão da
    Esri). `publico`: todos leem e escrevem. Quem tem `feicoes.editar_total` passa em tudo — é o papel
    de administração de dado do inquilino, não um contorno."""
    if _pode_editar_qualquer(auth):
        return
    dono = versao["dono_id"] == auth.usuario_id
    if dono:
        return
    if versao["acesso"] == "privado":
        raise ErroAPI(404, "versao_inexistente", "ramo inexistente nesta camada", {"id": str(versao["id"])})
    if escrita and versao["acesso"] == "protegido":
        raise ErroAPI(
            403, "versao_protegida", "ramo protegido: só o dono edita, reconcilia, publica ou apaga",
            {"id": str(versao["id"])},
        )


def obter_versao(cur, camada_id: str, versao_ref: str, auth: Auth, escrita: bool = False) -> dict:
    """Ramo por identificador OU por nome (o protocolo Esri usa os dois: `gdbVersion` na consulta vem
    com o NOME, o VersionManagementServer trabalha com o identificador)."""
    cur.execute(
        "SELECT * FROM plat.versao WHERE item_id = %s::uuid AND estado <> 'apagada' "
        "  AND (CASE WHEN %s ~ '^[0-9a-fA-F-]{36}$' THEN id::text = lower(%s) ELSE false END "
        "       OR lower(nome) = lower(%s))",
        (camada_id, versao_ref, versao_ref, versao_ref),
    )
    v = cur.fetchone()
    if v is None:
        raise ErroAPI(404, "versao_inexistente", "ramo inexistente nesta camada", {"ref": versao_ref})
    exigir_acesso(auth, v, escrita)
    return v


def listar_versoes(cur, camada_id: str, auth: Auth) -> list[dict]:
    cur.execute(
        "SELECT * FROM plat.versao WHERE item_id = %s::uuid AND estado <> 'apagada' ORDER BY criada_em",
        (camada_id,),
    )
    saida = []
    for v in cur.fetchall():
        if not _pode_editar_qualquer(auth) and v["acesso"] == "privado" and v["dono_id"] != auth.usuario_id:
            continue
        saida.append(como_json(v))
    return saida


def como_json(v: dict) -> dict:
    return {
        "id": str(v["id"]),
        "nome": v["nome"],
        "descricao": v["descricao"],
        "dono_id": v["dono_id"],
        "acesso": v["acesso"],
        "pai": str(v["pai"]) if v["pai"] else None,
        "criada_em": v["criada_em"],
        "momento": v["momento"],
        "reconciliada_em": v["reconciliada_em"],
        "publicada_em": v["publicada_em"],
        "estado": v["estado"],
    }


# ---------------------------------------------------------------- ciclo de vida
def criar_versao(
    cur, request: Request, auth: Auth, camada_id: str, nome: str, descricao: str | None, acesso: str
) -> dict:
    item, dados = camada_versionada_ou_erro(cur, camada_id)
    if acesso not in ACESSOS:
        raise ErroAPI(422, "acesso_invalido", f"acesso precisa ser um de {', '.join(ACESSOS)}")
    teto = teto_de_ramos(dados)
    cur.execute(
        "SELECT count(*) AS n FROM plat.versao WHERE item_id = %s::uuid AND estado = 'aberta'", (camada_id,)
    )
    if cur.fetchone()["n"] >= teto:
        raise ErroAPI(
            409, "ramos_demais", f"a camada já tem {teto} ramos abertos (teto declarado desta camada)",
            {"maximo": teto},
        )
    cur.execute(
        "INSERT INTO plat.versao(tenant_id, item_id, nome, dono_id, acesso, descricao) "
        "VALUES (plat.tenant_atual(), %s::uuid, %s, %s, %s, %s) RETURNING *",
        (camada_id, nome, auth.usuario_id, acesso, descricao),
    )
    v = cur.fetchone()
    comum.registrar_evento(
        cur, request, "versoes/criar", "item", camada_id, {"versao_id": str(v["id"]), "nome": nome, "acesso": acesso}
    )
    return como_json(v)


def apagar_versao(cur, request: Request, auth: Auth, camada_id: str, versao_ref: str) -> dict:
    """Descarta o ramo E as edições dele (é o que o `delete` da Esri faz; nada vai para o padrão)."""
    _item, dados = camada_versionada_ou_erro(cur, camada_id)
    v = obter_versao(cur, camada_id, versao_ref, auth, escrita=True)
    schema, tabela = dados["schema"], dados["tabela"]
    ramo = leitura.tabela_ramo(tabela)
    cur.execute(f'DELETE FROM "{schema}"."{ramo}" WHERE versao_id = %s::uuid', (str(v["id"]),))
    descartadas = cur.rowcount
    cur.execute("DELETE FROM plat.versao_conflito WHERE versao_id = %s::uuid", (str(v["id"]),))
    cur.execute(
        "UPDATE plat.versao SET estado = 'apagada', apagada_em = now() WHERE id = %s::uuid", (str(v["id"]),)
    )
    comum.registrar_evento(
        cur, request, "versoes/apagar", "item", camada_id,
        {"versao_id": str(v["id"]), "linhas_descartadas": descartadas},
    )
    return {"id": str(v["id"]), "linhas_descartadas": descartadas}


# ---------------------------------------------------------------- reconciliação
def _atributos_de(linha: dict | None, campos: list[str]) -> dict:
    if linha is None:
        return {}
    return {c: linha.get(c) for c in campos}


def _campos_de_dado(dados: dict) -> list[str]:
    return [c["nome"] for c in dados.get("campos") or []]


def _linha_padrao_atual(cur, schema: str, tabela: str, globalid: str, tem_geom: bool) -> dict | None:
    extra = ", ST_AsGeoJSON(geom) AS __geom" if tem_geom else ""
    cur.execute(f'SELECT *{extra} FROM "{schema}"."{tabela}" WHERE globalid = %s::uuid', (globalid,))
    return cur.fetchone()


def _momento_ultima_mudanca(cur, schema: str, tabela: str, globalid: str, desde) -> Any:
    cur.execute(
        "SELECT max(momento) AS m FROM plat.feicao_historico "
        "WHERE schema_dado = %s AND tabela_dado = %s AND globalid = %s::uuid AND momento > %s",
        (schema, tabela, globalid, desde),
    )
    return cur.fetchone()["m"]


def _geom_igual(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return json.loads(a) == json.loads(b)
    except (TypeError, ValueError):
        return a == b


def _linhas_vigentes_do_ramo(cur, schema: str, ramo: str, versao_id: str, tem_geom: bool) -> list[dict]:
    extra = ", ST_AsGeoJSON(geom) AS __geom" if tem_geom else ""
    cur.execute(
        f'SELECT *{extra} FROM "{schema}"."{ramo}" WHERE versao_id = %s::uuid AND momento_fim IS NULL '
        f"ORDER BY ramo_pk",
        (versao_id,),
    )
    return cur.fetchall()


def detectar_conflitos(cur, camada_id: str, versao: dict, dados: dict) -> list[dict]:
    """Compara ramo × padrão desde o momento base. Conflito = a MESMA feição mudou dos dois lados.
    Devolve a lista (sem gravar); `reconciliar` é quem grava."""
    schema, tabela = dados["schema"], dados["tabela"]
    ramo = leitura.tabela_ramo(tabela)
    srid = int(dados["srid"])
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    campos = _campos_de_dado(dados)
    base_momento = versao["momento"]
    conflitos: list[dict] = []
    for linha in _linhas_vigentes_do_ramo(cur, schema, ramo, str(versao["id"]), tem_geom):
        gid = str(linha["globalid"])
        base = leitura.feicao_no_padrao_em(cur, schema, tabela, srid, base_momento, gid)
        atual = _linha_padrao_atual(cur, schema, tabela, gid, tem_geom)
        momento_padrao = _momento_ultima_mudanca(cur, schema, tabela, gid, base_momento)
        if momento_padrao is None:
            continue  # o padrão não tocou nesta feição desde o momento base: não há conflito
        if base is None and atual is None:
            continue  # feição nasceu no ramo e o padrão nunca a viu
        ramo_apagou = bool(linha.get("apagada"))
        padrao_apagou = atual is None
        base_attrs = _atributos_de(base, campos)
        ramo_attrs = _atributos_de(linha, campos)
        padrao_attrs = _atributos_de(atual, campos)
        atributos = {}
        for c in campos:
            mudou_ramo = ramo_attrs.get(c) != base_attrs.get(c)
            mudou_padrao = padrao_attrs.get(c) != base_attrs.get(c)
            if mudou_ramo or mudou_padrao:
                atributos[c] = {
                    "base": base_attrs.get(c), "ramo": ramo_attrs.get(c), "padrao": padrao_attrs.get(c),
                    "mudou_no_ramo": mudou_ramo, "mudou_no_padrao": mudou_padrao,
                }
        geometria = None
        if tem_geom:
            geometria = {
                "mudou_no_ramo": not _geom_igual(linha.get("__geom"), (base or {}).get("__geom")),
                "mudou_no_padrao": not _geom_igual((atual or {}).get("__geom"), (base or {}).get("__geom")),
                "base": (base or {}).get("__geom"),
                "ramo": linha.get("__geom"),
                "padrao": (atual or {}).get("__geom"),
            }
        if base is None and atual is not None:
            tipo = "inserir-inserir"
        elif ramo_apagou:
            tipo = "apagar-atualizar"
        elif padrao_apagou:
            tipo = "atualizar-apagar"
        else:
            tipo = "atualizar-atualizar"
            mexeu_ramo = any(a["mudou_no_ramo"] for a in atributos.values()) or (
                geometria is not None and geometria["mudou_no_ramo"]
            )
            mexeu_padrao = any(a["mudou_no_padrao"] for a in atributos.values()) or (
                geometria is not None and geometria["mudou_no_padrao"]
            )
            if not (mexeu_ramo and mexeu_padrao):
                continue  # os dois lados escreveram, mas não na mesma feição de forma divergente
        conflitos.append(
            {
                "globalid": gid, "tipo": tipo, "momento_padrao": momento_padrao,
                "detalhe": {"atributos": atributos, "geometria": geometria,
                            "ramo_apagou": ramo_apagou, "padrao_apagou": padrao_apagou},
            }
        )
    return conflitos


def _reconciliar_nucleo(cur, camada_id: str, v: dict, dados: dict) -> tuple[list[dict], list[str]]:
    """Detecta, grava e devolve (conflitos, pendentes). Sem evento e sem avançar o momento — é a parte
    que `reconciliar_versao` e `publicar_versao` compartilham (publicar SEMPRE reconcilia antes, que é
    a regra da Esri: não se publica sem reconciliar)."""
    achados = detectar_conflitos(cur, camada_id, v, dados)
    vistos = {c["globalid"] for c in achados}
    cur.execute("SELECT * FROM plat.versao_conflito WHERE versao_id = %s::uuid", (str(v["id"]),))
    antigos = {str(r["globalid"]): r for r in cur.fetchall()}
    for gid in set(antigos) - vistos:
        cur.execute(
            "DELETE FROM plat.versao_conflito WHERE versao_id = %s::uuid AND globalid = %s::uuid",
            (str(v["id"]), gid),
        )
    for c in achados:
        anterior = antigos.get(c["globalid"])
        # a decisão anterior só sobrevive se o padrão NÃO andou de novo depois dela: se andou, o
        # conflito REABRE. É isto que impede publicar sobre um padrão que mudou depois da resolução.
        manter = (
            anterior is not None and anterior["resolvido_em"] is not None
            and anterior["momento_padrao"] == c["momento_padrao"]
        )
        cur.execute(
            "INSERT INTO plat.versao_conflito(tenant_id, versao_id, globalid, tipo, detalhe, momento_padrao) "
            "VALUES (plat.tenant_atual(), %s::uuid, %s::uuid, %s, %s, %s) "
            "ON CONFLICT (versao_id, globalid) DO UPDATE SET tipo = EXCLUDED.tipo, "
            "  detalhe = EXCLUDED.detalhe, momento_padrao = EXCLUDED.momento_padrao, "
            "  detectado_em = now(), "
            "  decisao = CASE WHEN %s THEN plat.versao_conflito.decisao ELSE NULL END, "
            "  resolvido_em = CASE WHEN %s THEN plat.versao_conflito.resolvido_em ELSE NULL END, "
            "  resolvido_por = CASE WHEN %s THEN plat.versao_conflito.resolvido_por ELSE NULL END",
            (str(v["id"]), c["globalid"], c["tipo"], _json(c["detalhe"]), c["momento_padrao"],
             manter, manter, manter),
        )
    return achados, _pendentes(cur, str(v["id"]))


def reconciliar_versao(cur, request: Request, auth: Auth, camada_id: str, versao_ref: str) -> dict:
    """Roda a detecção, grava a lista de conflitos (apagando os que deixaram de valer) e, quando não
    sobra nenhum pendente, avança o momento base — que é o que faz o ramo passar a enxergar o padrão
    de agora nas feições que ele não tocou."""
    _item, dados = camada_versionada_ou_erro(cur, camada_id)
    v = obter_versao(cur, camada_id, versao_ref, auth, escrita=True)
    if v["estado"] != "aberta":
        raise ErroAPI(409, "versao_fechada", "ramo já publicado ou apagado; não aceita reconciliação")
    achados, pendentes = _reconciliar_nucleo(cur, camada_id, v, dados)
    if pendentes:
        cur.execute("UPDATE plat.versao SET reconciliada_em = now() WHERE id = %s::uuid", (str(v["id"]),))
    else:
        cur.execute(
            "UPDATE plat.versao SET reconciliada_em = now(), momento = now() WHERE id = %s::uuid",
            (str(v["id"]),),
        )
    comum.registrar_evento(
        cur, request, "versoes/reconciliar", "item", camada_id,
        {"versao_id": str(v["id"]), "conflitos": len(achados), "pendentes": len(pendentes)},
    )
    return {
        "versao_id": str(v["id"]), "conflitos": listar_conflitos(cur, str(v["id"])),
        "pendentes": len(pendentes), "momento_avancado": not pendentes,
    }


def _pendentes(cur, versao_id: str) -> list[str]:
    cur.execute(
        "SELECT globalid FROM plat.versao_conflito WHERE versao_id = %s::uuid AND resolvido_em IS NULL",
        (versao_id,),
    )
    return [str(r["globalid"]) for r in cur.fetchall()]


def listar_conflitos(cur, versao_id: str) -> list[dict]:
    cur.execute(
        "SELECT * FROM plat.versao_conflito WHERE versao_id = %s::uuid ORDER BY detectado_em, id",
        (versao_id,),
    )
    return [
        {
            "globalid": str(r["globalid"]), "tipo": r["tipo"], "detalhe": r["detalhe"],
            "detectado_em": r["detectado_em"], "decisao": r["decisao"], "resolvido_em": r["resolvido_em"],
            "resolvido_por": r["resolvido_por"],
        }
        for r in cur.fetchall()
    ]


def conflitos_da_versao(cur, camada_id: str, versao_ref: str, auth: Auth) -> dict:
    _item, _dados = camada_versionada_ou_erro(cur, camada_id)
    v = obter_versao(cur, camada_id, versao_ref, auth)
    return {"versao_id": str(v["id"]), "conflitos": listar_conflitos(cur, str(v["id"]))}


# ---------------------------------------------------------------- resolução de conflito
DECISOES = ("ramo", "padrao", "manual")


def resolver_conflito(
    cur, request: Request, auth: Auth, camada_id: str, versao_ref: str, globalid: str,
    decisao: str, atributos: dict | None, geometria: dict | None,
) -> dict:
    """Decide UMA feição em conflito. `ramo` mantém o que o ramo tem; `padrao` traz o estado atual do
    padrão para dentro do ramo; `manual` grava no ramo os valores que o usuário escolheu campo a campo
    (é o lado direito do diff da tela). Em todos os casos a decisão fica gravada com o momento do padrão
    em que foi tomada: se o padrão andar de novo, a próxima reconciliação reabre o conflito."""
    from app.edicao import servico as edicao_servico  # noqa: PLC0415 — evita ciclo de importação
    from app.versionamento import escrita

    _item, dados = camada_versionada_ou_erro(cur, camada_id)
    v = obter_versao(cur, camada_id, versao_ref, auth, escrita=True)
    if v["estado"] != "aberta":
        raise ErroAPI(409, "versao_fechada", "ramo já publicado ou apagado; não aceita resolução")
    if decisao not in DECISOES:
        raise ErroAPI(422, "decisao_invalida", f"decisao precisa ser um de {', '.join(DECISOES)}")
    cur.execute(
        "SELECT * FROM plat.versao_conflito WHERE versao_id = %s::uuid AND globalid = %s::uuid",
        (str(v["id"]), globalid),
    )
    conflito = cur.fetchone()
    if conflito is None:
        raise ErroAPI(
            404, "conflito_inexistente", "esta feição não está na lista de conflitos deste ramo; reconcilie antes",
            {"globalid": globalid},
        )
    schema, tabela = dados["schema"], dados["tabela"]
    srid = int(dados["srid"])
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    colunas = leitura.colunas_fisicas(cur, schema, tabela)
    vigente = escrita.linha_vigente(cur, schema, tabela, str(v["id"]), globalid, tem_geom)
    if vigente is None:
        raise ErroAPI(409, "linha_de_ramo_ausente", "o ramo já não tem linha vigente para esta feição")

    if decisao == "padrao":
        atual = _linha_padrao_atual(cur, schema, tabela, globalid, tem_geom)
        escrita.fechar(cur, schema, tabela, vigente["ramo_pk"])
        if atual is None:
            escrita.escrever(
                cur, schema, tabela, colunas, str(v["id"]), srid,
                base=vigente, apagada=True, usuario_id=auth.usuario_id,
            )
        else:
            escrita.escrever(
                cur, schema, tabela, colunas, str(v["id"]), srid, base=vigente,
                atributos={c["nome"]: atual.get(c["nome"]) for c in dados.get("campos") or []},
                geom_geojson=atual.get("__geom"), usuario_id=auth.usuario_id,
            )
    elif decisao == "manual":
        limpos, _avisos = edicao_servico.validar_atributos(atributos or {}, dados, "atualizar")
        geom_wkb = escrita.MANTER
        if geometria is not None:
            if not tem_geom:
                raise ErroAPI(422, "camada_sem_geometria", "esta camada não aceita geometria")
            geom_wkb, _aviso = edicao_servico._preparar_geometria(  # noqa: SLF001
                cur, geometria, None, dados, False
            )
        escrita.fechar(cur, schema, tabela, vigente["ramo_pk"])
        escrita.escrever(
            cur, schema, tabela, colunas, str(v["id"]), srid, base=vigente, atributos=limpos,
            geom_wkb=geom_wkb, usuario_id=auth.usuario_id,
        )
    # `ramo` não mexe na linha: o que o ramo tem já é a decisão.

    momento_padrao = _momento_ultima_mudanca(cur, schema, tabela, globalid, v["momento"])
    cur.execute(
        "UPDATE plat.versao_conflito SET decisao = %s, resolvido_em = now(), resolvido_por = %s, "
        "  momento_padrao = coalesce(%s, momento_padrao) "
        "WHERE versao_id = %s::uuid AND globalid = %s::uuid",
        (decisao, auth.usuario_id, momento_padrao, str(v["id"]), globalid),
    )
    if cur.rowcount != 1:
        raise ErroAPI(409, "conflito_nao_resolvido", "a linha do conflito não pôde ser marcada")
    comum.registrar_evento(
        cur, request, "versoes/resolver", "item", camada_id,
        {"versao_id": str(v["id"]), "globalid": globalid, "decisao": decisao},
    )
    return {"versao_id": str(v["id"]), "globalid": globalid, "decisao": decisao}


# ---------------------------------------------------------------- publicar (post)
MODOS_PUBLICACAO = ("fechar", "rebasear")


def _publicar_linha(cur, schema: str, tabela: str, dados: dict, linha: dict, tem_geom: bool) -> str:
    """Leva UMA linha vigente do ramo para o padrão. A escrita é feita na tabela do padrão, logo passa
    pelo gatilho de histórico (20260907T1025) como qualquer outra edição: o momento histórico do padrão
    continua completo depois de publicar."""
    gid = str(linha["globalid"])
    campos = [c["nome"] for c in dados.get("campos") or []]
    existe = _linha_padrao_atual(cur, schema, tabela, gid, False) is not None
    if linha["apagada"]:
        if existe:
            cur.execute(f'DELETE FROM "{schema}"."{tabela}" WHERE globalid = %s::uuid', (gid,))
            if cur.rowcount != 1:
                raise ErroAPI(409, "publicacao_falhou", "a feição do padrão não pôde ser apagada")
            return "apagada"
        return "ja_ausente"
    srid = int(dados["srid"])
    sets, valores = [], []
    for c in campos:
        sets.append(f'"{c}" = %s')
        valores.append(linha.get(c))
    if tem_geom:
        if linha.get("__geom") is None:
            sets.append("geom = NULL")
        else:
            sets.append("geom = ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)")
            valores += [linha["__geom"], srid]
    if existe:
        cur.execute(
            f'UPDATE "{schema}"."{tabela}" SET {", ".join(sets)} WHERE globalid = %s::uuid', [*valores, gid]
        )
        if cur.rowcount != 1:
            # RLS FORCE por inquilino: sem contexto o UPDATE toca zero linhas em silêncio
            raise ErroAPI(409, "publicacao_falhou", "a feição do padrão não pôde ser atualizada")
        return "atualizada"
    colunas_sql = [f'"{c}"' for c in campos] + ['"globalid"', '"fid"']
    marcadores = ["%s"] * len(campos) + ["%s::uuid", "%s"]
    entrada = [linha.get(c) for c in campos] + [gid, linha["fid"]]
    if tem_geom and linha.get("__geom") is not None:
        colunas_sql.append("geom")
        marcadores.append("ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)")
        entrada += [linha["__geom"], srid]
    cur.execute(
        f'INSERT INTO "{schema}"."{tabela}" ({", ".join(colunas_sql)}) VALUES ({", ".join(marcadores)})',
        entrada,
    )
    return "inserida"


def publicar_versao(
    cur, request: Request, auth: Auth, camada_id: str, versao_ref: str, modo: str = "fechar"
) -> dict:
    """Post: reconcilia (obrigatório, regra da Esri), recusa se sobrar conflito pendente, e move as
    linhas vigentes do ramo para o padrão. `modo=fechar` encerra o ramo; `modo=rebasear` mantém o ramo
    aberto, descarta as linhas já publicadas e reposiciona o momento base no agora."""
    _item, dados = camada_versionada_ou_erro(cur, camada_id)
    v = obter_versao(cur, camada_id, versao_ref, auth, escrita=True)
    if v["estado"] != "aberta":
        raise ErroAPI(409, "versao_fechada", "ramo já publicado ou apagado", {"estado": v["estado"]})
    if modo not in MODOS_PUBLICACAO:
        raise ErroAPI(422, "modo_invalido", f"modo precisa ser um de {', '.join(MODOS_PUBLICACAO)}")
    achados, pendentes = _reconciliar_nucleo(cur, camada_id, v, dados)
    if pendentes:
        # a recusa desfaz a transação inteira, inclusive as linhas de conflito que a detecção acabou de
        # gravar — por isso a lista vai NO ERRO, e não fica só no banco. Quem quer a lista persistida
        # chama `reconciliar` (que é o passo obrigatório da Esri antes do post).
        raise ErroAPI(
            409, "conflitos_pendentes",
            f"{len(pendentes)} conflito(s) sem decisão; reconcilie e resolva antes de publicar",
            {"pendentes": pendentes,
             "conflitos": [{**c, "momento_padrao": c["momento_padrao"].isoformat()} for c in achados]},
        )
    schema, tabela = dados["schema"], dados["tabela"]
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    ramo = leitura.tabela_ramo(tabela)
    resumo = {"inserida": 0, "atualizada": 0, "apagada": 0, "ja_ausente": 0}
    for linha in _linhas_vigentes_do_ramo(cur, schema, ramo, str(v["id"]), tem_geom):
        resumo[_publicar_linha(cur, schema, tabela, dados, linha, tem_geom)] += 1
    if modo == "fechar":
        cur.execute(
            "UPDATE plat.versao SET estado = 'publicada', publicada_em = now(), momento = now(), "
            "reconciliada_em = now() WHERE id = %s::uuid", (str(v["id"]),)
        )
    else:
        cur.execute(f'DELETE FROM "{schema}"."{ramo}" WHERE versao_id = %s::uuid', (str(v["id"]),))
        cur.execute(
            "UPDATE plat.versao SET momento = now(), reconciliada_em = now(), publicada_em = now() "
            "WHERE id = %s::uuid", (str(v["id"]),)
        )
    cur.execute("DELETE FROM plat.versao_conflito WHERE versao_id = %s::uuid", (str(v["id"]),))
    cur.execute(
        "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
        "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid",
        (camada_id,),
    )
    comum.registrar_evento(
        cur, request, "versoes/publicar", "item", camada_id,
        {"versao_id": str(v["id"]), "modo": modo, "conflitos_resolvidos": len(achados), **resumo},
    )
    return {"versao_id": str(v["id"]), "modo": modo, **resumo}

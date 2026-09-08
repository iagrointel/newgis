"""Edição DENTRO de um ramo (item L2-13-a): mesma porta de escrita da plataforma
(`POST /api/camadas/{id}/edicoes`, e por tabela de baixo o `applyEdits` do FeatureServer), só que as
linhas vão para a tabela companheira do ramo em vez da tabela do padrão.

Tudo o que valida atributo, domínio, tipo de geometria, CRS e propriedade da feição é reaproveitado de
`app.edicao.servico` sem cópia: o que muda aqui é ONDE a linha é gravada e QUAL é o estado de partida
(a linha vigente do ramo, ou, se o ramo ainda não tocou a feição, a linha do padrão no momento base).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.auth.sessao import Auth
from app.catalogo import comum
from app.edicao import servico as edicao_servico
from app.edicao.modelos import EdicoesEntrada, EdicoesSaida, ResultadoFeicao
from app.erros import ErroAPI
from app.versionamento import escrita, leitura, servico


def _contexto(cur, camada_id: str, versao_ref: str, auth: Auth) -> dict:
    item, dados = servico.camada_versionada_ou_erro(cur, camada_id)
    v = servico.obter_versao(cur, camada_id, versao_ref, auth, escrita=True)
    if v["estado"] != "aberta":
        raise ErroAPI(409, "versao_fechada", "ramo já publicado ou apagado; não aceita edição")
    schema, tabela = dados["schema"], dados["tabela"]
    return {
        "item": item, "dados": dados, "versao": v, "schema": schema, "tabela": tabela,
        "srid": int(dados["srid"]), "tem_geom": dados.get("geometria") not in (None, "nenhuma"),
        "colunas": leitura.colunas_fisicas(cur, schema, tabela),
    }


def _estado(cur, ctx: dict, globalid: str) -> tuple[dict | None, bool]:
    """(estado de partida, já é linha do ramo?). Uma feição que o ramo apagou continua "tocada" mas não
    tem estado de partida utilizável — quem tenta editá-la recebe 404, como no padrão."""
    linha = escrita.linha_vigente(
        cur, ctx["schema"], ctx["tabela"], str(ctx["versao"]["id"]), globalid, ctx["tem_geom"]
    )
    if linha is not None:
        if linha["apagada"]:
            raise ErroAPI(404, "feicao_inexistente", "feição apagada neste ramo", {"id": globalid})
        return linha, True
    base = leitura.feicao_no_padrao_em(
        cur, ctx["schema"], ctx["tabela"], ctx["srid"], ctx["versao"]["momento"], globalid
    )
    if base is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente neste ramo", {"id": globalid})
    return base, False


def _conferir_versao(feicao_versao: Any, atual: dict, globalid: str) -> None:
    if feicao_versao is None:
        return
    if atual["versao"] != feicao_versao:
        raise ErroAPI(
            409, "conflito_versao", "a feição foi alterada por outra sessão do mesmo ramo desde a leitura",
            {"id": globalid, "versao_enviada": feicao_versao, "versao_atual": atual["versao"]},
        )


def _geometria(cur, ctx: dict, corpo: EdicoesEntrada, geometria: dict | None) -> tuple[Any, list[str]]:
    if geometria is None:
        return escrita.MANTER, []
    if not ctx["tem_geom"]:
        raise ErroAPI(422, "camada_sem_geometria", "esta camada não aceita geometria")
    if (ctx["dados"].get("edicao") or {}).get("geometria_travada"):
        raise ErroAPI(422, "geometria_travada", "geometria travada nesta camada: só atributo é editável")
    wkb, aviso = edicao_servico._preparar_geometria(  # noqa: SLF001 — mesma validação do padrão, sem cópia
        cur, geometria, corpo.crs.srid if corpo.crs else None, ctx["dados"], corpo.corrigir_geometria
    )
    return wkb, ([aviso] if aviso else [])


def _inserir(cur, auth: Auth, ctx: dict, corpo: EdicoesEntrada, feicao) -> tuple[ResultadoFeicao, list[str]]:
    atributos, avisos = edicao_servico.validar_atributos(feicao.atributos, ctx["dados"], "adicionar")
    if ctx["tem_geom"] and feicao.geometria is None:
        raise ErroAPI(422, "geometria_ausente", "geometria obrigatória para adicionar nesta camada")
    wkb, avisos_geom = _geometria(cur, ctx, corpo, feicao.geometria)
    r = escrita.escrever(
        cur, ctx["schema"], ctx["tabela"], ctx["colunas"], str(ctx["versao"]["id"]), ctx["srid"],
        base=None, atributos=atributos, geom_wkb=wkb, usuario_id=auth.usuario_id,
    )
    resultado = ResultadoFeicao(
        sucesso=True, id=str(r["globalid"]), fid=r["fid"], versao=r["versao"], atributos=atributos
    )
    return resultado, avisos + avisos_geom


def _atualizar(cur, auth: Auth, ctx: dict, corpo: EdicoesEntrada, feicao) -> tuple[ResultadoFeicao, list[str]]:
    atual, do_ramo = _estado(cur, ctx, feicao.id)
    edicao_servico._exigir_dono_ou_admin(auth, ctx["dados"], atual)  # noqa: SLF001
    _conferir_versao(feicao.versao, atual, feicao.id)
    avisos: list[str] = []
    atributos: dict = {}
    if feicao.atributos:
        atributos, avisos = edicao_servico.validar_atributos(feicao.atributos, ctx["dados"], "atualizar")
    wkb, avisos_geom = _geometria(cur, ctx, corpo, feicao.geometria)
    if do_ramo:
        escrita.fechar(cur, ctx["schema"], ctx["tabela"], atual["ramo_pk"])
    r = escrita.escrever(
        cur, ctx["schema"], ctx["tabela"], ctx["colunas"], str(ctx["versao"]["id"]), ctx["srid"],
        base=atual, atributos=atributos, geom_wkb=wkb, usuario_id=auth.usuario_id,
    )
    return ResultadoFeicao(sucesso=True, id=feicao.id, fid=r["fid"], versao=r["versao"]), avisos + avisos_geom


def _apagar(cur, auth: Auth, ctx: dict, corpo: EdicoesEntrada, feicao) -> tuple[ResultadoFeicao, list[str]]:
    atual, do_ramo = _estado(cur, ctx, feicao.id)
    edicao_servico._exigir_dono_ou_admin(auth, ctx["dados"], atual)  # noqa: SLF001
    _conferir_versao(feicao.versao, atual, feicao.id)
    if do_ramo:
        escrita.fechar(cur, ctx["schema"], ctx["tabela"], atual["ramo_pk"])
    r = escrita.escrever(
        cur, ctx["schema"], ctx["tabela"], ctx["colunas"], str(ctx["versao"]["id"]), ctx["srid"],
        base=atual, apagada=True, usuario_id=auth.usuario_id,
    )
    return ResultadoFeicao(sucesso=True, id=feicao.id, fid=r["fid"]), []


def aplicar_edicoes_no_ramo(
    cur, request: Request, auth: Auth, camada_id: str, corpo: EdicoesEntrada
) -> EdicoesSaida:
    ctx = _contexto(cur, camada_id, corpo.versao, auth)
    edicao_servico.exigir_camada_editavel(auth, ctx["dados"])
    resultados_add, av1 = edicao_servico._processar_lista(  # noqa: SLF001
        cur, corpo.adicionar, lambda c, f: _inserir(c, auth, ctx, corpo, f), corpo.modo, "sp_radd"
    )
    resultados_upd, av2 = edicao_servico._processar_lista(  # noqa: SLF001
        cur, corpo.atualizar, lambda c, f: _atualizar(c, auth, ctx, corpo, f), corpo.modo, "sp_rupd"
    )
    resultados_del, av3 = edicao_servico._processar_lista(  # noqa: SLF001
        cur, corpo.apagar, lambda c, f: _apagar(c, auth, ctx, corpo, f), corpo.modo, "sp_rdel"
    )
    n_add = sum(1 for r in resultados_add if r.sucesso)
    n_upd = sum(1 for r in resultados_upd if r.sucesso)
    n_del = sum(1 for r in resultados_del if r.sucesso)
    comum.registrar_evento(
        cur, request, "camadas/editar", "item", camada_id,
        {"adicionados": n_add, "atualizados": n_upd, "apagados": n_del, "modo": corpo.modo,
         "versao_id": str(ctx["versao"]["id"])},
    )
    return EdicoesSaida(
        modo=corpo.modo, adicionar=resultados_add, atualizar=resultados_upd, apagar=resultados_del,
        avisos=[*av1, *av2, *av3],
    )

"""Núcleo de `POST /api/camadas/{id}/edicoes` (item L2-03-a): validação (tipo de geometria/SRID, ST_IsValid com
ST_MakeValid opcional, campo obrigatório/domínio/tamanho), concorrência otimista por `versao`, rastreio no
servidor, "só as próprias feições" e evento por lote. Roda contra a tabela `d_<slug>.c_<uuid16>` que
`app/ingestao/carregar.py`/`plat.camada_preparar` já criam — nenhuma tabela nova.

Domínio de atributo (portão cláusula 3): `dados.regras_campo` é o mecanismo PRÓPRIO deste item, escopado à
camada (migração 20260906T1859). O item L2-10-a-dominios-subtipos (entregue noutra trilha, ainda não integrada
a esta árvore) traz um domínio COMPARTILHADO entre camadas com subtipo — quando integrado, vira uma segunda
fonte de regra além de `regras_campo`, não substitui esta."""

from __future__ import annotations

import json
import re
from typing import Any

import psycopg2
import psycopg2.errors
from fastapi import Request

from app import limites
from app.auth.sessao import Auth
from app.catalogo import comum
from app.edicao.modelos import (
    EdicoesEntrada,
    EdicoesSaida,
    FeicaoAdicionar,
    FeicaoApagar,
    FeicaoAtualizar,
    ResultadoFeicao,
)
from app.erros import ErroAPI
from app.ingestao.geometria import MULTI_DE, TIPOS_CONCRETOS

# campos de rastreio e sistema: NUNCA aceitos do cliente, mesmo que ele os inclua em `atributos` — ignorados em
# silêncio (portão cláusula 7). Nunca fazem parte de `dados.campos` (a ingestão nunca os lista lá), então isso
# é só uma segunda trava explícita, não a única.
RESERVADOS = frozenset(
    {"fid", "globalid", "versao", "tenant_id", "criado_em", "atualizado_em", "criado_por", "atualizado_por", "geom"}
)
_RE_SCHEMA = re.compile(r"^d_[a-z0-9_]{1,60}$")
_RE_TABELA = re.compile(r"^c_[0-9a-f]{16}$")
_RE_CAMPO = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def _ident(nome: str) -> str:
    if not _RE_CAMPO.match(nome or ""):
        raise ErroAPI(409, "camada_configuracao_invalida", f"nome de campo inválido no metadado da camada: {nome!r}")
    return '"' + nome + '"'


def _schema_tabela(dados: dict) -> tuple[str, str]:
    schema, tabela = dados.get("schema"), dados.get("tabela")
    ok = (
        isinstance(schema, str) and _RE_SCHEMA.match(schema)
        and isinstance(tabela, str) and _RE_TABELA.match(tabela)
    )
    if not ok:
        raise ErroAPI(409, "camada_configuracao_invalida", "metadado de schema/tabela da camada inconsistente")
    return schema, tabela


def camada_ou_404(cur, camada_id: str) -> tuple[dict, dict]:
    """Item de camada (404 se inexistente/ilegível — a RLS de `plat.item` já isola por inquilino, portão
    cláusula 11) validado como `camada_vetorial` hospedada (a única editável por aqui; camada referenciada não
    tem `versao`/rastreio, é escopo de outro item)."""
    r = comum.item_ou_404(cur, camada_id)
    if r["tipo"] != "camada_vetorial":
        raise ErroAPI(404, "item_inexistente", "item inexistente")
    dados = r["dados"] or {}
    if dados.get("fonte") != "hospedada":
        raise ErroAPI(409, "camada_nao_editavel", "só camada hospedada aceita edição de feição por esta API")
    return r, dados


def exigir_camada_editavel(auth: Auth, dados: dict) -> None:
    """`feicoes.editar_total` (perfil admin) ignora a chave `edicao.habilitada`; sem ela, `feicoes.editar`
    exige que a camada tenha ligado edição (hipótese do item; ADR Esri de editor tracking)."""
    if auth.tem("feicoes.editar_total"):
        return
    if not (dados.get("edicao") or {}).get("habilitada"):
        raise ErroAPI(403, "edicao_desabilitada", "edição de feição não habilitada nesta camada")


def _exigir_dono_ou_admin(auth: Auth, dados: dict, linha_atual: dict) -> None:
    """'Só as próprias feições' (portão cláusula 6): `feicoes.editar_total` sempre passa; senão, só quando a
    camada NÃO liga `edicao.somente_proprias`, ou quando a feição é do próprio ator."""
    if auth.tem("feicoes.editar_total"):
        return
    if (dados.get("edicao") or {}).get("somente_proprias") and linha_atual.get("criado_por") != auth.usuario_id:
        raise ErroAPI(403, "feicao_de_outro_usuario", "esta camada só permite editar/apagar as próprias feições")


def _validar_tipo_e_tamanho(campo: str, valor: Any, tipo_pg: str) -> Any:
    if valor is None:
        return None
    if tipo_pg == "text":
        s = valor if isinstance(valor, str) else str(valor)
        if len(s.encode("utf-8")) > limites.EDICAO_TEXTO_MAX:
            raise ErroAPI(
                422, "texto_grande", f"campo {campo} acima de {limites.EDICAO_TEXTO_MAX} bytes", {"campo": campo}
            )
        return s
    if tipo_pg in ("integer", "bigint"):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or (
            isinstance(valor, float) and not valor.is_integer()
        ):
            raise ErroAPI(422, "tipo_invalido", f"campo {campo} exige inteiro", {"campo": campo, "valor": valor})
        return int(valor)
    if tipo_pg in ("double precision", "real"):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroAPI(422, "tipo_invalido", f"campo {campo} exige número", {"campo": campo, "valor": valor})
        return float(valor)
    if tipo_pg == "boolean":
        if not isinstance(valor, bool):
            raise ErroAPI(
                422, "tipo_invalido", f"campo {campo} exige verdadeiro/falso", {"campo": campo, "valor": valor}
            )
        return valor
    return valor  # date/time/timestamp/bytea: o Postgres recusa na gravação (mapeado por erro_do_banco)


def _validar_dominio(campo: str, valor: Any, regra: dict) -> None:
    if valor is None or not regra:
        return
    valores = regra.get("dominio_valores")
    if valores is not None and valor not in valores:
        raise ErroAPI(
            422, "fora_do_dominio", f"valor fora do domínio do campo {campo}: {valor!r}",
            {"campo": campo, "valor": valor},
        )
    minimo, maximo = regra.get("dominio_min"), regra.get("dominio_max")
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if minimo is not None and valor < minimo:
            raise ErroAPI(
                422, "fora_do_dominio", f"valor abaixo do domínio do campo {campo}: {valor!r}",
                {"campo": campo, "valor": valor, "minimo": minimo},
            )
        if maximo is not None and valor > maximo:
            raise ErroAPI(
                422, "fora_do_dominio", f"valor acima do domínio do campo {campo}: {valor!r}",
                {"campo": campo, "valor": valor, "maximo": maximo},
            )


def validar_atributos(atributos: dict | None, dados: dict, operacao: str) -> tuple[dict, list[str]]:
    """Filtra rastreio (cláusula 7), confere campo existente, tipo/tamanho, domínio (cláusula 3) e
    obrigatoriedade (só em `adicionar`, uma feição nova sem o campo obrigatório é 422)."""
    campos_validos = {c["nome"]: c for c in dados.get("campos") or []}
    regras = dados.get("regras_campo") or {}
    limpos: dict[str, Any] = {}
    avisos: list[str] = []
    for campo, valor in (atributos or {}).items():
        if campo in RESERVADOS:
            avisos.append(f"campo de rastreio ignorado (preenchido pelo servidor): {campo}")
            continue
        if campo not in campos_validos:
            raise ErroAPI(422, "campo_inexistente", f"campo inexistente nesta camada: {campo}", {"campo": campo})
        regra = regras.get(campo) or {}
        if regra.get("somente_leitura"):
            avisos.append(f"campo somente-leitura ignorado: {campo}")
            continue
        valor = _validar_tipo_e_tamanho(campo, valor, campos_validos[campo]["tipo"])
        _validar_dominio(campo, valor, regra)
        limpos[campo] = valor
    if operacao == "adicionar":
        for campo, regra in regras.items():
            if regra.get("obrigatorio") and not regra.get("somente_leitura") and campo in campos_validos:
                if campo not in limpos or limpos[campo] is None:
                    raise ErroAPI(422, "campo_obrigatorio", f"campo obrigatório ausente: {campo}", {"campo": campo})
    return limpos, avisos


def _preparar_geometria(
    cur, geometria: dict, srid_entrada: int | None, dados: dict, corrigir: bool
) -> tuple[bytes, str | None]:
    """Confere tipo (família + promoção Point/LineString/Polygon -> Multi*, mesma regra de
    app/ingestao/carregar.py), transforma para o SRID da camada quando declarado diferente, e valida
    (ST_IsValid); com `corrigir=True` aplica ST_MakeValid e devolve aviso, sem isso recusa (422, cláusula 5)."""
    tipo_coluna = dados.get("geometria")
    if tipo_coluna in (None, "nenhuma"):
        raise ErroAPI(422, "camada_sem_geometria", "esta camada não tem coluna de geometria")
    tipo_enviado = geometria.get("type") if isinstance(geometria, dict) else None
    if tipo_enviado not in TIPOS_CONCRETOS:
        raise ErroAPI(
            422, "tipo_geometria_invalido", f"tipo de geometria não reconhecido: {tipo_enviado!r}",
            {"tipo_enviado": tipo_enviado, "tipo_esperado": tipo_coluna},
        )
    promover = False
    if tipo_coluna != "Geometry" and tipo_enviado != tipo_coluna:
        if MULTI_DE.get(tipo_enviado) == tipo_coluna:
            promover = True
        else:
            raise ErroAPI(
                422, "tipo_geometria_invalido",
                f"geometria do tipo {tipo_enviado} não é aceita nesta camada (esperado {tipo_coluna})",
                {"tipo_enviado": tipo_enviado, "tipo_esperado": tipo_coluna},
            )
    try:
        geojson_txt = json.dumps(geometria)
    except (TypeError, ValueError) as e:
        raise ErroAPI(422, "geometria_invalida", "geometria não é um GeoJSON serializável") from e

    srid_camada = int(dados["srid"])
    srid_declarado = srid_entrada is not None
    srid_origem = int(srid_entrada) if srid_entrada else srid_camada
    expr = "ST_SetSRID(ST_GeomFromGeoJSON(%s), %s)"
    parametros: list[Any] = [geojson_txt, srid_origem]
    if srid_origem != srid_camada:
        expr = f"ST_Transform({expr}, %s)"
        parametros.append(srid_camada)
    if promover:
        expr = f"ST_Multi({expr})"
    # sanidade de CRS não declarado (refutação do item: "geometria em outro CRS sem declarar"): sem `crs` no
    # corpo, a entrada é tratada como já estando no SRID da camada (hipótese do item). Quando esse SRID é
    # geográfico (grau, ex. 4326/4674) e a geometria enviada tem coordenada fora de [-180,180]/[-90,90], NÃO é
    # coordenada geográfica válida em NENHUMA hipótese — é quase sempre um envio em metros (UTM/Web Mercator)
    # sem declarar o `crs`. Detectável sem heurística de "provavelmente errado": os limites do próprio domínio
    # matemático do grau já bastam. Só roda quando o CRS NÃO foi declarado (é exatamente a lacuna do teste do
    # adversário) — com `crs` declarado, ST_Transform já converteu para o sistema certo antes desta checagem.
    if not srid_declarado:
        cur.execute(
            "SELECT proj4text ~ '\\+proj=longlat' AS geografico FROM spatial_ref_sys WHERE srid = %s",
            (srid_camada,),
        )
        rr = cur.fetchone()
        if rr and rr["geografico"]:
            cur.execute(
                "WITH g AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), %s) AS geom) "
                "SELECT ST_XMin(geom) AS xmin, ST_XMax(geom) AS xmax, "
                "ST_YMin(geom) AS ymin, ST_YMax(geom) AS ymax FROM g",
                [geojson_txt, srid_origem],
            )
            ext = cur.fetchone()
            fora = (
                ext and (
                    ext["xmin"] < -180 or ext["xmax"] > 180 or ext["ymin"] < -90 or ext["ymax"] > 90
                )
            )
            if fora:
                raise ErroAPI(
                    422, "geometria_fora_do_crs",
                    "coordenada fora do intervalo geográfico da camada (grau: longitude em [-180,180], "
                    "latitude em [-90,90]); declare `crs.srid` se a geometria não estiver no SRID da camada",
                    {"srid_camada": srid_camada, "extent": {"xmin": ext["xmin"], "xmax": ext["xmax"],
                                                             "ymin": ext["ymin"], "ymax": ext["ymax"]}},
                )
    try:
        cur.execute(
            f"WITH g AS (SELECT {expr} AS geom) SELECT ST_IsValid(geom) AS valido, "
            f"ST_IsValidReason(geom) AS motivo, ST_AsBinary(geom) AS original, "
            f"ST_AsBinary(ST_MakeValid(geom)) AS corrigida FROM g",
            parametros,
        )
    except psycopg2.Error as e:
        raise ErroAPI(
            422, "geometria_invalida", "geometria não pôde ser interpretada (coordenadas ou GeoJSON inválidos)",
            {"detalhe": str(e).strip()[:300]},
        ) from e
    r = cur.fetchone()
    if r["valido"]:
        return bytes(r["original"]), None
    if not corrigir:
        raise ErroAPI(
            422, "geometria_invalida", f"geometria inválida: {r['motivo']}",
            {"motivo": r["motivo"], "corrigir_disponivel": True},
        )
    return bytes(r["corrigida"]), f"geometria corrigida por ST_MakeValid: {r['motivo']}"


def _feicao_atual_json(atual: dict, dados: dict) -> dict:
    campos = [c["nome"] for c in dados.get("campos") or []]
    saida = {
        "id": str(atual["globalid"]),
        "versao": atual["versao"],
        "atributos": {c: atual.get(c) for c in campos if c in atual},
    }
    geo = atual.get("__geom_geojson")
    if geo:
        saida["geometria"] = json.loads(geo)
    return saida


def _inserir(
    cur, auth: Auth, dados: dict, corpo: EdicoesEntrada, feicao: FeicaoAdicionar
) -> tuple[ResultadoFeicao, list[str]]:
    schema, tabela = _schema_tabela(dados)
    atributos, avisos = validar_atributos(feicao.atributos, dados, "adicionar")
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    colunas = list(atributos.keys())
    valores: list[Any] = [atributos[c] for c in colunas]
    campos_valores_sql = ["%s"] * len(colunas)
    if tem_geom:
        if feicao.geometria is None:
            raise ErroAPI(422, "geometria_ausente", "geometria obrigatória para adicionar nesta camada")
        wkb, aviso_geom = _preparar_geometria(
            cur, feicao.geometria, corpo.crs.srid if corpo.crs else None, dados, corpo.corrigir_geometria
        )
        if aviso_geom:
            avisos.append(aviso_geom)
        colunas.append("geom")
        campos_valores_sql.append("ST_SetSRID(ST_GeomFromWKB(%s), %s)")
        valores += [psycopg2.Binary(wkb), int(dados["srid"])]
    elif feicao.geometria is not None:
        raise ErroAPI(422, "camada_sem_geometria", "esta camada não aceita geometria")

    if not colunas:
        cur.execute(f'INSERT INTO "{schema}"."{tabela}" DEFAULT VALUES RETURNING fid, globalid, versao')
    else:
        cols_sql = ", ".join(_ident(c) if c != "geom" else "geom" for c in colunas)
        cur.execute(
            f'INSERT INTO "{schema}"."{tabela}" ({cols_sql}) VALUES ({", ".join(campos_valores_sql)}) '
            f"RETURNING fid, globalid, versao",
            valores,
        )
    r = cur.fetchone()
    resultado = ResultadoFeicao(
        sucesso=True, id=str(r["globalid"]), fid=r["fid"], versao=r["versao"], atributos=atributos
    )
    return resultado, avisos


def _atualizar(
    cur, auth: Auth, dados: dict, corpo: EdicoesEntrada, feicao: FeicaoAtualizar
) -> tuple[ResultadoFeicao, list[str]]:
    schema, tabela = _schema_tabela(dados)
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    extra = ", ST_AsGeoJSON(geom) AS __geom_geojson" if tem_geom else ""
    cur.execute(f'SELECT *{extra} FROM "{schema}"."{tabela}" WHERE globalid = %s FOR UPDATE', (feicao.id,))
    atual = cur.fetchone()
    if atual is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"id": feicao.id})
    _exigir_dono_ou_admin(auth, dados, atual)
    if atual["versao"] != feicao.versao:
        raise ErroAPI(
            409, "conflito_versao", "a feição foi alterada por outra sessão desde a versão lida",
            {"id": feicao.id, "versao_enviada": feicao.versao, "versao_atual": atual["versao"],
             "atual": _feicao_atual_json(atual, dados)},
        )
    avisos: list[str] = []
    sets: list[str] = []
    valores: list[Any] = []
    if feicao.atributos:
        atributos, avisos_a = validar_atributos(feicao.atributos, dados, "atualizar")
        avisos += avisos_a
        for c, v in atributos.items():
            sets.append(f"{_ident(c)} = %s")
            valores.append(v)
    if feicao.geometria is not None:
        if not tem_geom:
            raise ErroAPI(422, "camada_sem_geometria", "esta camada não aceita geometria")
        if (dados.get("edicao") or {}).get("geometria_travada"):
            raise ErroAPI(422, "geometria_travada", "geometria travada nesta camada: só atributo é editável")
        wkb, aviso_geom = _preparar_geometria(
            cur, feicao.geometria, corpo.crs.srid if corpo.crs else None, dados, corpo.corrigir_geometria
        )
        if aviso_geom:
            avisos.append(aviso_geom)
        sets.append("geom = ST_SetSRID(ST_GeomFromWKB(%s), %s)")
        valores += [psycopg2.Binary(wkb), int(dados["srid"])]
    if not sets:
        return ResultadoFeicao(sucesso=True, id=feicao.id, fid=atual["fid"], versao=atual["versao"]), avisos
    valores.append(feicao.id)
    cur.execute(
        f'UPDATE "{schema}"."{tabela}" SET {", ".join(sets)} WHERE globalid = %s RETURNING fid, versao',
        valores,
    )
    r = cur.fetchone()
    return ResultadoFeicao(sucesso=True, id=feicao.id, fid=r["fid"], versao=r["versao"]), avisos


def _apagar(
    cur, auth: Auth, dados: dict, corpo: EdicoesEntrada, feicao: FeicaoApagar
) -> tuple[ResultadoFeicao, list[str]]:
    schema, tabela = _schema_tabela(dados)
    cur.execute(
        f'SELECT fid, globalid, versao, criado_por FROM "{schema}"."{tabela}" WHERE globalid = %s FOR UPDATE',
        (feicao.id,),
    )
    atual = cur.fetchone()
    if atual is None:
        raise ErroAPI(404, "feicao_inexistente", "feição inexistente nesta camada", {"id": feicao.id})
    _exigir_dono_ou_admin(auth, dados, atual)
    if feicao.versao is not None and atual["versao"] != feicao.versao:
        raise ErroAPI(
            409, "conflito_versao", "a feição foi alterada por outra sessão desde a versão lida",
            {"id": feicao.id, "versao_enviada": feicao.versao, "versao_atual": atual["versao"]},
        )
    cur.execute(f'DELETE FROM "{schema}"."{tabela}" WHERE globalid = %s', (feicao.id,))
    return ResultadoFeicao(sucesso=True, id=feicao.id, fid=atual["fid"]), []


def _processar_lista(cur, lista: list, aplicar, modo: str, prefixo: str) -> tuple[list[ResultadoFeicao], list[str]]:
    """Modo `transacao` (padrão): a primeira falha propaga (o `with db.db()` do chamador desfaz tudo — portão
    cláusula 1). Modo `parcial`: cada feição roda sob SAVEPOINT próprio, um erro desfaz só ELA e o lote segue
    (como o `applyEdits` com `rollbackOnFailure=false`), devolvendo o resultado feição a feição."""
    resultados: list[ResultadoFeicao] = []
    avisos: list[str] = []
    for indice, feicao in enumerate(lista):
        savepoint = f"{prefixo}_{indice}"
        if modo == "parcial":
            cur.execute(f"SAVEPOINT {savepoint}")
        try:
            resultado, avisos_item = aplicar(cur, feicao)
            resultados.append(resultado)
            avisos.extend(avisos_item)
            if modo == "parcial":
                cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        except (ErroAPI, psycopg2.Error) as e:
            if modo != "parcial":
                raise
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
            erro = e if isinstance(e, ErroAPI) else comum.erro_do_banco(e)
            resultados.append(
                ResultadoFeicao(
                    sucesso=False,
                    id=getattr(feicao, "id", None),
                    erro=erro.erro,
                    mensagem=erro.mensagem,
                    detalhe=erro.detalhe,
                )
            )
    return resultados, avisos


def aplicar_edicoes(cur, request: Request, auth: Auth, camada_id: str, corpo: EdicoesEntrada) -> EdicoesSaida:
    item, dados = camada_ou_404(cur, camada_id)
    exigir_camada_editavel(auth, dados)

    resultados_add, av1 = _processar_lista(
        cur, corpo.adicionar, lambda c, f: _inserir(c, auth, dados, corpo, f), corpo.modo, "sp_add"
    )
    resultados_upd, av2 = _processar_lista(
        cur, corpo.atualizar, lambda c, f: _atualizar(c, auth, dados, corpo, f), corpo.modo, "sp_upd"
    )
    resultados_del, av3 = _processar_lista(
        cur, corpo.apagar, lambda c, f: _apagar(c, auth, dados, corpo, f), corpo.modo, "sp_del"
    )
    avisos = [*av1, *av2, *av3]

    n_add = sum(1 for r in resultados_add if r.sucesso)
    n_upd = sum(1 for r in resultados_upd if r.sucesso)
    n_del = sum(1 for r in resultados_del if r.sucesso)
    if n_add or n_upd or n_del:
        # bump de `tiles_versao` (invalida cache de tiles do L2-01-b, ainda pendente — o contador já existe
        # para quando aquele item ler daqui; não é retrabalho, o consumidor é que falta) + evento por LOTE
        # (portão cláusula 9: uma linha por chamada, nunca uma por feição).
        cur.execute(
            "UPDATE plat.item SET dados = dados || jsonb_build_object('tiles_versao', "
            "coalesce((dados->>'tiles_versao')::int, 0) + 1) WHERE id = %s::uuid",
            (item["id"],),
        )
    comum.registrar_evento(
        cur, request, "camadas/editar", "item", item["id"],
        {"adicionados": n_add, "atualizados": n_upd, "apagados": n_del, "modo": corpo.modo},
    )
    return EdicoesSaida(
        modo=corpo.modo, adicionar=resultados_add, atualizar=resultados_upd, apagar=resultados_del, avisos=avisos
    )

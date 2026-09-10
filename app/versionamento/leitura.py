"""Relação SQL que uma leitura versionada enxerga (item L2-13-a).

Regra da Esri, escrita por extenso porque é o coração do produto: ler no ramo é ver **as linhas do ramo
desde o início dele, mais as linhas do padrão anteriores ao momento base do ramo, tirando as feições que
o ramo já tocou**. Uma feição que o ramo apagou some do ramo e continua no padrão; uma que o padrão mudou
depois do momento base continua no ramo com o valor antigo, até que o ramo seja reconciliado.

Como o padrão não guarda `momento_inicio`/`momento_fim` nas suas próprias linhas (ver a decisão de desenho
na migração 20260908T1225), o estado do padrão num momento anterior é RECONSTRUÍDO a partir de
`plat.feicao_historico` (item L2-03-d), que grava atributos e geometria de antes e de depois de toda
escrita. Para cada feição, a PRIMEIRA entrada de histórico posterior ao momento pedido carrega, no seu
campo "antes", exatamente o estado daquela feição naquele momento — e se essa primeira entrada é um
`inserir`, a feição ainda não existia. Isso vale também para feição apagada depois do momento: ela não
está mais na tabela, mas o "antes" do histórico a devolve inteira.

A saída é um trecho de SQL para usar no lugar de `"schema"."tabela"` no `FROM`, com os parâmetros na
ordem em que os `%s` aparecem. Quem chama continua escrevendo `WHERE`, `ORDER BY` e projeção como se
fosse a tabela física: as colunas têm os mesmos nomes e a mesma ordem.
"""

from __future__ import annotations

import re

from app.erros import ErroAPI

_RE_SCHEMA = re.compile(r"^d_[a-z0-9_]{1,60}$")
_RE_TABELA = re.compile(r"^c_[0-9a-f]{16}$")
_RE_CAMPO = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def nomes_ok(schema: str, tabela: str) -> tuple[str, str]:
    if not (isinstance(schema, str) and _RE_SCHEMA.match(schema)):
        raise ErroAPI(409, "camada_configuracao_invalida", "metadado de schema da camada inconsistente")
    if not (isinstance(tabela, str) and _RE_TABELA.match(tabela)):
        raise ErroAPI(409, "camada_configuracao_invalida", "metadado de tabela da camada inconsistente")
    return schema, tabela


def tabela_ramo(tabela: str) -> str:
    """Nome da tabela companheira que guarda as linhas de ramo (`plat.camada_versionar` a cria)."""
    return tabela + "__ramo"


def colunas_fisicas(cur, schema: str, tabela: str) -> list[str]:
    """Colunas da tabela da camada, na ordem física. É esta lista, e não `dados.campos`, que define a
    projeção das três pernas do UNION: o `UNION ALL` exige mesma aridade e mesma ordem, e a tabela tem
    colunas que o metadado do catálogo não lista (fid, globalid, versao, tenant_id, rastreio)."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, tabela),
    )
    nomes = [r["column_name"] for r in cur.fetchall()]
    if not nomes:
        raise ErroAPI(409, "camada_configuracao_invalida", "tabela da camada inexistente")
    for n in nomes:
        if not _RE_CAMPO.match(n):
            raise ErroAPI(409, "camada_configuracao_invalida", f"nome de coluna inválido na camada: {n!r}")
    return nomes


def _projecao(colunas: list[str], prefixo: str) -> str:
    return ", ".join(f'{prefixo}."{c}"' for c in colunas)


def _projecao_reconstruida(colunas: list[str], srid: int) -> tuple[str, list]:
    """Projeção da perna que vem do histórico: cada coluna sai do registro remontado por
    `jsonb_populate_record` sobre o rowtype da própria tabela (tipos convertidos pelo Postgres, sem
    adivinhação nossa); `geom` vem à parte, do GeoJSON que o gatilho gravou."""
    partes = []
    params: list = []
    for c in colunas:
        if c == "geom":
            partes.append("ST_SetSRID(ST_GeomFromGeoJSON(h.geom_antes), %s)")
            params.append(srid)
        else:
            partes.append(f'r."{c}"')
    return ", ".join(partes), params


def _cte_historico(schema: str, tabela: str) -> tuple[str, list]:
    """PRIMEIRA alteração de cada feição depois do momento pedido: o campo "antes" dela é o estado no
    momento. `DISTINCT ON ... ORDER BY globalid, momento ASC` devolve uma linha por feição."""
    sql = (
        "h AS (SELECT DISTINCT ON (globalid) globalid, operacao, atributos_antes, geom_antes "
        "      FROM plat.feicao_historico "
        "     WHERE schema_dado = %s AND tabela_dado = %s AND momento > %s "
        "     ORDER BY globalid, momento ASC)"
    )
    return sql, [schema, tabela]


def relacao_padrao_no_momento(
    cur, schema: str, tabela: str, srid: int, momento, colunas: list[str] | None = None
) -> tuple[str, list]:
    """Padrão como estava em `momento` (o `historicMoment` da Esri)."""
    colunas = colunas or colunas_fisicas(cur, schema, tabela)
    cte, cte_params = _cte_historico(schema, tabela)
    recon, recon_params = _projecao_reconstruida(colunas, srid)
    sql = (
        f"(WITH {cte} "
        f'SELECT {_projecao(colunas, "p")} FROM "{schema}"."{tabela}" p '
        f"  LEFT JOIN h ON h.globalid = p.globalid WHERE h.globalid IS NULL "
        f"UNION ALL "
        f"SELECT {recon} FROM h, LATERAL jsonb_populate_record(NULL::\"{schema}\".\"{tabela}\", "
        f"       h.atributos_antes) r WHERE h.operacao <> 'inserir') AS q"
    )
    return sql, [*cte_params, momento, *recon_params]


def relacao_do_ramo(
    cur, schema: str, tabela: str, srid: int, versao_id: str, momento_base, colunas: list[str] | None = None
) -> tuple[str, list]:
    """Leitura dentro do ramo: linhas vigentes do ramo + padrão no momento base, sem as feições que o
    ramo tocou (tocar inclui apagar — por isso a exclusão é por `globalid` presente no ramo, não por
    linha vigente)."""
    colunas = colunas or colunas_fisicas(cur, schema, tabela)
    ramo = tabela_ramo(tabela)
    cte, cte_params = _cte_historico(schema, tabela)
    recon, recon_params = _projecao_reconstruida(colunas, srid)
    toque = f'toque AS (SELECT DISTINCT globalid FROM "{schema}"."{ramo}" WHERE versao_id = %s::uuid)'
    sql = (
        f"(WITH {cte}, {toque} "
        f'SELECT {_projecao(colunas, "b")} FROM "{schema}"."{ramo}" b '
        f"  WHERE b.versao_id = %s::uuid AND b.momento_fim IS NULL AND NOT b.apagada "
        f"UNION ALL "
        f'SELECT {_projecao(colunas, "p")} FROM "{schema}"."{tabela}" p '
        f"  LEFT JOIN h ON h.globalid = p.globalid "
        f"  WHERE h.globalid IS NULL AND p.globalid NOT IN (SELECT globalid FROM toque) "
        f"UNION ALL "
        f"SELECT {recon} FROM h, LATERAL jsonb_populate_record(NULL::\"{schema}\".\"{tabela}\", "
        f"       h.atributos_antes) r "
        f"  WHERE h.operacao <> 'inserir' AND h.globalid NOT IN (SELECT globalid FROM toque)) AS q"
    )
    return sql, [*cte_params, momento_base, versao_id, versao_id, *recon_params]


def feicao_no_padrao_em(cur, schema: str, tabela: str, srid: int, momento, globalid: str) -> dict | None:
    """Uma feição do padrão como estava em `momento` (atributos + geometria em GeoJSON), ou None se ela
    ainda não existia. Base da comparação atributo a atributo da reconciliação."""
    colunas = colunas_fisicas(cur, schema, tabela)
    origem, params = relacao_padrao_no_momento(cur, schema, tabela, srid, momento, colunas)
    tem_geom = "geom" in colunas
    extra = ", ST_AsGeoJSON(geom) AS __geom" if tem_geom else ""
    cur.execute(f"SELECT *{extra} FROM {origem} WHERE globalid = %s::uuid", [*params, globalid])
    return cur.fetchone()

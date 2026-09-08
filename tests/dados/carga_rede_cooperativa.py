"""Carrega um recorte REAL de rede de distribuidora (item L4-20-consumidores-e-enderecos) nas tabelas
`plat.rede_*` do inquilino de demonstração. O schema de origem vem do ambiente da trilha
(`PLAT_REDE_ESQUEMA_COOP`; dado aberto BDGD já em disco, nada baixado) e NUNCA entra no git — os
arquivos comitados se referem a ele só pelo nome lido do ambiente.

Regra de privacidade da carga: só atributos de rede. De `ucbt` NÃO copiam `pn_con` (nome), `brr`,
`cep`, `cnae`, `ceg_gd` nem nenhum campo que identifique pessoa; o consumo anual (`ene_sum`) entra
em `plat.rede_uc_consumo` e nenhuma rota o devolve por unidade.

Heurística declarada do ponto do transformador: a BDGD do recorte não traz geometria de transformador
(`eqtrmt` é só atributo), então o ponto é o início do primeiro trecho de baixa tensão que o
transformador alimenta (a derivação nasce no poste dele). Heurística do ano de referência: `ene_sum`
é o somatório anual do recorte (BDGD 2024), gravado com ANO_REFERENCIA fixo e declarado."""

from __future__ import annotations

import os

ANO_REFERENCIA = 2024

TABELAS_ORIGEM = ("ssdmt", "ssdbt", "ucbt", "cnefe_pt")


def esquema_coop() -> str | None:
    return os.environ.get("PLAT_REDE_ESQUEMA_COOP") or None


def disponivel(con) -> bool:
    """True quando o schema de origem existe e tem as quatro tabelas que a carga lê."""
    esquema = esquema_coop()
    if not esquema:
        return False
    with con.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM information_schema.tables"
            " WHERE table_schema = %s AND table_name = ANY(%s)",
            (esquema, list(TABELAS_ORIGEM)),
        )
        return cur.fetchone()["n"] == len(TABELAS_ORIGEM)


def carregar(con, tenant_slug: str = "demo") -> dict:
    """Carga completa e idempotente para um inquilino. Devolve as contagens por tabela."""
    esquema = esquema_coop()
    if not esquema:
        raise RuntimeError("PLAT_REDE_ESQUEMA_COOP não definido no ambiente")
    contagem: dict[str, int] = {}
    # cursor da própria conexão (CursorSchemaAmbiente): o `plat.` literal é reescrito para o schema
    # da trilha; um cursor_factory novo aqui ignoraria a reescrita e bateria no schema de produção
    with con.cursor() as cur:
        # o id do inquilino vem pela função SECURITY DEFINER (a tabela tenant tem RLS pelo próprio id)
        cur.execute("SELECT tenant_id::text AS id FROM plat.auth_login(%s, 'admin')", (tenant_slug,))
        linha = cur.fetchone()
        if linha is None:
            raise RuntimeError(f"inquilino '{tenant_slug}' não existe na trilha")
        tid = linha["id"]
        cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (tid,))

        # recomeço: a carga é a fonte de verdade da rede de teste do inquilino
        cur.execute(
            "DELETE FROM plat.rede_uc_consumo WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_uc WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_trafo WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_trecho WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_endereco_sem_rede WHERE tenant_id = plat.tenant_atual();"
            "DELETE FROM plat.rede_endereco WHERE tenant_id = plat.tenant_atual();"
        )

        # trechos de média e baixa tensão (wkt MULTILINESTRING de 1 parte -> LineString 4674);
        # o snapshot tem código repetido em algumas linhas: fica a primeira (DISTINCT ON cod_id)
        for tabela, nivel in (("ssdmt", "mt"), ("ssdbt", "bt")):
            cur.execute(
                f"INSERT INTO plat.rede_trecho (tenant_id, nivel, codigo, ctmt, comprimento_m, geometria) "
                f"SELECT %s, %s, cod_id, ctmt, comp, ST_GeometryN(ST_GeomFromText(wkt, 4674), 1)"
                f"  FROM (SELECT DISTINCT ON (cod_id) cod_id, ctmt, comp, wkt"
                f"          FROM {esquema}.{tabela}"
                f"         WHERE wkt IS NOT NULL AND wkt <> ''"
                f"           AND ST_NumGeometries(ST_GeomFromText(wkt, 4674)) = 1"
                f"         ORDER BY cod_id) t",
                (tid, nivel),
            )
            contagem[f"trechos_{nivel}"] = cur.rowcount

        # transformadores: ponto = início do primeiro trecho de bt que ele alimenta
        cur.execute(
            f"INSERT INTO plat.rede_trafo (tenant_id, codigo, ctmt, geometria) "
            f"SELECT %s, uni_tr_mt, ctmt, ST_StartPoint(ST_GeometryN(ST_GeomFromText(wkt, 4674), 1))"
            f"  FROM (SELECT DISTINCT ON (uni_tr_mt) uni_tr_mt, ctmt, wkt"
            f"          FROM {esquema}.ssdbt WHERE uni_tr_mt IS NOT NULL AND wkt IS NOT NULL AND wkt <> ''"
            f"         ORDER BY uni_tr_mt, cod_id) t",
            (tid,),
        )
        contagem["trafos"] = cur.rowcount

        # unidades consumidoras: whitelist de atributos de rede (nunca nome/bairro/cep/cnae)
        cur.execute(
            f"INSERT INTO plat.rede_uc (tenant_id, codigo, ctmt, uni_tr_mt, situacao, grupo_tensao) "
            f"SELECT %s, cod_id, ctmt, uni_tr_mt, sit_ativ, gru_ten"
            f"  FROM (SELECT DISTINCT ON (cod_id) * FROM {esquema}.ucbt ORDER BY cod_id) u",
            (tid,),
        )
        contagem["ucs"] = cur.rowcount
        cur.execute(
            f"INSERT INTO plat.rede_uc_consumo (uc_id, tenant_id, ano, ene_kwh) "
            f"SELECT u.id, %s, %s, b.ene_sum"
            f"  FROM (SELECT DISTINCT ON (id) id, tenant_id, codigo FROM plat.rede_uc"
            f"         WHERE tenant_id = plat.tenant_atual() ORDER BY id) u"
            f"       JOIN (SELECT DISTINCT ON (cod_id) cod_id, ene_sum FROM {esquema}.ucbt"
            f"              WHERE ene_sum IS NOT NULL ORDER BY cod_id) b ON b.cod_id = u.codigo",
            (tid, ANO_REFERENCIA),
        )
        contagem["consumos"] = cur.rowcount

        # endereços do censo (ponto público)
        cur.execute(
            f"INSERT INTO plat.rede_endereco (tenant_id, fonte, endereco_id, geometria) "
            f"SELECT %s, 'censo', id, ST_SetSRID(geom, 4674)"
            f"  FROM (SELECT DISTINCT ON (id) * FROM {esquema}.cnefe_pt ORDER BY id) e",
            (tid,),
        )
        contagem["enderecos"] = cur.rowcount
    con.commit()
    return contagem

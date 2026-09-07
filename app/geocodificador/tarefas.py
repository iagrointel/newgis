"""Job `geocodificador.lote_csv` (item L2-11-a-geocodificacao-csv): geocodifica uma tabela CSV inteira com o
motor do L2-11-b (`app.geocodificador.lote.processar_lote`) e grava o resultado como camada nova
(`d_<slug>.c_<uuid16>`, mesma máquina de `plat.camada_preparar` que o L0-04-c usa) com as colunas de qualidade
(`score`, `tipo_acerto`, `origem`, `pendente`) que a tela de revisão (rotas em `rotas_lote.py`) lê e escreve. A
ficha de proveniência (`plat.geocodificacao_lote.proveniencia`) registra a VERSÃO da base de endereços usada
(sha256 do zip do CNEFE + data de instalação, de `plat.geo_instalacao`) — sem isso um re-geocodificar depois de
trocar a base de endereços não seria auditável."""

from __future__ import annotations

import time
import uuid

import psycopg2
from pydantic import BaseModel, Field, field_validator

from app import limites
from app.catalogo.comum import jsonb
from app.geocodificador import lote
from app.jobs.registro import FalhaDefinitiva, tarefa


class GeocodificarLoteParametros(BaseModel):
    titulo: str = Field(min_length=1, max_length=limites.GEOCODIFICADOR_LOTE_TITULO_MAX)
    csv_texto: str = Field(min_length=1)
    mapeamento: dict[str, str]
    delimitador: str = Field(default=",", min_length=1, max_length=1)
    limiar_pendente: float = Field(default=limites.GEOCODIFICADOR_LOTE_LIMIAR_PENDENTE_PADRAO, ge=0, le=100)

    @field_validator("mapeamento")
    @classmethod
    def _v_mapeamento(cls, v):
        if not v:
            raise ValueError("mapeamento vazio")
        return v


def _inserir_pontos(cur, schema: str, tabela: str, linhas: list[lote.LinhaGeocodificada]) -> None:
    cur.execute(
        f'CREATE TABLE "{schema}"."{tabela}" ('
        "  fid serial PRIMARY KEY, geom geometry(Point,4326), endereco_entrada text NOT NULL, "
        "  linha_origem integer NOT NULL, campos_entrada jsonb NOT NULL, score numeric, tipo_acerto text, "
        "  cod_municipio integer, origem text NOT NULL DEFAULT 'automatica', pendente boolean NOT NULL, "
        "  erro text, avisos text[] NOT NULL DEFAULT '{}', "
        "  atualizado_em timestamptz NOT NULL DEFAULT now(), atualizado_por int"
        ")"
    )
    for linha in linhas:
        geom = f"SRID=4326;POINT({linha.lon} {linha.lat})" if linha.lon is not None else None
        cur.execute(
            f'INSERT INTO "{schema}"."{tabela}" '
            "(geom, endereco_entrada, linha_origem, campos_entrada, score, tipo_acerto, cod_municipio, "
            " pendente, erro, avisos) "
            "VALUES (CASE WHEN %(geom)s IS NULL THEN NULL ELSE ST_GeomFromEWKT(%(geom)s) END, "
            "        %(endereco)s, %(linha_origem)s, %(campos)s, %(score)s, %(tipo_acerto)s, %(cod_municipio)s, "
            "        %(pendente)s, %(erro)s, %(avisos)s)",
            {
                "geom": geom, "endereco": linha.endereco_entrada, "linha_origem": linha.linha_origem,
                "campos": jsonb(linha.campos_entrada), "score": linha.score, "tipo_acerto": linha.tipo_acerto,
                "cod_municipio": linha.cod_municipio, "pendente": linha.pendente, "erro": linha.erro,
                "avisos": linha.avisos,
            },
        )


def _proveniencia_enderecos(cur, linhas: list[lote.LinhaGeocodificada]) -> list[dict]:
    """Ficha de proveniência: uma linha por UF do CNEFE efetivamente usada pelo lote (join com
    `plat.geo_instalacao`, escrito por `scripts/geocodificador_instalar_uf.py`) — a VERSÃO da base de
    endereços, não um "confie em mim"."""
    cods_municipio = sorted({linha.cod_municipio for linha in linhas if linha.cod_municipio is not None})
    if not cods_municipio:
        return []
    cur.execute(
        "SELECT DISTINCT i.cod_uf, i.sigla, i.fonte_url, i.sha256_zip, i.instalado_em, i.linhas "
        "FROM plat.geo_instalacao i "
        "JOIN plat.geo_municipio m ON m.cod_uf = i.cod_uf "
        "WHERE m.cod = ANY(%s)",
        (cods_municipio,),
    )
    return [
        {
            "cod_uf": r["cod_uf"], "sigla": r["sigla"], "fonte_url": r["fonte_url"], "sha256_zip": r["sha256_zip"],
            "instalado_em": r["instalado_em"].isoformat(), "linhas_instaladas": r["linhas"],
        }
        for r in cur.fetchall()
    ]


@tarefa(
    nome="geocodificador.lote_csv",
    descricao="Geocodifica uma tabela CSV (endereço sem coordenada) com o motor do L2-11-b e publica os pontos "
               "como camada nova, com pendentes para revisão manual (item L2-11-a)",
    parametros=GeocodificarLoteParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=900,
    tentativas=1,
    perfil_minimo="editor",
)
def geocodificador_lote_csv(ctx, **parametros) -> dict:
    p = GeocodificarLoteParametros.model_validate(parametros)
    t0 = time.monotonic()
    cabecalho, linhas_csv = lote.ler_csv(p.csv_texto, delimitador=p.delimitador)
    try:
        lote.validar_mapeamento(cabecalho, p.mapeamento)
    except lote.MapeamentoInvalido as e:
        raise FalhaDefinitiva(str(e)) from e

    with ctx.db() as cur:
        cur.execute("SELECT slug FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        slug = cur.fetchone()["slug"]
    # `d_<slug>` é um schema físico COMPARTILHADO entre trilhas (achado F2/L2-04-a): o DDL de
    # `camada_schema_garantir` (GRANT em schema já existente) pode colidir com o DDL de outra trilha
    # rodando ao mesmo tempo (`tuple concurrently updated`, transitório). Repete até 3x com pausa curta
    # antes de desistir — nunca engolir silenciosamente um erro que não seja essa colisão conhecida.
    tentativas_schema = 8
    for tentativa in range(tentativas_schema):
        try:
            with ctx.db() as cur:
                cur.execute("SELECT plat.camada_schema_garantir(%s)", (slug,))
            break
        except psycopg2.errors.InternalError_ as e:
            if "concurrently updated" not in str(e) or tentativa == tentativas_schema - 1:
                raise
            time.sleep(0.3 * (tentativa + 1))
    schema = f"d_{slug}"
    tabela = f"c_{uuid.uuid4().hex[:16]}"

    ctx.progresso(5, "geocodificando")
    with ctx.db() as cur:
        def _avancar(i, total):
            ctx.progresso(5 + int(70 * i / max(total, 1)), f"geocodificando {i}/{total}")

        linhas = lote.processar_lote(cur, linhas_csv, p.mapeamento, limiar_pendente=p.limiar_pendente,
                                      ao_progredir=_avancar)

    ctx.progresso(80, "publicando a camada")
    item_id = str(uuid.uuid4())
    with ctx.db() as cur:
        _inserir_pontos(cur, schema, tabela, linhas)
        cur.execute("SELECT plat.camada_preparar(%s, %s, %s, %s, %s)", (schema, tabela, 4326, "Point",
                                                                          ctx.usuario_id))
        proveniencia_enderecos = _proveniencia_enderecos(cur, linhas)
        resumo = lote.resumo(linhas)
        titulo = p.titulo[:limites.GEOCODIFICADOR_LOTE_TITULO_MAX]
        item_dados = {
            "schema": schema, "tabela": tabela, "geometria": "Point", "srid": 4326,
            "fonte": "geocodificacao_lote",
            "procedencia": {
                "gerador": "plat geocodificador.lote_csv v1", "job_id": str(ctx.job_id),
                "mapeamento": p.mapeamento, "proveniencia_enderecos": proveniencia_enderecos,
            },
            "geocodificacao": {"resumo": resumo, "limiar_pendente": p.limiar_pendente},
        }
        cur.execute(
            "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, criado_por, modificado_por) "
            "VALUES (%s::uuid, %s, 'camada_vetorial', %s, %s, %s, %s, %s)",
            (item_id, ctx.tenant_id, titulo, ctx.usuario_id, jsonb(item_dados), ctx.usuario_id, ctx.usuario_id),
        )
        cur.execute(
            "INSERT INTO plat.geocodificacao_lote(item_id, tenant_id, mapeamento, limiar_pendente, "
            " proveniencia, resumo) VALUES (%s::uuid, %s, %s, %s, %s, %s)",
            (item_id, ctx.tenant_id, jsonb(p.mapeamento), p.limiar_pendente, jsonb(proveniencia_enderecos),
             jsonb(resumo)),
        )
    ctx.progresso(100, "concluído")
    duracao_s = time.monotonic() - t0
    return {"item_id": item_id, "duracao_s": round(duracao_s, 3), **resumo}

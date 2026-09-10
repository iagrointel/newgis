"""Job `wmts.publicar` (item L2-04-i): pré-renderiza a camada inteira numa faixa de zoom e grava um
PMTiles raster no bucket do inquilino. Depois disso o `GetTile` do WMTS lê uma faixa de bytes do
arquivo em vez de consultar o banco — é o que faz uma camada de 100 mil feições responder tile em
dezenas de milissegundos em vez de segundos.

O job é `pesado` (ocupa CPU por minutos) e tem chave por item, então dois pedidos para a mesma camada
não geram dois arquivos.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.consulta import campos as campos_mod
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.ogc_mapas import dados as dados_mod
from app.ogc_mapas import estilo as estilo_mod
from app.ogc_mapas import matrizes, pintor, prerenderizado

Z_MAX_JOB = 18


class PublicarParametros(BaseModel):
    item_id: uuid.UUID
    z_min: int = Field(0, ge=0, le=Z_MAX_JOB)
    z_max: int = Field(14, ge=0, le=Z_MAX_JOB)
    estilo: str | None = Field(None, description="uuid de item `estilo`; vazio = estilo padrão da camada")


@tarefa(
    nome="wmts.publicar",
    descricao="Publica a camada como WMTS pré-renderizado (PMTiles raster no bucket, servido por Range)",
    parametros=PublicarParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"wmts:{p.get('item_id')}",
    perfil_minimo="editor",
)
def wmts_publicar(ctx, item_id: uuid.UUID, z_min: int = 0, z_max: int = 14, estilo: str | None = None) -> dict:
    iid = str(item_id)
    if z_max < z_min:
        raise FalhaDefinitiva("z_max menor que z_min")
    with ctx.db() as cur:
        cur.execute("SELECT tipo, dados, plat.pode_editar(id) AS pode FROM plat.item WHERE id = %s::uuid", (iid,))
        r = cur.fetchone()
        if r is None or not r["pode"]:
            raise FalhaDefinitiva("item inexistente ou sem permissão de edição")
        if r["tipo"] != "camada_vetorial":
            raise FalhaDefinitiva(f"tipo {r['tipo']} não é camada vetorial")
        dados = r["dados"] or {}
        schema, tabela, srid = dados.get("schema", ""), dados.get("tabela", ""), int(dados.get("srid") or 4326)
        est = estilo_mod.resolver(cur, iid, dados, nome_estilo=estilo)
        campos = ([c["nome"] for c in campos_mod.campos_da_camada(cur, schema, tabela) if c["papel"] == "atributo"]
                  if any(c.get("teste") is not None for c in est["classes"]) else [])
        caixa4326 = dados_mod.extensao_nativa(cur, schema, tabela, srid, 4326)
        if not caixa4326:
            raise FalhaDefinitiva("camada vazia: nada a pré-renderizar")
        ctx.progresso(5, f"desenhando z{z_min}-z{z_max}")

        def desenhar(z: int, x: int, y: int):
            caixa = matrizes.caixa_do_tile(z, x, y)
            feicoes = dados_mod.feicoes_da_caixa(cur, schema, tabela, srid, caixa, 3857,
                                                 matrizes.pixel_span(z) * 0.5, campos=campos)
            if not feicoes:
                return None                      # tile sem feição não entra no arquivo (economia real)
            png, _n = pintor.pintar(feicoes, est, caixa, matrizes.TAMANHO_TILE, matrizes.TAMANHO_TILE,
                                    transparente=True, formato="png")
            return png

        resumo = prerenderizado.gerar(cur, iid, desenhar=desenhar, z_min=z_min, z_max=z_max,
                                      caixa4326=caixa4326, estilo_nome=estilo or "padrao",
                                      usuario_id=getattr(ctx, "usuario_id", None), job_id=ctx.job_id,
                                      progresso=ctx.progresso)
        cur.execute("SELECT plat.evento_registrar('camadas/wmts_publicar', 'item', %s, %s::jsonb, NULL, NULL)",
                    (iid, __import__("json").dumps(resumo, default=str)))
    ctx.progresso(100, f"{resumo['tiles']} tiles em {resumo['bytes']} bytes")
    return {"item_id": iid, **resumo}

"""Job `agol.publicar` (item L2-08-migracao-agol; ADR 0003): publica uma `camada_vetorial` hospedada do
inquilino como hosted feature layer na conta ArcGIS Online do CLIENTE (`app/agol/cliente.py`, portado de
`/home/dev/fgr/sig/pipeline/20_agol_publish.py`). Ordem pensada para cancelamento/retentativa, mesma regra de
`app/imagens/ingestao.py`: o trabalho caro (export do GeoJSON, upload, publish) acontece fora de qualquer
`with ctx.db()` que precise ficar aberto por muito tempo; o estado em `plat.agol_publicacao` é gravado antes
(estado='publicando') e depois (estado='publicado'|'erro') em transações curtas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app import limites
from app.agol import cliente, geojson, publicacao
from app.agol.config import agol_efetivo
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.settings import settings


class PublicarParametros(BaseModel):
    item_id: uuid.UUID
    titulo: str | None = Field(default=None, max_length=limites.AGOL_TITULO_MAX)


def _nome_servico(tenant_slug: str, item_id: str) -> str:
    # mesmo padrão de nome do script original (`sigcorp_<tenant>_<tabela>`), adaptado ao id do item (único
    # entre inquilinos, ao contrário do nome da tabela, que pode se repetir)
    return f"plat_{tenant_slug}_{item_id.replace('-', '')}"[:120]


@tarefa(
    nome="agol.publicar",
    descricao="publica uma camada vetorial hospedada do inquilino como hosted feature layer na conta "
    "ArcGIS Online do cliente (generateToken -> addItem -> publish; overwrite nas rodadas seguintes)",
    parametros=PublicarParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=900,
    tentativas=1,
    perfil_minimo="editor",
    chave=lambda p: p.get("item_id"),  # duas publicações do MESMO item não correm em paralelo (item L0-19)
)
def agol_publicar(ctx, item_id: uuid.UUID, titulo: str | None = None) -> dict:
    item_id_s = str(item_id)
    with ctx.db() as cur:
        cur.execute(
            "SELECT id, titulo, dados FROM plat.item WHERE id = %s::uuid AND tipo = 'camada_vetorial'",
            (item_id_s,),
        )
        item = cur.fetchone()
        cur.execute("SELECT slug, config FROM plat.tenant WHERE id = %s", (ctx.tenant_id,))
        tenant = cur.fetchone()
    if item is None:
        raise FalhaDefinitiva(f"item {item_id_s} inexistente (ou não é camada_vetorial) neste inquilino")
    dados = item["dados"] or {}
    if dados.get("fonte") != "hospedada":
        raise FalhaDefinitiva("só camada vetorial HOSPEDADA pode ser publicada no ArcGIS Online (esta é "
                              "referenciada: não existe tabela própria a exportar)")
    schema, tabela = dados.get("schema"), dados.get("tabela")
    if not schema or not tabela:
        raise FalhaDefinitiva("item de camada vetorial sem schema/tabela em dados")

    cfg = agol_efetivo(tenant["config"] if tenant else None)
    if cfg is None:
        raise FalhaDefinitiva("credencial ArcGIS Online não configurada para este inquilino "
                              "(PUT /api/agol/credencial)")
    credencial = None
    try:
        from app.agol.config import decifrar_credencial

        credencial = decifrar_credencial(cfg, settings.PLAT_SECRET, settings.PLAT_SECRET_ANTERIOR)
    except Exception as e:  # noqa: BLE001 — PLAT_SECRET rotacionado sem o ANTERIOR, ou dado corrompido
        raise FalhaDefinitiva(f"não foi possível decifrar a credencial ArcGIS Online: {e}") from e

    titulo_final = (titulo or item["titulo"] or "camada")[:limites.AGOL_TITULO_MAX]
    nome_servico = _nome_servico(tenant["slug"], item_id_s)

    with ctx.db() as cur:
        publicacao.registrar(cur, ctx.tenant_id, item_id_s, job_id=str(ctx.job_id), estado="publicando",
                             portal=cfg.portal, mensagem=None)
    with ctx.db() as cur:
        anterior = publicacao.obter(cur, ctx.tenant_id, item_id_s)

    ctx.progresso(10, "exportando a camada para GeoJSON")
    caminho_geojson = ctx.dir_trabalho / "camada.geojson"
    with ctx.db() as cur:
        n_feicoes = geojson.exportar_para_arquivo(cur, schema, tabela, caminho_geojson)
    ctx.log("INFO", f"{n_feicoes} feições exportadas de {schema}.{tabela} para {caminho_geojson}")

    ctx.progresso(25, "autenticando na organização ArcGIS Online")
    try:
        if cfg.tipo == "senha":
            token = cliente.gerar_token(cfg.portal, cfg.usuario or "", credencial)
        else:
            token = credencial  # token de longa duração informado pelo administrador do inquilino
        info = cliente.info_portal(cfg.portal, token)
        usuario_agol = info.get("usuario") or cfg.usuario
        if not usuario_agol:
            raise cliente.ErroAGOL("não foi possível determinar o usuário autenticado no ArcGIS Online")

        resultado = cliente.publicar_camada(
            cfg.portal, token, usuario_agol, nome_servico=nome_servico, titulo=titulo_final,
            caminho_geojson=caminho_geojson, n_feicoes=n_feicoes,
            geojson_item_id_existente=(anterior or {}).get("agol_geojson_item_id"),
            dormir=ctx.dormir, progresso=lambda pct, msg: ctx.progresso(pct, msg),
        )
    except cliente.ErroAGOL as e:
        with ctx.db() as cur:
            publicacao.registrar(cur, ctx.tenant_id, item_id_s, job_id=str(ctx.job_id), estado="erro",
                                 mensagem=str(e)[:2000])
        raise FalhaDefinitiva(f"publicação no ArcGIS Online falhou: {e}") from e
    finally:
        credencial = token = None  # noqa: F841 — nunca sobrevive além deste bloco (log/exceção nunca as usam)

    with ctx.db() as cur:
        estado_final = publicacao.registrar(
            cur, ctx.tenant_id, item_id_s, job_id=str(ctx.job_id), estado="publicado", portal=cfg.portal,
            agol_geojson_item_id=resultado.geojson_item_id, agol_servico_item_id=resultado.servico_item_id,
            servico_url=resultado.servico_url, n_feicoes=resultado.n_feicoes, mensagem=None,
        )
    ctx.progresso(100, "concluído")
    return {
        "item_id": item_id_s, "estado": "publicado", "servico_url": resultado.servico_url,
        "n_feicoes": resultado.n_feicoes, "atualizado_em": estado_final["atualizado_em"],
    }


__all__ = ["agol_publicar", "PublicarParametros"]

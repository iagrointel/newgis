"""Dois jobs do item L1-01-j (proveniência verificável): a metade "reconferir a promessa" do Lastro
aplicado à imagem, para os itens que JÁ existiam quando este item nasceu (ingeridos por uma versão de
`imagens.ingestar` que ainda não gravava `plat:cadeia`/`plat:manifesto_sha256`).

`imagens.preencher_proveniencia` (leve, sem GDAL): só grava metadado — `processing:software` a partir do
`plat:versoes` que a ingestão original JÁ media, `processing:lineage` retroativo e `plat:manifesto_sha256`.
`plat:cadeia` fica `None` de propósito: o comando exato usado na ingestão original não foi capturado e os
percentis 2-98 que parametrizam o perfil visual não sobreviveram em nenhum campo do item antigo — inventar
um argv plausível seria uma medição fabricada (regra da casa: ausência de dado nunca vira medição).

`imagens.reexecutar` (pesado, roda GDAL de verdade): baixa o BRUTO já armazenado, reconverte os dois perfis
com o `app/imagens/cog.py` ATUAL e compara o sha256 obtido com o registrado — é a prova de determinismo do
portão ("`reexecutar` sobre a ortofoto aberta produz COG com o mesmo sha256... ou, quando o GDAL não é
determinístico, com estatísticas iguais e diferença documentada"). Quando roda, GRAVA a cadeia de verdade
(medida agora, não reconstruída) — supera o preenchimento leve para o mesmo item. NUNCA sobrescreve os
assets/checksums originais: a comparação fica ao lado deles, em `plat:reexecucao`, para que uma
reexecução que não bateu não apague a proveniência que já existia.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel

from app import objetos
from app.imagens import cog
from app.imagens import pgstac as ps
from app.imagens import proveniencia as prov
from app.imagens.cog import ErroConversao
from app.imagens.validacao import RecusaValidacao, validar
from app.jobs.registro import FalhaDefinitiva, tarefa


class ItemParametros(BaseModel):
    item_id: uuid.UUID


def _carregar(cur, tenant_id: int, item_id: uuid.UUID) -> tuple[str, str, dict]:
    """(colecao_id, stac_id, item_stac) do item raster do inquilino — 404 (via FalhaDefinitiva, que é o
    contrato de erro do worker; a rota HTTP tem o seu próprio 404 em `rotas_imagens.py`) para item
    inexistente, de outro tipo, ou de outro inquilino (RLS de `plat.item` já filtra; o filtro por coleção
    é defesa em profundidade, igual ao resto de `app/imagens`)."""
    cur.execute("SELECT dados FROM plat.item WHERE id = %s::uuid AND tipo = 'raster'", (str(item_id),))
    r = cur.fetchone()
    if r is None:
        raise FalhaDefinitiva(f"item raster {item_id} inexistente")
    dados = r["dados"] or {}
    colecao_id = dados.get("colecao") or ""
    stac_id = dados.get("stac_id") or str(item_id)
    if not ps.colecao_pertence(colecao_id, tenant_id):
        raise FalhaDefinitiva(f"item raster {item_id} sem coleção válida no inquilino")
    stac = ps.item_obter(cur, tenant_id, colecao_id, stac_id)
    if stac is None:
        raise FalhaDefinitiva(f"item STAC {stac_id} inexistente na coleção {colecao_id}")
    return colecao_id, stac_id, stac


# ---------------------------------------------------------------- preenchimento leve (sem reconversão)
@tarefa(
    nome="imagens.preencher_proveniencia",
    descricao="preenche retroativamente processing:software/lineage e plat:manifesto_sha256 de um item "
    "raster ingerido antes do item L1-01-j, SEM reconverter (plat:cadeia fica None: o comando exato da "
    "ingestão original não foi capturado)",
    parametros=ItemParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=60,
    tentativas=2,
    perfil_minimo="editor",
)
def imagens_preencher_proveniencia(ctx, item_id: uuid.UUID) -> dict:
    with ctx.db() as cur:
        colecao_id, stac_id, stac = _carregar(cur, ctx.tenant_id, item_id)
        props_antes = stac.get("properties") or {}
        if props_antes.get("plat:manifesto_sha256") and "plat:cadeia_origem" in props_antes:
            return {"item_id": str(item_id), "ja_preenchido": True, "origem": props_antes.get("plat:cadeia_origem")}
        novo_stac = prov.preencher_leve(cur, ctx.tenant_id, colecao_id, stac_id, stac)
    ctx.entrada(item_id, novo_stac["properties"]["plat:manifesto_sha256"], "proveniência preenchida (sem reconversão)")
    return {
        "item_id": str(item_id), "ja_preenchido": False, "origem": "retroativa_sem_reconversao",
        "manifesto_sha256": novo_stac["properties"]["plat:manifesto_sha256"],
    }


# ---------------------------------------------------------------- reexecução (com reconversão real)
def _comparar_estatisticas(stats_novas: list[dict], bandas_registradas: list[dict]) -> list[dict]:
    """Compara min/max/mean/std medidos AGORA (científico) com `raster:bands.statistics` já registrado no
    item — só chamado quando o sha256 diverge, para dizer SE a diferença é de bytes (empacotamento/overview)
    ou também de conteúdo medido."""
    saida = []
    for i, novas in enumerate(stats_novas):
        antigas = (bandas_registradas[i] if i < len(bandas_registradas) else {}).get("statistics") or {}
        saida.append({
            "banda": novas.get("banda", i + 1),
            "min_novo": novas.get("min"), "min_registrado": antigas.get("minimum"),
            "max_novo": novas.get("max"), "max_registrado": antigas.get("maximum"),
            "mean_novo": novas.get("mean"), "mean_registrado": antigas.get("mean"),
            "std_novo": novas.get("std"), "std_registrado": antigas.get("stddev"),
            "iguais": (
                novas.get("min") == antigas.get("minimum") and novas.get("max") == antigas.get("maximum")
                and novas.get("mean") == antigas.get("mean") and novas.get("std") == antigas.get("stddev")
            ),
        })
    return saida


@tarefa(
    nome="imagens.reexecutar",
    descricao="baixa o bruto de um item raster já ingerido, reconverte os dois perfis COG com o cog.py "
    "ATUAL e compara o sha256 obtido com o registrado — prova de determinismo (ou, se o GDAL não for "
    "determinístico, compara estatísticas) e grava a cadeia de proveniência MEDIDA agora",
    parametros=ItemParametros,
    pesado=True,
    memoria_mb=1024,
    timeout_s=3600,
    tentativas=1,
    perfil_minimo="editor",
    ferramentas=("gdalinfo", "gdal_translate"),
)
def imagens_reexecutar(ctx, item_id: uuid.UUID) -> dict:
    with ctx.db() as cur:
        colecao_id, stac_id, stac = _carregar(cur, ctx.tenant_id, item_id)
    props = stac.get("properties") or {}
    assets = stac.get("assets") or {}
    bruto_asset = assets.get("bruto") or {}
    bruto_href = bruto_asset.get("href") or ""
    if not bruto_href.startswith("/api/objetos/"):
        raise FalhaDefinitiva(f"item {item_id}: asset 'bruto' sem href endereçável")
    chave_bruto = bruto_href[len("/api/objetos/"):]
    try:
        bruto_sha_registrado = prov.sha256_de_multihash(bruto_asset.get("file:checksum") or "")
    except ValueError as e:
        raise FalhaDefinitiva(f"item {item_id}: checksum do bruto ausente/inválido: {e}") from e

    ctx.progresso(5, "baixando o bruto do armazenamento")
    bruto = ctx.dir_trabalho / "bruto.tif"
    try:
        objetos.baixar(chave_bruto, bruto)
    except (FileNotFoundError, objetos.ChaveInvalida) as e:
        raise FalhaDefinitiva(f"o objeto bruto não existe mais no armazenamento: {e}") from e
    ctx.entrada(item_id, bruto_sha_registrado, "bruto relido para reexecução")

    ctx.progresso(15, "validando o raster (gdalinfo isolado)")
    try:
        rel = validar(ctx, str(bruto))
    except RecusaValidacao as e:
        raise FalhaDefinitiva(f"raster recusado na reexecução ({e.codigo}): {e}") from e

    ctx.progresso(25, "medindo estatísticas do bruto")
    stats = cog.estatisticas_bruto(bruto, rel)

    try:
        ctx.progresso(35, "reconvertendo o perfil científico (ZSTD)")
        cientifico = cog.converter_cientifico(ctx, bruto, rel, ctx.dir_trabalho / "cientifico.tif")
        ctx.progresso(65, "reconvertendo o perfil visual (JPEG/WEBP)")
        visual = cog.converter_visual(ctx, bruto, rel, stats, ctx.dir_trabalho / "visual.tif")
    except ErroConversao as e:
        raise FalhaDefinitiva(f"a reconversão para COG falhou: {e}") from e

    def _registrado(nome: str) -> str | None:
        chk = (assets.get(nome) or {}).get("file:checksum")
        if not chk:
            return None
        try:
            return prov.sha256_de_multihash(chk)
        except ValueError:
            return None

    sha_cientifico_registrado = _registrado("cientifico")
    sha_visual_registrado = _registrado("visual")
    det_cientifico = sha_cientifico_registrado is not None and cientifico.sha256 == sha_cientifico_registrado
    det_visual = sha_visual_registrado is not None and visual.sha256 == sha_visual_registrado
    determinismo = det_cientifico and det_visual

    quando = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    reexecucao: dict = {
        "quando": quando,
        "determinismo": determinismo,
        "versoes_na_reexecucao": cog.versoes_software(),
        "cientifico": {
            "sha256_registrado": sha_cientifico_registrado, "sha256_obtido": cientifico.sha256,
            "igual": det_cientifico,
        },
        "visual": {
            "sha256_registrado": sha_visual_registrado, "sha256_obtido": visual.sha256, "igual": det_visual,
        },
    }
    if not determinismo:
        # portão: "com estatísticas iguais e diferença documentada" — só mede isto quando o sha256 divergiu
        bandas_registradas = (assets.get("cientifico") or {}).get("raster:bands") or []
        reexecucao["estatisticas"] = _comparar_estatisticas(stats, bandas_registradas)

    versoes_originais = props.get("plat:versoes") or {}
    cadeia_medida_agora = prov.montar_cadeia_ingestao(
        bruto_sha256=bruto_sha_registrado, cientifico=cientifico, visual=visual,
    )
    novas_props = prov.preencher_propriedades_proveniencia(
        props, versoes=versoes_originais, cadeia=cadeia_medida_agora,
        origem="reexecucao_retroativa", reexecucao=reexecucao,
    )
    novo_stac = prov.selar_manifesto({**stac, "properties": novas_props})
    ctx.progresso(95, "gravando a proveniência medida")
    with ctx.db() as cur:
        ps.item_atualizar(cur, ctx.tenant_id, colecao_id, stac_id, novo_stac)
    ctx.progresso(100, "concluído")
    return {
        "item_id": str(item_id),
        "determinismo": determinismo,
        "sha256_cientifico_obtido": cientifico.sha256,
        "sha256_cientifico_registrado": sha_cientifico_registrado,
        "sha256_visual_obtido": visual.sha256,
        "sha256_visual_registrado": sha_visual_registrado,
        "manifesto_sha256": novo_stac["properties"]["plat:manifesto_sha256"],
    }


__all__ = ["imagens_preencher_proveniencia", "imagens_reexecutar", "ItemParametros"]

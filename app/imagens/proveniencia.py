"""Proveniência verificável do item raster (item L1-01-j): o "Lastro" da casa aplicado à imagem — em vez de
descrever a cadeia de conversão em prosa, ela fica gravada no PRÓPRIO item STAC como dado que qualquer um
pode CONFERIR (baixar o objeto de novo, recalcular o sha256, comparar com o registrado), nunca como
promessa. Três peças:

1. `montar_cadeia_ingestao`/`preencher_propriedades_proveniencia`/`selar_manifesto` — o que `imagens.ingestar`
   (app/imagens/ingestao.py) chama para GRAVAR a proveniência no item novo, com o comando exato e os sha256
   de entrada/saída medidos NA HORA da conversão.
2. `conferir_item` — o que a rota `POST /api/imagens/{item_id}/conferir` e o job `imagens.conferir_lote`
   chamam para CONFERIR: baixa cada asset do balde outra vez, recalcula o sha256 em stream
   (`objetos.sha256_remoto`) e compara com `file:checksum`; recalcula também `plat:manifesto_sha256`.
3. Canonicalização do manifesto — regra FIXA, documentada aqui porque o hash só é reproduzível se todo
   mundo que o calcula usar a MESMA serialização: `json.dumps(obj, sort_keys=True, separators=(",", ":"),
   ensure_ascii=False)`, codificado UTF-8. `sort_keys=True` ordena as chaves em TODO nível do dicionário
   (o `json` da stdlib ordena recursivamente, não só o topo); `separators` compactos tiram o espaço que o
   padrão do Python insere depois de `:` e de `,`; `ensure_ascii=False` mantém acento como está em vez de
   escapar para `\\uXXXX` (a mesma escolha de `app.catalogo.comum.jsonb`) — qualquer uma das três escolhas
   trocada muda os bytes e, com eles, o hash. `plat:manifesto_sha256` é o sha256 do item STAC inteiro SEM
   essa própria chave (ela não pode depender de si mesma): mudar 1 byte de QUALQUER outro campo do item —
   bbox, propriedade, checksum de asset — quebra o hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.erros import ErroAPI
from app.garage import ErroGarage
from app.imagens import pgstac as ps
from app.objetos import ChaveInvalida

EXTENSAO_PROCESSING = "https://stac-extensions.github.io/processing/v1.2.0/schema.json"
MULTIHASH_SHA256_PREFIXO = "1220"  # 0x12 sha2-256, 0x20 = 32 bytes (prefixo já usado em ingestao._asset_objeto)

LINEAGE_INGESTAO = (
    "Ingestão automática (job imagens.ingestar): arquivo bruto enviado pelo usuário; validado por gdalinfo "
    "isolado; estatísticas medidas por amostragem do bruto; convertido para dois perfis de Cloud-Optimized "
    "GeoTIFF (científico: ZSTD, dtype e nodata originais; visual: JPEG ou WEBP 8 bits, escalado pelo "
    "percentil 2-98 do bruto); os dois produtos validados pelo rio-cogeo antes de subir ao armazenamento de "
    "objetos. Comando exato e sha256 de entrada/saída de cada passo em plat:cadeia."
)

LINEAGE_RETROATIVA = (
    "Item ingerido antes do item L1-01-j (proveniência verificável): plat:cadeia abaixo foi RECONSTRUÍDA "
    "reexecutando a mesma conversão (job imagens.reexecutar) sobre o bruto já armazenado — não foi capturada "
    "ao vivo na ingestão original. O sha256 de cada asset (file:checksum) continua sendo o original, nunca "
    "sobrescrito por esta reconstrução; ver plat:reexecucao para o resultado medido da comparação. "
    "processing:software continua sendo a versão medida NA INGESTÃO original (o que realmente produziu os "
    "bytes hoje armazenados), mesmo que esta reexecução tenha rodado com outra versão de GDAL/rio-cogeo — "
    "conferir plat:reexecucao.versoes_mudaram_desde_a_ingestao antes de tratar processing:software e "
    "plat:cadeia como descrevendo o MESMO software (achado do adversário independente, 10/09)."
)

LINEAGE_RETROATIVA_SEM_RECONVERSAO = (
    "Item ingerido antes do item L1-01-j (proveniência verificável): esta ficha foi PREENCHIDA "
    "retroativamente sem reexecutar a conversão (job imagens.preencher_proveniencia) — plat:cadeia fica "
    "AUSENTE de propósito porque o comando exato usado na ingestão original não foi capturado e não há como "
    "reconstruí-lo sem reabrir o bruto (os percentis 2-98 que parametrizam o perfil visual não ficaram "
    "gravados em nenhum campo do item antigo). `processing:software` vem de plat:versoes, que JÁ era medido "
    "na ingestão original. Rode `imagens.reexecutar` sobre este item para medir a cadeia de verdade."
)


# ---------------------------------------------------------------- multihash
def multihash_sha256(sha256_hex: str) -> str:
    return f"{MULTIHASH_SHA256_PREFIXO}{sha256_hex}"


def sha256_de_multihash(multihash: str) -> str:
    """Sha256 hex a partir de um multihash `1220<64 hex>` — só sha2-256/32 bytes é aceito nesta casa (mesmo
    prefixo de `_asset_objeto`); `ValueError` se o formato não bate."""
    if not isinstance(multihash, str) or not multihash.startswith(MULTIHASH_SHA256_PREFIXO) or len(multihash) != 68:
        raise ValueError(f"multihash não é sha2-256/32 bytes: {multihash!r}")
    return multihash[len(MULTIHASH_SHA256_PREFIXO):]


# ---------------------------------------------------------------- canonicalização + manifesto
def canonicalizar(manifesto: dict) -> bytes:
    """JSON canônico (ver docstring do módulo): chaves ordenadas em todo nível, sem espaço supérfluo, UTF-8
    sem escapar acento. É a ÚNICA função que decide a serialização — gerar e conferir sempre passam por
    aqui, nunca por um `json.dumps` avulso, ou o hash deixa de ser reproduzível entre os dois."""
    return json.dumps(manifesto, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifesto_sha256(item_stac: dict) -> str:
    """Sha256 do item STAC inteiro MENOS `properties.plat:manifesto_sha256` (o campo não pode depender de
    si mesmo). Cópia profunda antes de mexer — nunca muta o dict do chamador."""
    copia: dict[str, Any] = json.loads(json.dumps(item_stac, default=str))
    (copia.get("properties") or {}).pop("plat:manifesto_sha256", None)
    return hashlib.sha256(canonicalizar(copia)).hexdigest()


def selar_manifesto(stac: dict) -> dict:
    """Última coisa que acontece antes do item ir para o catálogo: calcula `plat:manifesto_sha256` sobre o
    item SEM essa chave e grava. Devolve uma CÓPIA (nunca muta `stac`) — qualquer edição posterior nos
    campos, inclusive por engano, deixa de bater com o hash gravado, que é o objetivo."""
    copia: dict[str, Any] = json.loads(json.dumps(stac, default=str))
    h = manifesto_sha256(copia)
    copia.setdefault("properties", {})["plat:manifesto_sha256"] = h
    return copia


# ---------------------------------------------------------------- montagem na ingestão
def montar_cadeia_ingestao(*, bruto_sha256: str, cientifico, visual) -> list[dict]:
    """`plat:cadeia`: um passo por perfil convertido, na ordem em que rodou (científico antes de visual —
    mesma ordem de `imagens_ingestar`). `comando` é o argv EXATO (lista de listas — cada elemento é um
    processo `gdal_translate` invocado; o perfil visual leva DOIS: a montagem do VRT escalado por percentil,
    depois o COG) — nunca uma string montada, que introduziria ambiguidade de aspas/espaço."""
    return [
        {
            "passo": "cientifico", "perfil": "cientifico",
            "comando": cientifico.comando, "entrada_sha256": bruto_sha256, "saida_sha256": cientifico.sha256,
        },
        {
            "passo": "visual", "perfil": "visual",
            "comando": visual.comando, "entrada_sha256": bruto_sha256, "saida_sha256": visual.sha256,
        },
    ]


def preencher_propriedades_proveniencia(
    properties: dict, *, versoes: dict, cadeia: list[dict] | None, origem: str, reexecucao: dict | None = None,
) -> dict:
    """Devolve uma CÓPIA de `properties` com os campos de proveniência preenchidos — `processing:software`
    (mapa nome -> versão, extensão `processing`), `processing:lineage` (texto, varia por `origem`),
    `plat:cadeia` e `plat:cadeia_origem` ∈ {'ingestao', 'reexecucao_retroativa',
    'retroativa_sem_reconversao'}. `reexecucao`, quando houver, é o resultado medido de rodar
    `imagens.reexecutar` (determinismo, sha256 obtidos x registrados).

    `cadeia=None` (só na origem `retroativa_sem_reconversao` — ausência de dado NUNCA vira comando
    fabricado) OMITE a chave `plat:cadeia` em vez de gravar `null`: MEDIDO (10/09) que o
    `pgstac.create_item`/`update_item` DESCARTA chave de `properties` com valor `null` na gravação — uma
    ficha selada com `"plat:cadeia": null` teria `plat:manifesto_sha256` calculado sobre um dict que o
    banco nunca devolve de volta, e `conferir_item` acusaria divergência de manifesto em TODO item sem
    cadeia, sempre, mesmo sem qualquer byte alterado (achado do próprio teste de integração deste item,
    não do adversário). `properties.get('plat:cadeia')` no lado de leitura continua devolvendo `None` do
    mesmo jeito — a ausência da chave e um valor `null` são indistinguíveis para quem só LÊ."""
    if origem not in ("ingestao", "reexecucao_retroativa", "retroativa_sem_reconversao"):
        raise ValueError(f"origem de proveniência desconhecida: {origem!r}")
    lineage = {
        "ingestao": LINEAGE_INGESTAO,
        "reexecucao_retroativa": LINEAGE_RETROATIVA,
        "retroativa_sem_reconversao": LINEAGE_RETROATIVA_SEM_RECONVERSAO,
    }[origem]
    novas = dict(properties)
    novas["processing:software"] = dict(versoes or {})
    novas["processing:lineage"] = lineage
    if cadeia is None:
        novas.pop("plat:cadeia", None)
    else:
        novas["plat:cadeia"] = cadeia
    novas["plat:cadeia_origem"] = origem
    if reexecucao is not None:
        novas["plat:reexecucao"] = reexecucao
    return novas


# ---------------------------------------------------------------- conferência
_ERROS_LEITURA = (FileNotFoundError, ChaveInvalida, ErroGarage)


def conferir_item(cur, tenant_id: int, colecao_id: str, item_id: str) -> dict:
    """Confere TODO asset com `file:checksum` do item: baixa em stream do balde (`objetos.sha256_remoto`,
    nunca o objeto inteiro em RAM), recalcula o sha256 e compara com o multihash registrado; recalcula
    também `plat:manifesto_sha256` quando o item já tem um. NUNCA lança por divergência (achado, não erro
    de execução) — "não consegui baixar o objeto" e "baixei e o sha256 diverge" são entradas DIFERENTES no
    resultado, porque confundir as duas seria mentir sobre o que foi conferido."""
    from app import objetos  # import tardio: objetos.py não depende de imagens; evita ciclo de import no boot

    stac = ps.item_obter(cur, tenant_id, colecao_id, item_id)
    if stac is None:
        raise ErroAPI(404, "item_inexistente", "item STAC inexistente")

    ativos: list[dict] = []
    tudo_ok = True
    for nome, asset in sorted((stac.get("assets") or {}).items()):
        checksum = asset.get("file:checksum")
        href = asset.get("href") or ""
        if not checksum:
            continue  # asset sem checksum registrado: nada a conferir (não é divergência, é ausência)
        if not href.startswith("/api/objetos/"):
            ativos.append({"asset": nome, "ok": False, "erro": f"href não endereçável: {href!r}"})
            tudo_ok = False
            continue
        chave = href[len("/api/objetos/"):]
        try:
            esperado = sha256_de_multihash(checksum)
        except ValueError as e:
            ativos.append({"asset": nome, "ok": False, "erro": str(e)})
            tudo_ok = False
            continue
        try:
            obtido = objetos.sha256_remoto(chave)
        except _ERROS_LEITURA as e:
            ativos.append({"asset": nome, "ok": False, "erro": f"não foi possível reler o objeto: {e}"})
            tudo_ok = False
            continue
        ok = obtido == esperado
        ativos.append({"asset": nome, "ok": ok, "sha256_registrado": esperado, "sha256_recalculado": obtido})
        tudo_ok = tudo_ok and ok

    manifesto_registrado = (stac.get("properties") or {}).get("plat:manifesto_sha256")
    manifesto_recalculado = manifesto_sha256(stac) if manifesto_registrado else None
    manifesto_ok = manifesto_registrado is None or manifesto_registrado == manifesto_recalculado
    tudo_ok = tudo_ok and manifesto_ok

    return {
        "item_id": item_id,
        "colecao": colecao_id,
        "ok": tudo_ok,
        "ativos": ativos,
        "manifesto_registrado": manifesto_registrado,
        "manifesto_recalculado": manifesto_recalculado,
        "manifesto_ok": manifesto_ok,
    }


# ---------------------------------------------------------------- preenchimento leve (sem GDAL)
def preencher_leve(cur, tenant_id: int, colecao_id: str, item_id: str, stac: dict) -> dict | None:
    """A metade sem-reconversão do backfill (item L1-01-j, cláusula 3): só grava metadado —
    `processing:software` a partir do `plat:versoes` que a ingestão original JÁ media, `processing:lineage`
    retroativo e `plat:manifesto_sha256`; `plat:cadeia` fica `None` de propósito (ver LINEAGE_RETROATIVA_
    SEM_RECONVERSAO). Idempotente: devolve `None` sem escrever nada se o item já tem `plat:manifesto_sha256`
    E `plat:cadeia_origem` — chamado tanto pelo job `imagens.preencher_proveniencia` quanto pela rota de
    administração que varre todos os itens pendentes de uma vez."""
    props = stac.get("properties") or {}
    if props.get("plat:manifesto_sha256") and "plat:cadeia_origem" in props:
        return None
    versoes_originais = props.get("plat:versoes") or {}
    novas_props = preencher_propriedades_proveniencia(
        props, versoes=versoes_originais, cadeia=None, origem="retroativa_sem_reconversao",
    )
    novo_stac = selar_manifesto({**stac, "properties": novas_props})
    ps.item_atualizar(cur, tenant_id, colecao_id, item_id, novo_stac)
    return novo_stac


SLUG_COLECAO_IMAGENS = "imagens"  # tem de bater com app.imagens.ingestao.SLUG_COLECAO (não importado
# aqui de propósito: ingestao.py já importa proveniencia.py — importar de volta criaria um ciclo)


def itens_pendentes(cur, tenant_id: int, limite: int) -> list[tuple[str, str]]:
    """(colecao, item_id) de itens da coleção `<tenant_id>-imagens` cujo item STAC ainda NÃO tem
    `plat:cadeia_origem` em `properties` — direto no jsonb de `pgstac.items` (`?` é o operador "tem a
    chave"), sem trazer para o Python nenhum item que a rota de administração só iria descartar.

    Escopo é SÓ a coleção `imagens` (onde `imagens.ingestar` cria item — a única coleção que este item
    precisa preencher retroativamente), nunca "toda coleção do inquilino": a tabela `pgstac.items` é
    particionada POR coleção, e este ambiente compartilhado acumula centenas de coleções efêmeras de
    outras suítes de teste (`isola-*`, `rlsdireto-*`, `medida10k`, ...) — 16.713 itens pendentes em 236
    coleções no momento em que isto foi medido (10/09), a maioria delas nunca vai ver `imagens.ingestar`.
    Sem o escopo, uma varredura teria de decidir entre paginar por essas 236 partições (lento, ~165 s
    para bem menos que isso) ou arriscar nunca alcançar o item que o chamador queria (limite estourado
    antes de chegar lá) — os dois errados. Varredura completa fora da coleção `imagens`, se algum dia
    precisar, é OUTRO endpoint, com esse recorte explícito no nome."""
    colecao_id = ps.nome_colecao(tenant_id, SLUG_COLECAO_IMAGENS)
    if ps.colecao_obter(cur, tenant_id, colecao_id) is None:
        return []
    cur.execute(
        "SELECT collection, id FROM pgstac.items WHERE collection = %s "
        "AND NOT (content -> 'properties' ? 'plat:cadeia_origem') ORDER BY datetime LIMIT %s",
        (colecao_id, limite),
    )
    return [(r["collection"], r["id"]) for r in cur.fetchall()]


__all__ = [
    "canonicalizar",
    "conferir_item",
    "itens_pendentes",
    "manifesto_sha256",
    "montar_cadeia_ingestao",
    "multihash_sha256",
    "preencher_leve",
    "preencher_propriedades_proveniencia",
    "selar_manifesto",
    "sha256_de_multihash",
]

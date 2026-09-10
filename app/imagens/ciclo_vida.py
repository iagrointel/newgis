"""Ciclo de vida do item de imagem (item L1-01-i-ciclo-de-vida-exclusao-e-coleta-de-lixo).

Regras escritas (a hipótese do item, uma por função):

- EXCLUIR (lixeira lógica, rota DELETE do catálogo): o item de catálogo ganha `apagado_em` (e a RLS já o
  esconde das rotas: os tiles respondem 404 na hora); AQUI marcamos `plat.raster_item.estado='excluido'`,
  GUARDAMOS o corpo STAC na coluna `stac`, REMOVEMOS o item do pgstac (a busca STAC deixa de listá-lo) e
  ENFILEIRAMOS o apagamento dos objetos do balde para daqui a `limites.RASTER_LIXEIRA_DIAS` (7 dias).
- RESTAURAR dentro da retenção: o corpo STAC guardado volta ao pgstac, o estado volta a 'ativo' e os
  objetos nunca saíram do balde — o item volta inteiro. Fora da retenção os objetos já se foram e a
  restauração é recusada (`objetos_ja_apagados`), porque devolveria um item sem dado.
- EXPURGAR (esvaziar a lixeira ou o expurgo periódico do catálogo): o destruidor do tipo 'raster' apaga
  os objetos do balde (`objetos_raster.apagar_item`), apaga o que sobrou do STAC e a linha do espelho.
- COLETA DE LIXO (job semanal `imagens.raster_gc` e CLI `plat raster gc`): LISTA objetos sem item
  (órfãos) e itens sem objeto/sem STAC (quebrados) e devolve o relatório como resultado do job — visível
  em Tarefas. A coleta LISTA e RELATA; apagar órfão é decisão humana, não automática.

O apagamento de objetos em job separado é idempotente e defensivo: se o item voltou para 'ativo' antes
do job rodar (restauração dentro da retenção), o job NÃO apaga nada e registra o pulo.

CLI (o `scripts/plat` é o único ponto de entrada): `plat raster gc [--inquilino <slug>]` roda a coleta
agora, por inquilino, e registra o relatório como job concluído do tipo `imagens.raster_gc` — visível
em Tarefas sem depender de worker rodar depois.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys

from pydantic import BaseModel, Field

from app import db, limites, objetos, objetos_raster
from app.catalogo.comum import jsonb
from app.erros import ErroAPI
from app.imagens import pgstac as ps

log = logging.getLogger("plat.imagens.ciclo_vida")

LIMITE_RELATORIO_CHAVES = 200


class ApagarObjetosParametros(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)


class ColetaParametros(BaseModel):
    limite_chaves: int = Field(default=LIMITE_RELATORIO_CHAVES, ge=1, le=1000)


def _dados_de(item: dict) -> tuple[str, str]:
    dados = item.get("dados") or {}
    return (dados.get("colecao") or "", dados.get("stac_id") or "")


def _linha_espelho(cur, item_id: str) -> dict | None:
    cur.execute(
        "SELECT tenant_id, colecao, item_id, estado, excluido_em, stac FROM plat.raster_item "
        "WHERE item_id = %s",
        (item_id,),
    )
    return cur.fetchone()


# ---------------------------------------------------------------- exclusão (lixeira) e restauração
def ao_ir_para_lixeira(cur, tenant_id: int, item: dict, enfileirar) -> None:
    """Chamado pela rota de exclusão do catálogo DEPOIS de `plat.item_lixeira(id, true)`, na MESMA
    transação. `enfileirar` é `app.jobs.sistema.enfileirar` (passado por quem chama para não criar
    dependência circular de importação)."""
    colecao, stac_id = _dados_de(item)
    if not stac_id:
        return
    stac = ps.item_obter(cur, tenant_id, colecao, stac_id) if colecao else None
    if stac is not None:
        ps.item_apagar(cur, stac_id, colecao)
    cur.execute(
        "UPDATE plat.raster_item SET estado = 'excluido', excluido_em = now(), stac = %s WHERE item_id = %s",
        (jsonb(stac), stac_id),
    )
    enfileirar(
        tenant_id,
        "imagens.raster_apagar_objetos",
        {"item_id": stac_id},
        agendado_para=datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(days=limites.RASTER_LIXEIRA_DIAS),
    )


def checar_restauravel(cur, tenant_id: int, item: dict) -> None:
    """Recusa a restauração quando a retenção passou e os objetos já foram apagados (409). Dentro da
    retenção os objetos estão no balde e a conferência custa só o HEAD do COG visual."""
    _, stac_id = _dados_de(item)
    if not stac_id:
        return
    linha = _linha_espelho(cur, stac_id)
    if linha is None or linha["estado"] != "excluido":
        return
    stac = linha["stac"] or {}
    href = ((stac.get("assets") or {}).get("visual") or {}).get("href") or ""
    # o asset visual é chave de IMAGEM (`slug/<item>/<asset>_<sha8>.<ext>`): conferir com objetos_raster,
    # não com objetos.existe (o padrão genérico de chave não casa com o de imagem e diria False sempre)
    if href.startswith("/api/objetos/") and not objetos_raster.existe(href[len("/api/objetos/"):]):
        raise ErroAPI(
            409,
            "objetos_ja_apagados",
            "os objetos deste item já foram apagados (retenção vencida); o caminho de volta é a reingestão",
        )


def ao_restaurar(cur, tenant_id: int, item: dict) -> None:
    """Chamado pela rota de restauração DEPOIS de `plat.item_lixeira(id, false)`, na mesma transação:
    devolve o corpo STAC guardado ao pgstac e volta o espelho a 'ativo'."""
    colecao, stac_id = _dados_de(item)
    if not stac_id:
        return
    linha = _linha_espelho(cur, stac_id)
    if linha is None:
        return
    stac = linha["stac"]
    if stac is not None and ps.item_obter(cur, tenant_id, colecao, stac_id) is None:
        ps.item_criar(cur, tenant_id, colecao, stac)
    cur.execute(
        "UPDATE plat.raster_item SET estado = 'ativo', excluido_em = NULL, stac = NULL WHERE item_id = %s",
        (stac_id,),
    )


# ---------------------------------------------------------------- expurgo (destruidor do catálogo)
def _padrao_log(nivel: str, mensagem: str) -> None:  # noqa: ARG001 — o nível já entra no formato do logging
    log.info("%s", mensagem)


def expurgar(cur, dados: dict, log=None) -> int:
    """Destruidor do tipo 'raster' do catálogo: apaga os objetos do balde, o item STAC que por ventura
    tenha ficado e a linha do espelho. Devolve os bytes liberados, para o evento de expurgo. `log` é o
    callable (nivel, mensagem) do ContextoJob — o MESMO contrato que `destruidores.destruir` recebe do
    worker; sem worker (testes, CLI) pode ficar em None e o registro vai só para o log da aplicação."""
    _, stac_id = _dados_de({"dados": dados})
    if not stac_id:
        return 0
    liberados = int(objetos_raster.apagar_item(cur, stac_id)["bytes"])
    tenant_id, _ = objetos._tenant_atual(cur)
    linha = _linha_espelho(cur, stac_id)
    colecao = linha["colecao"] if linha is not None else ""
    if ps.item_obter(cur, tenant_id, colecao, stac_id) is not None:
        ps.item_apagar(cur, stac_id, colecao)
    cur.execute("DELETE FROM plat.raster_item WHERE item_id = %s", (stac_id,))
    (log or _padrao_log)("INFO", f"ciclo_vida: item {stac_id} expurgado ({liberados} bytes de objetos)")
    return liberados


# ---------------------------------------------------------------- job: apagar objetos após a retenção
def apagar_objetos(ctx, item_id: str) -> dict:
    """Corpo do job `imagens.raster_apagar_objetos`. Defensivo: só age se o espelho segue 'excluido'
    (não voltou por restauração) — restauração dentro da retenção deixa o balde intacto."""
    with ctx.db() as cur:
        linha = _linha_espelho(cur, item_id)
        if linha is None:
            ctx.progresso(100, "espelho inexistente (item expurgado antes): nada a apagar")
            return {"pulado": "espelho_inexistente", "objetos": 0, "bytes": 0}
        if linha["estado"] != "excluido":
            ctx.progresso(100, f"estado atual é {linha['estado']}: item restaurado, balde intacto")
            return {"pulado": linha["estado"], "objetos": 0, "bytes": 0}
        resultado = objetos_raster.apagar_item(cur, item_id)
    ctx.progresso(100, f"{resultado['objetos']} objeto(s), {resultado['bytes']} bytes")
    return {**resultado, "pulado": None}


# ---------------------------------------------------------------- coleta de lixo (órfãos e quebrados)
def coleta_de_lixo(ctx, limite_chaves: int = LIMITE_RELATORIO_CHAVES) -> dict:
    """Corpo do job `imagens.raster_gc` e da CLI `plat raster gc`, para o inquilino do contexto.
    Órfão = objeto no balde na forma de imagem (`<item_id>/<asset>_<sha8>.<ext>`) sem linha no espelho.
    Quebrado = espelho 'ativo' sem item STAC, ou cujo COG visual não está mais no balde.
    Lixeira vencida = 'excluido' há mais de RASTER_LIXEIRA_DIAS (o disco aperta; alguém decide)."""
    relatorio: dict = {"orfaos": {"objetos": 0, "bytes": 0, "chaves": []}, "quebrados": [], "lixeira_vencida": 0}
    with ctx.db() as cur:
        tenant_id, slug = objetos._tenant_atual(cur)
        relatorio["inquilino"] = slug
        bucket = objetos._linha_bucket(cur, tenant_id)
        if bucket is None:
            return relatorio
        cli = objetos._cliente(bucket)
        cur.execute(
            "SELECT item_id FROM plat.raster_item WHERE estado = 'excluido' "
            "AND excluido_em < now() - make_interval(days => %s)",
            (limites.RASTER_LIXEIRA_DIAS,),
        )
        relatorio["lixeira_vencida"] = len(cur.fetchall())
    objetos_no_balde = cli.listar(bucket["bucket_alias"], prefixo="")

    with ctx.db() as cur:
        cur.execute("SELECT item_id FROM plat.raster_item")
        itens_no_espelho = {r["item_id"] for r in cur.fetchall()}
    # órfãos: chave na forma de imagem cujo item não existe mais no espelho (outros formatos de chave
    # no mesmo balde — uploads genéricos — não casam com `partes` e são pulados). `listar` devolve o
    # caminho DENTRO do balde; `partes` espera a chave completa com o slug na frente — compor antes.
    for o in objetos_no_balde:
        try:
            completa = objetos_raster.chave(relatorio["inquilino"], o["chave"])
            partes = objetos_raster.partes(completa)
        except objetos_raster.ChaveInvalida:
            continue
        if partes["item_id"] in itens_no_espelho:
            continue
        relatorio["orfaos"]["objetos"] += 1
        relatorio["orfaos"]["bytes"] += int(o["bytes"])
        if len(relatorio["orfaos"]["chaves"]) < int(limite_chaves):
            relatorio["orfaos"]["chaves"].append(completa)

    # quebrados: item ativo sem STAC ou sem o COG visual no balde
    with ctx.db() as cur:
        cur.execute(
            "SELECT item_id, colecao FROM plat.raster_item WHERE estado = 'ativo' ORDER BY item_id"
        )
        ativos = cur.fetchall()
        for linha in ativos:
            stac = ps.item_obter(cur, tenant_id, linha["colecao"], linha["item_id"])
            if stac is None:
                relatorio["quebrados"].append(
                    {"item_id": linha["item_id"], "colecao": linha["colecao"], "motivo": "sem_stac"}
                )
                continue
            href = ((stac.get("assets") or {}).get("visual") or {}).get("href") or ""
            if href.startswith("/api/objetos/") and not objetos_raster.existe(href[len("/api/objetos/"):]):
                relatorio["quebrados"].append(
                    {"item_id": linha["item_id"], "colecao": linha["colecao"], "motivo": "sem_objeto_visual"}
                )
    return relatorio


# ---------------------------------------------------------------- CLI (scripts/plat raster gc)
class _CtxCLI:
    """Mínimo da interface de `ContextoJob` que `coleta_de_lixo` usa, fora do worker: um cursor por bloco,
    dentro do inquilino, e progresso que não escreve nada."""

    def __init__(self, tenant_id: int):
        self._ctx = db.Contexto(tenant_id, 0, "sistema")

    def db(self):
        return db.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:  # noqa: ARG002 — CLI não publica progresso
        log.info("progresso %s%%: %s", pct, mensagem)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plat raster", description="coleta de lixo das imagens")
    sub = parser.add_subparsers(dest="comando", required=True)
    gc = sub.add_parser("gc", help="lista órfãos e quebrados e registra o relatório em Tarefas")
    gc.add_argument("--inquilino", help="slug de UM inquilino; sem isto, todos")
    argumentos = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app.jobs import sistema

    saida = []
    with db.db() as cur:
        # `plat.tenant` tem RLS `id = tenant_atual()`: fora de uma sessão de inquilino ela não devolve
        # linha nenhuma — a enumeração da manutenção passa pela leitura SECURITY DEFINER (migração 1932)
        cur.execute("SELECT id, slug FROM plat.tenants_para_manutencao()")
        alvos = [(r["id"], r["slug"]) for r in cur.fetchall()]
    if argumentos.inquilino:
        alvos = [(i, s) for i, s in alvos if s == argumentos.inquilino]
    for tenant_id, slug in alvos:
        try:
            relatorio = coleta_de_lixo(_CtxCLI(tenant_id))
        except Exception as e:  # noqa: BLE001 — um inquilino com problema não para os outros
            log.error("coleta de lixo falhou para %s: %s", slug, e)
            continue
        job_id = sistema.registrar_concluido(
            tenant_id, "imagens.raster_gc", {"origem": "cli", "inquilino": slug}, relatorio
        )
        saida.append({"inquilino": slug, "job_id": job_id, **relatorio})
    print(json.dumps(saida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())

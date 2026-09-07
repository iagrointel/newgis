"""Tipos de job do catálogo (ADR 0004 seção 11.4), registrados pelo decorador @tarefa do L0-05 e importados em
app/jobs/tipos.py: catalogo.miniatura, catalogo.lixeira_expurgar (pesado), catalogo.versoes_compactar,
catalogo.tags_renomear, catalogo.migrar_dados, catalogo.exportar_lista. Importar este módulo também soma os
periódicos do catálogo à lista do worker (app/catalogo/periodicos.py)."""

import csv
import datetime
import importlib
import io
import json
import uuid

from pydantic import BaseModel, Field, field_validator

from app import objetos
from app.catalogo import destruidores, miniatura, tipos
from app.jobs.registro import FalhaDefinitiva, tarefa


def _evento(cur, tenant_id: int, tipo: str, alvo_id, propriedades: dict) -> None:
    """Evento no inquilino do item (o job pode rodar no inquilino técnico): troca o contexto só para gravar."""
    cur.execute("SELECT current_setting('plat.tenant_id', true) AS t")
    anterior = cur.fetchone()["t"]
    cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (str(tenant_id),))
    cur.execute(
        "SELECT plat.evento_registrar(%s, 'item', %s, %s::jsonb, NULL, NULL)",
        (tipo, str(alvo_id) if alvo_id else None, json.dumps(propriedades, default=str)),
    )
    cur.execute("SELECT set_config('plat.tenant_id', %s, true)", (anterior or "",))


# ---------------------------------------------------------------- catalogo.miniatura
class MiniaturaParametros(BaseModel):
    item_id: uuid.UUID


@tarefa(
    nome="catalogo.miniatura",
    descricao="Gera a miniatura 600×400 de um item de dado (camada vetorial: render das feições)",
    parametros=MiniaturaParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=120,
    tentativas=2,
    chave=lambda p: f"miniatura:{p.get('item_id')}",
    perfil_minimo="editor",
)
def catalogo_miniatura(ctx, item_id: uuid.UUID) -> dict:
    iid = str(item_id)
    with ctx.db() as cur:
        cur.execute("SELECT tipo, dados, plat.pode_editar(id) AS pode FROM plat.item WHERE id = %s::uuid", (iid,))
        r = cur.fetchone()
        if r is None or not r["pode"]:
            raise FalhaDefinitiva("item inexistente ou sem permissão de edição")
        if r["tipo"] not in miniatura.GERADORES:
            raise FalhaDefinitiva(f"tipo {r['tipo']} sem gerador de miniatura")
        dados = r["dados"] or {}
        ctx.progresso(10, "lendo feições")
        try:
            png = miniatura.render_camada(cur, dados.get("schema", ""), dados.get("tabela", ""))
        except ValueError as e:
            raise FalhaDefinitiva(str(e)) from e
        ctx.progresso(80, "gravando miniatura")
        o = miniatura.guardar(cur, iid, png)
        _evento(
            cur,
            ctx.tenant_id,
            "itens/miniatura",
            iid,
            {"acao": "gerada", "sha256": o["sha256"], "job_id": str(ctx.job_id)},
        )
    ctx.progresso(100, "miniatura gerada")
    return {"item_id": iid, "miniatura_chave": o["chave"], "sha256": o["sha256"], "bytes": o["bytes"]}


# ---------------------------------------------------------------- catalogo.lixeira_expurgar
class ExpurgoParametros(BaseModel):
    dias: int = Field(30, ge=0, le=3650)
    ids: list[uuid.UUID] | None = Field(None, max_length=1000)
    agora: datetime.datetime | None = Field(None, description="relógio simulado; só em PLAT_AMBIENTE=dev")

    @field_validator("agora")
    @classmethod
    def _so_em_dev(cls, v):
        if v is not None:
            from app import settings as cfg

            if cfg.obter().producao:
                raise ValueError("o parâmetro agora só é aceito em ambiente dev")
        return v


@tarefa(
    nome="catalogo.lixeira_expurgar",
    descricao="Expurgo da lixeira: apaga dado físico e registro dos itens apagados há mais de N dias",
    parametros=ExpurgoParametros,
    pesado=True,
    memoria_mb=512,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: "lixeira_expurgar",
    perfil_minimo="admin",
)
def catalogo_lixeira_expurgar(
    ctx, dias: int = 30, ids: list[uuid.UUID] | None = None, agora: datetime.datetime | None = None
) -> dict:
    with ctx.db() as cur:
        cur.execute(
            "SELECT * FROM plat.lixeira_expurgar(%s, %s, %s::uuid[])",
            (dias, agora or datetime.datetime.now(datetime.UTC), [str(x) for x in ids] if ids else None),
        )
        candidatos = cur.fetchall()
    ctx.log("INFO", f"{len(candidatos)} itens a expurgar (dias={dias}, agora={agora or 'now'})")
    expurgados, recusados, bytes_total = 0, [], 0
    for n, c in enumerate(candidatos, 1):
        iid = str(c["item_id"])
        try:
            with ctx.db() as cur:
                liberados = destruidores.destruir(cur, c["tipo"], c["dados"], c["miniatura_chave"], ctx.log)
                cur.execute("SELECT plat.item_expurgar(%s::uuid) AS ok", (iid,))
                if not cur.fetchone()["ok"]:
                    raise destruidores.Recusado("registro já não estava na lixeira")
                bytes_total += liberados or int(c["tamanho_bytes"] or 0)
                _evento(
                    cur,
                    c["tenant_id"],
                    "lixeira/expurgar",
                    iid,
                    {
                        "item_id": iid,
                        "tipo": c["tipo"],
                        "bytes_liberados": liberados or int(c["tamanho_bytes"] or 0),
                        "titulo": (c["titulo"] or "")[:250],
                        "job_id": str(ctx.job_id),
                    },
                )
            expurgados += 1
        except destruidores.Recusado as e:
            recusados.append({"item_id": iid, "tipo": c["tipo"], "motivo": str(e)})
            ctx.log("AVISO", f"{iid} ({c['tipo']}) não expurgado: {e}")
        ctx.progresso(int(n * 100 / max(1, len(candidatos))), f"{n} de {len(candidatos)}")
    return {"expurgados": expurgados, "recusados": recusados, "bytes_liberados": bytes_total}


# ---------------------------------------------------------------- catalogo.versoes_compactar
class CompactarParametros(BaseModel):
    manter: int = Field(50, ge=1, le=1000)
    item_id: uuid.UUID | None = None


@tarefa(
    nome="catalogo.versoes_compactar",
    descricao="Compacta versões antigas de item (mantém as 50 mais recentes; blocos de 10 viram uma)",
    parametros=CompactarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=1800,
    tentativas=1,
    chave=lambda p: "versoes_compactar",
    perfil_minimo="admin",
)
def catalogo_versoes_compactar(ctx, manter: int = 50, item_id: uuid.UUID | None = None) -> dict:
    with ctx.db() as cur:
        if item_id:
            itens = [str(item_id)]
        else:
            cur.execute("SELECT plat.itens_com_versoes_acima(%s) AS id", (manter,))
            itens = [str(r["id"]) for r in cur.fetchall()]
    removidas = 0
    for n, iid in enumerate(itens, 1):
        with ctx.db() as cur:
            cur.execute("SELECT plat.item_versoes_compactar(%s::uuid, %s) AS n", (iid, manter))
            removidas += cur.fetchone()["n"]
        ctx.progresso(int(n * 100 / max(1, len(itens))), f"{n} de {len(itens)} itens")
    return {"itens": len(itens), "versoes_removidas": removidas}


# ---------------------------------------------------------------- catalogo.tags_renomear
class TagsParametros(BaseModel):
    de: str = Field(min_length=1, max_length=128)
    para: str | None = Field(None, max_length=128)


@tarefa(
    nome="catalogo.tags_renomear",
    descricao="Renomeia (ou remove, com para vazio) uma tag em todos os itens do inquilino",
    parametros=TagsParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=600,
    tentativas=1,
    chave=lambda p: "tags",
    perfil_minimo="admin",
)
def catalogo_tags_renomear(ctx, de: str, para: str | None = None) -> dict:
    with ctx.db() as cur:
        if para:
            cur.execute(
                "UPDATE plat.item SET tags = ARRAY(SELECT DISTINCT CASE WHEN t = %s THEN %s ELSE t END "
                "FROM unnest(tags) t) "
                "WHERE %s = ANY (tags) AND apagado_em IS NULL",
                (de, para, de),
            )
        else:
            cur.execute(
                "UPDATE plat.item SET tags = array_remove(tags, %s) WHERE %s = ANY (tags) AND apagado_em IS NULL",
                (de, de),
            )
        n = cur.rowcount
    return {"itens": n, "de": de, "para": para}


# ---------------------------------------------------------------- catalogo.migrar_dados
class MigrarParametros(BaseModel):
    tipo: str = Field(min_length=2, max_length=41)
    funcao: str = Field(min_length=3, max_length=200, description="caminho python 'app.<linha>.migrar_dados:funcao'")
    esquema_versao: int = Field(ge=1)


@tarefa(
    nome="catalogo.migrar_dados",
    descricao="Aplica uma função de migração de dados a todos os itens de um tipo (esquema novo)",
    parametros=MigrarParametros,
    pesado=False,
    memoria_mb=512,
    timeout_s=3600,
    tentativas=1,
    chave=lambda p: f"migrar:{p.get('tipo')}",
    perfil_minimo="admin",
)
def catalogo_migrar_dados(ctx, tipo: str, funcao: str, esquema_versao: int) -> dict:
    if ":" not in funcao or not funcao.startswith("app."):
        raise FalhaDefinitiva("funcao exige o formato app.<modulo>:<funcao>")
    modulo, nome = funcao.split(":", 1)
    try:
        f = getattr(importlib.import_module(modulo), nome)
    except (ImportError, AttributeError) as e:
        raise FalhaDefinitiva(f"função de migração não encontrada: {funcao}") from e
    tipos.todos(forcar=True)
    with ctx.db() as cur:
        cur.execute(
            "SELECT id, dados FROM plat.item WHERE tipo = %s AND plat.pode_editar(id) ORDER BY criado_em", (tipo,)
        )
        itens = cur.fetchall()
    falhas, ok = [], 0
    for n, it in enumerate(itens, 1):
        iid = str(it["id"])
        try:
            novos = f(it["dados"] or {})
            erros = tipos.erros_de(tipo, novos)
            if erros:
                raise ValueError(f"esquema: {erros[0]['campo']}: {erros[0]['erro']}")
            with ctx.db() as cur:
                cur.execute(
                    "SELECT set_config('plat.versao_rotulo', 'migracao', true), "
                    "set_config('plat.versao_comentario', %s, true)",
                    (f"dados migrados para o esquema {esquema_versao}",),
                )
                cur.execute(
                    "UPDATE plat.item SET dados = %s::jsonb WHERE id = %s::uuid", (json.dumps(novos, default=str), iid)
                )
                _evento(
                    cur,
                    ctx.tenant_id,
                    "itens/dados_migrar",
                    iid,
                    {"tipo": tipo, "esquema_versao": esquema_versao, "job_id": str(ctx.job_id)},
                )
            ok += 1
        except Exception as e:  # noqa: BLE001 — a falha de um item não para a migração dos outros
            falhas.append({"item_id": iid, "erro": str(e)[:300]})
        ctx.progresso(int(n * 100 / max(1, len(itens))), f"{n} de {len(itens)}")
    return {"itens": ok, "falhas": falhas}


# ---------------------------------------------------------------- catalogo.exportar_lista
class ExportarParametros(BaseModel):
    formato: str = Field("csv", pattern="^(csv|json)$")
    ids: list[uuid.UUID] | None = Field(None, max_length=100000)


@tarefa(
    nome="catalogo.exportar_lista",
    descricao="Exporta a lista de itens (csv/json) para um objeto do armazenamento",
    parametros=ExportarParametros,
    pesado=False,
    memoria_mb=256,
    timeout_s=600,
    tentativas=1,
    perfil_minimo="editor",
    # L7-33: só lê o catálogo e grava o artefato no armazenamento — é o tipo que atravessa o modo de
    # manutenção (a hipótese do item manda a exportação continuar; ver app/modo.py e plat.job_pegar)
    somente_leitura=True,
)
def catalogo_exportar_lista(ctx, formato: str = "csv", ids: list[uuid.UUID] | None = None) -> dict:
    with ctx.db() as cur:
        if ids:
            cur.execute(
                "SELECT i.id, i.tipo, i.titulo, i.resumo, i.tags, u.login AS dono, i.acesso, "
                "i.status, i.criado_em, i.modificado_em "
                "FROM plat.item i JOIN plat.usuario u ON u.id = i.dono_id WHERE i.id = ANY "
                "(%s::uuid[]) AND i.apagado_em IS NULL ORDER BY i.titulo",
                ([str(x) for x in ids],),
            )
        else:
            cur.execute(
                "SELECT i.id, i.tipo, i.titulo, i.resumo, i.tags, u.login AS dono, i.acesso, "
                "i.status, i.criado_em, i.modificado_em "
                "FROM plat.item i JOIN plat.usuario u ON u.id = i.dono_id WHERE i.apagado_em IS NULL ORDER BY i.titulo"
            )
        linhas = [dict(r) for r in cur.fetchall()]
    if formato == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(
            buf,
            fieldnames=[
                "id",
                "tipo",
                "titulo",
                "resumo",
                "tags",
                "dono",
                "acesso",
                "status",
                "criado_em",
                "modificado_em",
            ],
        )
        w.writeheader()
        for r in linhas:
            r["tags"] = ";".join(r["tags"] or [])
            w.writerow({k: r[k] for k in w.fieldnames})
        dados, ct = buf.getvalue().encode("utf-8"), "text/csv"
    else:
        dados, ct = json.dumps(linhas, ensure_ascii=False, default=str).encode("utf-8"), "application/json"
    with ctx.db() as cur:
        o = objetos.guardar(cur, "exportacao", dados, ct, item_id=ctx.job_id)
    ctx.progresso(100, f"{len(linhas)} itens exportados")
    return {"linhas": len(linhas), "chave": o["chave"], "sha256": o["sha256"], "bytes": o["bytes"], "formato": formato}


from app.catalogo import periodicos  # noqa: E402,F401 — importar registra os periódicos do catálogo na lista do worker

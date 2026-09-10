"""Job `camadas.validar` (item L2-10-d-regras-de-atributo; o Evaluate Rules da Esri): percorre a tabela da camada
em lotes (cursor no servidor), avalia toda regra de VALIDAÇÃO habilitada em cada feição e grava as falhas na tabela
e_<hex16> ao lado da camada (fid da feição, regra, código, mensagem, instante, geometria copiada) — a camada de
erros é um item `camada_vetorial` (só leitura) que aponta para essa tabela e aparece no catálogo e no mapa como
qualquer camada. Cada execução substitui a anterior. Registrado em app/jobs/tipos.py."""

from __future__ import annotations

import datetime
import json
import uuid

import psycopg2.extras
from pydantic import BaseModel

from app import limites
from app.jobs.registro import FalhaDefinitiva, tarefa
from app.regras import motor


class ValidarParametros(BaseModel):
    item_id: uuid.UUID


def _ident(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _json(v) -> psycopg2.extras.Json:
    return psycopg2.extras.Json(v, dumps=lambda x: json.dumps(x, ensure_ascii=False, default=str))


def _garantir_camada_de_erros(cur, item: dict, dados: dict, tabela_erros: str, usuario_id: int | None) -> str:
    """Item camada_vetorial da camada de erros (cria uma vez; reaproveita quando já existe e ainda é do inquilino)."""
    validacao = dados.get("validacao") or {}
    existente = validacao.get("item_erros_id")
    if existente:
        cur.execute("SELECT id FROM plat.item WHERE id = %s::uuid AND apagado_em IS NULL", (existente,))
        if cur.fetchone():
            return existente
    iid = str(uuid.uuid4())
    dados_erros = {
        "schema": dados["schema"], "tabela": tabela_erros,
        "geometria": dados.get("geometria") or "Geometry", "srid": dados["srid"],
        "campos": [
            {"nome": "feicao_fid", "tipo": "integer", "alias": "fid da feição"},
            {"nome": "regra", "tipo": "text"}, {"nome": "codigo", "tipo": "text"},
            {"nome": "mensagem", "tipo": "text"}, {"nome": "em", "tipo": "timestamp with time zone"},
        ],
        "fonte": "hospedada", "edicao": {"habilitada": False},
        "procedencia": {"origem": "validacao", "camada_id": item["id"], "protocolo": "regras"},
    }
    cur.execute(
        "INSERT INTO plat.item(id, tenant_id, tipo, titulo, dono_id, dados, acesso, criado_por, modificado_por, tags) "
        "VALUES (%s::uuid, plat.tenant_atual(), 'camada_vetorial', %s, %s, %s, 'privado', %s, %s, %s)",
        (iid, f"Erros de validação — {item['titulo']}"[:200], usuario_id or item["dono_id"], _json(dados_erros),
         usuario_id or item["dono_id"], usuario_id or item["dono_id"], ["validacao", "erros"]),
    )
    return iid


@tarefa(
    nome="camadas.validar",
    descricao="Avalia as regras de validação de uma camada em toda feição e grava a camada de erros (L2-10-d)",
    parametros=ValidarParametros, pesado=False, memoria_mb=768, timeout_s=3600, tentativas=1,
    chave=lambda p: f"camadas.validar:{p.get('item_id')}", perfil_minimo="editor", versao=1,
)
def camadas_validar(ctx, item_id: uuid.UUID) -> dict:
    iid = str(item_id)
    with ctx.db() as cur:
        cur.execute(
            "SELECT id::text AS id, titulo, dono_id, dados, plat.pode_editar(id) AS pode FROM plat.item "
            "WHERE id = %s::uuid AND tipo = 'camada_vetorial' AND apagado_em IS NULL", (iid,),
        )
        r = cur.fetchone()
        if r is None or not r["pode"]:
            raise FalhaDefinitiva("camada inexistente ou sem permissão de edição")
        dados = r["dados"] or {}
        if dados.get("fonte") != "hospedada":
            raise FalhaDefinitiva("só camada hospedada é validada por este job")
        comp = motor.compilar(dados)
        regras = [x for x in comp.regras if x.tipo == "validacao" and x.habilitada]
        if not regras:
            raise FalhaDefinitiva("a camada não tem regra de validação habilitada")
        schema, tabela = dados["schema"], dados["tabela"]
        padrao = "e_" + tabela[2:] if tabela.startswith("c_") else "e_" + uuid.uuid4().hex[:16]
        tabela_erros = (dados.get("validacao") or {}).get("tabela_erros") or padrao
        cur.execute(
            "SELECT plat.tabela_erros_preparar(%s, %s, %s, %s)",
            (schema, tabela_erros, int(dados["srid"]), dados.get("geometria")),
        )
        cur.execute(f"SELECT count(*) AS n FROM {_ident(schema)}.{_ident(tabela)}")
        total = cur.fetchone()["n"]
        item_erros = _garantir_camada_de_erros(cur, r, dados, tabela_erros, ctx.usuario_id)
    ctx.log("INFO", f"{total} feições, {len(regras)} regra(s) de validação; erros em {schema}.{tabela_erros}")
    tem_geom = dados.get("geometria") not in (None, "nenhuma")
    colunas = ["fid", "globalid", *sorted(comp.campos)]
    sel = ", ".join(_ident(c) for c in colunas) + (", geom" if tem_geom else "")
    inicio = datetime.datetime.now(datetime.UTC)
    n_erros = n_lidas = 0
    truncado = False
    with ctx.db() as cur:
        cur.execute(f"DELETE FROM {_ident(schema)}.{_ident(tabela_erros)}")
        nome_cursor = f"val_{uuid.uuid4().hex[:8]}"
        cur.execute(
            f"DECLARE {nome_cursor} NO SCROLL CURSOR FOR "
            f"SELECT {sel} FROM {_ident(schema)}.{_ident(tabela)} ORDER BY fid"
        )
        while True:
            ctx.verificar()
            cur.execute(f"FETCH FORWARD {limites.REGRAS_VALIDACAO_LOTE} FROM {nome_cursor}")
            lote = cur.fetchall()
            if not lote:
                break
            linhas = []
            for li in lote:
                for f in motor.avaliar_validacao(comp, li):
                    linhas.append(
                        (li["fid"], str(li["globalid"]), f["regra"], f["codigo"], f["mensagem"], li.get("geom"))
                    )
            n_lidas += len(lote)
            if linhas:
                if n_erros + len(linhas) > limites.REGRAS_VALIDACAO_ERROS_MAX:
                    linhas = linhas[: max(0, limites.REGRAS_VALIDACAO_ERROS_MAX - n_erros)]
                    truncado = True
                psycopg2.extras.execute_values(
                    cur,
                    f"INSERT INTO {_ident(schema)}.{_ident(tabela_erros)} "
                    "(feicao_fid, feicao_globalid, regra, codigo, mensagem, geom) VALUES %s",
                    linhas, template="(%s, %s::uuid, %s, %s, %s, %s)", page_size=1000,
                )
                n_erros += len(linhas)
            pct = min(99, int(n_lidas * 100 / max(total, 1)))
            ctx.progresso(pct, f"{n_lidas} de {total} feições, {n_erros} erro(s)")
            if truncado:
                ctx.log("WARN", f"teto de {limites.REGRAS_VALIDACAO_ERROS_MAX} erros atingido; validação interrompida")
                break
        cur.execute(f"CLOSE {nome_cursor}")
    fim = datetime.datetime.now(datetime.UTC)
    resumo = {
        "tabela_erros": tabela_erros, "item_erros_id": item_erros, "job_id": str(ctx.job_id),
        "em": fim.isoformat(timespec="seconds"), "n_feicoes": n_lidas, "n_erros": n_erros, "truncado": truncado,
        "regras": [x.id for x in regras], "duracao_s": round((fim - inicio).total_seconds(), 3),
    }
    with ctx.db() as cur:
        cur.execute("UPDATE plat.item SET dados = dados || %s::jsonb WHERE id = %s::uuid",
                    (json.dumps({"validacao": resumo}, ensure_ascii=False), iid))
        cur.execute(
            "SELECT plat.evento_registrar(%s, 'item', %s, %s::jsonb, NULL, NULL)",
            ("camadas/validar", iid,
             json.dumps({k: resumo[k] for k in ("n_feicoes", "n_erros", "truncado", "duracao_s", "item_erros_id")})),
        )
    ctx.progresso(100, f"{n_lidas} feições, {n_erros} erro(s)")
    return resumo

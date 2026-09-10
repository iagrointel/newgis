"""Leitura e escrita de `plat.modelo3d` e `plat.modelo3d_elemento`.

Só SQL e forma de resposta: a geodésia está em `posicionamento`, o formato em `glb`/`ifc`/`tiles3d`, e o
trabalho pesado nas tarefas da fila. As rotas não escrevem SQL.

Isolamento: toda consulta passa pelo cursor com contexto de sessão (RLS por `tenant_id`), como o resto do
repositório — nenhuma consulta aqui filtra inquilino no `WHERE` à mão, porque duas defesas iguais que
divergem é pior que uma só que vale sempre.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg2.extras

from app.erros import ErroAPI

CAMPOS = ("id", "nome", "origem", "arquivo_sha256", "arquivo_classe", "glb_sha256", "glb_bytes", "lon", "lat",
          "altura_m", "rotacao_graus", "escala", "estado", "erro", "elementos", "elementos_sem_forma",
          "tileset", "tileset_tiles", "caixa", "criado_em", "atualizado_em")
OCULTOS = ("tileset_arquivos",)  # chave interna do armazenamento: nunca sai na resposta da API


def _ficha(linha: dict) -> dict:
    d = {c: linha[c] for c in CAMPOS if c in linha}
    for chave in ("criado_em", "atualizado_em"):
        if d.get(chave) is not None:
            d[chave] = d[chave].isoformat()
    d["id"] = str(d["id"])
    return d


def listar(cur, limite: int = 50, deslocamento: int = 0) -> dict:
    cur.execute("SELECT count(*) AS n FROM plat.modelo3d")
    total = cur.fetchone()["n"]
    cur.execute("SELECT * FROM plat.modelo3d ORDER BY criado_em DESC, id LIMIT %s OFFSET %s",
                (limite, deslocamento))
    return {"total": total, "itens": [_ficha(r) for r in cur.fetchall()]}


def obter(cur, modelo_id: str) -> dict:
    cur.execute("SELECT * FROM plat.modelo3d WHERE id = %s::uuid", (modelo_id,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "nao_encontrado", "modelo 3D inexistente")
    return _ficha(linha)


def criar(cur, dono_id: int, tenant_id: int, corpo: dict) -> dict:
    cur.execute(
        "INSERT INTO plat.modelo3d(tenant_id, nome, origem, arquivo_sha256, arquivo_classe, lon, lat, "
        "altura_m, rotacao_graus, escala, dono_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
        (tenant_id, corpo["nome"], corpo["origem"], corpo["arquivo_sha256"], corpo.get("arquivo_classe",
         "modelo3d"), corpo["lon"], corpo["lat"], corpo.get("altura_m", 0.0), corpo.get("rotacao_graus", 0.0),
         corpo.get("escala", 1.0), dono_id),
    )
    return _ficha(cur.fetchone())


def apagar(cur, modelo_id: str) -> dict:
    cur.execute("DELETE FROM plat.modelo3d WHERE id = %s::uuid RETURNING id, nome, arquivo_classe",
                (modelo_id,))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "nao_encontrado", "modelo 3D inexistente")
    return {"id": str(linha["id"]), "nome": linha["nome"], "classe": linha["arquivo_classe"]}


def marcar(cur, modelo_id: str, **campos: Any) -> None:
    if not campos:
        return
    pedacos, valores = [], []
    for chave, valor in campos.items():
        pedacos.append(f"{chave} = %s")
        valores.append(psycopg2.extras.Json(valor) if isinstance(valor, (dict, list)) else valor)
    valores.append(modelo_id)
    cur.execute(f"UPDATE plat.modelo3d SET {', '.join(pedacos)}, atualizado_em = now() "
                "WHERE id = %s::uuid", valores)


def gravar_elementos(cur, tenant_id: int, modelo_id: str, elementos) -> int:
    """Substitui os elementos do modelo. Uma linha por elemento do IFC, com o GUID do próprio arquivo."""
    cur.execute("DELETE FROM plat.modelo3d_elemento WHERE modelo_id = %s::uuid", (modelo_id,))
    if not elementos:
        return 0
    linhas = [(tenant_id, modelo_id, e.guid, e.tipo, (e.nome or None), (e.descricao or None),
               e.pavimento, e.tem_geometria, json.dumps(e.propriedades, ensure_ascii=False))
              for e in elementos]
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO plat.modelo3d_elemento(tenant_id, modelo_id, guid, tipo, nome, descricao, pavimento, "
        "tem_geometria, propriedades) VALUES %s "
        "ON CONFLICT (modelo_id, guid) DO UPDATE SET tipo = EXCLUDED.tipo, nome = EXCLUDED.nome, "
        "descricao = EXCLUDED.descricao, pavimento = EXCLUDED.pavimento, "
        "tem_geometria = EXCLUDED.tem_geometria, propriedades = EXCLUDED.propriedades",
        linhas, template="(%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb)", page_size=500,
    )
    return len(linhas)


def listar_elementos(cur, modelo_id: str, tipo: str | None = None, pavimento: str | None = None,
                     limite: int = 200, deslocamento: int = 0) -> dict:
    onde = ["modelo_id = %s::uuid"]
    valores: list = [modelo_id]
    if tipo:
        onde.append("tipo = %s")
        valores.append(tipo.upper())
    if pavimento:
        onde.append("pavimento = %s")
        valores.append(pavimento)
    filtro = " AND ".join(onde)
    cur.execute(f"SELECT count(*) AS n FROM plat.modelo3d_elemento WHERE {filtro}", valores)
    total = cur.fetchone()["n"]
    cur.execute(
        f"SELECT guid, tipo, nome, pavimento, tem_geometria FROM plat.modelo3d_elemento WHERE {filtro} "
        "ORDER BY tipo, guid LIMIT %s OFFSET %s", [*valores, limite, deslocamento])
    return {"total": total, "itens": [dict(r) for r in cur.fetchall()]}


def obter_elemento(cur, modelo_id: str, guid: str) -> dict:
    cur.execute("SELECT guid, tipo, nome, descricao, pavimento, tem_geometria, propriedades "
                "FROM plat.modelo3d_elemento WHERE modelo_id = %s::uuid AND guid = %s", (modelo_id, guid))
    linha = cur.fetchone()
    if linha is None:
        raise ErroAPI(404, "nao_encontrado", "elemento inexistente neste modelo")
    return dict(linha)


__all__ = ["listar", "obter", "criar", "apagar", "marcar", "gravar_elementos", "listar_elementos",
           "obter_elemento"]

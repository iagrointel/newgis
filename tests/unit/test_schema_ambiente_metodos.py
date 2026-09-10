"""Guarda do cursor que reescreve o schema (app/schema_ambiente.py).

Incidente de 06/09/2026: `CursorSchemaAmbiente` sobrescrevia `execute` e `callproc`, mas não `executemany`. O
INSERT em lote de `plat.papel_privilegio` (app/auth/rotas_usuarios.py) ia ao servidor com o literal `plat.`, e
todo ambiente que roda noutro schema (homologação, trilha de worktree) respondia InsufficientPrivilege — que o
app traduz para 403 "operação fora do inquilino da sessão". Duas rotas de papel ficaram inutilizáveis fora de
produção sem ninguém perceber, porque nenhum teste rodava fora do schema `plat`.

Este teste varre app/ atrás de QUALQUER método de cursor que mande SQL ao servidor e exige que ele esteja
sobrescrito na classe. Método novo em uso sem sobrescrita reprova aqui, não em produção.
"""

import re
from pathlib import Path

from app.schema_ambiente import CursorSchemaAmbiente, reescrever_schema

ROOT = Path(__file__).resolve().parents[2]
# Métodos do cursor psycopg2 que levam texto de SQL ao servidor.
MANDAM_SQL = {"execute", "executemany", "callproc", "mogrify", "copy_expert", "copy_from", "copy_to"}
CHAMADA = re.compile(r"\b(?:cur|cursor|c)\.(\w+)\s*\(")


def _usados_em_app() -> set[str]:
    usados = set()
    for arquivo in (ROOT / "app").rglob("*.py"):
        for metodo in CHAMADA.findall(arquivo.read_text(encoding="utf-8")):
            if metodo in MANDAM_SQL:
                usados.add(metodo)
    return usados


def test_todo_metodo_de_cursor_usado_no_app_reescreve_o_schema():
    faltando = sorted(m for m in _usados_em_app() if m not in vars(CursorSchemaAmbiente))
    assert faltando == [], faltando


def test_reescrita_troca_schema_e_poupa_producao():
    sql = "INSERT INTO plat.papel_privilegio(papel_id, privilegio) VALUES (%s, %s)"
    assert reescrever_schema(sql, "plat_th", "plat_trabalho_th").startswith("INSERT INTO plat_th.papel_privilegio")
    assert reescrever_schema(sql) is sql  # caminho de produção: nenhuma regex roda
    guc = "SELECT set_config('plat.tenant_id', %s, true), current_setting('plat.login', true)"
    assert reescrever_schema(guc, "plat_th", "plat_trabalho_th") == guc  # GUC não é schema

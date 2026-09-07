"""Fixtures do catálogo: fábrica de itens zt* pela API (limpos no fim: lixeira + expurgo físico como plat_app no
contexto do admin, só itens do próprio inquilino), usuários temporários do inquilino demo e a semente de 10 mil itens
(tests/api/semear_catalogo.py) usada pelas medidas."""

import os
import secrets

import psycopg2
import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests.api.conftest import PREFIXO_TESTE, sob_xdist
from tests.api.semear_catalogo import PREFIXO as SEMENTE
from tests.api.test_rls import contexto, ids_por_slug

# 07/09: a base por trilha reescreve só o texto SQL, não o metadado do item
_TRAB = os.environ.get("PLAT_SCHEMA_TRABALHO", "plat_trabalho")

DADOS_POR_TIPO = {
    "mapa": {"esquema_versao": 1, "corpo": {}},
    "cena": {"esquema_versao": 1, "corpo": {}},
    "estilo": {"esquema_versao": 1, "corpo": {}},
    "app": {"tipo": "app", "esquema_versao": 1, "corpo": {}},
    "painel": {"tipo": "painel", "esquema_versao": 1, "corpo": {}},
    "formulario": {"tipo": "formulario", "esquema_versao": 1, "corpo": {}},
    "fluxo": {"tipo": "fluxo", "esquema_versao": 1, "corpo": {}},
    "arquivo": {
        "chave": "arquivo/00000000-0000-0000-0000-000000000000/" + "a" * 64 + ".bin",
        "sha256": "a" * 64,
        "bytes": 10,
        "content_type": "application/octet-stream",
        "nome_original": "x.bin",
    },
    "camada_vetorial": {
        "schema": _TRAB,
        "tabela": "zt_inexistente",
        "geometria": "Point",
        "srid": 4326,
        "campos": [{"nome": "a", "tipo": "text"}],
        "fonte": "hospedada",
    },
    "conexao": {"protocolo": "wms", "url": "https://exemplo.gov.br/wms"},
    "modelo_amc": {"esquema_versao": 1, "fatores": [], "metodo": "soma_ponderada"},
}


def titulo_zt(base: str = "item") -> str:
    return f"{PREFIXO_TESTE} {base} {secrets.token_hex(3)}"


class Itens:
    """Cria itens pela API com uma sessão e registra para limpeza."""

    def __init__(self, sessao):
        self.sessao = sessao
        self.criados: list[str] = []

    def criar(self, tipo="mapa", sessao=None, **campos) -> dict:
        s = sessao or self.sessao
        corpo = {"tipo": tipo, "titulo": titulo_zt(tipo), "dados": DADOS_POR_TIPO.get(tipo, {})}
        corpo.update(campos)
        r = s.post("/api/itens", json=corpo)
        assert r.status_code == 201, r.text
        j = r.json()
        self.criados.append(j["id"])
        return j


def _expurgar_zt(env, slug: str) -> None:
    """Limpeza física dos itens/pastas/categorias zt* do inquilino: como plat_app no contexto do admin."""
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        ids = ids_por_slug(con)
        with con.cursor() as cur:
            cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", (slug,))
            adm = cur.fetchone()["usuario_id"]
        contexto(con, ids[slug], usuario_id=adm, login="admin")
        with con.cursor() as cur:
            cur.execute("SELECT set_config('plat.lixeira', 'on', true)")
            # o corpus de escala (zt-semente, 10 mil em demo e 1 mil em demo2) NÃO é apagado: semeá-lo custa minutos
            # a cada rodada e é dele que saem as medidas de busca. Para removê-lo à mão:
            # venv/bin/python -m tests.api.semear_catalogo 0
            cur.execute(
                "UPDATE plat.item SET protegido = false, status = NULL "
                "WHERE titulo LIKE %s AND titulo NOT LIKE %s AND protegido",
                (PREFIXO_TESTE + "%", SEMENTE + "%"),
            )
            cur.execute(
                "SELECT id FROM plat.item WHERE titulo LIKE %s AND titulo NOT LIKE %s",
                (PREFIXO_TESTE + "%", SEMENTE + "%"),
            )
            for r in cur.fetchall():
                cur.execute("SELECT plat.item_lixeira(%s::uuid, true)", (r["id"],))
                cur.execute("SELECT plat.item_expurgar(%s::uuid)", (r["id"],))
            # o gatilho pasta_vazia recusa apagar pasta com filha: das folhas para a raiz, até não sobrar nenhuma
            for _ in range(10):
                cur.execute(
                    "DELETE FROM plat.pasta WHERE nome LIKE %s "
                    "AND NOT EXISTS (SELECT 1 FROM plat.pasta f WHERE f.pai_id = plat.pasta.id) RETURNING id",
                    (PREFIXO_TESTE + "%",),
                )
                if not cur.fetchall():
                    break
            cur.execute("DELETE FROM plat.categoria WHERE nome LIKE %s AND nivel = 3", (PREFIXO_TESTE + "%",))
            cur.execute("DELETE FROM plat.categoria WHERE nome LIKE %s AND nivel = 2", (PREFIXO_TESTE + "%",))
            cur.execute("DELETE FROM plat.categoria WHERE nome LIKE %s", (PREFIXO_TESTE + "%",))
        con.commit()
    finally:
        con.close()


@pytest.fixture(scope="session")
def itens_a(sessao_a, env):
    f = Itens(sessao_a)
    yield f
    if not sob_xdist():
        _expurgar_zt(env, "demo")


@pytest.fixture(scope="session")
def itens_b(sessao_b, env):
    f = Itens(sessao_b)
    yield f
    if not sob_xdist():
        _expurgar_zt(env, "demo2")


@pytest.fixture(scope="session")
def editor_a(usuarios_a):
    """Editor comum do inquilino demo: (cliente, usuario)."""
    c, u, _ = usuarios_a.sessao("editor")
    return c, u


@pytest.fixture(scope="session")
def visualizador_a(usuarios_a):
    c, u, _ = usuarios_a.sessao("visualizador")
    return c, u


@pytest.fixture(scope="session")
def editor2_a(usuarios_a):
    c, u, _ = usuarios_a.sessao("editor")
    return c, u


@pytest.fixture(scope="session")
def worker_vivo(cliente):
    """Jobs do catálogo (miniatura, expurgo) exigem a unidade plat-worker viva com os tipos catalogo.* registrados."""
    r = cliente.get("/saude").json()
    fila = r.get("fila") or {}
    if not fila.get("workers_vivos"):
        pytest.fail(f"nenhum worker vivo em /saude ({fila}); rode `sudo systemctl restart plat-worker`")
    return fila


def esperar_job(sessao, job_id: str, timeout: float = 60) -> dict:
    """Espera o job chegar a estado final; devolve o JSON (falha com o último visto)."""
    import json
    import time

    fim = time.monotonic() + timeout
    ultimo = None
    while time.monotonic() < fim:
        r = sessao.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo["estado"] in ("concluido", "falhou", "cancelado"):
            return ultimo
        time.sleep(0.3)
    pytest.fail(f"job {job_id} não terminou em {timeout} s: {json.dumps(ultimo)[:600]}")

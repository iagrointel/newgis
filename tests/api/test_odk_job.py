"""Job `odk.sincronizar` (item L2-07-e-odk-central-ponte): o caminho SEM ninguém na tela.

A cláusula do portão é "job repetido não duplica (instanceID)", e a idempotência tem de valer também quando a
sincronização vem do relógio do L0-05, agindo como o dono da ponte — não só quando vem da rota. O contexto de
job aqui é de mentira (um objeto com `db()`, `progresso()` e `verificar()`), mas o banco, a ponte, o formulário
e as camadas são reais; o Central é o dublê de `tests/odk_central_duble.py`."""

import pytest

from app import db
from app.jobs.registro import REGISTRO, FalhaDefinitiva
from app.odk.tarefas import odk_sincronizar
from tests.api.test_odk_ponte import _preparar, duble, limpeza  # noqa: F401 — fixtures reusadas
from tests.api.test_rls import ids_por_slug


class CtxFalso:
    def __init__(self, tenant_id: int, usuario_id: int, login: str):
        self.tenant_id = tenant_id
        self._ctx = db.Contexto(tenant_id, usuario_id, login)
        self.progressos: list[tuple[int, str]] = []

    def db(self):
        return db.db(self._ctx)

    def progresso(self, pct: int, mensagem: str = "") -> None:
        self.progressos.append((pct, mensagem))

    def verificar(self) -> None:
        pass


@pytest.fixture
def ctx(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login(%s, 'admin')", ("demo",))
        admin = cur.fetchone()["usuario_id"]
    return CtxFalso(ids["demo"], admin, "admin")


def test_o_tipo_de_job_esta_registrado_com_chave_por_ponte():
    tarefa = REGISTRO["odk.sincronizar"]
    assert tarefa.perfil_minimo == "editor" and tarefa.pesado is False
    assert tarefa.chave({"ponte": "abc"}) == "odk_sincronizar:abc"


def test_o_job_aplica_uma_vez_e_repete_sem_duplicar(sessao_a, duble, limpeza, ctx, conexao_plat_app):  # noqa: F811
    _c, _f, ponte = _preparar(sessao_a, limpeza, duble)
    duble.semear_envios(5)
    primeira = odk_sincronizar(ctx, ponte=ponte["id"])
    segunda = odk_sincronizar(ctx, ponte=ponte["id"])
    assert (primeira["aplicados"], primeira["repetidos"]) == (5, 0)
    assert (segunda["aplicados"], segunda["repetidos"]) == (0, 5)
    assert ctx.progressos[-1][0] == 100
    # e o que a ROTA já tinha aplicado também não é reaplicado pelo job (a memória é a mesma tabela)
    duble.semear_envios(2, prefixo="uuid:zt-odk-rota-")
    pela_rota = sessao_a.post(f"/api/odk/pontes/{ponte['id']}/sincronizar").json()
    assert pela_rota["aplicados"] == 2
    assert odk_sincronizar(ctx, ponte=ponte["id"])["aplicados"] == 0


def test_ponte_inexistente_e_falha_definitiva(ctx):
    with pytest.raises(FalhaDefinitiva):
        odk_sincronizar(ctx, ponte="00000000-0000-0000-0000-000000000000")

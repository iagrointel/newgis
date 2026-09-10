"""app/db.py::_preparar com contexto (item L7-06-a-metricas-exporters): application_name vira 'plat:<tenant_id>'
— o único jeito de o postgres_exporter contar conexões por inquilino em pg_stat_activity de OUTRA sessão sem
tocar no slug (current_setting só lê os GUCs 'plat.*' da PRÓPRIA sessão; application_name é visível de fora)."""

from app import db


def test_application_name_e_plat_dois_pontos_tenant_id():
    ctx = db.Contexto(tenant_id=987654, usuario_id=1, login="zt-teste")
    with db.db(ctx) as cur:
        cur.execute("SHOW application_name")
        assert cur.fetchone()["application_name"] == "plat:987654"


def test_sem_contexto_nao_mexe_em_application_name():
    with db.db() as cur:
        cur.execute("SHOW application_name")
        nome = cur.fetchone()["application_name"]
    assert not nome.startswith("plat:987654")

"""Adversário de linha L0 (turno 9) — item `L0-06-backup-status`.

Portão (literal): "backup diário + WAL, dump por inquilino em formato aberto ... sob demanda, restore drill
scriptado, página de status e log de correções" -- hipótese explícita: "o dump é do schema `d_<slug>` do
PRÓPRIO inquilino que pediu o backup".

Dois achados, medidos ao vivo em `plat.agenda` (trilha uniao, 2026-09-16), não em teoria:

1. Os dois periódicos do PRÓPRIO item (`backup.executar`, `backup.ensaio_restauracao`) nascem `ativa=false`
   por decisão explícita de `app/backup/periodicos.py` ("Os dois entram PAUSADOS por padrão ... quem liga é
   o dono, à mão") e continuam pausados hoje: nenhum dos dois jamais rodou (`ultima_em IS NULL` para os
   dois). "Backup diário" não é o que acontece por padrão para nenhum inquilino -- é uma opção que ninguém
   liga.

2. Mais grave que "pausado": mesmo que um admin ligasse os dois à mão, eles nunca alcançariam um inquilino
   de CLIENTE. `app/jobs/agenda.py::sincronizar_periodicos` faz upsert de TODOS os periódicos globais
   (inclusive os dois de L0-06-backup-status) só no inquilino TÉCNICO `plataforma` -- limitação que o
   próprio módulo documenta ("rodando dali, esses dois fariam backup só do schema `d_plataforma`, não de
   cada inquilino de cliente ... o sistema de periódicos de hoje não tem [agenda por tenant]"). Medido: o
   inquilino `demo` (um inquilino de cliente comum) tem ZERO linhas de `tipo IN ('backup.executar',
   'backup.ensaio_restauracao')` em `plat.agenda` -- não pausadas, AUSENTES. "Backup por inquilino"
   automático não existe hoje para nenhum inquilino além do técnico -- só o disparo manual
   (`POST /api/jobs {tipo: backup.executar}`) funciona, e depende de o admin lembrar de rodá-lo."""

import pytest

from tests.api.test_rls import contexto, ids_por_slug

TIPOS_BACKUP_POR_INQUILINO = ("backup.executar", "backup.ensaio_restauracao")


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO (turno 9, adversário de linha L0, item L0-06-backup-status): os periódicos "
    "backup.executar/backup.ensaio_restauracao nascem ativa=false (app/backup/periodicos.py, 'quem liga é o "
    "dono, à mão') e nunca rodaram (ultima_em NULL) -- 'backup diário' não é o comportamento padrão do "
    "sistema para nenhum inquilino.",
)
def test_periodicos_de_backup_por_inquilino_estao_ativos_por_padrao(conexao_plat_app):
    tenant_plataforma = _id_plataforma(conexao_plat_app)
    contexto(conexao_plat_app, tenant_plataforma, usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT tipo, ativa, ultima_em FROM plat.agenda WHERE tipo = ANY(%s) ORDER BY tipo",
            (list(TIPOS_BACKUP_POR_INQUILINO),),
        )
        linhas = {r["tipo"]: r for r in cur.fetchall()}
    faltando = [t for t in TIPOS_BACKUP_POR_INQUILINO if t not in linhas]
    assert not faltando, f"periódico(s) nunca sincronizados para o inquilino plataforma: {faltando}"
    inativos = [t for t, r in linhas.items() if not r["ativa"]]
    assert not inativos, f"periódico(s) de backup por inquilino continuam pausados por padrão: {inativos}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO (turno 9, adversário de linha L0, item L0-06-backup-status): "
    "app/jobs/agenda.py::sincronizar_periodicos só faz upsert no inquilino TÉCNICO `plataforma` -- um "
    "inquilino de cliente comum (`demo`) nunca ganha uma linha de backup.executar/backup.ensaio_restauracao "
    "em plat.agenda, ligada ou pausada. 'Backup por inquilino diário' (a hipótese do item) é "
    "arquiteturalmente impossível de automatizar hoje para qualquer inquilino além do técnico -- só o "
    "disparo manual (POST /api/jobs) alcança um inquilino de cliente.",
)
def test_inquilino_de_cliente_tem_periodico_de_backup_proprio(conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], usuario_id=0, login="teste")
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM plat.agenda WHERE tipo = ANY(%s)",
            (list(TIPOS_BACKUP_POR_INQUILINO),),
        )
        n = cur.fetchone()["n"]
    assert n == len(TIPOS_BACKUP_POR_INQUILINO), (
        f"inquilino de cliente `demo` tem {n}/{len(TIPOS_BACKUP_POR_INQUILINO)} periódicos de backup próprio "
        "em plat.agenda (esperado: um por tipo, como qualquer inquilino de verdade precisaria para ter "
        "'backup diário' automático)"
    )


def _id_plataforma(con):
    """Mesmo caminho de tests.api.test_rls.ids_por_slug (SECURITY DEFINER que vê além do inquilino), para o
    inquilino técnico -- que ids_por_slug não inclui (só varre demo/demo2)."""
    with con.cursor() as cur:
        cur.execute("SELECT tenant_id FROM plat.auth_login(%s, 'admin')", ("plataforma",))
        r = cur.fetchone()
        assert r is not None, "admin de plataforma não semeado (rode install.sh)"
        return r["tenant_id"]

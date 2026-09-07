"""Métricas que dão dado real às regras de `deploy/alertas.yml` (item L7-06-b-alertas): idade do job
mais antigo rodando e horas desde o último backup/drill. As famílias já existiam parcialmente cobertas
em test_metricas_rota.py; aqui o foco é a FONTE (plat.job/plat.backup_execucao), não a forma do texto."""

from tests.api.conftest import InquilinoTemporario


def _valor(texto: str, nome_metrica: str) -> float | None:
    for linha in texto.splitlines():
        if linha == nome_metrica or linha.startswith(f"{nome_metrica} ") or linha.startswith(f"{nome_metrica}{{"):
            return float(linha.rsplit(" ", 1)[1])
    return None


def test_jobs_rodando_mais_antigo_segundos_sobe_com_job_de_verdade(cliente, conexao_plat_app, sessao_plat):
    """Sem nenhum job rodando, a família existe e é >= 0; com um job marcado 'rodando' com iniciado_em de
    35 min atrás (o limiar do portão é 30 min), o valor exposto reflete essa idade de verdade. O inquilino
    é criado pela via de verdade (POST /api/plataforma/inquilinos, SECURITY DEFINER) — inserir direto em
    plat.tenant como plat_app esbarra na própria RLS que protege a tabela."""
    inq = InquilinoTemporario(sessao_plat)
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "INSERT INTO plat.job (tenant_id, tipo, parametros, estado, iniciado_em, executor, "
                "pesado, memoria_mb, timeout_s) "
                "VALUES (%s, 'teste_alerta', '{}'::jsonb, 'rodando', now() - interval '35 minutes', "
                "'local', false, 256, 60)",
                (inq.id,),
            )
        conexao_plat_app.commit()

        texto = cliente.get("/metrics").text
        idade = _valor(texto, "plat_jobs_rodando_mais_antigo_segundos")
        assert idade is not None
        assert idade >= 35 * 60 - 5, f"esperava >= ~2100s (35 min), achou {idade}"
    finally:
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.job WHERE tenant_id = %s AND tipo = 'teste_alerta'", (inq.id,))
        conexao_plat_app.commit()
        inq.apagar()


def test_backup_horas_desde_ultimo_reflete_registro_recente_e_atraso(cliente, conexao_plat_app):
    """plat.backup_registrar('backup', true) agora -> horas ~0; sem NENHUM registro de 'drill' na base de
    teste, a família fica no valor 'sem prazo' (999999) — que é maior que qualquer limiar do portão, ou
    seja, o alerta de drill dispararia (comportamento correto: drill nunca rodou)."""
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT plat.backup_registrar('backup', true, 'teste il706balert')")
    conexao_plat_app.commit()
    try:
        texto = cliente.get("/metrics").text
        assert 'plat_backup_horas_desde_ultimo{tipo="backup"}' in texto
        horas_backup = _valor(texto, 'plat_backup_horas_desde_ultimo{tipo="backup"}')
        assert horas_backup is not None and horas_backup < 0.05
        horas_drill = _valor(texto, 'plat_backup_horas_desde_ultimo{tipo="drill"}')
        assert horas_drill is not None and horas_drill >= 999_999 - 1
    finally:
        with conexao_plat_app.cursor() as cur:
            cur.execute("DELETE FROM plat.backup_execucao WHERE detalhe = 'teste il706balert'")
        conexao_plat_app.commit()

"""Métricas que dão dado real às regras de `deploy/alertas.yml` (item L7-06-b-alertas): idade do job
mais antigo rodando e horas desde o último backup/drill. As famílias já existiam parcialmente cobertas
em test_metricas_rota.py; aqui o foco é a FONTE (plat.job/plat.backup_execucao), não a forma do texto."""

import psycopg2

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.conftest import InquilinoTemporario


def _valor(texto: str, nome_metrica: str) -> float | None:
    for linha in texto.splitlines():
        if linha == nome_metrica or linha.startswith(f"{nome_metrica} ") or linha.startswith(f"{nome_metrica}{{"):
            return float(linha.rsplit(" ", 1)[1])
    return None


def test_jobs_rodando_mais_antigo_segundos_sobe_com_job_de_verdade(cliente, conexao_plat_app, sessao_plat, env):
    """Sem job rodando a família vale 0; com um job DE VERDADE em estado 'rodando' ela passa a contar a
    idade dele. É a métrica que alimenta a regra FilaComJobLongo de `deploy/alertas.yml`.

    Cada passo usa o caminho que o produto usa, e cada atalho tentado foi barrado pelo próprio banco —
    o que é o isolamento funcionando, não obstáculo do teste:
      · o inquilino nasce por POST /api/plataforma/inquilinos (SECURITY DEFINER); inserir em plat.tenant
        como plat_app esbarra na RLS da tabela;
      · o job nasce por INSERT de plat_app COM o contexto do inquilino na sessão (sem ele a política de
        RLS de plat.job recusa a linha) e SEMPRE em 'pendente' (gatilho plat.job_transicao: "job nasce
        pendente e sem resultado");
      · a passagem para 'rodando' é `plat.job_pegar` chamada pela conexão de plat_worker, exatamente
        como o worker faz: plat_app não tem UPDATE em plat.job nem EXECUTE nessa função, e um UPDATE
        cru pela conexão de plat_worker não enxergaria a linha (a política de RLS nomeia só plat_app,
        e quem não está em política nenhuma não vê nada) — a função é SECURITY DEFINER e por isso é o
        único caminho que funciona, que é o desenho pretendido.

    O limiar de 30 min da regra não é encenado aqui (seria esperar 30 min): ele é provado de duas outras
    formas — pelo caso determinístico de `deploy/alertas_teste.yml` e pela encenação de verdade de
    `deploy/alertas_homologacao.sh`, que backdata `iniciado_em` como o postgres e vê o alerta chegar ao
    canal (93,5 s medidos, `tests/medidas/L7-06-b-alertas.json`).
    """
    inq = InquilinoTemporario(sessao_plat)
    try:
        antes = _valor(cliente.get("/metrics").text, "plat_jobs_rodando_mais_antigo_segundos")
        assert antes is not None and antes >= 0

        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "SELECT set_config('plat.tenant_id', %s, false), set_config('plat.usuario_id', %s, false)",
                (str(inq.id), str(inq.admin_id)),
            )
            cur.execute(
                "INSERT INTO plat.job (tenant_id, tipo, parametros, executor, pesado, memoria_mb, "
                "timeout_s) VALUES (%s, 'teste_alerta', '{}'::jsonb, 'local', false, 256, 60)",
                (inq.id,),
            )
        conexao_plat_app.commit()

        worker = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente)
        try:
            with worker, worker.cursor() as cur:
                cur.execute("SELECT (plat.job_pegar('zt-worker-alertas', false)).id AS id")
                pego = cur.fetchone()["id"]
        finally:
            worker.close()
        assert pego is not None, "plat.job_pegar não pegou nenhum job pendente"

        # a função devolve segundos inteiros: um job recém-pego dá 0, que é indistinguível de "nenhum
        # job rodando". Dois segundos de espera no próprio banco separam os dois casos sem ambiguidade.
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT pg_sleep(2)")
            cur.execute("SELECT plat.fila_job_mais_antigo_rodando_segundos() AS v")
            do_banco = cur.fetchone()["v"]
        conexao_plat_app.commit()

        idade = _valor(cliente.get("/metrics").text, "plat_jobs_rodando_mais_antigo_segundos")
        assert idade is not None
        assert idade > 0, "com um job rodando há 2 s, a métrica não pode ser 0"
        assert idade < 300, f"o job acabou de começar; idade implausível: {idade}"
        # a métrica é a função, não um número paralelo: as duas leituras são do mesmo relógio
        assert abs(idade - do_banco) <= 3, (idade, do_banco)
    finally:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT set_config('plat.tenant_id', %s, false)", (str(inq.id),))
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

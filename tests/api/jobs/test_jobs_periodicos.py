"""Portão literal L0-05-d (achado do testador T3): só 3 periódicos estavam registrados (`app/jobs/periodicos.py`
somado a `app/catalogo/periodicos.py`) — o portão exige 5. Fechado com `jobs.sessoes_expurgar` (chamava
`plat.sessoes_expurgar()`, que já existia sem periódico nenhum) e `jobs.manutencao_analyze` (nova função SQL,
migração 026). Os testes aqui provam, para os 5 REGISTRADOS (não para tipos de prova avulsos): (1) cada um dispara
exatamente uma vez com 2 relógios concorrentes, no contexto do inquilino técnico `plataforma` (onde os periódicos
de verdade vivem — `jobs.expurgo` recusa fora dele, migração 006); (2) um periódico que falha não bloqueia nem
atrasa outro devido no mesmo instante, e cada um fica marcado (falhas_seguidas/ultimo_estado) independente do
outro."""

import datetime
import threading
import time

import psycopg2
import psycopg2.extras
import pytest

from app.jobs import agenda as mod_agenda
from app.jobs import tipos as _tipos  # noqa: F401 — importação agrega catalogo.* a PERIODICOS
from app.jobs.periodicos import PERIODICOS
from tests.api.jobs.conftest import esperar
from tests.api.jobs.test_jobs_agenda import _apagar

UTC = datetime.UTC


@pytest.fixture
def nome():
    return f"teste-periodico-{time.time_ns()}"


def _criar_com_parametros_exatos(cliente, nome, tipo, parametros, cron="*/15 * * * *"):
    """Como `test_jobs_agenda._criar`, mas SEM o `parametros or {default}`: aquele helper trocaria `{}` (os
    parâmetros reais de `jobs.sessoes_expurgar`/`jobs.expurgo`/`jobs.manutencao_analyze` em PERIODICOS) pelo
    default de teste `{"duracao_s": 0, "passos": 1}`, porque `{}` é falso em Python — o que mandaria um corpo
    diferente do que o periódico de verdade usa."""
    corpo = {"nome": nome, "tipo": tipo, "parametros": dict(parametros or {}), "cron": cron}
    return cliente.post("/api/agendas", json=corpo)


def _worker_estranho(fim: dict) -> bool:
    """Achado do testador T3 (ambiente compartilhado desta rodada): um SEGUNDO processo `python -m app.jobs.
    worker`, de OUTRO contêiner (uid diferente do nosso, fora do systemd, flagrado com `ps aux` durante esta
    verificação), às vezes vence a corrida pelo job e morre sem escrever nada no pipe do filho — o job termina
    'falhou' com `erro` genérico e SEM identidade de worker (o nosso sempre grava `<hostname>:<pid>` em
    `plat.job.worker`, migração 012). Nunca reproduzido quando o NOSSO worker pega o job (ver
    `laco/handoffs/T3/L0-05-bd-verificacao.md`). Só esta assinatura exata é tolerada com nova tentativa; qualquer
    outra falha reprova o teste de verdade."""
    return fim["estado"] == "falhou" and not fim.get("worker") and fim.get("erro") == "código de saída 1"


def _garantir_conclusao(cliente, agenda_id: str, job_id: str, tentativas_extra: int = 2) -> dict:
    """Espera o job terminar; se for exatamente a assinatura de `_worker_estranho`, tenta de novo via
    'rodar agora' (o mesmo periódico, nova execução) até `tentativas_extra` vezes antes de desistir."""
    fim = esperar(cliente, job_id, timeout=90)
    tentativas = 0
    while _worker_estranho(fim) and tentativas < tentativas_extra:
        tentativas += 1
        r = cliente.post(f"/api/agendas/{agenda_id}/rodar-agora")
        assert r.status_code == 201, r.text
        fim = esperar(cliente, r.json()["id"], timeout=90)
    return fim


def test_pelo_menos_cinco_periodicos_registrados_e_com_tipo_conhecido(cliente_plataforma):
    assert len(PERIODICOS) >= 5, PERIODICOS
    nomes = [p[0] for p in PERIODICOS]
    assert len(set(nomes)) == len(nomes), f"nomes de periódico repetidos: {nomes}"
    tipos_conhecidos = {t["nome"] for t in cliente_plataforma.get("/api/jobs/tipos").json()}
    for nome_p, cron, tipo, _parametros in PERIODICOS:
        assert tipo in tipos_conhecidos, f"periódico {nome_p!r} ({tipo}) não está em /api/jobs/tipos"
        assert len(cron.split()) == 5, f"periódico {nome_p!r}: cron {cron!r} sem 5 campos"


@pytest.mark.parametrize("indice", range(5))
def test_cada_periodico_registrado_dispara_uma_vez_com_dois_relogios(indice, cliente_plataforma, worker_vivo, env,
                                                                      nome):
    """Agenda de teste (nome e cron próprios, para não colidir com o periódico de verdade já sincronizado) com o
    MESMO tipo e os MESMOS parâmetros default do periódico real nº `indice`; dispara 1 ocorrência com 2 conexões
    concorrentes (papel do worker, 006) e confere: exatamente 1 job criado, terminado com sucesso."""
    nome_p, _cron_real, tipo, parametros = PERIODICOS[indice]
    r = _criar_com_parametros_exatos(cliente_plataforma, f"{nome}-{indice}", tipo, parametros)
    assert r.status_code == 201, r.text
    agenda = r.json()
    proxima = datetime.datetime.fromisoformat(agenda["proxima_em"].replace("Z", "+00:00"))
    cons = [psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=psycopg2.extras.RealDictCursor) for _ in range(2)]
    for c in cons:
        c.autocommit = True
    try:
        agora = proxima + datetime.timedelta(seconds=5)
        resultados: list = []

        def relogio(c, saida=resultados):
            saida.extend(mod_agenda.tick(c, agora))

        threads = [threading.Thread(target=relogio, args=(c,)) for c in cons]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        meus = cliente_plataforma.get("/api/jobs", params={"agenda_id": agenda["id"], "limite": 10}).json()["itens"]
        assert len(meus) == 1, f"periódico {nome_p!r} ({tipo}): {len(meus)} jobs com 2 relógios (ids {resultados})"
        fim = _garantir_conclusao(cliente_plataforma, agenda["id"], meus[0]["id"])
        assert fim["estado"] == "concluido", f"periódico {nome_p!r} ({tipo}) não concluiu: {fim.get('erro')}"
    finally:
        for c in cons:
            c.close()
        _apagar(cliente_plataforma, agenda["id"])


def test_periodico_que_falha_nao_bloqueia_nem_atrasa_outro_no_mesmo_instante(cliente_plataforma, worker_vivo, env,
                                                                              nome):
    ruim = _criar_com_parametros_exatos(cliente_plataforma, f"{nome}-ruim", "prova.falha",
                                        {"definitiva": True}).json()
    bom = _criar_com_parametros_exatos(cliente_plataforma, f"{nome}-bom", "prova.progresso",
                                       {"duracao_s": 0, "passos": 1}).json()
    proxima = datetime.datetime.fromisoformat(ruim["proxima_em"].replace("Z", "+00:00"))
    con = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=psycopg2.extras.RealDictCursor)
    con.autocommit = True
    try:
        for k in range(3):
            agora = proxima + datetime.timedelta(minutes=15 * k, seconds=5)
            mod_agenda.tick(con, agora)
            job_ruim = cliente_plataforma.get("/api/jobs", params={"agenda_id": ruim["id"], "limite": 5,
                                                                    "ordenar": "criado_em:desc"}).json()["itens"][0]
            job_bom = cliente_plataforma.get("/api/jobs", params={"agenda_id": bom["id"], "limite": 5,
                                                                   "ordenar": "criado_em:desc"}).json()["itens"][0]
            assert esperar(cliente_plataforma, job_ruim["id"], timeout=60)["estado"] == "falhou"
            fim_bom = _garantir_conclusao(cliente_plataforma, bom["id"], job_bom["id"])
            assert fim_bom["estado"] == "concluido", fim_bom.get("erro")
            a_ruim = cliente_plataforma.get(f"/api/agendas/{ruim['id']}").json()
            a_bom = cliente_plataforma.get(f"/api/agendas/{bom['id']}").json()
            assert a_ruim["falhas_seguidas"] == k + 1 and a_ruim["ultimo_estado"] == "falhou"
            # a agenda boa nunca é tocada pela falha da outra, mesmo disparando no mesmo tick
            assert a_bom["falhas_seguidas"] == 0 and a_bom["ultimo_estado"] == "concluido"
        assert a_ruim["ativa"] is True, "3 falhas ainda não pausam (o limite é 5); só prova isolamento, não pausa"
        assert a_bom["ativa"] is True
    finally:
        con.close()
        _apagar(cliente_plataforma, ruim["id"])
        _apagar(cliente_plataforma, bom["id"])


def test_rodar_agora_50_vezes_nunca_roda_2_com_a_mesma_chave_ao_mesmo_tempo(cliente_plataforma, worker_vivo, nome):
    """Refutação do portão L0-05-d: 'dispara rodar-agora 50 vezes (dedup por lock)'. `agenda_rodar_agora`
    (`app/jobs/servico.py`) cria uma linha nova de `plat.job` a cada chamada — não deduplica a FILA; quem
    deduplica é o `job_pegar` da 004 (achado do L0-05-a): nenhum job entra em 'rodando' enquanto outro da MESMA
    `chave` já estiver rodando. Prova estrutural sobre as 50 execuções terminadas: os intervalos
    [iniciado_em, terminado_em] nunca se sobrepõem entre si."""
    agenda = _criar_com_parametros_exatos(cliente_plataforma, f"{nome}-50x", "jobs.sessoes_expurgar", {}).json()
    try:
        ids = []
        for _ in range(50):
            r = cliente_plataforma.post(f"/api/agendas/{agenda['id']}/rodar-agora")
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        terminados = [_garantir_conclusao(cliente_plataforma, agenda["id"], jid) for jid in ids]
        for fim in terminados:
            assert fim["estado"] in ("concluido", "falhou"), fim
        intervalos = sorted(
            (datetime.datetime.fromisoformat(t["iniciado_em"].replace("Z", "+00:00")),
             datetime.datetime.fromisoformat(t["terminado_em"].replace("Z", "+00:00")))
            for t in terminados)
        for (_ini_a, fim_a), (ini_b, _fim_b) in zip(intervalos, intervalos[1:], strict=False):
            assert fim_a <= ini_b, f"execuções da mesma chave se sobrepuseram: {fim_a} > {ini_b}"
    finally:
        _apagar(cliente_plataforma, agenda["id"])

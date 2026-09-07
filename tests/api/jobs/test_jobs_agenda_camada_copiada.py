"""Item L6-02-k-agendamento: atualização agendada de camadas copiadas. Não é outro relógio — reusa o
mesmo mecanismo do L0-05 provado em `test_jobs_agenda.py` (`mod_agenda.tick`, "5 falhas seguidas pausam").
Portão LITERAL:
  - tarefa de 15 min roda 3 vezes em teste acelerado                 -> test_atualiza_tres_vezes_e_troca_atomica
  - 5 falhas pausam                                                  -> já provado em test_jobs_agenda.py; aqui
                                                                          só o ACRÉSCIMO (aviso por e-mail)
  - troca atômica provada (consulta nunca vê tabela vazia)           -> test_troca_atomica_sobrevive_a_rollback
  - tela 'Tarefas' lista                                             -> test_tipo_aparece_nos_tipos_e_na_listagem
  - teste                                                            -> este arquivo + a migração
"""

import datetime
import threading
import time

import psycopg2
import psycopg2.extras
import pytest

from app.jobs import agenda as mod_agenda
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (make homolog / bases por trilha)
from tests import jobs_sessao
from tests.api.jobs.conftest import esperar

UTC = datetime.UTC
URL_PUBLICA = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/35"  # dado aberto federal (IBGE)


@pytest.fixture
def nome():
    return f"teste-{time.time_ns()}"


def _criar_conexao_copiada(conexao_plat_app, tenant_id, usuario_id, url=URL_PUBLICA):
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
        cur.execute(
            "INSERT INTO plat.conexao(tenant_id, tipo, modo, nome, url, dono_id) "
            "VALUES (%s, 'http', 'copiada', %s, %s, %s) RETURNING id",
            (tenant_id, f"zt-camada-{time.time_ns()}", url, usuario_id),
        )
        cid = cur.fetchone()["id"]
    conexao_plat_app.commit()
    return str(cid)


def _apagar_conexao(conexao_plat_app, tenant_id, usuario_id, conexao_id):
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
        cur.execute("DELETE FROM plat.conexao WHERE id = %s::uuid", (conexao_id,))  # cascade: versao/atual
    conexao_plat_app.commit()


def _agenda(cliente, nome, tipo, parametros, cron="*/15 * * * *"):
    return cliente.post("/api/agendas", json={"nome": nome, "tipo": tipo, "parametros": parametros, "cron": cron})


def _ticar_e_esperar(cliente, con_worker, agenda_id, agendado_proxima, k, estado_esperado="concluido", timeout=90):
    criados_antes = {j["id"] for j in cliente.get(
        "/api/jobs", params={"agenda_id": agenda_id, "limite": 50}).json()["itens"]}
    mod_agenda.tick(con_worker, agendado_proxima + datetime.timedelta(minutes=15 * k, seconds=5))
    depois = cliente.get("/api/jobs", params={"agenda_id": agenda_id, "limite": 50}).json()["itens"]
    novos = [j for j in depois if j["id"] not in criados_antes]
    assert len(novos) == 1, f"ocorrência {k}: esperava 1 job novo, achou {len(novos)} ({novos})"
    return esperar(cliente, novos[0]["id"], estados=(estado_esperado,), timeout=timeout)


@pytest.mark.lento  # rede real (IBGE); mesmo pressuposto de tests/unit/test_conexao_seguranca.py
def test_atualiza_tres_vezes_e_troca_atomica(cliente_demo, worker_vivo, env, sessao_demo, conexao_plat_app, nome):
    """15 min, acelerado por `mod_agenda.tick` com instante injetado: 3 ocorrências, cada uma busca a URL
    pública de verdade, grava uma versão nova e troca o ponteiro — nunca mais de 1 versão sobra (poda)."""
    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    conexao_id = _criar_conexao_copiada(conexao_plat_app, tenant_id, usuario_id)
    r = _agenda(cliente_demo, nome, "conexao.atualizar_copia", {"conexao_id": conexao_id})
    assert r.status_code == 201, r.text
    agenda = r.json()
    proxima = datetime.datetime.fromisoformat(agenda["proxima_em"].replace("Z", "+00:00"))
    con = psycopg2.connect(env["PLAT_DSN_WORKER"], cursor_factory=CursorSchemaAmbiente)
    con.autocommit = True
    try:
        for k in range(3):
            fim = _ticar_e_esperar(cliente_demo, con, agenda["id"], proxima, k)
            assert fim["resultado"]["conexao_id"] == conexao_id
            assert fim["resultado"]["tamanho_bytes"] > 0
            with conexao_plat_app.cursor() as cur:
                jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
                cur.execute("SELECT versao_id FROM plat.camada_copia_atual WHERE conexao_id = %s::uuid", (conexao_id,))
                atual = cur.fetchone()
                assert atual is not None and atual["versao_id"] is not None, \
                    f"ocorrência {k}: camada sem ponteiro corrente (nunca pode ficar vazia)"
                cur.execute("SELECT count(*) AS n, sum(tamanho_bytes) AS bytes FROM plat.camada_copia_versao "
                            "WHERE conexao_id = %s::uuid", (conexao_id,))
                versoes = cur.fetchone()
                assert versoes["n"] == 1, f"ocorrência {k}: poda deveria manter só 1 versão, achou {versoes['n']}"
                assert versoes["bytes"] > 0
            conexao_plat_app.rollback()
        depois = cliente_demo.get(f"/api/agendas/{agenda['id']}").json()
        assert depois["ultimo_estado"] == "concluido" and depois["falhas_seguidas"] == 0
    finally:
        con.close()
        cliente_demo.delete(f"/api/agendas/{agenda['id']}")
        _apagar_conexao(conexao_plat_app, tenant_id, usuario_id, conexao_id)


def test_troca_atomica_sobrevive_a_rollback(env, sessao_demo, conexao_plat_app):
    """Refutação do item: 'adversário mata o worker no meio da troca: a camada antiga tem de continuar
    íntegra'. Simula a morte do worker por ROLLBACK da transação que chamaria `camada_copia_trocar` depois
    de já ter gravado a versão nova (o pior caso: a versão nova existe, só o ponteiro não trocou) — e prova,
    com uma SEGUNDA conexão lendo ao mesmo tempo, que o ponteiro NUNCA aparece nulo nem vazio."""
    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    conexao_id = _criar_conexao_copiada(conexao_plat_app, tenant_id, usuario_id)
    try:
        # versão 1: grava e troca (comitado) — é a "camada antiga" que tem de sobreviver
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("SELECT plat.camada_copia_versao_inserir(%s::uuid, 'http', %s) AS id",
                        (conexao_id, psycopg2.Binary(b"versao-1")))
            v1 = cur.fetchone()["id"]
            cur.execute("SELECT plat.camada_copia_trocar(%s::uuid, %s::uuid) AS anterior", (conexao_id, v1))
        conexao_plat_app.commit()

        leituras: list = []
        parar = threading.Event()

        def leitor():
            # autocommit=False e contexto() UMA vez só: `set_config(..., is_local=true)` vale só até o fim
            # da transação — com autocommit=True cada SELECT é a SUA PRÓPRIA transação e o contexto do
            # inquilino (RLS) reseta a cada volta, fazendo a política filtrar tudo (achado ao rodar este
            # teste: "linha is None" não era a camada vazia, era o inquilino não setado). READ COMMITTED já
            # garante que cada SELECT dentro desta MESMA transação aberta enxerga o que foi comitado até ali.
            con_leitor = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
            con_leitor.autocommit = False
            try:
                with con_leitor.cursor() as cur:
                    jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
                    while not parar.is_set():
                        cur.execute("SELECT versao_id FROM plat.camada_copia_atual WHERE conexao_id = %s::uuid",
                                    (conexao_id,))
                        leituras.append(cur.fetchone())
                        time.sleep(0.02)
            finally:
                con_leitor.close()

        t = threading.Thread(target=leitor)
        t.start()
        try:
            # "o worker": grava a versão 2 inteira, chama a troca, mas MORRE antes do commit (rollback)
            con_worker = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
            con_worker.autocommit = False
            try:
                with con_worker.cursor() as cur:
                    jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
                    cur.execute("SELECT plat.camada_copia_versao_inserir(%s::uuid, 'http', %s) AS id",
                                (conexao_id, psycopg2.Binary(b"versao-2-nunca-deveria-aparecer")))
                    v2 = cur.fetchone()["id"]
                    cur.execute("SELECT plat.camada_copia_trocar(%s::uuid, %s::uuid) AS anterior", (conexao_id, v2))
                    time.sleep(0.3)  # janela para o leitor concorrente passar por cima da troca em aberto
                con_worker.rollback()  # o worker morreu: nada do que fez acima existe
            finally:
                con_worker.close()
            time.sleep(0.1)
        finally:
            parar.set()
            t.join(timeout=5)

        assert leituras, "o leitor concorrente não chegou a rodar"
        for linha in leituras:
            assert linha is not None and linha["versao_id"] is not None, \
                "a consulta viu a camada sem ponteiro (vazia) durante a troca"
            assert str(linha["versao_id"]) == str(v1), \
                "a consulta viu uma versão que nunca foi comitada (o rollback do worker morto vazou)"

        # confirma no fim: a camada antiga (v1) continua íntegra, a v2 nunca existiu
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("SELECT versao_id FROM plat.camada_copia_atual WHERE conexao_id = %s::uuid", (conexao_id,))
            assert str(cur.fetchone()["versao_id"]) == str(v1)
            cur.execute("SELECT bytes FROM plat.camada_copia_versao WHERE id = %s::uuid", (v1,))
            assert bytes(cur.fetchone()["bytes"]) == b"versao-1"
            cur.execute("SELECT count(*) AS n FROM plat.camada_copia_versao WHERE conexao_id = %s::uuid", (conexao_id,))
            assert cur.fetchone()["n"] == 1, "a versão da transação que fez rollback não deveria ter sobrevivido"
        conexao_plat_app.rollback()
    finally:
        _apagar_conexao(conexao_plat_app, tenant_id, usuario_id, conexao_id)


def test_cinco_falhas_registram_aviso_com_throttle_de_6h(sessao_demo, conexao_plat_app):
    """Acréscimo deste item sobre o mecanismo já provado em test_jobs_agenda.py::test_cinco_falhas_seguidas_
    pausam_a_agenda: quando `plat.agenda_registrar_fim` pausa a agenda, grava 1 aviso pendente — e nunca um
    segundo dentro de 6h (throttle), mesmo que a agenda pause de novo."""
    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
        cur.execute(
            "INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, ativa, proxima_em) "
            "VALUES (%s, %s, %s, 'prova.falha', '{}', '*/15 * * * *', true, now()) RETURNING id",
            (tenant_id, usuario_id, f"zt-aviso-{time.time_ns()}"),
        )
        agenda_id = cur.fetchone()["id"]
    conexao_plat_app.commit()
    try:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            for _ in range(5):
                cur.execute("SELECT plat.agenda_registrar_fim(gen_random_uuid(), %s::uuid, 'falhou')", (agenda_id,))
            cur.execute("SELECT ativa, falhas_seguidas FROM plat.agenda WHERE id = %s::uuid", (agenda_id,))
            a = cur.fetchone()
            assert a["ativa"] is False and a["falhas_seguidas"] == 5
            cur.execute("SELECT id, enviado_em, motivo FROM plat.agenda_aviso WHERE agenda_id = %s::uuid", (agenda_id,))
            avisos = cur.fetchall()
            assert len(avisos) == 1, f"esperava 1 aviso pendente, achou {len(avisos)}"
            assert avisos[0]["enviado_em"] is None and "5 falhas" in avisos[0]["motivo"]

            # pausa "de novo" (ex.: reativada e falhou outra vez) dentro da janela de 6h: sem 2º aviso
            cur.execute("SELECT plat.agenda_registrar_fim(gen_random_uuid(), %s::uuid, 'falhou')", (agenda_id,))
            cur.execute("SELECT count(*) AS n FROM plat.agenda_aviso WHERE agenda_id = %s::uuid", (agenda_id,))
            assert cur.fetchone()["n"] == 1, "throttle de 6h não pode deixar 2 avisos passarem"
        conexao_plat_app.commit()
    finally:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("DELETE FROM plat.agenda WHERE id = %s::uuid", (agenda_id,))  # cascade: agenda_aviso
        conexao_plat_app.commit()


def test_avisos_enviar_enfileira_correio_para_o_dono_com_email(
    cliente_demo, worker_vivo, conexao_plat_app, sessao_demo, nome
):
    """`agenda.avisos_enviar` drena `plat.agenda_aviso` e enfileira `correio.enviar` (somente_sistema) para
    o e-mail do dono; marca `enviado_em` mesmo se o SMTP não estiver configurado no inquilino de teste (o
    que importa aqui é o ENFILEIRAMENTO, não a entrega — entrega é de app/correio/tarefas.py, já testado)."""
    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
        cur.execute("SELECT email FROM plat.usuario WHERE id = %s", (usuario_id,))
        email_original = cur.fetchone()["email"]
        cur.execute("UPDATE plat.usuario SET email = 'zt-aviso@example.org' WHERE id = %s", (usuario_id,))
        cur.execute(
            "INSERT INTO plat.agenda(tenant_id, usuario_id, nome, tipo, parametros, cron, ativa, falhas_seguidas) "
            "VALUES (%s, %s, %s, 'prova.falha', '{}', '*/15 * * * *', false, 5) RETURNING id",
            (tenant_id, usuario_id, f"zt-aviso-envio-{time.time_ns()}"),
        )
        agenda_id = cur.fetchone()["id"]
        cur.execute("SELECT plat.agenda_aviso_registrar(%s::uuid, 'teste direto') AS id", (agenda_id,))
        aviso_id = cur.fetchone()["id"]
    conexao_plat_app.commit()
    try:
        r = cliente_demo.post("/api/jobs", json={"tipo": "agenda.avisos_enviar", "parametros": {}})
        assert r.status_code == 201, r.text
        fim = esperar(cliente_demo, r.json()["id"], timeout=60)
        assert fim["estado"] == "concluido", fim
        assert fim["resultado"]["enviados"] >= 1

        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("SELECT enviado_em FROM plat.agenda_aviso WHERE id = %s", (aviso_id,))
            assert cur.fetchone()["enviado_em"] is not None
            cur.execute(
                "SELECT parametros FROM plat.job WHERE tenant_id = %s AND tipo = 'correio.enviar' "
                "AND parametros->>'categoria' = 'aviso_agenda_pausada' ORDER BY criado_em DESC LIMIT 1",
                (tenant_id,),
            )
            job_correio = cur.fetchone()
            assert job_correio is not None, "correio.enviar não foi enfileirado pelo aviso"
            assert job_correio["parametros"]["destinatario"] == "zt-aviso@example.org"
        conexao_plat_app.rollback()
    finally:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("UPDATE plat.usuario SET email = %s WHERE id = %s", (email_original, usuario_id))
            cur.execute("DELETE FROM plat.agenda WHERE id = %s::uuid", (agenda_id,))
        conexao_plat_app.commit()


def test_teto_de_agendas_ativas_por_usuario(cliente_demo, sessao_demo, conexao_plat_app, nome):
    """Esri publica 10 tarefas ativas por usuário (e 50 por organização, já coberto por
    test_cota_de_agendas_413_e_rls). Aqui o teto é rebaixado por config, mesma técnica daquele teste, para
    não depender de quantas agendas outros testes já deixaram."""
    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    with conexao_plat_app.cursor() as cur:
        jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
        cur.execute("SELECT plat.agendas_ativas_usuario(%s) AS n", (usuario_id,))
        existentes = cur.fetchone()["n"]
        cur.execute("UPDATE plat.tenant SET config = config || jsonb_build_object('cota_agendas_usuario', %s) "
                    "WHERE id = %s", (existentes + 1, tenant_id))
    conexao_plat_app.commit()
    criada = None
    try:
        r = _agenda(cliente_demo, nome, "prova.progresso", {"duracao_s": 0, "passos": 1})
        assert r.status_code == 201, r.text
        criada = r.json()
        r2 = _agenda(cliente_demo, nome + "-2", "prova.progresso", {"duracao_s": 0, "passos": 1})
        assert r2.status_code == 413 and r2.json()["erro"] == "cota_agendas_usuario", r2.text
    finally:
        with conexao_plat_app.cursor() as cur:
            jobs_sessao.contexto(cur, tenant_id, usuario_id, "admin")
            cur.execute("UPDATE plat.tenant SET config = config - 'cota_agendas_usuario' WHERE id = %s", (tenant_id,))
        conexao_plat_app.commit()
        if criada:
            cliente_demo.delete(f"/api/agendas/{criada['id']}")


def test_tipo_aparece_nos_tipos_e_agenda_na_listagem_de_tarefas(cliente_demo, sessao_demo, conexao_plat_app, nome):
    """A tela 'Tarefas' (web/tarefas.html) lista `GET /api/agendas` e monta o formulário a partir de
    `GET /api/jobs/tipos` — os dois têm de conhecer `conexao.atualizar_copia`."""
    tipos = {t["nome"]: t for t in cliente_demo.get("/api/jobs/tipos").json()}
    assert "conexao.atualizar_copia" in tipos
    schema = tipos["conexao.atualizar_copia"]["parametros_schema"]
    assert "conexao_id" in schema.get("properties", {})
    assert "conexao_id" in schema.get("required", [])
    assert "agenda.avisos_enviar" in tipos

    tenant_id, usuario_id = sessao_demo[1], sessao_demo[2]
    conexao_id = _criar_conexao_copiada(conexao_plat_app, tenant_id, usuario_id)
    r = _agenda(cliente_demo, nome, "conexao.atualizar_copia", {"conexao_id": conexao_id})
    assert r.status_code == 201, r.text
    agenda = r.json()
    try:
        lista = cliente_demo.get("/api/agendas", params={"tipo": "conexao.atualizar_copia"}).json()
        assert any(a["id"] == agenda["id"] for a in lista["itens"])
    finally:
        cliente_demo.delete(f"/api/agendas/{agenda['id']}")
        _apagar_conexao(conexao_plat_app, tenant_id, usuario_id, conexao_id)

"""Ataque adversarial G3 — fila, cancelamento, periódicos e tela de tarefas (itens L0-05-a-fila-postgres,
L0-05-b-progresso-cancelamento, L0-05-c-tela-tarefas, L0-05-d-periodicos, L0-05-e-worker-em-container).
Cada teste é uma cláusula LITERAL do portão de pronto ou da refutação. `xfail(strict=True)`: vira prova
quando alguém consertar."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

from app.schema_ambiente import CursorSchemaAmbiente
from tests.api.test_rls import contexto, ids_por_slug

LACO = Path("/home/dev/plataforma/laco/estado.json")


@pytest.fixture
def con_pg(env):
    con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
    try:
        yield con
    finally:
        con.rollback()
        con.close()


def _postgres(sql: str) -> str:
    """Roda SQL como superusuário no schema da trilha (o job_pegar exige papel de worker)."""
    import subprocess
    esquema = os.environ.get("PLAT_SCHEMA", "plat")
    r = subprocess.run(["sudo", "-u", "postgres", "psql", "-d", os.environ.get("PLAT_DB", "iagro_sat"),
                        "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
                        f"SET search_path = {esquema}, public; " + sql],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # psql -A -t ainda ecoa o rótulo de comando (SET/BEGIN/INSERT 0 1/ROLLBACK): só as linhas de RESULTADO
    ruido = re.compile(r"^(SET|BEGIN|COMMIT|ROLLBACK|DO|CREATE .*|SELECT \d+|INSERT \d+ \d+|UPDATE \d+|DELETE \d+)$")
    return "\n".join(ln for ln in r.stdout.splitlines() if ln.strip() and not ruido.match(ln.strip()))


# ---------------------------------------------------------------- L0-05-a: isolamento entre inquilinos
@pytest.mark.xfail(strict=True, reason="L0-05-a: a chave do lock e global; um inquilino congela o job de outro")
def test_lock_por_chave_nao_atravessa_inquilino():
    """Hipótese do L0-05-a: 'lock por chave (mesma camada não importa duas vezes ao mesmo tempo)'. O recurso
    que a chave protege é do INQUILINO; a chave, não. Um inquilino que use a mesma chave de outro congela o
    job do outro pelo tempo do seu (prova.progresso aceita `chave` livre do usuário, timeout_s=7200)."""
    saida = _postgres("""
      BEGIN;
      UPDATE job SET agendado_para = now() + interval '1 day' WHERE estado = 'pendente';
      INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
        SELECT id, 'zadv3.A', 'X', false, 128, 7200 FROM tenant WHERE slug = 'demo';
      INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
        SELECT id, 'zadv3.B', 'X', false, 128, 7200 FROM tenant WHERE slug = 'demo2';
      SELECT (job_pegar('adv3:1', true)).tipo;
      SELECT coalesce((job_pegar('adv3:2', true)).tipo, 'NENHUM');
      ROLLBACK;""")
    linhas = [ln for ln in saida.splitlines() if ln.strip()]
    assert linhas[-1] != "NENHUM", (
        "o job do inquilino B ficou impedido pela chave em uso pelo inquilino A "
        f"(saída do psql: {linhas})")


@pytest.mark.xfail(
    strict=True,
    reason="L0-05-a: ordenacao global e prioridade 1..9 livre ao usuario; sem justica entre inquilinos",
)
def test_fila_serve_o_inquilino_que_chegou_primeiro():
    """Refutação do L0-05-a: 'enfileira 10 mil jobs e mede se a API continua respondendo'. O ponto que a
    fila não cobre é a JUSTIÇA: a ordenação é global (prioridade, agendado_para, criado_em) e a prioridade
    1..9 é livre a qualquer usuário (app/jobs/servico.py::criar). Um inquilino atrasa o outro sem limite."""
    saida = _postgres("""
      BEGIN;
      UPDATE job SET agendado_para = now() + interval '1 day' WHERE estado = 'pendente';
      INSERT INTO job(tenant_id, tipo, prioridade, pesado, memoria_mb, timeout_s)
        SELECT id, 'zadvA.espera', 5, false, 128, 60 FROM tenant WHERE slug = 'demo';
      INSERT INTO job(tenant_id, tipo, prioridade, pesado, memoria_mb, timeout_s)
        SELECT t.id, 'zadvB.fura-fila', 1, false, 128, 60 FROM tenant t, generate_series(1,20)
        WHERE t.slug = 'demo2';
      CREATE TEMP TABLE ordem(posicao int, tipo text);
      DO $$DECLARE j job; i int; pos int := 0; BEGIN
        FOR i IN 1..21 LOOP
          j := job_pegar('adv3:1vaga', true); EXIT WHEN j.id IS NULL; pos := pos + 1;
          INSERT INTO ordem VALUES (pos, j.tipo);
          PERFORM job_terminar(j.id, 'adv3:1vaga', 'concluido', NULL, NULL, NULL);
        END LOOP; END$$;
      SELECT posicao FROM ordem WHERE tipo = 'zadvA.espera';
      ROLLBACK;""")
    posicao = int([ln for ln in saida.splitlines() if ln.strip()][-1])
    assert posicao == 1, (f"o inquilino A criou o job PRIMEIRO e foi servido na posição {posicao} de 21: "
                          "20 jobs criados depois, por outro inquilino, com prioridade 1, passaram na frente")


@pytest.mark.xfail(
    strict=True,
    reason="L0-05-d: as chaves dos periodicos sao constantes e qualquer inquilino pode ocupa-las",
)
def test_periodico_da_plataforma_nao_e_travado_por_chave_escolhida_por_inquilino():
    """As chaves dos periódicos são CONSTANTES no código ('sessoes_expurgar', 'manutencao_analyze', …,
    app/jobs/periodicos.py). Um usuário 'editor' de qualquer inquilino pode enfileirar prova.progresso com
    essa chave (duracao_s até 3600) e impedir o expurgo de sessões vencidas enquanto o dele roda."""
    saida = _postgres("""
      BEGIN;
      UPDATE job SET agendado_para = now() + interval '1 day' WHERE estado = 'pendente';
      INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
        SELECT id, 'prova.progresso', 'sessoes_expurgar', false, 256, 7200 FROM tenant WHERE slug = 'demo';
      INSERT INTO job(tenant_id, tipo, chave, pesado, memoria_mb, timeout_s)
        SELECT id, 'jobs.sessoes_expurgar', 'sessoes_expurgar', false, 256, 600 FROM tenant WHERE slug = 'plataforma';
      SELECT (job_pegar('adv3:1', true)).tipo;
      SELECT coalesce((job_pegar('adv3:2', true)).tipo, 'NENHUM');
      ROLLBACK;""")
    linhas = [ln for ln in saida.splitlines() if ln.strip()]
    assert linhas[-1] == "jobs.sessoes_expurgar", (
        "o periódico do inquilino técnico ficou impedido pela chave escolhida por um inquilino comum: "
        f"{linhas}")


# ---------------------------------------------------------------- L0-05-a: traceback saneado
@pytest.mark.xfail(
    strict=True,
    reason="L0-05-a: filho.py grava traceback.format_exception() cru em plat.job_log; nao ha saneamento",
)
def test_traceback_do_job_que_falhou_e_saneado(cliente, sessao_a):
    """Portão literal do L0-05-a: 'job com exceção é retentado 3 vezes ... e termina falhou com o traceback
    SANEADO'. app/jobs/filho.py grava traceback.format_exception() inteiro em plat.job_log."""
    r = sessao_a.post("/api/jobs", json={"tipo": "prova.falha", "parametros": {}})
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    fim = time.monotonic() + 90
    estado = None
    while time.monotonic() < fim:
        estado = sessao_a.get(f"/api/jobs/{jid}").json()["estado"]
        if estado in ("concluido", "falhou", "cancelado"):
            break
        time.sleep(0.3)
    assert estado == "falhou", f"job terminou em {estado}"
    linhas = sessao_a.get(f"/api/jobs/{jid}/log?limite=2000").json()["linhas"]
    texto = "\n".join(ln["mensagem"] for ln in linhas)
    vazamentos = [p for p in ("/home/dev/plataforma", "site-packages", "venv/lib") if p in texto]
    assert not vazamentos, (f"o log do job devolvido pela API expõe o caminho absoluto do servidor "
                            f"{vazamentos}; trecho: ...{texto[max(0, texto.find(vazamentos[0]) - 60):][:220]}...")


# ---------------------------------------------------------------- L0-05-b: estados finais imutáveis
@pytest.mark.xfail(strict=True, reason="L0-05-b: job_estado_final_imutavel nao cobre plat.job_log nem linhas_log")
def test_log_do_job_nao_aceita_linha_depois_do_estado_final(con_pg, env):
    """Hipótese do L0-05-b: 'estados finais imutáveis'. O gatilho job_estado_final_imutavel congela estado/
    progresso/erro, mas NÃO `linhas_log`, e plat.job_log não checa o estado do job: um filho perdido segue
    escrevendo no log de um job já falhou/cancelado (e o contador do job sobe)."""
    ids = ids_por_slug(con_pg)
    with con_pg.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(con_pg, ids["demo"], usuario_id=adm, login="admin")
    with con_pg.cursor() as cur:
        cur.execute("SELECT id, linhas_log FROM plat.job WHERE estado IN ('concluido','falhou','cancelado') "
                    "ORDER BY terminado_em DESC LIMIT 1")
        r = cur.fetchone()
        if r is None:
            pytest.skip("nenhum job em estado final nesta base ainda")
        jid, antes = r["id"], r["linhas_log"]
        erro = None
        try:
            cur.execute("INSERT INTO plat.job_log(job_id, tenant_id, nivel, mensagem) "
                        "VALUES (%s, plat.tenant_atual(), 'ERRO', 'linha escrita DEPOIS do estado final')",
                        (jid,))
        except psycopg2.Error as e:
            erro = type(e).__name__
        con_pg.rollback()
    assert erro is not None, (f"o banco aceitou uma linha de log no job {jid} já em estado final "
                              f"(linhas_log era {antes})")


# ---------------------------------------------------------------- L0-05-b: limite de conexões SSE
@pytest.mark.xfail(
    strict=True,
    reason="L0-05-b refutacao: _por_usuario e contador em memoria do processo e a unidade sobe --workers 2",
)
def test_limite_de_conexoes_sse_vale_para_a_instalacao_e_nao_por_processo():
    """Refutação literal do L0-05-b: 'abre 200 conexões SSE no mesmo job (limite por usuário ...)'. O contador
    é um dicionário em memória do processo (app/jobs/eventos.py `_por_usuario`), e a unidade roda uvicorn com
    --workers 2: o limite real por usuário é 2x o publicado."""
    from app.jobs import eventos
    unidade = Path("deploy/plat-api.service").read_text(encoding="utf-8")
    m = re.search(r"--workers\s+(\d+)", unidade)
    processos = int(m.group(1)) if m else 1
    efetivo = eventos.POR_USUARIO_MAX * processos
    assert efetivo == eventos.POR_USUARIO_MAX, (
        f"POR_USUARIO_MAX={eventos.POR_USUARIO_MAX} é por processo e a unidade sobe {processos} processos: "
        f"o limite real por usuário é {efetivo}")


# ---------------------------------------------------------------- L0-05-e: portão nunca escrito
@pytest.mark.xfail(
    strict=True,
    reason="L0-05-e: item marcado entregue com o portao ainda no texto 'portao a fixar pelo arquiteto'",
)
def test_portao_do_worker_em_container_foi_fixado_antes_de_construir():
    """O próprio portão do L0-05-e diz: 'portão a fixar pelo arquiteto no turno em que o item que a pediu
    entrar (registrar aqui antes de construir)'. O item está marcado ENTREGUE com o portão ainda em branco."""
    if not LACO.exists():
        pytest.skip("estado.json fora de alcance")
    estado = json.loads(LACO.read_text(encoding="utf-8"))
    item = next(i for i in estado["backlog"] if i["id"] == "L0-05-e-worker-em-container")
    portao = item["portao_de_pronto"]
    assert "a fixar" not in portao and "registrar aqui antes de construir" not in portao, \
        f"item em estado '{item['estado']}' com portão não escrito: {portao!r}"

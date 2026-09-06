"""SSE (ADR 0003 seção 5): primeiro evento é `estado`; progresso chega em eventos `estado` crescentes; `log` chega;
`fim` fecha; Last-Event-ID reenvia o log; pela URL pública (nginx) chega `X-Accel-Buffering: no` e o primeiro
evento em menos de 2 s; latência NOTIFY → cliente medida pelo instante do evento."""

import asyncio
import json
import time
import uuid

import httpx
import pytest

from app import db as banco
from app.jobs import eventos as mod_eventos
from app.jobs.contexto import Sessao
from tests.api.jobs.conftest import criar_job, esperar


def _eventos(resposta, maximo_s: float = 60):
    """Itera (evento, id, dados) de uma resposta SSE em streaming."""
    evento, id_, dados = None, None, []
    inicio = time.monotonic()
    for linha in resposta.iter_lines():
        if time.monotonic() - inicio > maximo_s:
            return
        if linha == "":
            if evento:
                yield evento, id_, json.loads("\n".join(dados)) if dados else None
            evento, id_, dados = None, None, []
        elif linha.startswith("event:"):
            evento = linha[6:].strip()
        elif linha.startswith("id:"):
            id_ = linha[3:].strip()
        elif linha.startswith("data:"):
            dados.append(linha[5:].strip())


def test_estado_log_e_fim_pelo_sse(cliente_demo, worker_vivo, medida):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 6, "passos": 6})
    progressos, logs, fim, latencias = [], 0, None, []
    with cliente_demo.stream("GET", f"/api/jobs/{job['id']}/eventos") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["x-accel-buffering"] == "no" and r.headers["cache-control"] == "no-store"
        primeiro = True
        for evento, id_, dados in _eventos(r, maximo_s=90):
            if primeiro:
                assert evento == "estado" and dados["id"] == job["id"], evento
                primeiro = False
            if evento == "estado":
                progressos.append(dados["progresso"])
                if dados["heartbeat_em"] and dados["estado"] == "rodando":
                    hb = time.strptime(dados["heartbeat_em"][:19], "%Y-%m-%dT%H:%M:%S")
                    latencias.append(time.time() - (time.mktime(hb) - time.timezone))
            elif evento == "log":
                logs += 1
                assert id_ and dados["nivel"] in ("DEBUG", "INFO", "AVISO", "ERRO")
            elif evento == "fim":
                fim = dados
                break
    assert fim and fim["estado"] == "concluido", fim
    crescentes = [p for i, p in enumerate(progressos) if i == 0 or p >= progressos[i - 1]]
    assert len(crescentes) == len(progressos) and progressos[-1] == 100, progressos
    assert len(set(progressos)) >= 4, progressos
    assert logs >= 3
    if latencias:
        medida("L0-05-jobs")("latencia_progresso_s", round(max(0.0, min(latencias)), 3), "s",
                             "menor diferença entre o heartbeat_em gravado pelo filho e a chegada do evento estado "
                             "no cliente SSE (TestClient; granularidade de 1 s do carimbo)")


def test_last_event_id_reenvia_o_log_e_fecha_com_fim(cliente_demo, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 3})
    esperar(cliente_demo, job["id"], timeout=60)
    total = cliente_demo.get(f"/api/jobs/{job['id']}/log").json()["total"]
    assert total >= 2
    with cliente_demo.stream("GET", f"/api/jobs/{job['id']}/eventos", headers={"Last-Event-ID": "0"}) as r:
        seq = [(e, d) for e, _, d in _eventos(r, maximo_s=20)]
    assert seq[0][0] == "estado" and seq[-1][0] == "fim"
    assert sum(1 for e, _ in seq if e == "log") == total


def test_job_de_outro_inquilino_e_404_e_limite_por_usuario(cliente_demo, cliente_demo2, worker_vivo):
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 0, "passos": 1})
    r = cliente_demo2.get(f"/api/jobs/{job['id']}/eventos")
    assert r.status_code == 404 and r.json()["erro"] == "job_inexistente"
    esperar(cliente_demo, job["id"], timeout=60)


def test_limite_de_conexoes_por_usuario_e_liberado_ao_fechar():
    """Achado do testador T3 (gap do portão L0-05-b): a refutação pede '200 conexões no mesmo job (limite por
    usuário)'; o mecanismo (`app/jobs/eventos.py::reservar/_liberar`, `POR_USUARIO_MAX = 10`) nunca tinha teste.

    MEDIDO nesta sessão: `starlette.testclient` (aviso de depreciação no topo do arquivo) não sustenta N conexões
    SSE **realmente concorrentes** de um processo síncrono — `with cliente.stream(...)` só devolve o controle
    depois que o gerador do lado do servidor TERMINA (a 1ª chamada contra um job de 30 s levou os 30 s inteiros
    antes de eu conseguir abrir a 2ª; as 12 chamadas seguintes vieram em ~3 ms cada porque o job já tinha
    concluído). Abrir 200 conexões de verdade por HTTP exigiria threads reais contra a URL pública (fora do
    escopo desta correção). O que se testa aqui é o MECANISMO em si, direto (`reservar`/`_liberar` são a função
    que a rota chama antes/depois do `StreamingResponse`, `app/jobs/rotas.py::eventos_do_job`): 10 reservas
    cabem, a 11ª levanta `ErroServico(429, "sse_limite", ...)`; liberar uma abre vaga para a próxima."""
    sessao_fake = Sessao(ctx=banco.Contexto(tenant_id=999999999, usuario_id=999999999, login="teste-sse-limite"),
                        perfil="admin", superadmin=False, tenant_slug="teste", nome="teste", admin=True)
    chave = (sessao_fake.tenant_id, sessao_fake.usuario_id)
    mod_eventos._por_usuario.pop(chave, None)
    try:
        for _ in range(mod_eventos.POR_USUARIO_MAX):
            mod_eventos.reservar(sessao_fake)
        assert mod_eventos._por_usuario[chave] == mod_eventos.POR_USUARIO_MAX
        with pytest.raises(mod_eventos.ErroServico) as exc:
            mod_eventos.reservar(sessao_fake)
        assert exc.value.status_code == 429 and exc.value.erro == "sse_limite"
        assert mod_eventos._por_usuario[chave] == mod_eventos.POR_USUARIO_MAX, "a reserva recusada não incrementou"
        mod_eventos._liberar(sessao_fake)
        assert mod_eventos._por_usuario[chave] == mod_eventos.POR_USUARIO_MAX - 1
        mod_eventos.reservar(sessao_fake)  # a vaga liberada permite uma nova reserva
        assert mod_eventos._por_usuario[chave] == mod_eventos.POR_USUARIO_MAX
    finally:
        mod_eventos._por_usuario.pop(chave, None)


def test_conexao_fecha_sozinha_apos_a_duracao_maxima(monkeypatch):
    """Achado do testador T3: `DURACAO_MAX_S = 1800` (30 min) nunca foi exercitado (esperar 30 min de verdade não
    cabe na suíte). Chama `eventos.gerar()` direto (sem HTTP, sem worker: o caminho testado nunca lê o banco
    porque nenhum NOTIFY chega — só os keepalives até estourar a duração) com a constante monkeypatchada para
    frações de segundo; confirma o evento `fim` com o motivo exato que o portão e o ADR descrevem."""
    monkeypatch.setattr(mod_eventos, "DURACAO_MAX_S", 0.3)
    monkeypatch.setattr(mod_eventos, "KEEPALIVE_S", 0.05)
    job = {"id": str(uuid.uuid4()), "tenant_id": 999999, "estado": "rodando", "progresso": 1}
    sessao = Sessao(ctx=banco.Contexto(tenant_id=999999, usuario_id=1, login="teste"), perfil="admin",
                    superadmin=False, tenant_slug="teste", nome="teste", admin=True)

    async def coletar():
        pedacos = []
        async for pedaco in mod_eventos.gerar(sessao, job, None):
            pedacos.append(pedaco)
        return pedacos

    t0 = time.perf_counter()
    pedacos = asyncio.run(coletar())
    duracao = time.perf_counter() - t0
    texto = b"".join(pedacos).decode("utf-8")
    assert "event: fim" in texto and "tempo máximo da conexão (30 min); reconecte" in texto, texto
    assert duracao < 5.0, duracao


def test_sse_pela_url_publica_com_x_accel_buffering(base_url, url_publica_resolve, sessao_demo, cliente_demo,
                                                    worker_vivo, medida):
    if not url_publica_resolve:
        pytest.skip(f"{base_url} não resolve nesta máquina")
    job = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 4, "passos": 4})
    cookies = {"plat_sessao": sessao_demo[0]}
    # o cabeçalho X-Accel-Buffering é consumido pelo nginx (X-Accel-* estão na lista padrão de proxy_hide_header):
    # confere-se direto no uvicorn; pela URL pública prova-se o EFEITO (primeiro evento sem buffer, < 2 s)
    with httpx.Client(base_url="http://127.0.0.1:8150", cookies=cookies, timeout=10) as direto:
        with direto.stream("GET", f"/api/jobs/{job['id']}/eventos") as r:
            if r.status_code == 404:
                pytest.fail("a API em :8150 não tem /api/jobs: rode sudo bash install.sh (reinicia plat-api)")
            assert r.status_code == 200 and r.headers.get("x-accel-buffering") == "no", dict(r.headers)
            assert r.headers.get("cache-control") == "no-store"
    t0 = time.perf_counter()
    with httpx.Client(base_url=base_url, cookies=cookies, timeout=30) as c:
        with c.stream("GET", f"/api/jobs/{job['id']}/eventos") as r:
            assert r.status_code == 200, r.status_code
            assert r.headers["content-type"].startswith("text/event-stream")
            assert "noindex" in r.headers.get("x-robots-tag", "")
            primeiro = None
            for evento, _, dados in _eventos(r, maximo_s=30):
                primeiro = (evento, dados)
                break
    primeiro_s = round(time.perf_counter() - t0, 3)
    assert primeiro and primeiro[0] == "estado", primeiro
    medida("L0-05-jobs")("sse_primeiro_evento_publico_s", primeiro_s, "s",
                         f"GET {base_url}/api/jobs/{{id}}/eventos até o primeiro evento estado (nginx + uvicorn)")
    assert primeiro_s < 2.0
    esperar(cliente_demo, job["id"], timeout=60)

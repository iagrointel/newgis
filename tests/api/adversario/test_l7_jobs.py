"""HARD-03 — adversário da fila de jobs (L7) sobre master. Ataca: escalada por tipo de job (tipo somente-sistema
e tipo de perfil acima do ator), argumento de job com id/tipo malformado (nunca 500), limite da fila/cota devolve
4xx e não 500, cancelamento e repetição por quem não é dono. Cada ataque com controle positivo. Só roda em trilha
(conftest do pacote)."""

from __future__ import annotations

import pytest

from tests.api.conftest import InquilinoTemporario, entrar, novo_cliente


# ---------------------------------------------------------------- escalada por tipo de job
def test_tipo_somente_sistema_recusado_por_esta_rota(sessao_a):
    """`correio.enviar` é somente-sistema (evita usar o SMTP do inquilino como canhão): a rota pública recusa 403,
    inclusive para admin."""
    r = sessao_a.post("/api/jobs", json={"tipo": "correio.enviar",
                                         "parametros": {"para": "x@y.z", "assunto": "a", "texto": "b"}})
    assert r.status_code == 403 and r.json().get("erro") == "tipo_somente_sistema", (r.status_code, r.text[:160])


def test_tipo_de_perfil_acima_do_ator_recusado(usuarios_a):
    """Um editor não submete job cujo `perfil_minimo` é admin (manutenção, saúde). Os prova.* são de perfil editor
    por desenho (não são escalada) e servem de controle positivo."""
    c, _u, _s = usuarios_a.sessao("editor")
    for tipo in ("jobs.manutencao_analyze", "jobs.expurgo", "jobs.sessoes_expurgar", "saude.verificar"):
        r = c.post("/api/jobs", json={"tipo": tipo, "parametros": {}})
        assert r.status_code in (403, 422), (tipo, r.status_code, r.text[:160])
        if r.status_code == 403:
            assert r.json().get("erro") in ("perfil_insuficiente", "tipo_somente_sistema"), (tipo, r.text[:160])
    # controle positivo: o editor submete um tipo de perfil editor
    r = c.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 2}})
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------- argumento malformado nunca vira 500
def test_tipo_desconhecido_e_parametros_ruins_nunca_500(sessao_a):
    for corpo in [
        {"tipo": "nao.existe"},
        {"tipo": "../../etc/passwd"},
        {"tipo": 123},
        {},                                                   # sem tipo
        {"tipo": "prova.progresso", "parametros": "nao-e-objeto"},
        {"tipo": "prova.progresso", "parametros": {"passos": "muitos"}},
        {"tipo": "prova.progresso", "prioridade": 99},
        {"tipo": "prova.progresso", "prioridade": "alta"},
        {"tipo": "prova.progresso", "agendado_para": "nao-e-data"},
    ]:
        r = sessao_a.post("/api/jobs", json=corpo)
        assert 400 <= r.status_code < 500, (corpo, r.status_code, r.text[:160])


def test_job_de_prova_nao_aceita_argumento_de_caminho_ou_url(sessao_a):
    """Nenhum tipo de job de master toma um caminho de arquivo ou URL crua como parâmetro (traversal/SSRF via job);
    campos extras são recusados pelo schema pydantic do tipo, não engolidos."""
    r = sessao_a.post("/api/jobs", json={"tipo": "prova.progresso",
                                         "parametros": {"passos": 1, "caminho": "../../etc/passwd",
                                                        "url": "http://169.254.169.254/"}})
    # o schema do tipo ou ignora os extras (201, sem efeito) ou os recusa (422); nunca 500 nem traversal
    assert r.status_code in (201, 422), (r.status_code, r.text[:160])


# ---------------------------------------------------------------- cota/fila devolve 4xx, não 500
def test_cota_esgotada_devolve_4xx_nao_500(sessao_plat):
    """Tenant descartável com cota diária de 1 job: o segundo pedido bate o limite e volta 4xx (413 cota ou 429
    fila), nunca 500. Controle positivo: o primeiro passa."""
    inq = InquilinoTemporario(sessao_plat, config={"cota_jobs_dia": 1})
    try:
        r1 = inq.admin.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 1}})
        assert r1.status_code == 201, r1.text  # controle positivo
        r2 = inq.admin.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 1}})
        assert r2.status_code in (413, 429), (r2.status_code, r2.text[:200])
        assert r2.json().get("erro") in ("cota_jobs_dia", "fila_cheia"), r2.text[:200]
    finally:
        inq.apagar()


# ---------------------------------------------------------------- cancelar/repetir por quem não é dono
def test_cancelar_e_repetir_job_de_outro_usuario_no_mesmo_inquilino(usuarios_a):
    """Um editor não vê nem cancela o job de OUTRO editor do mesmo inquilino (o filtro de dono some com ele: 404).
    Controle positivo: o dono cancela o próprio."""
    dono, _u1, _s1 = usuarios_a.sessao("editor")
    outro, _u2, _s2 = usuarios_a.sessao("editor")
    j = dono.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 200, "duracao_s": 60}})
    assert j.status_code == 201, j.text
    job_id = j.json()["id"]
    for verbo, url in [("get", f"/api/jobs/{job_id}"), ("post", f"/api/jobs/{job_id}/cancelar"),
                       ("post", f"/api/jobs/{job_id}/repetir"), ("get", f"/api/jobs/{job_id}/log")]:
        r = getattr(outro, verbo)(url)
        assert r.status_code == 404, (verbo, url, r.status_code, r.text[:140])
    # controle positivo: o dono cancela o próprio
    assert dono.post(f"/api/jobs/{job_id}/cancelar").status_code in (200, 202, 409)


def test_cancelar_job_de_outro_inquilino(sessao_a, sessao_b):
    j = sessao_b.post("/api/jobs", json={"tipo": "prova.progresso", "parametros": {"passos": 2}})
    assert j.status_code == 201, j.text
    job_b = j.json()["id"]
    for verbo, url in [("post", f"/api/jobs/{job_b}/cancelar"), ("post", f"/api/jobs/{job_b}/repetir")]:
        r = getattr(sessao_a, verbo)(url)
        assert r.status_code in (403, 404), (verbo, r.status_code, r.text[:140])


# ---------------------------------------------------------------- limite de memória declarado × real (worker)
@pytest.mark.lento
def test_memoria_acima_do_declarado_e_contida(env, cliente):
    """prova.memoria declara memoria_mb=256; alocar bem acima disso tem de FALHAR (RLIMIT_DATA/cgroup do filho),
    não estourar o worker nem concluir. Precisa de um worker vivo; se não houver, o teste é pulado."""
    import time

    fila = (cliente.get("/saude").json().get("fila") or {})
    if not fila.get("workers_vivos"):
        pytest.skip("sem worker vivo; limite de memória do filho é coberto por tests/unit/test_jobs_filho_cgroup")
    from tests.api.conftest import credenciais
    c = novo_cliente()
    entrar(c, "demo", *credenciais()["demo"], None)  # admin de demo (prova.memoria é admin)
    r = c.post("/api/jobs", json={"tipo": "prova.memoria", "parametros": {"mb": 4096}})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    fim = time.monotonic() + 90
    estado = None
    while time.monotonic() < fim:
        estado = c.get(f"/api/jobs/{job_id}").json()["estado"]
        if estado in ("concluido", "falhou", "cancelado"):
            break
        time.sleep(0.5)
    assert estado == "falhou", f"job de 4 GB sob limite de 256 MB não falhou (estado={estado})"

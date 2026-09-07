"""Justiça entre inquilinos (item L0-05-e-justica-entre-inquilinos; migração 20260906T2110, ADR próprio).

Portão literal: escalonamento por inquilino (rodízio por turno = max(iniciado_em) do inquilino, NULLS FIRST) de
forma que, com 2 inquilinos e 1 worker, um job curto de A espera no máximo 1 job de B; medido enfileirando
2 × 300 s de B e 1 × 1 s de A; a tela Tarefas mostra a posição na fila (campo posicao_fila da API); a cota de
simultâneos por inquilino segue respeitada.

Refutação do adversário reproduzida aqui: 50 jobs longos de B enfileirados e a espera de 1 job de A medida em
"jobs de B iniciados antes de A" — mais que 1 reprova.

Nenhum teste espera os 300 s: o que se mede é a ORDEM DE ESCOLHA do escalonador. O job de B em curso é cancelado
para liberar o único processo do worker; o próximo escolhido tem de ser o de A, não o segundo de B (na fila
global antiga seria o segundo de B, e A esperaria 600 s — o cenário da hipótese medida no T2).
"""

import datetime
import os

from tests import jobs_sessao
from tests.api.jobs.conftest import criar_job, esperar

PORTA_JUSTICA = 18222
PORTA_ADVERSARIO = 18223
PORTA_COTA = 18224
UTC = datetime.UTC


def _iso(valor: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _ram_livre_gb() -> float:
    """Memória disponível agora, em GB (MemAvailable de /proc/meminfo)."""
    with open("/proc/meminfo", encoding="utf-8") as f:
        for linha in f:
            if linha.startswith("MemAvailable:"):
                return round(int(linha.split()[1]) / 1024 / 1024, 1)
    return 0.0


def _cancelar_pendentes(con, sessao) -> int:
    """Higiene: cancela todo job pendente do inquilino da sessão (restos de outras corridas virariam ruído de
    ordenação). Devolve quantos foram cancelados."""
    with con.cursor() as cur:
        jobs_sessao.contexto(cur, sessao[1], sessao[2], "admin")
        cur.execute("SELECT id FROM plat.job WHERE estado = 'pendente'")
        ids = [r["id"] for r in cur.fetchall()]
        for jid in ids:
            cur.execute("SELECT plat.job_cancelar(%s, %s)", (str(jid), sessao[2]))
    con.commit()
    return len(ids)


def _config_cota_simultaneos(con, sessao, valor: int | None) -> None:
    with con.cursor() as cur:
        jobs_sessao.contexto(cur, sessao[1], sessao[2], "admin")
        if valor is None:
            cur.execute("UPDATE plat.tenant SET config = config - 'cota_jobs_simultaneos' WHERE id = %s",
                        (sessao[1],))
        else:
            cur.execute("UPDATE plat.tenant SET config = config || jsonb_build_object("
                        "'cota_jobs_simultaneos', %s::int) WHERE id = %s", (valor, sessao[1]))
    con.commit()


def _jobs_b_antes_de_a(cliente_b, ids_b: list[str], inicio_a: str) -> int:
    """Quantos dos jobs de B criados pelo teste iniciaram antes (ou no instante) do início de A."""
    marco = _iso(inicio_a)
    n = 0
    for jid in ids_b:
        j = cliente_b.get(f"/api/jobs/{jid}").json()
        if j["iniciado_em"] and _iso(j["iniciado_em"]) <= marco:
            n += 1
    return n


def _workers_vivos(cliente) -> int:
    """Quantos workers estão servindo ESTA base agora (plat.worker do schema em uso, por /saude). O portão fala de
    1 worker; se a máquina tiver outro worker ligado na mesma base, ele ocupa mais um lugar de execução e o limite
    honesto passa a ser um job de B por lugar — nunca a fila inteira de B, que é o que o item afirma."""
    return int(((cliente.get("/saude").json() or {}).get("fila") or {}).get("workers_vivos") or 1)


def _cenario_a_atropelado(cliente_a, cliente_b, iniciar_worker, nome: str, porta: int, longos: int,
                          medida, prefixo: str) -> None:
    """N jobs de 300 s de B + 1 job de 1 s de A, worker com 1 processo: A tem de ser o próximo escolhido quando
    o job de B em curso sai (aqui por cancelamento, para não esperar 300 s). Mede espera e jobs de B antes de A."""
    worker = iniciar_worker(nome, 1, porta)
    assert worker.nome
    lugares = _workers_vivos(cliente_a)
    longo = {"duracao_s": 300, "passos": 600}  # passo de 0,5 s: o cancelamento é percebido em ≤ 1 s
    ids_b = [criar_job(cliente_b, "prova.progresso", dict(longo))["id"] for _ in range(longos)]
    b1 = esperar(cliente_b, ids_b[0], timeout=30, condicao=lambda j: j["estado"] == "rodando")
    a = criar_job(cliente_a, "prova.progresso", {"duracao_s": 1, "passos": 1})
    r = cliente_b.post(f"/api/jobs/{ids_b[0]}/cancelar")
    assert r.status_code == 202, r.text
    try:
        fa = esperar(cliente_a, a["id"], timeout=90)
        assert fa["estado"] == "concluido", fa
        antes = _jobs_b_antes_de_a(cliente_b, ids_b, fa["iniciado_em"])
        espera_s = round((_iso(fa["iniciado_em"]) - _iso(a["criado_em"])).total_seconds(), 1)
        # na fila global antiga A esperaria os N × 300 s; com o rodízio espera só o job de B em curso
        assert antes <= lugares, (f"A esperou {antes} jobs de B (máximo {lugares}, um por worker vivo na base): "
                                  f"início de A {fa['iniciado_em']}, B1 {b1['iniciado_em']}")
        assert espera_s < 60, f"espera de A ({espera_s} s) incompatível com 'no máximo 1 job de B'"
        medida("L0-05-e-justica-entre-inquilinos")(f"{prefixo}_espera_a_s", espera_s, "s",
            f"{longos} × prova.progresso(300 s) de demo2 + 1 × prova.progresso(1 s) de demo, worker 1 processo; "
            "B em curso cancelado para liberar o worker; espera = iniciado_em(A) − criado_em(A)")
        medida("L0-05-e-justica-entre-inquilinos")(f"{prefixo}_jobs_b_antes_de_a", antes, "jobs",
            "contagem dos jobs de demo2 criados pelo teste com iniciado_em <= iniciado_em(A); portão: <= 1 por "
            "worker vivo na base")
        medida("L0-05-e-justica-entre-inquilinos")(f"{prefixo}_workers_vivos_na_base", lugares, "workers",
            "GET /saude campo fila.workers_vivos no instante da medida (o portão fala de 1)")
        # a espera é medida em segundos: a carga da máquina no instante vai gravada ao lado (regra do laço)
        medida("L0-05-e-justica-entre-inquilinos")(f"{prefixo}_carga_1min", round(os.getloadavg()[0], 2),
            "carga", "os.getloadavg()[0] no instante da medida da espera")
        medida("L0-05-e-justica-entre-inquilinos")(f"{prefixo}_ram_livre_gb", _ram_livre_gb(),
            "GB", "MemAvailable de /proc/meminfo no instante da medida da espera")
    finally:
        for jid in ids_b:
            cliente_b.post(f"/api/jobs/{jid}/cancelar")


def test_job_curto_de_a_espera_no_maximo_um_job_de_b(cliente_demo, cliente_demo2, iniciar_worker,
                                                     conexao_plat_app, sessao_demo, sessao_demo2, medida):
    """Portão literal: 2 × 300 s de B e 1 × 1 s de A com 1 worker; A espera no máximo 1 job de B."""
    _cancelar_pendentes(conexao_plat_app, sessao_demo)
    _cancelar_pendentes(conexao_plat_app, sessao_demo2)
    _cenario_a_atropelado(cliente_demo, cliente_demo2, iniciar_worker,
                          f"teste-justica-{os.getpid()}", PORTA_JUSTICA, 2, medida, "portao")


def test_adversario_50_jobs_longos_de_b(cliente_demo, cliente_demo2, iniciar_worker,
                                        conexao_plat_app, sessao_demo, sessao_demo2, medida):
    """Refutação exigida: 50 jobs longos de B; a espera de 1 job de A em jobs de B antes dele tem de ser <= 1."""
    _cancelar_pendentes(conexao_plat_app, sessao_demo)
    _cancelar_pendentes(conexao_plat_app, sessao_demo2)
    _cenario_a_atropelado(cliente_demo, cliente_demo2, iniciar_worker,
                          f"teste-adversario-{os.getpid()}", PORTA_ADVERSARIO, 50, medida, "adversario50")


def test_cota_de_simultaneos_por_inquilino_respeitada(cliente_demo, cliente_demo2, iniciar_worker,
                                                      conexao_plat_app, sessao_demo, sessao_demo2, medida):
    """Cota por inquilino (migração 004, mantida no job_pegar novo): com cota 1 no inquilino demo e worker com
    2 processos, dois jobs de demo rodam em SÉRIE, enquanto demo e demo2 rodam em PARALELO (a cota é por
    inquilino, não global)."""
    _cancelar_pendentes(conexao_plat_app, sessao_demo)
    _cancelar_pendentes(conexao_plat_app, sessao_demo2)
    _config_cota_simultaneos(conexao_plat_app, sessao_demo, 1)
    worker = iniciar_worker(f"teste-cota-{os.getpid()}", 2, PORTA_COTA)
    assert worker.nome
    try:
        a1 = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 3, "passos": 6})
        a2 = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 3, "passos": 6})
        fa1, fa2 = esperar(cliente_demo, a1["id"], timeout=60), esperar(cliente_demo, a2["id"], timeout=60)
        assert fa1["estado"] == fa2["estado"] == "concluido"
        primeiro, segundo = sorted((fa1, fa2), key=lambda j: j["iniciado_em"])
        assert _iso(segundo["iniciado_em"]) >= _iso(primeiro["terminado_em"]), (
            f"cota 1 de demo violada: {primeiro['iniciado_em']}–{primeiro['terminado_em']} x "
            f"{segundo['iniciado_em']}–{segundo['terminado_em']}")

        a3 = criar_job(cliente_demo, "prova.progresso", {"duracao_s": 3, "passos": 6})
        b1 = criar_job(cliente_demo2, "prova.progresso", {"duracao_s": 3, "passos": 6})
        fa3, fb1 = esperar(cliente_demo, a3["id"], timeout=60), esperar(cliente_demo2, b1["id"], timeout=60)
        assert fa3["estado"] == fb1["estado"] == "concluido"
        sobreposicao = min(_iso(fa3["terminado_em"]), _iso(fb1["terminado_em"])) \
            - max(_iso(fa3["iniciado_em"]), _iso(fb1["iniciado_em"]))
        assert sobreposicao.total_seconds() > 0, (
            "cota por inquilino virou global: demo e demo2 não rodaram em paralelo com 2 processos livres")
        medida("L0-05-e-justica-entre-inquilinos")("cota_simultaneos_sobreposicao_inquilinos_s",
                                                   round(sobreposicao.total_seconds(), 1), "s",
            "worker 2 processos, demo com cota_jobs_simultaneos=1: 2 jobs de demo em série (inicio2 >= fim1) e "
            "demo x demo2 em paralelo (sobreposição > 0); tests/api/jobs/test_jobs_justica.py")
    finally:
        _config_cota_simultaneos(conexao_plat_app, sessao_demo, None)


def test_posicao_na_fila_na_api(cliente_demo, conexao_plat_app, sessao_demo):
    """Tela Tarefas (portão): a API expõe posicao_fila — posição do job pendente na fila do inquilino
    (1 = o próximo quando chegar a vez dele), respeitando prioridade e ordem de criação; fora de 'pendente'
    é null. Os jobs nascem agendados para o futuro: assim ficam pendentes de propósito, sem depender de haver ou
    não worker ligado nesta base (o mesmo instante nos quatro mantém `criado_em` como chave de desempate)."""
    _cancelar_pendentes(conexao_plat_app, sessao_demo)
    ids = []
    daqui_a_uma_hora = (datetime.datetime.now(UTC) + datetime.timedelta(hours=1)).isoformat()
    parado = {"duracao_s": 0, "passos": 1}
    try:
        j1 = criar_job(cliente_demo, "prova.progresso", dict(parado), agendado_para=daqui_a_uma_hora)
        j2 = criar_job(cliente_demo, "prova.progresso", dict(parado), agendado_para=daqui_a_uma_hora)
        j3 = criar_job(cliente_demo, "prova.progresso", dict(parado), agendado_para=daqui_a_uma_hora)
        ids = [j1["id"], j2["id"], j3["id"]]
        p1 = cliente_demo.get(f"/api/jobs/{j1['id']}").json()["posicao_fila"]
        p2 = cliente_demo.get(f"/api/jobs/{j2['id']}").json()["posicao_fila"]
        p3 = cliente_demo.get(f"/api/jobs/{j3['id']}").json()["posicao_fila"]
        assert isinstance(p1, int) and p1 >= 1, p1
        assert (p2 - p1, p3 - p2) == (1, 1), (p1, p2, p3)  # ordem de criação, independente do que havia antes

        urgente = criar_job(cliente_demo, "prova.progresso", dict(parado), prioridade=1,
                            agendado_para=daqui_a_uma_hora)
        ids.append(urgente["id"])
        pu = cliente_demo.get(f"/api/jobs/{urgente['id']}").json()["posicao_fila"]
        p1_depois = cliente_demo.get(f"/api/jobs/{j1['id']}").json()["posicao_fila"]
        assert pu == p1 and p1_depois == p1 + 1, (pu, p1, p1_depois)  # prioridade 1 furou a fila do inquilino

        r = cliente_demo.post(f"/api/jobs/{j1['id']}/cancelar")
        assert r.status_code == 202
        assert r.json()["posicao_fila"] is None  # fora de 'pendente' não há posição
    finally:
        for jid in ids:
            cliente_demo.post(f"/api/jobs/{jid}/cancelar")

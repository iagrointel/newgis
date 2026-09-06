"""Notificações internas do item L0-03-k (achado G2-7 do adversário do grupo G2: a metade de notificação do item
não existia). Cobre as cláusulas do portão que são de API:

  - notificação de convite de grupo chega para o convidado e o sino conta;
  - notificação de outro usuário é invisível (segurança de linha por usuario_id) e não é alcançável por id;
  - chave repetida NÃO duplica;
  - marcar lida (uma e todas) zera o sino;
  - teto por minuto por usuário (refutação "10 mil notificações para um usuário em 1 min");
  - expurgo por idade com relógio simulado;
  - medida: a consulta do sino em ≤ 20 ms.

A notificação de job concluído é escrita pelo worker (app/jobs/worker.py::_notificar_dono) e depende de worker
vivo; aqui o mesmo caminho é exercido pela função plat.notificar, que é o que o worker chama.
"""

import time
import uuid

from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-catalogo"
SINO_MS_MAX = 20


def _limpar(sessao):
    j = sessao.get("/api/notificacoes?limite=100").json()
    for n in j["itens"]:
        sessao.delete(f"/api/notificacoes/{n['id']}")


def test_convite_de_grupo_notifica_o_convidado_e_o_sino_conta(sessao_a, editor_a):
    cliente, usuario = editor_a
    _limpar(cliente)
    antes = cliente.get("/api/notificacoes/contagem").json()["nao_lidas"]
    g = sessao_a.post("/api/grupos", json={"nome": f"zt notif {uuid.uuid4().hex[:8]}", "entrada": "convite"}).json()
    try:
        r = sessao_a.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": usuario["id"], "papel": "membro"})
        assert r.status_code == 201, r.text
        j = cliente.get("/api/notificacoes").json()
        minhas = [n for n in j["itens"] if n["alvo_id"] == g["id"]]
        assert len(minhas) == 1, j
        assert minhas[0]["tipo"] == "grupos/convite"
        assert minhas[0]["lida_em"] is None
        assert cliente.get("/api/notificacoes/contagem").json()["nao_lidas"] == antes + 1
        # quem convidou não recebe nada: a notificação é do convidado
        assert not [n for n in sessao_a.get("/api/notificacoes").json()["itens"] if n["alvo_id"] == g["id"]]
    finally:
        sessao_a.delete(f"/api/grupos/{g['id']}")


def test_notificacao_de_outro_usuario_invisivel_e_inalcancavel(sessao_a, editor_a, conexao_plat_app):
    cliente, usuario = editor_a
    _limpar(cliente)
    chave = f"zt/{uuid.uuid4().hex}"
    ids = ids_por_slug(conexao_plat_app)
    admin_id = sessao_a.get("/api/eu").json()["id"]
    contexto(conexao_plat_app, ids["demo"], admin_id, "admin")
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt do admin', %s, NULL, NULL, NULL, NULL, 60) AS id",
                (ids["demo"], admin_id, chave),
            )
            do_admin = str(cur.fetchone()["id"])
        conexao_plat_app.commit()
    except Exception:
        conexao_plat_app.rollback()
        raise
    try:
        assert do_admin not in [n["id"] for n in cliente.get("/api/notificacoes?limite=100").json()["itens"]]
        assert cliente.delete(f"/api/notificacoes/{do_admin}").status_code == 404
        assert (
            cliente.post("/api/notificacoes/lidas", json={"ids": [do_admin]}).status_code == 404
        ), "marcou como lida uma notificação de outro usuário"
    finally:
        sessao_a.delete(f"/api/notificacoes/{do_admin}")


def test_chave_repetida_nao_duplica_e_teto_por_minuto_segura_enxurrada(sessao_a, conexao_plat_app):
    from app import limites

    ids = ids_por_slug(conexao_plat_app)
    admin_id = sessao_a.get("/api/eu").json()["id"]
    contexto(conexao_plat_app, ids["demo"], admin_id, "admin")
    chave = f"zt/{uuid.uuid4().hex}"
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute(
                "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt repetida', %s, NULL, NULL, NULL, NULL, 60) AS id",
                (ids["demo"], admin_id, chave),
            )
            primeira = cur.fetchone()["id"]
            cur.execute(
                "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt repetida', %s, NULL, NULL, NULL, NULL, 60) AS id",
                (ids["demo"], admin_id, chave),
            )
            segunda = cur.fetchone()["id"]
            cur.execute("SELECT count(*) AS n FROM plat.notificacao WHERE chave = %s", (chave,))
            linhas = cur.fetchone()["n"]
            # enxurrada de uma origem só: 500 pedidos, teto por minuto
            inicio = time.monotonic()
            criadas = 0
            for n_pedido in range(500):
                cur.execute(
                    "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt enxurrada', %s, NULL, NULL, NULL, NULL, %s) "
                    "AS id",
                    (ids["demo"], admin_id, f"{chave}/{n_pedido}", limites.NOTIFICACOES_POR_MINUTO),
                )
                criadas += 1 if cur.fetchone()["id"] else 0
            gasto = time.monotonic() - inicio
    finally:
        conexao_plat_app.rollback()
    assert primeira is not None and segunda is None, "a mesma chave criou duas notificações"
    assert linhas == 1
    assert criadas <= limites.NOTIFICACOES_POR_MINUTO, f"{criadas} notificações criadas em {gasto:.1f} s"


def test_marcar_lida_uma_e_todas(sessao_a, editor_a):
    cliente, usuario = editor_a
    _limpar(cliente)
    grupos = []
    try:
        for _ in range(2):
            g = sessao_a.post(
                "/api/grupos", json={"nome": f"zt notif {uuid.uuid4().hex[:8]}", "entrada": "convite"}
            ).json()
            grupos.append(g)
            sessao_a.post(f"/api/grupos/{g['id']}/membros", json={"usuario_id": usuario["id"], "papel": "membro"})
        assert cliente.get("/api/notificacoes/contagem").json()["nao_lidas"] == 2
        um = cliente.get("/api/notificacoes").json()["itens"][0]["id"]
        r = cliente.post("/api/notificacoes/lidas", json={"ids": [um]})
        assert r.status_code == 200 and r.json()["nao_lidas"] == 1, r.text
        r = cliente.post("/api/notificacoes/lidas", json={"todas": True})
        assert r.status_code == 200 and r.json()["nao_lidas"] == 0, r.text
        # lista vazia nunca é "todas" (mesma disciplina do expurgo da lixeira, achado G2-4)
        assert cliente.post("/api/notificacoes/lidas", json={"ids": [], "todas": False}).status_code == 422
    finally:
        for g in grupos:
            sessao_a.delete(f"/api/grupos/{g['id']}")


def test_expurgo_por_idade_apaga_so_o_que_passou_dos_dias(sessao_a, conexao_plat_app):
    ids = ids_por_slug(conexao_plat_app)
    admin_id = sessao_a.get("/api/eu").json()["id"]
    contexto(conexao_plat_app, ids["demo"], admin_id, "admin")
    chave = f"zt/{uuid.uuid4().hex}"
    try:
        with conexao_plat_app.cursor() as cur:
            for sufixo, dias in (("velha", 200), ("nova", 1)):
                cur.execute(
                    "SELECT plat.notificar(%s, %s, 'grupos/convite', 'zt expurgo', %s, NULL, NULL, NULL, NULL, 60) "
                    "AS id",
                    (ids["demo"], admin_id, f"{chave}/{sufixo}"),
                )
                cur.execute(
                    "UPDATE plat.notificacao SET criado_em = now() - make_interval(days => %s) WHERE chave = %s",
                    (dias, f"{chave}/{sufixo}"),
                )
            cur.execute("SELECT plat.notificacoes_expurgar(90, now()) AS n")
            apagadas = cur.fetchone()["n"]
            cur.execute("SELECT chave FROM plat.notificacao WHERE chave LIKE %s", (f"{chave}/%",))
            sobraram = [r["chave"] for r in cur.fetchall()]
    finally:
        conexao_plat_app.rollback()
    assert apagadas >= 1
    assert sobraram == [f"{chave}/nova"], sobraram


def test_medida_sino_abaixo_de_20ms(sessao_a, conexao_plat_app, medida):
    """Cláusula do portão: "sino consulta <= 20 ms". O que o portão chama de consulta do sino é a contagem de não
    lidas no banco (índice parcial ix_notificacao_sino), medida aqui em 20 execuções; o tempo do HTTP é gravado
    junto, como informação, porque inclui sessão, middleware e rede local."""
    ids = ids_por_slug(conexao_plat_app)
    admin_id = sessao_a.get("/api/eu").json()["id"]
    contexto(conexao_plat_app, ids["demo"], admin_id, "admin")
    consulta = []
    try:
        with conexao_plat_app.cursor() as cur:
            for _ in range(20):
                inicio = time.perf_counter()
                cur.execute(
                    "SELECT count(*) FROM plat.notificacao WHERE usuario_id = %s AND lida_em IS NULL", (admin_id,)
                )
                cur.fetchone()
                consulta.append((time.perf_counter() - inicio) * 1000)
    finally:
        conexao_plat_app.rollback()
    http = []
    for _ in range(20):
        inicio = time.perf_counter()
        r = sessao_a.get("/api/notificacoes/contagem")
        http.append((time.perf_counter() - inicio) * 1000)
        assert r.status_code == 200
    consulta.sort()
    http.sort()
    p95 = round(consulta[int(len(consulta) * 0.95) - 1], 3)
    medida(ITEM)(
        "sino_consulta_p95_ms", p95, "ms",
        "SELECT count(*) FROM plat.notificacao WHERE usuario_id = ? AND lida_em IS NULL, 20 execuções",
    )
    medida(ITEM)(
        "sino_http_p95_ms", round(http[int(len(http) * 0.95) - 1], 2), "ms",
        "GET /api/notificacoes/contagem, 20 execuções",
    )
    assert p95 <= SINO_MS_MAX, f"p95 da consulta do sino = {p95} ms (teto {SINO_MS_MAX} ms)"

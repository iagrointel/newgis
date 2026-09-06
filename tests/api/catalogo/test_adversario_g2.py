"""Laudo executável do adversário do grupo G2 (catálogo de conteúdo, itens L0-03-a..l).

Cada teste aqui é um achado MEDIDO em 06/09/2026 numa base isolada (schema plat_tadv2, criado por
`laco/trilha_ambiente.sh adv2`). Todos estão marcados `xfail(strict=True)`: enquanto o defeito existir
o teste é xfail; quando alguém consertar, ele vira XPASS e a suíte reprova — é assim que o achado vira
prova. O adversário NÃO conserta nada.

Reproduzir:
  bash /home/dev/plataforma/laco/trilha_ambiente.sh adv2
  set -a; source /home/dev/plataforma/laco/var/trilha/adv2.env; set +a
  venv/bin/pytest tests/api/catalogo/test_adversario_g2.py -q -rx
"""

import datetime
import json
import time

import pytest

from tests.api.catalogo.conftest import titulo_zt
from tests.api.conftest import novo_cliente
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-catalogo"


# ---------------------------------------------------------------- L0-03-l (e isolamento por inquilino)
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-1: plat.item_versoes_compactar(uuid,int) é SECURITY DEFINER e NÃO compara "
    "tenant_atual() com o inquilino do item: no contexto do inquilino A ela apaga linhas de "
    "plat.item_versao de item do inquilino B (medido: 2 linhas removidas).",
)
def test_g2_1_compactar_versoes_nao_deve_cruzar_inquilino(sessao_b, itens_b, conexao_plat_app):
    it_b = itens_b.criar("mapa")
    for i in range(3):
        assert sessao_b.put(f"/api/itens/{it_b['id']}", json={"titulo": titulo_zt(f"v{i}")}).status_code == 200
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], 2, "admin")  # contexto do inquilino A
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT plat.item_versoes_compactar(%s::uuid, 1) AS n", (it_b["id"],))
            removidas = cur.fetchone()["n"]
    finally:
        conexao_plat_app.rollback()
    assert removidas == 0, f"o inquilino A apagou {removidas} versões de um item do inquilino B"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-2: POST /api/jobs aceita (201) o tipo catalogo.versoes_compactar com item_id de "
    "OUTRO inquilino; somado ao G2-1, um admin de qualquer inquilino apaga o histórico de versões "
    "de item alheio pela fila.",
)
def test_g2_2_job_de_compactacao_nao_deve_aceitar_item_de_outro_inquilino(sessao_a, sessao_b, itens_b):
    it_b = itens_b.criar("mapa")
    r = sessao_a.post(
        "/api/jobs", json={"tipo": "catalogo.versoes_compactar", "parametros": {"manter": 1, "item_id": it_b["id"]}}
    )
    assert r.status_code >= 400, f"job aceito com item de outro inquilino: {r.status_code} {r.text[:200]}"


@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-3: a compactação não cumpre o teto declarado na refutação do item ('manter <= 50 "
    "linhas'): depois de 200 PUTs uma passada deixa 66 linhas (com 1.000 PUTs deixa 146), e o "
    "periódico roda uma passada por dia.",
)
def test_g2_3_compactacao_mantem_no_maximo_50_linhas(sessao_a, itens_a, conexao_plat_app):
    it = itens_a.criar("mapa")
    iid = it["id"]
    for i in range(200):
        assert sessao_a.put(f"/api/itens/{iid}", json={"titulo": f"zt v{i:04d}"}).status_code == 200
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], 2, "admin")
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT plat.item_versoes_compactar(%s::uuid, 50) AS n", (iid,))
            cur.fetchone()
            cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (iid,))
            linhas = cur.fetchone()["n"]
    finally:
        conexao_plat_app.rollback()
    assert linhas <= 50, f"{linhas} linhas de versão depois de uma passada de compactação"


# ---------------------------------------------------------------- L0-03-h
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-4: POST /api/lixeira/esvaziar com uma lista de ids que a RLS não resolve (item de "
    "outro inquilino, ou uuid inexistente) enfileira o job com ids=[]; a tarefa converte [] em NULL "
    "(`[str(x) for x in ids] if ids else None`) e plat.lixeira_expurgar(0, now(), NULL) devolve TODA "
    "a lixeira do inquilino. Pedir o expurgo de 1 item apaga a lixeira inteira.",
)
def test_g2_4_esvaziar_com_id_que_nao_resolve_nao_deve_expurgar_tudo(sessao_a, itens_a, conexao_plat_app):
    a1, a2 = itens_a.criar("mapa"), itens_a.criar("mapa")
    assert sessao_a.delete(f"/api/itens/{a1['id']}").status_code == 204
    assert sessao_a.delete(f"/api/itens/{a2['id']}").status_code == 204
    bogus = "00000000-0000-0000-0000-0000000000ff"
    r = sessao_a.post("/api/lixeira/esvaziar", json={"ids": [bogus]})
    assert r.status_code == 202, r.text
    p = sessao_a.get(f"/api/jobs/{r.json()['job_id']}").json()["parametros"]
    # a MESMA linha da tarefa (app/catalogo/tarefas.py, catalogo_lixeira_expurgar)
    ids_worker = [str(x) for x in p["ids"]] if p["ids"] else None
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], 2, "admin")
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.lixeira_expurgar(0, now(), %s::uuid[])", (ids_worker,))
            candidatos = cur.fetchone()["n"]
    finally:
        conexao_plat_app.rollback()
    assert candidatos == 0, f"o worker expurgaria {candidatos} itens, e o pedido nomeava 1 item que nem existe"


# ---------------------------------------------------------------- L0-03-j
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-5: a transferência grava o evento itens/transferir de um item arrastado que a RLS "
    "impediu de atualizar (UPDATE sem linha afetada, sem erro): o dono não muda, a API responde 200 e "
    "o histórico afirma que mudou.",
)
def test_g2_5_evento_de_transferencia_so_do_que_mudou(sessao_a, itens_a, editor_a, editor2_a):
    dono_c, _ = editor_a
    outro_c, outro = editor2_a
    camada = itens_a.criar("camada_vetorial", sessao=dono_c)
    dono_c.put(f"/api/itens/{camada['id']}/compartilhamento", json={"acesso": "inquilino"})
    vista = itens_a.criar("camada_vetorial", sessao=outro_c)
    outro_c.put(f"/api/itens/{vista['id']}/compartilhamento", json={"acesso": "inquilino"})
    assert (
        outro_c.put(
            f"/api/itens/{vista['id']}/relacoes",
            json={"relacoes": [{"destino": camada["id"], "tipo": "vista_de_camada"}]},
        ).status_code
        == 200
    )
    admin_id = sessao_a.get("/api/eu").json()["id"]
    r = dono_c.post(
        "/api/itens/transferir", json={"ids": [camada["id"]], "novo_dono_id": admin_id, "simular": False}
    )
    assert r.status_code == 200, r.text
    dono_da_vista = sessao_a.get(f"/api/itens/{vista['id']}").json()["dono"]["id"]
    eventos = sessao_a.get("/api/eventos?tipo=itens/transferir&limite=20").json()["itens"]
    mentiu = [e for e in eventos if e["alvo_id"] == vista["id"]] and dono_da_vista == outro["id"]
    assert not mentiu, "evento diz que a vista foi transferida; o dono continua o mesmo"


# ---------------------------------------------------------------- L0-03-e
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-6: a miniatura entregue pelo link compartilhável sai com "
    "'Cache-Control: private, max-age=300' (miniatura.entregar), enquanto todas as outras rotas do "
    "link são no-store; depois de revogar, o cliente que já a baixou continua servindo do cache por "
    "até 5 minutos — a refutação do item diz que o cache não pode servir.",
)
def test_g2_6_miniatura_por_link_sem_cache(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    assert sessao_a.post(f"/api/itens/{it['id']}/miniatura", json={"conteudo": png}).status_code == 200
    tok = sessao_a.post(f"/api/itens/{it['id']}/links", json={}).json()["token"]
    anon = novo_cliente()
    r = anon.get(f"/api/compartilhado/{tok}/itens/{it['id']}/miniatura")
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control", "").startswith("no-store"), r.headers.get("cache-control")


# ---------------------------------------------------------------- L0-03-k
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-7: metade do item não existe. Não há rota, tabela, migração nem código de "
    "notificação interna (grep por 'notific' em app/, db/ e web/ = 0); o item declara sino na barra, "
    "lida/não lida, dedup por chave, expurgo em 90 dias e medida 'sino consulta <= 20 ms'.",
)
def test_g2_7_notificacoes_internas_existem(sessao_a):
    codigos = {rota: sessao_a.get(rota).status_code for rota in ("/api/notificacoes", "/api/eu/notificacoes")}
    assert any(c != 404 for c in codigos.values()), codigos


# ---------------------------------------------------------------- transversal (segurança de esquema)
@pytest.mark.xfail(
    strict=True,
    reason="ACHADO G2-8: funções do schema plat sem REVOKE de PUBLIC (proacl nulo ou com '='). São 13 no "
    "schema de produção `plat` (6 delas SECURITY DEFINER: convite_aceitar, convite_resolver, "
    "redefinicao_contexto/resolver/solicitar, uploads_expirar_candidatos) e 9 no schema desta trilha. "
    "É o mesmo teste que já existe no repositório (tests/api/catalogo/"
    "test_eventos_e_seguranca.py::test_funcoes_do_catalogo_sem_public_e_worker_fechado_a_plat_app), "
    "que está VERMELHO no master — as migrações novas (030 conexão, 046 uploads, 047 convites) não "
    "repetiram o padrão de REVOKE da 011.",
)
def test_g2_8_funcoes_do_plat_sem_execute_para_public(conexao_plat_app, env):
    esquema = env.get("PLAT_SCHEMA") or "plat"
    with conexao_plat_app.cursor() as cur:
        cur.execute(
            "SELECT proname FROM pg_proc WHERE pronamespace = %s::regnamespace "
            "AND (proacl IS NULL OR EXISTS (SELECT 1 FROM unnest(proacl) a WHERE a::text LIKE '=%%')) "
            "ORDER BY proname",
            (esquema,),
        )
        abertas = [r["proname"] for r in cur.fetchall()]
    assert abertas == [], f"{len(abertas)} funções de {esquema} com EXECUTE para PUBLIC: {abertas}"

"""Laudo executável do adversário do grupo G2 (catálogo de conteúdo, itens L0-03-a..l).

Cada teste aqui é um achado MEDIDO em 06/09/2026 numa base isolada (schema plat_tadv2, criado por
`laco/trilha_ambiente.sh adv2`). Nasceram marcados `xfail(strict=True)`: enquanto o defeito existir o
teste é xfail; quando alguém conserta, vira XPASS e a suíte reprova — é assim que o achado vira prova.
O adversário NÃO conserta nada.

Turno de conserto (trilha g2fix, 06/09/2026): os achados G2-3, G2-4, G2-5, G2-6, G2-7 e G2-9 foram
consertados e a marca xfail SAIU dos testes correspondentes — eles agora exigem o comportamento certo e
ficam vermelhos se alguém regredir. Nenhum teste foi apagado nem afrouxado; onde a rota passou a recusar
o pedido, o teste passou a exigir a recusa E o efeito medido (nenhum expurgo, nenhum evento falso).
G2-1, G2-2 e G2-8 CONTINUAM xfail de propósito: são função SECURITY DEFINER e permissão de função, que
estão com a trilha dedicada à varredura das 102 funções definidoras (ressalva do gerente).

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


def test_g2_3_compactacao_mantem_no_maximo_50_linhas(sessao_a, itens_a, conexao_plat_app):
    """ACHADO G2-3 (consertado): uma passada de plat.item_versoes_compactar deixa manter + ceil((N-manter)/10)
    linhas — 66 depois de 200 PUTs, 146 depois de 1.000 — e o periódico rodava uma passada por dia, então o item
    ficava dias acima do teto. O conserto está em app/catalogo/tarefas.py::compactar_item: repete a passada até
    estabilizar (o excedente cai por 10 a cada vez) e pede manter = teto - 1, porque o ponto fixo é manter + 1
    linha. O periódico passou a rodar de hora em hora. A função do banco NÃO foi tocada."""
    from app.catalogo.tarefas import LINHAS_MAX_POR_ITEM, compactar_item

    it = itens_a.criar("mapa")
    iid = it["id"]
    for i in range(200):
        assert sessao_a.put(f"/api/itens/{iid}", json={"titulo": f"zt v{i:04d}"}).status_code == 200
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], 2, "admin")
    try:
        with conexao_plat_app.cursor() as cur:
            removidas, linhas = compactar_item(cur, iid, LINHAS_MAX_POR_ITEM)
            cur.execute("SELECT count(*) AS n FROM plat.item_versao WHERE item_id = %s::uuid", (iid,))
            conferida = cur.fetchone()["n"]
            # segunda execução sobre o mesmo item não remove mais nada: uma passagem já estabilizou
            de_novo, _ = compactar_item(cur, iid, LINHAS_MAX_POR_ITEM)
    finally:
        conexao_plat_app.rollback()
    assert linhas == conferida
    assert linhas <= 50, f"{linhas} linhas de versão depois de uma passagem de compactação (removidas {removidas})"
    assert de_novo == 0, f"a compactação não estabilizou: a passagem seguinte ainda removeu {de_novo} linhas"


# ---------------------------------------------------------------- L0-03-h
def test_g2_4_esvaziar_com_id_que_nao_resolve_nao_deve_expurgar_tudo(sessao_a, itens_a, conexao_plat_app):
    """ACHADO G2-4 (consertado): POST /api/lixeira/esvaziar com id que a segurança de linha não resolve enfileirava
    ids=[]; a tarefa fazia `[str(x) for x in ids] if ids else None`, [] virava NULL e plat.lixeira_expurgar(0,
    now(), NULL) devolvia TODA a lixeira do inquilino — expurgo físico, sem volta. Conserto nos dois níveis: a rota
    recusa o pedido que não resolveu nada e a tarefa recusa lista vazia em vez de tratá-la como 'tudo'."""
    from app.catalogo.tarefas import catalogo_lixeira_expurgar
    from app.jobs.registro import FalhaDefinitiva

    a1, a2 = itens_a.criar("mapa"), itens_a.criar("mapa")
    assert sessao_a.delete(f"/api/itens/{a1['id']}").status_code == 204
    assert sessao_a.delete(f"/api/itens/{a2['id']}").status_code == 204
    bogus = "00000000-0000-0000-0000-0000000000ff"

    # 1. a rota recusa o pedido que não resolveu nenhum item (antes: 202 com ids=[])
    r = sessao_a.post("/api/lixeira/esvaziar", json={"ids": [bogus]})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "nenhum_item_na_lixeira", r.text

    # 2. a tarefa recusa lista vazia (nível 2: mesmo que algo enfileire [], não vira "toda a lixeira")
    try:
        catalogo_lixeira_expurgar(None, dias=0, ids=[])
        raise AssertionError("a tarefa aceitou uma lista vazia de ids")
    except FalhaDefinitiva:
        pass

    # 3. pedido legítimo de UM item enfileira exatamente aquele item, e o expurgo alcança 1, não 2
    r = sessao_a.post("/api/lixeira/esvaziar", json={"ids": [a1["id"]]})
    assert r.status_code == 202, r.text
    p = sessao_a.get(f"/api/jobs/{r.json()['job_id']}").json()["parametros"]
    assert p["ids"] == [a1["id"]], p
    sessao_a.post(f"/api/jobs/{r.json()['job_id']}/cancelar")
    ids = ids_por_slug(conexao_plat_app)
    contexto(conexao_plat_app, ids["demo"], 2, "admin")
    try:
        with conexao_plat_app.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM plat.lixeira_expurgar(0, now(), %s::uuid[])", ([str(a1["id"])],))
            um = cur.fetchone()["n"]
            cur.execute("SELECT count(*) AS n FROM plat.lixeira_expurgar(0, now(), %s::uuid[])", ([],))
            vazia = cur.fetchone()["n"]
    finally:
        conexao_plat_app.rollback()
    assert um == 1, f"o pedido nomeava 1 item e o expurgo alcançaria {um}"
    assert vazia == 0, f"lista vazia alcançaria {vazia} itens: lista vazia nunca é 'tudo'"


# ---------------------------------------------------------------- L0-03-j
def test_g2_5_evento_de_transferencia_so_do_que_mudou(sessao_a, itens_a, editor_a, editor2_a):
    """ACHADO G2-5 (consertado): a transferência arrastava a vista de outro dono com um UPDATE que a segurança de
    linha barrava — no Postgres isso afeta zero linhas e NÃO levanta erro — e gravava o evento itens/transferir
    assim mesmo: a API respondia 200, o dono continuava o mesmo e a auditoria dizia que tinha mudado. Conserto:
    a pré-checagem declara a falha `arrasto_sem_edicao` antes de executar, e no execução um UPDATE que afeta zero
    linhas vira erro 409 (a transação inteira cai, ninguém fica com meia transferência gravada)."""
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

    # 1. a simulação avisa ANTES: o arrasto prometido não pode acontecer
    plano = dono_c.post(
        "/api/itens/transferir", json={"ids": [camada["id"]], "novo_dono_id": admin_id, "simular": True}
    ).json()
    codigos = [f["codigo"] for l in plano["plano"] for f in l["falhas"]]
    assert "arrasto_sem_edicao" in codigos, plano
    assert plano["com_falha"] == 1, plano

    # 2. executar recusa (o plano tem falha) em vez de responder 200 prometendo o que não faz
    r = dono_c.post(
        "/api/itens/transferir", json={"ids": [camada["id"]], "novo_dono_id": admin_id, "simular": False}
    )
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "plano_com_falhas", r.text

    # 3. nada mudou e o histórico não inventa: nem para a vista nem para a camada
    assert sessao_a.get(f"/api/itens/{vista['id']}").json()["dono"]["id"] == outro["id"]
    eventos = sessao_a.get("/api/eventos?tipo=itens/transferir&limite=50").json()["itens"]
    alvos = {e["alvo_id"] for e in eventos}
    assert vista["id"] not in alvos, "evento de transferência gravado para item que não mudou de dono"
    assert camada["id"] not in alvos, "evento de transferência gravado sem transferência"


# ---------------------------------------------------------------- L0-03-e
# ACHADO G2-6 (consertado): a miniatura entregue pelo link compartilhável saía com
# "Cache-Control: private, max-age=300" (miniatura.entregar), enquanto as outras duas rotas do link são no-store:
# depois de revogar, o navegador de quem já tinha baixado continuava mostrando por até 5 minutos. Conserto:
# miniatura.entregar recebe o Cache-Control de quem chama; as rotas anônimas (link por token e público) passam
# CACHE_SEM ("no-store, must-revalidate").
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

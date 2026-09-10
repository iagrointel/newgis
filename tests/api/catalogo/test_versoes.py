"""Versões (L0-03-l; ADR 0004 seção 4): 5 PUTs = 5 versões com diff correto; restaurar a 2ª gera a 6ª com o mesmo
sha256; lista paginada; sem edição não restaura (403); outro inquilino 404; 1.000 PUTs → compactação mantém
≤ 50 + pendentes/10 (função chamada direto e pelo job); publicar aponta versao_publicada; PUT com versão custa
≤ +5 ms sobre um UPDATE sem gatilho de versão (medida versao_custo_ms)."""

import statistics
import time

from tests.api.catalogo.conftest import titulo_zt
from tests.api.test_rls import contexto, ids_por_slug

ITEM = "L0-03-catalogo"


def test_cinco_puts_cinco_versoes_e_restaurar(sessao_a, itens_a, editor_a):
    it = itens_a.criar("mapa", resumo="v1")
    iid = it["id"]
    for n in range(2, 6):
        r = sessao_a.put(f"/api/itens/{iid}", json={"resumo": f"v{n}"})
        assert r.status_code == 200 and r.json()["versao_atual"] == n
    lista = sessao_a.get(f"/api/itens/{iid}/versoes?limite=3").json()
    assert lista["total"] == 5 and [v["versao"] for v in lista["itens"]] == [5, 4, 3]
    assert all(v["rotulo"] == "edicao" and len(v["sha256"]) == 64 and v["autor"]["login"] for v in lista["itens"])
    v3 = sessao_a.get(f"/api/itens/{iid}/versoes/3?diff_de=2").json()
    assert v3["corpo"]["resumo"] == "v3" and v3["diff"] == [{"op": "replace", "path": "/resumo", "value": "v3"}]
    assert sessao_a.get(f"/api/itens/{iid}/versoes/99").status_code == 404
    v2 = sessao_a.get(f"/api/itens/{iid}/versoes/2").json()
    r = sessao_a.post(f"/api/itens/{iid}/versoes/2/restaurar", json={"comentario": "volta"})
    assert r.status_code == 200 and r.json()["versao_atual"] == 6 and r.json()["resumo"] == "v2"
    v6 = sessao_a.get(f"/api/itens/{iid}/versoes/6").json()
    assert v6["sha256"] == v2["sha256"] and v6["rotulo"] == "restauracao" and v6["comentario"] == "volta"
    assert sessao_a.get(f"/api/itens/{iid}/versoes").json()["total"] == 6  # nunca apaga
    # sem edição: 403 (o item é visível por inquilino) ; outro inquilino: 404
    sessao_a.put(f"/api/itens/{iid}/compartilhamento", json={"acesso": "inquilino"})
    c, _ = editor_a
    assert c.get(f"/api/itens/{iid}/versoes").status_code == 200
    r = c.post(f"/api/itens/{iid}/versoes/2/restaurar", json={})
    assert r.status_code == 403 and r.json()["erro"] == "sem_edicao_no_item"
    # publicar
    r = sessao_a.post(f"/api/itens/{iid}/versoes/3/publicar")
    assert r.status_code == 200 and r.json()["versao_publicada"] == 3
    assert sessao_a.post(f"/api/itens/{iid}/versoes/42/publicar").status_code == 404


def test_versoes_de_outro_inquilino_404(sessao_a, itens_b):
    it = itens_b.criar("mapa")
    assert sessao_a.get(f"/api/itens/{it['id']}/versoes").status_code == 404
    assert sessao_a.post(f"/api/itens/{it['id']}/versoes/1/restaurar", json={}).status_code == 404


def test_mil_edicoes_e_compactacao(sessao_a, itens_a, conexao_plat_app, medida):
    it = itens_a.criar("mapa")
    iid = it["id"]
    ids = ids_por_slug(conexao_plat_app)
    with conexao_plat_app.cursor() as cur:
        cur.execute("SELECT usuario_id FROM plat.auth_login('demo', 'admin')")
        adm = cur.fetchone()["usuario_id"]
    contexto(conexao_plat_app, ids["demo"], usuario_id=adm, login="admin")
    tempos_com, tempos_sem = [], []
    with conexao_plat_app.cursor() as cur:
        for n in range(1000):
            t0 = time.perf_counter()
            cur.execute("UPDATE plat.item SET resumo = %s WHERE id = %s::uuid", (f"edição {n}", iid))
            tempos_com.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            cur.execute("UPDATE plat.item SET tamanho_bytes = %s WHERE id = %s::uuid", (n, iid))  # sem versão nova
            tempos_sem.append((time.perf_counter() - t0) * 1000)
        cur.execute("SELECT count(*) AS n, max(versao) AS v FROM plat.item_versao WHERE item_id = %s::uuid", (iid,))
        r = cur.fetchone()
        assert r["n"] == 1001 and r["v"] == 1001
        cur.execute("SELECT plat.item_versoes_compactar(%s::uuid, 50) AS removidas", (iid,))
        removidas = cur.fetchone()["removidas"]
        cur.execute("SELECT count(*) AS n, sum(compactou) AS c FROM plat.item_versao WHERE item_id = %s::uuid", (iid,))
        r = cur.fetchone()
    conexao_plat_app.commit()
    custo = statistics.median(tempos_com) - statistics.median(tempos_sem)
    medida(ITEM)(
        "versao_custo_ms",
        round(custo, 3),
        "ms",
        "mediana(UPDATE resumo, com versão) - mediana(UPDATE tamanho_bytes, sem versão), 1.000 pares como plat_app",
    )
    assert custo <= 5, custo
    assert r["n"] <= 50 + 1000 // 10 + 1, r["n"]
    assert removidas >= 800 and r["c"] >= 900
    lista = sessao_a.get(f"/api/itens/{iid}/versoes?limite=200").json()
    assert lista["total"] == r["n"] and any(
        v["compactou"] >= 10 and v["rotulo"] == "compactada" for v in lista["itens"]
    )
    assert sessao_a.get(f"/api/itens/{iid}").json()["versao_atual"] == 1001


def test_diff_forjado_nao_existe_e_titulo_ignora_versao_igual(sessao_a, itens_a):
    it = itens_a.criar("mapa")
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"titulo": it["titulo"]})  # mesmo retrato: sem versão nova
    assert r.status_code == 200 and r.json()["versao_atual"] == 1
    r = sessao_a.put(f"/api/itens/{it['id']}", json={"titulo": titulo_zt("novo")})
    assert r.json()["versao_atual"] == 2


def test_patch_rotulo_rascunho_nao_publica(sessao_a, itens_a):
    """item L5-09-desfazer-refazer-rascunho: `PATCH ?rotulo=rascunho` é o autosave — grava versão nova rotulada
    'rascunho' (não 'edicao') e nunca mexe em `versao_publicada` (só `.../publicar` muda isso). Qualquer outro
    valor de rótulo pedido pelo cliente é 422 (as outras palavras do enum só o servidor escreve sozinho)."""
    it = itens_a.criar("mapa", resumo="v1")
    iid = it["id"]
    r = sessao_a.post(f"/api/itens/{iid}/versoes/1/publicar")
    assert r.status_code == 200 and r.json()["versao_publicada"] == 1

    r = sessao_a.patch(f"/api/itens/{iid}?rotulo=rascunho", json={"resumo": "rascunho v2"})
    assert r.status_code == 200
    item = r.json()
    assert item["versao_atual"] == 2 and item["versao_publicada"] == 1, item

    versoes = sessao_a.get(f"/api/itens/{iid}/versoes?limite=5").json()["itens"]
    por_versao = {v["versao"]: v["rotulo"] for v in versoes}
    assert por_versao == {1: "edicao", 2: "rascunho"}, por_versao

    # a versão publicada (1) continua com o conteúdo de antes, imutável
    v1 = sessao_a.get(f"/api/itens/{iid}/versoes/1").json()
    assert v1["corpo"]["resumo"] == "v1"

    # PATCH normal (sem o parâmetro) continua rotulando 'edicao', como sempre
    r = sessao_a.patch(f"/api/itens/{iid}", json={"resumo": "v3"})
    assert r.status_code == 200 and r.json()["versao_atual"] == 3
    versoes = sessao_a.get(f"/api/itens/{iid}/versoes?limite=5").json()["itens"]
    assert {v["versao"]: v["rotulo"] for v in versoes}[3] == "edicao"

    # nenhum outro rótulo entra por fora
    r = sessao_a.patch(f"/api/itens/{iid}?rotulo=publicacao", json={"resumo": "v4"})
    assert r.status_code == 422, r.text
    r = sessao_a.put(f"/api/itens/{iid}?rotulo=rascunho", json={"resumo": "v5"})  # PUT não aceita o parâmetro
    assert r.status_code == 200  # ignorado silenciosamente pelo FastAPI (rota sem o parâmetro declarado)
    versoes = sessao_a.get(f"/api/itens/{iid}/versoes?limite=5").json()["itens"]
    assert {v["versao"]: v["rotulo"] for v in versoes}.get(4) == "edicao"

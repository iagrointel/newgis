"""Identidade e numeração de ativos (item L4-28-identificadores-e-numeracao) — portão cláusula a cláusula:

1. "reservar faixa de 100 códigos para um usuário e criar 100 ativos offline sem colisão (teste)" ->
   test_reserva_100_e_cria_100_offline_sem_colisao;
2. "código externo duplicado recusado" -> test_codigo_externo_duplicado_recusado (+ escopo por rede/inquilino);
3. "renomear mantém o global_id e grava histórico" -> test_renomear_mantem_global_id_e_grava_historico;
4. "API unitIdentifiers da fachada Esri mapeada" -> test_fachada_esri_* (descritor, reserve, query);
5. refutação: "adversário reserva a mesma faixa em dois clientes e confere que o segundo recebe outra" ->
   test_reservas_concorrentes_recebem_faixas_disjuntas (10 reservas em threads, duas sessões).
"""

import concurrent.futures

import psycopg2
import pytest

from app.rede_utilidades import instalados
from app.schema_ambiente import CursorSchemaAmbiente  # honra PLAT_SCHEMA (base própria por trilha)
from tests.api.conftest import PREFIXO_TESTE
from tests.api.test_rls import contexto, ids_por_slug

N = 100  # o tamanho de faixa do portão


@pytest.fixture
def limpar_redes(sessao_a, sessao_b):
    criadas = []
    yield criadas
    for sessao, rid in criadas:
        sessao.delete(f"/api/rede/{rid}")


def _rede_com_pacote(sessao, limpar, sufixo):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-ident-{sufixo}", "disciplina": "agua"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append((sessao, rid))
    bruto = instalados.bruto("agua-epanet")
    r = sessao.post(f"/api/rede/{rid}/pacote", content=bruto,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


@pytest.fixture
def tipo_id(sessao_a, env):
    """O tipo_id de uma rede é dado do inquilino: vem do banco com o contexto RLS do inquilino demo."""
    cache = {}

    def pegar(rede_id):
        if rede_id in cache:
            return cache[rede_id]
        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        try:
            ids = ids_por_slug(con)
            contexto(con, ids["demo"])
            with con.cursor() as cur:
                cur.execute(
                    "SELECT id FROM plat.rede_tipo WHERE rede_id = %s::uuid ORDER BY codigo LIMIT 1",
                    (rede_id,))
                r = cur.fetchone()
                assert r, "rede sem tipo de ativo (o pacote agua-epanet tem tipos)"
                cache[rede_id] = str(r["id"])
        finally:
            con.close()
        return cache[rede_id]

    return pegar


def _criar_offline(sessao, rid, tid, numero, codigo=None):
    return sessao.post(f"/api/rede/{rid}/ativos",
                       json={"tipo_id": tid, "numero": numero, "codigo_externo": codigo})


# --- cláusula 1: reservar 100 e criar 100 offline sem colisão -----------------------------------------

def test_reserva_100_e_cria_100_offline_sem_colisao(sessao_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "cem")
    tid = tipo_id(rid)
    r = sessao_a.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": N})
    assert r.status_code == 201, r.text
    faixa = r.json()
    assert faixa["tamanho"] == N and faixa["fim"] - faixa["inicio"] + 1 == N
    assert faixa["estado"] == "aberta" and faixa["consumidos"] == 0

    global_ids, numeros = set(), set()
    for i in range(N):
        numero = faixa["inicio"] + i
        r = _criar_offline(sessao_a, rid, tid, numero, codigo=f"COD-{i:03d}")
        assert r.status_code == 201, (i, r.text)
        corpo = r.json()
        global_ids.add(corpo["global_id"])
        numeros.add(corpo["numero"])
    assert len(global_ids) == N and len(numeros) == N, "colisão: global_id ou número repetido"

    # o centésimo primeiro número da faixa não existe: o próximo pedido offline é recusado
    r = _criar_offline(sessao_a, rid, tid, faixa["fim"] + 1)
    assert r.status_code == 422 and r.json()["erro"] == "numero_fora_de_faixa", r.text
    # e repetir um número já consumido é colisão de verdade: 409
    r = _criar_offline(sessao_a, rid, tid, faixa["inicio"])
    assert r.status_code == 409 and r.json()["erro"] == "numero_em_uso", r.text

    # a faixa consta esgotada com os 100 consumidos
    f = sessao_a.get(f"/api/rede/{rid}/faixas?minhas=true").json()["itens"][0]
    assert f["consumidos"] == N and f["estado"] == "esgotada"


def test_criacao_conectada_nunca_recebe_numero_reservado(sessao_a, limpar_redes, tipo_id):
    """O contador pula a faixa reservada: depois de reservar [1..100], a criação online recebe 101."""
    rid = _rede_com_pacote(sessao_a, limpar_redes, "pula-faixa")
    tid = tipo_id(rid)
    faixa = sessao_a.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": N}).json()
    r = sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "ONLINE-1"})
    assert r.status_code == 201, r.text
    assert r.json()["numero"] == faixa["fim"] + 1


def test_numero_na_faixa_de_outro_usuario_e_recusado(sessao_a, usuarios_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "faixa-alheia")
    tid = tipo_id(rid)
    faixa = sessao_a.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": 10}).json()
    outro, _, _ = usuarios_a.sessao(perfil="editor")
    r = _criar_offline(outro, rid, tid, faixa["inicio"])
    assert r.status_code == 422 and r.json()["erro"] == "numero_fora_de_faixa", r.text


# --- refutação: dois clientes reservando ao mesmo tempo recebem faixas disjuntas -----------------------

def test_reservas_concorrentes_recebem_faixas_disjuntas(sessao_a, usuarios_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "corrida")
    tid = tipo_id(rid)
    segundo, _, _ = usuarios_a.sessao(perfil="editor")
    sessoes = [sessao_a, segundo]

    def reservar(i):
        s = sessoes[i % 2]
        r = s.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": 10})
        assert r.status_code == 201, r.text
        return r.json()["inicio"], r.json()["fim"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        faixas = list(ex.map(reservar, range(10)))
    faixas.sort()
    for (i1, f1), (i2, f2) in zip(faixas, faixas[1:]):
        assert f1 < i2, f"faixas sobrepostas: [{i1},{f1}] e [{i2},{f2}]"
    # e nenhuma veio vazia ou repetida: 10 blocos de 10 = 100 números distintos
    assert sum(f - i + 1 for i, f in faixas) == 100


# --- cláusula 2: código externo duplicado recusado -----------------------------------------------------

def test_codigo_externo_duplicado_recusado(sessao_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "codigo-dup")
    tid = tipo_id(rid)
    r = sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "TR-0001"})
    assert r.status_code == 201, r.text
    r = sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "TR-0001"})
    assert r.status_code == 409 and r.json()["erro"] == "codigo_externo_existente", r.text


@pytest.fixture
def tipo_id_b(sessao_b, env):
    """tipo_id de rede do inquilino demo2 (contexto RLS de demo2)."""
    def pegar(rede_id):
        con = psycopg2.connect(env["PLAT_DSN"], cursor_factory=CursorSchemaAmbiente)
        try:
            ids = ids_por_slug(con)
            contexto(con, ids["demo2"])
            with con.cursor() as cur:
                cur.execute(
                    "SELECT id FROM plat.rede_tipo WHERE rede_id = %s::uuid ORDER BY codigo LIMIT 1",
                    (rede_id,))
                r = cur.fetchone()
                assert r, "rede sem tipo de ativo"
                return str(r["id"])
        finally:
            con.close()
    return pegar


def test_codigo_externo_mesmo_codigo_em_outra_rede_e_aceito(sessao_a, sessao_b, limpar_redes,
                                                            tipo_id, tipo_id_b):
    rid_a = _rede_com_pacote(sessao_a, limpar_redes, "mesmo-cod-a")
    rid_a2 = _rede_com_pacote(sessao_a, limpar_redes, "mesmo-cod-a2")
    rid_b = _rede_com_pacote(sessao_b, limpar_redes, "mesmo-cod-b")
    r = sessao_a.post(f"/api/rede/{rid_a}/ativos",
                      json={"tipo_id": tipo_id(rid_a), "codigo_externo": "REP-1"})
    assert r.status_code == 201, r.text
    # outra rede, mesmo inquilino: aceito (único por rede)
    r = sessao_a.post(f"/api/rede/{rid_a2}/ativos",
                      json={"tipo_id": tipo_id(rid_a2), "codigo_externo": "REP-1"})
    assert r.status_code == 201, r.text
    # outro inquilino: aceito (isolamento por RLS)
    r = sessao_b.post(f"/api/rede/{rid_b}/ativos",
                      json={"tipo_id": tipo_id_b(rid_b), "codigo_externo": "REP-1"})
    assert r.status_code == 201, r.text


# --- cláusula 3: renomear mantém global_id e grava histórico ------------------------------------------

def test_renomear_mantem_global_id_e_grava_historico(sessao_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "renomear")
    tid = tipo_id(rid)
    r = sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "ANTIGO-1"})
    gid = r.json()["global_id"]

    r = sessao_a.patch(f"/api/rede/{rid}/ativos/{gid}", json={"codigo_externo": "NOVO-1"})
    assert r.status_code == 200, r.text
    assert r.json()["global_id"] == gid and r.json()["codigo_externo"] == "NOVO-1"

    r = sessao_a.patch(f"/api/rede/{rid}/ativos/{gid}", json={"codigo_externo": "NOVO-2"})
    assert r.status_code == 200 and r.json()["global_id"] == gid

    h = sessao_a.get(f"/api/rede/{rid}/ativos/{gid}/renomeacoes").json()
    assert h["total"] == 2
    assert [(i["codigo_externo_anterior"], i["codigo_externo_novo"]) for i in h["itens"]] == [
        ("ANTIGO-1", "NOVO-1"), ("NOVO-1", "NOVO-2")]

    # o código liberado pela renomeação volta a poder ser usado por outro ativo
    r = sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "ANTIGO-1"})
    assert r.status_code == 201, r.text
    # e renomear PARA um código em uso é recusado
    r = sessao_a.patch(f"/api/rede/{rid}/ativos/{gid}", json={"codigo_externo": "ANTIGO-1"})
    assert r.status_code == 409 and r.json()["erro"] == "codigo_externo_existente", r.text
    # renomear pelo MESMO código é idempotente: 200 sem linha nova de histórico
    r = sessao_a.patch(f"/api/rede/{rid}/ativos/{gid}", json={"codigo_externo": "NOVO-2"})
    assert r.status_code == 200
    assert sessao_a.get(f"/api/rede/{rid}/ativos/{gid}/renomeacoes").json()["total"] == 2


# --- cláusula 4: fachada Esri unitIdentifiers ----------------------------------------------------------

UN = "/rest/services/{s}/UtilityNetworkServer/unitIdentifiers"


def test_fachada_esri_descritor_reserve_e_query(sessao_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "esri")
    tid = tipo_id(rid)

    r = sessao_a.get(UN.format(s=rid))
    assert r.status_code == 200, r.text
    assert r.json()["operations"] == ["query", "reserve"] and r.json()["currentVersion"] == 12.1

    # reserve com a extensão count (próximo bloco livre) — a forma documentada para campo
    r = sessao_a.post(UN.format(s=rid) + "/reserve",
                      data={"object": f'{{"sourceId": 9, "globalId": "{tid}"}}', "count": "50", "f": "json"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["success"] is True
    ui = corpo["unitIdentifiers"][0]
    assert ui["sourceId"] == 9 and ui["lastUnit"] - ui["firstUnit"] + 1 == 50

    # reserve com bloco EXATO (firstUnit/lastUnit), a forma Esri
    r = sessao_a.post(UN.format(s=rid) + "/reserve",
                      data={"object": f'{{"sourceId": 9, "globalId": "{tid}"}}',
                            "firstUnit": "1001", "lastUnit": "1100", "f": "json"})
    assert r.status_code == 200, r.text
    ui2 = r.json()["unitIdentifiers"][0]
    assert (ui2["firstUnit"], ui2["lastUnit"]) == (1001, 1100)

    # bloco exato que sobrepõe o anterior: recusado
    r = sessao_a.post(UN.format(s=rid) + "/reserve",
                      data={"object": f'{{"sourceId": 9, "globalId": "{tid}"}}',
                            "firstUnit": "1050", "lastUnit": "1200", "f": "json"})
    assert r.status_code == 409, r.text

    # query: as duas faixas aparecem como unitIdentifiers; a lacuna [51,1000] aparece como gap
    r = sessao_a.get(UN.format(s=rid) + "/query",
                     params={"objects": f'[{{"sourceId": 9, "globalIds": ["{tid}"]}}]', "f": "json"})
    assert r.status_code == 200, r.text
    obj = r.json()["objects"][0]
    faixas = {(u["firstUnit"], u["lastUnit"]) for u in obj["unitIdentifiers"]}
    assert faixas == {(ui["firstUnit"], ui["lastUnit"]), (1001, 1100)}
    assert {"start": 51, "end": 1000} in obj["gaps"]


def test_fachada_esri_resolve_servico_por_nome_e_token_na_url(sessao_a, usuarios_a, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "esri-nome")
    tid = tipo_id(rid)
    nome = sessao_a.get(f"/api/rede/{rid}").json()["nome"]
    r = sessao_a.get(UN.format(s=nome))
    assert r.status_code == 200, r.text
    # ?token= (protocolo Esri, sem cabeçalho): token de serviço com escopo catalogo:ler
    editor, u, _ = usuarios_a.sessao(perfil="editor")
    tok = editor.post("/api/tokens", json={"nome": f"{PREFIXO_TESTE}-un", "escopos": ["catalogo:ler"]}).json()
    from tests.api.conftest import novo_cliente
    anon = novo_cliente()
    r = anon.get(UN.format(s=rid), params={"token": tok["token"]})
    assert r.status_code == 200, r.text
    r = anon.get(UN.format(s=rid))  # sem token nenhum: 401
    assert r.status_code == 401
    editor.delete(f"/api/tokens/{tok['id']}")


# --- isolamento entre inquilinos (RLS) -----------------------------------------------------------------

def test_inquilino_b_nao_ve_ativos_nem_faixas_de_a(sessao_a, sessao_b, limpar_redes, tipo_id):
    rid = _rede_com_pacote(sessao_a, limpar_redes, "rls")
    tid = tipo_id(rid)
    sessao_a.post(f"/api/rede/{rid}/ativos", json={"tipo_id": tid, "codigo_externo": "SO-DE-A"})
    sessao_a.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": 5})
    # para o inquilino B a rede nem existe (RLS esconde): 404 em tudo
    assert sessao_b.get(f"/api/rede/{rid}/ativos").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/faixas").status_code == 404
    assert sessao_b.post(f"/api/rede/{rid}/faixas", json={"tipo_id": tid, "quantidade": 5}).status_code == 404

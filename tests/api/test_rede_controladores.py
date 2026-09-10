"""Controlador de subrede e tiers (item L4-04-a-controladores-e-tiers).

Cláusulas do portão provadas aqui:
1. `POST .../controlador` e `DELETE` com validação de categoria — `test_definir_controlador_no_disjuntor`,
   `test_controlador_em_poste_e_recusado`, `test_remover_controlador_apaga_a_subrede_sem_controlador`;
2. a marcação a partir da importação marca 1 controlador por CTMT (pelo terminal do disjuntor quando o
   arquivo traz o equipamento, pelo nó de cabeça quando não traz) e 1 por transformador no tier de baixa
   tensão — `test_importar_marca_um_por_ctmt_e_um_por_trafo`;
3. `plat.rede_subrede` lista as subredes com controlador, tier, estado (limpa/suja) e resumo —
   `test_tabela_de_subredes_lista_tier_estado_e_resumo`;
4. a ficha do controlador (`GET .../controlador/{id}`) — `test_ficha_do_controlador`; a da TELA está no e2e
   `tests/e2e/test_rede_controladores.py`;
5. tiers: hierarquia declarada e tipo — `test_tiers_na_ordem_da_hierarquia`.

Refutação (papel adversário), provada aqui:
- `test_controlador_em_poste_e_recusado`: poste (categoria `estrutura_de_suporte`) é recusado;
- `test_dois_controladores_com_o_mesmo_nome_no_tier_sao_recusados`: nome de controlador repetido dentro do
  MESMO tier é recusado — a regra da fonte é "a unique name for the controller in the tier must be
  provided"; o nome da SUBREDE é que pode reunir vários controladores
  (`test_uma_subrede_aceita_dois_controladores_com_nomes_diferentes`)."""

import pytest

from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-04-a-controladores-e-tiers"

CTMT_COM_EQUIPAMENTO = "1_TST_1"
CTMT_SEM_EQUIPAMENTO = "2_TST_1"
SUB = "TST"
DISJUNTOR = 4  # tipo de ativo `disjuntor` dentro do grupo chave_de_media_tensao (pacote eletrica-br)


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-ctrl-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _linha(sessao, rid, coordenadas, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "coordenadas": coordenadas}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat}
    if atributos:
        corpo["atributos"] = atributos
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _habilitar(sessao, rid):
    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    return r.json()


def _rede_bdgd(sessao, rid, lon0=30.0, lat0=10.0):
    """Rede no formato da BDGD Módulo 10, pequena e explícita, com os DOIS casos do portão:

      * alimentador `1_TST_1`: tem o disjuntor de saída (grupo `chave_de_media_tensao`, tipo `disjuntor`),
        com o mesmo `ctmt` nos atributos — a marcação tem de usar o TERMINAL dele;
      * alimentador `2_TST_1`: os trechos existem, o equipamento de saída NÃO — a marcação cai no nó de
        cabeça, e o controlador nasce com `origem='no_de_cabeca'`.

    Um transformador de distribuição fica no fim do primeiro alimentador, com um trecho de BAIXA tensão
    saindo dele: é o que faz a topologia separar o terminal de alta do de baixa (regra do tier)."""
    d = 0.001
    a, b, c = (lon0, lat0), (lon0 + d, lat0), (lon0 + 2 * d, lat0)
    bt = (lon0 + 2 * d, lat0 + d)
    a2, b2 = (lon0, lat0 + 10 * d), (lon0 + d, lat0 + 10 * d)
    at1 = {"ctmt": CTMT_COM_EQUIPAMENTO, "sub": SUB}
    at2 = {"ctmt": CTMT_SEM_EQUIPAMENTO, "sub": SUB}
    disjuntor = _ponto(sessao, rid, *a, "chave_de_media_tensao", DISJUNTOR, atributos=at1)
    _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao", atributos={**at1, "cod_id": "MT1"})
    _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao", atributos={**at1, "cod_id": "MT2"})
    trafo = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1, atributos={"cod_id": "TR1"})
    _linha(sessao, rid, [list(c), list(bt)], "trecho_de_baixa_tensao", atributos={"cod_id": "BT1"})
    _linha(sessao, rid, [list(a2), list(b2)], "trecho_de_media_tensao", atributos={**at2, "cod_id": "MT3"})
    poste = _ponto(sessao, rid, lon0 + 3 * d, lat0, "ponto_notavel", 1)
    _habilitar(sessao, rid)
    return {"disjuntor": disjuntor, "trafo": trafo, "poste": poste}


# --- cláusula 1: definir e remover, com validação de categoria ------------------------------------------

def test_definir_controlador_no_disjuntor(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "definir", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": CTMT_COM_EQUIPAMENTO,
        "tier": "media_tensao", "papel": "fonte"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["subrede"] == CTMT_COM_EQUIPAMENTO
    assert c["tier"] == "media_tensao" and c["tier_tipo"] == "hierarquico"
    assert c["terminal"] == 2 and c["papel"] == "fonte" and c["origem"] == "dispositivo"
    assert c["tipo_chave"] == "disjuntor"
    assert c["no_id"], "o controlador tem de apontar um nó da topologia corrente"


def test_controlador_em_poste_e_recusado(sessao_a, limpar_redes):
    """Refutação do adversário: poste é `estrutura_de_suporte`, nunca `controlador`."""
    rid = _criar_rede(sessao_a, "poste", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["poste"]["id"], "subrede": "qualquer", "tier": "estrutura"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "categoria_nao_controladora", r.text


def test_terminal_inexistente_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "terminal-ruim", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["trafo"]["id"], "terminal": 5, "subrede": "TR1", "tier": "baixa_tensao"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "terminal_invalido", r.text


def test_terminal_obrigatorio_quando_o_tipo_tem_dois(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "terminal-faltando", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["trafo"]["id"], "subrede": "TR1", "tier": "baixa_tensao"})
    assert r.status_code == 422, r.text
    assert r.json()["erro"] == "terminal_obrigatorio", r.text


def test_dois_controladores_com_o_mesmo_nome_no_tier_sao_recusados(sessao_a, limpar_redes):
    """Refutação do adversário: o nome do controlador é único DENTRO DO TIER."""
    rid = _criar_rede(sessao_a, "nome-repetido", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    primeiro = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": CTMT_COM_EQUIPAMENTO,
        "tier": "media_tensao", "nome": "saida-1"})
    assert primeiro.status_code == 201, primeiro.text
    segundo = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["trafo"]["id"], "terminal": 1, "subrede": "outra-subrede",
        "tier": "media_tensao", "nome": "saida-1"})
    assert segundo.status_code == 409, segundo.text
    assert segundo.json()["erro"] == "nome_de_controlador_repetido", segundo.text


def test_uma_subrede_aceita_dois_controladores_com_nomes_diferentes(sessao_a, limpar_redes):
    """"Both radial and mesh subnetworks support multiple subnetwork controllers": o que não pode repetir é
    o NOME do controlador dentro do tier, não a subrede."""
    rid = _criar_rede(sessao_a, "dois-controladores", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    a = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": "alimentador-x",
        "tier": "media_tensao", "nome": "ctrl-a"})
    assert a.status_code == 201, a.text
    b = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["trafo"]["id"], "terminal": 1, "subrede": "alimentador-x",
        "tier": "media_tensao", "nome": "ctrl-b"})
    assert b.status_code == 201, b.text
    assert b.json()["subrede_id"] == a.json()["subrede_id"]
    subredes = sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"]
    alvo = [s for s in subredes if s["nome"] == "alimentador-x"]
    assert len(alvo) == 1 and len(alvo[0]["controladores"]) == 2, subredes


def test_mesmo_terminal_duas_vezes_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "terminal-repetido", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    base = {"feicao_id": rede["disjuntor"]["id"], "terminal": 2, "tier": "media_tensao"}
    assert sessao_a.post(f"/api/rede/{rid}/controlador",
                         json={**base, "subrede": "s1", "nome": "n1"}).status_code == 201
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={**base, "subrede": "s2", "nome": "n2"})
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "terminal_ja_controlador", r.text


def test_remover_controlador_apaga_a_subrede_sem_controlador(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "remover", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": CTMT_COM_EQUIPAMENTO,
        "tier": "media_tensao"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert sessao_a.get(f"/api/rede/{rid}/subredes").json()["total"] == 1
    assert sessao_a.delete(f"/api/rede/{rid}/controlador/{cid}").status_code == 204
    assert sessao_a.get(f"/api/rede/{rid}/subredes").json()["total"] == 0
    assert sessao_a.get(f"/api/rede/{rid}/controlador/{cid}").status_code == 404


# --- cláusula 2: marcação a partir da importação --------------------------------------------------------

def test_importar_marca_um_por_ctmt_e_um_por_trafo(sessao_a, limpar_redes, medida):
    rid = _criar_rede(sessao_a, "importar", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    contagem = r.json()
    assert contagem["alimentadores"] == 2, contagem
    assert contagem["alimentadores_por_dispositivo"] == 1, contagem
    assert contagem["alimentadores_por_no_de_cabeca"] == 1, contagem
    assert contagem["transformadores"] == 1 and contagem["transformadores_marcados"] == 1, contagem
    assert contagem["tier_media_tensao"] == "media_tensao"
    assert contagem["tier_baixa_tensao"] == "baixa_tensao"

    itens = sessao_a.get(f"/api/rede/{rid}/controladores").json()["itens"]
    por_nome = {c["nome"]: c for c in itens}
    assert set(por_nome) == {CTMT_COM_EQUIPAMENTO, CTMT_SEM_EQUIPAMENTO, "TR1"}, por_nome
    com = por_nome[CTMT_COM_EQUIPAMENTO]
    assert com["origem"] == "dispositivo" and com["feicao_id"] == rede["disjuntor"]["id"]
    assert com["tier"] == "media_tensao"
    sem = por_nome[CTMT_SEM_EQUIPAMENTO]
    assert sem["origem"] == "no_de_cabeca" and sem["feicao_id"] is None
    assert sem["no_id"], "o nó de cabeça tem de resolver para um nó da topologia corrente"
    tr = por_nome["TR1"]
    assert tr["tier"] == "baixa_tensao" and tr["terminal"] == 2, tr
    assert tr["feicao_id"] == rede["trafo"]["id"]

    de_novo = sessao_a.post(f"/api/rede/{rid}/controladores/importar").json()
    assert de_novo["alimentadores_por_dispositivo"] == 0 and de_novo["transformadores_marcados"] == 0
    assert de_novo["ja_marcados"] == 3, de_novo  # 1 disjuntor + 1 nó de cabeça + 1 transformador
    assert sessao_a.get(f"/api/rede/{rid}/controladores").json()["total"] == 3

    gravar = medida(ITEM)
    comando = "bash laco/roda_teste.sh tests/api/test_rede_controladores.py"
    gravar("alimentadores_marcados_por_dispositivo", contagem["alimentadores_por_dispositivo"],
           "alimentadores", comando)
    gravar("alimentadores_marcados_por_no_de_cabeca", contagem["alimentadores_por_no_de_cabeca"],
           "alimentadores", comando)
    gravar("transformadores_marcados", contagem["transformadores_marcados"], "transformadores", comando)
    gravar("controladores_apos_segunda_importacao", 3, "controladores",
           comando + " (a marcação é idempotente: a 2ª rodada não duplica)")


def test_importar_sem_topologia_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-topologia", limpar_redes)
    r = sessao_a.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 409, r.text
    assert r.json()["erro"] == "topologia_inexistente", r.text


# --- cláusula 3: a tabela de subredes --------------------------------------------------------------------

def test_tabela_de_subredes_lista_tier_estado_e_resumo(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "subredes", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    assert sessao_a.post(f"/api/rede/{rid}/controladores/importar").status_code == 200

    itens = sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"]
    assert {s["nome"] for s in itens} == {CTMT_COM_EQUIPAMENTO, CTMT_SEM_EQUIPAMENTO, "TR1"}
    assert all(s["estado"] == "suja" for s in itens), "subrede recém-controlada nasce suja"
    assert all(s["resumo"] == {} for s in itens)
    assert [s["tier_ordem"] for s in itens] == sorted(s["tier_ordem"] for s in itens)

    alvo = [s for s in itens if s["nome"] == CTMT_COM_EQUIPAMENTO][0]
    r = sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar")
    assert r.status_code == 200, r.text
    atualizada = r.json()
    assert atualizada["estado"] == "limpa"
    assert atualizada["resumo"]["elementos"] > 0 and atualizada["resumo"]["controladores"] == 1

    depois = sessao_a.get(f"/api/rede/{rid}/subredes", params={"tier": "media_tensao"}).json()["itens"]
    limpa = [s for s in depois if s["nome"] == CTMT_COM_EQUIPAMENTO][0]
    assert limpa["estado"] == "limpa" and limpa["atualizado_em"]
    assert limpa["resumo"]["elementos"] == atualizada["resumo"]["elementos"]
    assert {s["tier"] for s in depois} == {"media_tensao"}, "o filtro por tier tem de filtrar"


def test_edicao_depois_da_topologia_deixa_a_subrede_suja(sessao_a, limpar_redes):
    """Ciclo de vida: a subrede limpa volta a suja quando a edição TOCA um elemento dela.

    Atualizado no item L4-04-b: a versão anterior deste teste dava a subrede por suja diante de QUALQUER área
    suja da rede, mesmo a quilômetros dela. Isso é grosseiro demais para a cooperativa (uma edição num
    alimentador sujaria os outros noventa) e contraria a cláusula do portão do L4-04-b — "só as 2 subredes
    afetadas ficam sujas". Aqui ficam os dois lados da mesma regra: edição LONGE não suja; edição EM CIMA
    suja, e a marcação fica gravada no registro (`estado_gravado`), porque reconstruir a topologia apaga a
    área suja e o estado da subrede não pode desaparecer com ela."""
    rid = _criar_rede(sessao_a, "ciclo-de-vida", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    assert sessao_a.post(f"/api/rede/{rid}/controladores/importar").status_code == 200
    alvo = [s for s in sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"]
            if s["nome"] == CTMT_COM_EQUIPAMENTO][0]
    assert sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar").status_code == 200

    _ponto(sessao_a, rid, 40.0, 40.0, "banco_de_capacitores")
    longe = [s for s in sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"]
             if s["nome"] == CTMT_COM_EQUIPAMENTO][0]
    assert longe["estado"] == "limpa", "edição longe da subrede não a suja"
    assert longe["areas_sujas_abertas"] >= 1, "a área suja da rede existe, só não toca esta subrede"

    # o disjuntor da rede de teste fica em (30.0, 10.0), o começo do primeiro trecho de média tensão
    _ponto(sessao_a, rid, 30.0, 10.0, "banco_de_capacitores")
    depois = [s for s in sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"]
              if s["nome"] == CTMT_COM_EQUIPAMENTO][0]
    assert depois["estado"] == "suja", depois
    assert depois["estado_gravado"] == "suja", "a marcação fica gravada e sobrevive a reconstruir a topologia"
    assert depois["tocada_por_area_suja"] is True


def test_atualizar_subrede_sem_controlador_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "sem-controlador", limpar_redes)
    _rede_bdgd(sessao_a, rid)
    assert sessao_a.post(f"/api/rede/{rid}/controladores/importar").status_code == 200
    alvo = sessao_a.get(f"/api/rede/{rid}/subredes").json()["itens"][0]
    for c in alvo["controladores"]:
        assert sessao_a.delete(f"/api/rede/{rid}/controlador/{c['id']}").status_code == 204
    r = sessao_a.post(f"/api/rede/{rid}/subredes/{alvo['id']}/atualizar")
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "subrede_inexistente", r.text


# --- cláusula 4: a ficha do controlador -----------------------------------------------------------------

def test_ficha_do_controlador(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "ficha", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    cid = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["trafo"]["id"], "terminal": 2, "subrede": "TR1",
        "tier": "baixa_tensao", "papel": "fonte"}).json()["id"]
    ficha = sessao_a.get(f"/api/rede/{rid}/controlador/{cid}").json()
    assert ficha["grupo"] == "transformador_de_distribuicao"
    assert ficha["tipo_chave"] == "transformador_de_distribuicao"
    assert ficha["tier_nome"] == "Baixa tensão" and ficha["tier_ordem"] == 3
    assert ficha["terminal"] == 2 and ficha["papel"] == "fonte"
    assert ficha["lon"] and ficha["lat"]


def test_controlador_sobrevive_a_reconstrucao_da_topologia(sessao_a, limpar_redes):
    """A âncora é a feição + o terminal, nunca o nó: reconstruir a topologia inteira não apaga controlador
    nenhum, e o `no_id` volta a resolver para o nó novo."""
    rid = _criar_rede(sessao_a, "reconstruir", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    cid = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": CTMT_COM_EQUIPAMENTO,
        "tier": "media_tensao"}).json()["id"]
    no_antes = sessao_a.get(f"/api/rede/{rid}/controlador/{cid}").json()["no_id"]
    _habilitar(sessao_a, rid)
    depois = sessao_a.get(f"/api/rede/{rid}/controlador/{cid}").json()
    assert depois["no_id"], "o controlador tem de reencontrar um nó depois da reconstrução"
    assert depois["no_id"] != no_antes, "a reconstrução cria nós novos (ids novos)"


# --- cláusula 5: tiers -----------------------------------------------------------------------------------

def test_tiers_na_ordem_da_hierarquia(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "tiers", limpar_redes)
    itens = sessao_a.get(f"/api/rede/{rid}/tiers").json()["itens"]
    eletricos = [t for t in itens if t["dominio"] == "eletrica_distribuicao"]
    assert [t["codigo"] for t in eletricos] == ["subtransmissao", "media_tensao", "baixa_tensao"]
    assert [t["ordem"] for t in eletricos] == [1, 2, 3]
    assert all(t["tipo"] == "hierarquico" for t in eletricos)
    estrutura = [t for t in itens if t["codigo"] == "estrutura"][0]
    assert estrutura["tipo"] == "particionado"
    assert all(t["subredes"] == 0 and t["controladores"] == 0 for t in itens)


def test_tier_inexistente_e_recusado(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "tier-ruim", limpar_redes)
    rede = _rede_bdgd(sessao_a, rid)
    r = sessao_a.post(f"/api/rede/{rid}/controlador", json={
        "feicao_id": rede["disjuntor"]["id"], "terminal": 2, "subrede": "x", "tier": "nao-existe"})
    assert r.status_code == 404, r.text
    assert r.json()["erro"] == "tier_inexistente", r.text

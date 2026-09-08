"""Configuração de traçado nomeada e compartilhável (item L4-02-e-configuracoes-de-tracado).

Cláusulas do portão provadas aqui, sobre uma rede pequena no vocabulário da BDGD com número redondo em cada
atributo — tudo conferível à mão:

  1. CRUD em `/api/rede/{id}/config_tracado` e uso por `config_id` no endpoint de traçado que já existia:
     `test_ciclo_de_vida_da_configuracao`, `test_tracar_por_config_id_usa_o_pedido_salvo`;
  2. ≥ 6 configurações prontas no pacote elétrica-BR, instaladas com o pacote:
     `test_pacote_traz_as_seis_configuracoes_prontas`;
  3. a função Σ kVA a jusante soma a potência nominal dos transformadores alcançados:
     `test_kva_a_jusante_soma_a_potencia_dos_trafos_alcancados` (a mesma conta contra o ARQUIVO da
     cooperativa de teste está em `test_rede_config_tracado_medida.py`, marcada `lento`);
  4. barreira de condição, barreira de filtro, filtro de saída, funções e tipos de resultado:
     `test_isolamento_para_na_chave_fusivel`, `test_barreira_de_filtro_estreita_sem_mudar_a_travessia`,
     `test_filtro_de_saida_por_fase_e_categoria`, `test_tipo_de_resultado_geometria_e_conectividade`,
     `test_incluir_estrutura_traz_o_poste_coincidente`;
  5. recusas: atributo inexistente, operador inválido, função desconhecida, código repetido —
     `test_recusa_atributo_inexistente_e_operador_invalido`, `test_recusa_funcao_e_resultado_desconhecidos`;
  6. a configuração NÃO atravessa inquilino: `test_configuracao_nao_aparece_em_outro_inquilino`.

A rede de teste (uma cooperativa de teste, nunca nome de cliente): um disjuntor de saída, dois ramos de
média tensão, uma chave fusível num deles, dois transformadores (75 e 45 kVA), duas unidades consumidoras e
um poste sob o transformador. A conta que o portão pede é 75 + 45 = 120 kVA a jusante do disjuntor, e 45 kVA
quando a chave fusível vira barreira."""

import pytest

from tests.api.conftest import PREFIXO_TESTE

ITEM = "L4-02-e-configuracoes-de-tracado"

CTMT = "1_CFG_1"
DISJUNTOR, FUSIVEL = 4, 2        # tipos dentro do grupo chave_de_media_tensao (pacote eletrica-br)
UC_BT, POSTE = 1, 1              # consumidor_de_baixa_tensao; poste dentro de ponto_notavel
LON0, LAT0, D = 34.0, 11.0, 0.001


@pytest.fixture
def limpar_redes(sessao_a):
    criadas = []
    yield criadas
    for rid in criadas:
        sessao_a.delete(f"/api/rede/{rid}")


def _criar_rede(sessao, sufixo, limpar):
    r = sessao.post("/api/rede", json={"nome": f"{PREFIXO_TESTE}-cfg-{sufixo}", "disciplina": "eletrica"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    limpar.append(rid)
    from app.rede_utilidades import instalados

    r = sessao.post(f"/api/rede/{rid}/pacote", content=instalados.bruto("eletrica-br"),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201, r.text
    return rid


def _ponto(sessao, rid, lon, lat, grupo, tipo_codigo=1, atributos=None):
    corpo = {"tipo_codigo": tipo_codigo, "grupo": grupo, "lon": lon, "lat": lat,
             "atributos": atributos or {}}
    r = sessao.post(f"/api/rede/{rid}/feicoes/pontos", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _linha(sessao, rid, coordenadas, grupo, atributos=None, fase=None):
    corpo = {"tipo_codigo": 1, "grupo": grupo, "coordenadas": coordenadas, "atributos": atributos or {}}
    if fase is not None:
        corpo["fase_bitmask"] = fase
    r = sessao.post(f"/api/rede/{rid}/feicoes/linhas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _rede(sessao, rid):
    """A cooperativa de teste deste item, com as coordenadas em variável para que a conta feche à mão.

        disjuntor(a) ──MT1(ABC,100)── fusivel(b) ──MT2(AB,200)── trafo1(75 kVA) ──BT1── uc1
              └────────MT3(ABC,300)── trafo2(45 kVA) ──BT2── uc2

    Sob o trafo1 há um poste (estrutura de suporte, sem terminal: nunca é percorrido).
    """
    a = (LON0, LAT0)
    b = (LON0 + D, LAT0)
    c = (LON0 + 2 * D, LAT0)          # trafo 1
    bt1 = (LON0 + 2 * D, LAT0 + D)
    e = (LON0, LAT0 + 3 * D)          # trafo 2
    bt2 = (LON0 + D, LAT0 + 3 * D)
    at = {"ctmt": CTMT, "sub": "CFG"}

    disjuntor = _ponto(sessao, rid, *a, "chave_de_media_tensao", DISJUNTOR,
                       {**at, "cod_id": "DJ1", "estado": "fechado"})
    fusivel = _ponto(sessao, rid, *b, "chave_de_media_tensao", FUSIVEL,
                     {**at, "cod_id": "FU1", "estado": "fechado"})
    _linha(sessao, rid, [list(a), list(b)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT1", "comp": 100, "fas_con": "ABC"}, fase=7)
    _linha(sessao, rid, [list(b), list(c)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT2", "comp": 200, "fas_con": "AB"}, fase=3)
    trafo1 = _ponto(sessao, rid, *c, "transformador_de_distribuicao", 1,
                    {**at, "cod_id": "TR1", "pot_nom": 75})
    _linha(sessao, rid, [list(c), list(bt1)], "trecho_de_baixa_tensao",
           {**at, "cod_id": "BT1", "uni_tr_mt": "TR1", "comp": 50}, fase=7)
    uc1 = _ponto(sessao, rid, *bt1, "unidade_consumidora", UC_BT,
                 {**at, "cod_id": "UC1", "uni_tr_mt": "TR1", "clas_sub": "RE1", "ene": 1200})
    _linha(sessao, rid, [list(a), list(e)], "trecho_de_media_tensao",
           {**at, "cod_id": "MT3", "comp": 300, "fas_con": "ABC"}, fase=7)
    trafo2 = _ponto(sessao, rid, *e, "transformador_de_distribuicao", 1,
                    {**at, "cod_id": "TR2", "pot_nom": 45})
    _linha(sessao, rid, [list(e), list(bt2)], "trecho_de_baixa_tensao",
           {**at, "cod_id": "BT2", "uni_tr_mt": "TR2", "comp": 60}, fase=7)
    uc2 = _ponto(sessao, rid, *bt2, "unidade_consumidora", UC_BT,
                 {**at, "cod_id": "UC2", "uni_tr_mt": "TR2", "clas_sub": "RU1", "ene": 600})
    poste = _ponto(sessao, rid, *c, "ponto_notavel", POSTE, {**at, "cod_id": "PN1"})

    r = sessao.post(f"/api/rede/{rid}/topologia/habilitar")
    assert r.status_code == 201, r.text
    r = sessao.post(f"/api/rede/{rid}/controladores/importar")
    assert r.status_code == 200, r.text
    return {"disjuntor": disjuntor, "fusivel": fusivel, "trafo1": trafo1, "trafo2": trafo2,
            "uc1": uc1, "uc2": uc2, "poste": poste}


def _configs(sessao, rid):
    r = sessao.get(f"/api/rede/{rid}/config_tracado?limite=500")
    assert r.status_code == 200, r.text
    return {c["codigo"]: c for c in r.json()["itens"]}


def _tracar(sessao, rid, config_id, feicao_id, terminal=None, esperado=200):
    ponto = {"feicao_id": feicao_id}
    if terminal is not None:
        ponto["terminal"] = terminal
    r = sessao.post(f"/api/rede/{rid}/tracar",
                    json={"config_id": config_id, "pontos_partida": [ponto]})
    assert r.status_code == esperado, r.text
    return r.json()


def _funcao(resultado, codigo):
    for f in resultado["funcoes"]:
        if f["codigo"] == codigo:
            return f
    raise AssertionError(f"função {codigo} não veio no resultado: {resultado['funcoes']}")


# --- cláusula 2: as configurações prontas do pacote -------------------------------------------------------

def test_pacote_traz_as_seis_configuracoes_prontas(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "pacote", limpar_redes)
    configs = _configs(sessao_a, rid)
    esperadas = {"clientes_a_jusante", "kva_a_jusante", "isolamento_por_fusivel", "alimentador_inteiro",
                 "protetores_a_montante", "trechos_sem_fase_c"}
    assert esperadas <= set(configs), sorted(configs)
    assert len(configs) >= 6, sorted(configs)
    for codigo in esperadas:
        assert configs[codigo]["origem"] == "pacote", configs[codigo]
        assert configs[codigo]["tipo"] in ("conectado", "subrede", "montante", "jusante")


# --- cláusula 1: CRUD e uso por config_id ------------------------------------------------------------------

def test_ciclo_de_vida_da_configuracao(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "crud", limpar_redes)
    corpo = {"codigo": "zt-minha", "nome": "Minha configuração", "tipo": "conectado",
             "config": {"funcoes": [{"codigo": "n", "nome": "n", "funcao": "contagem"}]}}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["origem"] == "usuario" and r.json()["compartilhada"] is True

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo)
    assert r.status_code == 409 and r.json()["erro"] == "codigo_repetido", r.text

    r = sessao_a.get(f"/api/rede/{rid}/config_tracado/{cid}")
    assert r.status_code == 200 and r.json()["nome"] == "Minha configuração", r.text

    r = sessao_a.put(f"/api/rede/{rid}/config_tracado/{cid}",
                     json={**corpo, "nome": "Outro nome", "tipo": "subrede"})
    assert r.status_code == 200 and r.json()["nome"] == "Outro nome" and r.json()["tipo"] == "subrede"

    assert "zt-minha" in _configs(sessao_a, rid)
    r = sessao_a.delete(f"/api/rede/{rid}/config_tracado/{cid}")
    assert r.status_code == 204, r.text
    assert "zt-minha" not in _configs(sessao_a, rid)
    r = sessao_a.get(f"/api/rede/{rid}/config_tracado/{cid}")
    assert r.status_code == 404 and r.json()["erro"] == "config_inexistente", r.text


def test_tracar_por_config_id_usa_o_pedido_salvo(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "usa", limpar_redes)
    f = _rede(sessao_a, rid)
    configs = _configs(sessao_a, rid)

    saida = _tracar(sessao_a, rid, configs["clientes_a_jusante"]["id"], f["disjuntor"]["id"], terminal=2)
    assert saida["config"]["codigo"] == "clientes_a_jusante", saida
    assert saida["tipo"] == "jusante" and saida["tipo_resultado"] == "elementos"
    # o filtro de saída da configuração deixa só o que tem a categoria consumo: as duas unidades
    codigos = {e["tipo_chave"] for e in saida["elementos"]}
    assert codigos == {"consumidor_de_baixa_tensao"}, saida["elementos"]
    assert _funcao(saida, "clientes")["valor"] == 2, saida["funcoes"]

    # sem tipo e sem config_id o pedido é recusado, e a mensagem diz o que falta
    r = sessao_a.post(f"/api/rede/{rid}/tracar", json={"pontos_partida": [{"feicao_id": f["uc1"]["id"]}]})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_obrigatorio", r.text
    # configuração de outra rede (id que não existe aqui) não traça
    r = sessao_a.post(f"/api/rede/{rid}/tracar", json={
        "config_id": "00000000-0000-4000-8000-000000000001",
        "pontos_partida": [{"feicao_id": f["uc1"]["id"]}]})
    assert r.status_code == 404 and r.json()["erro"] == "config_inexistente", r.text


# --- cláusula 3: Σ kVA a jusante ---------------------------------------------------------------------------

def test_kva_a_jusante_soma_a_potencia_dos_trafos_alcancados(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "kva", limpar_redes)
    f = _rede(sessao_a, rid)
    configs = _configs(sessao_a, rid)
    saida = _tracar(sessao_a, rid, configs["kva_a_jusante"]["id"], f["disjuntor"]["id"], terminal=2)
    kva = _funcao(saida, "kva_instalado")
    assert kva["valor"] == pytest.approx(120.0), saida        # 75 + 45, os dois transformadores
    assert kva["unidade"] == "kVA" and kva["elementos_considerados"] == 2, kva
    assert {e["feicao_id"] for e in saida["elementos"]} == {f["trafo1"]["id"], f["trafo2"]["id"]}


# --- cláusula 4: barreiras, filtros, funções e tipos de resultado -------------------------------------------

def test_isolamento_para_na_chave_fusivel(sessao_a, limpar_redes):
    """A barreira de condição por TIPO tira a chave fusível do grafo: o ramo que sai dela não é alcançado,
    e a mesma partida que somava 120 kVA passa a somar 45."""
    rid = _criar_rede(sessao_a, "isola", limpar_redes)
    f = _rede(sessao_a, rid)
    configs = _configs(sessao_a, rid)
    saida = _tracar(sessao_a, rid, configs["isolamento_por_fusivel"]["id"], f["disjuntor"]["id"], terminal=2)
    assert saida["barreiras_de_condicao"]["nos"] >= 1, saida["barreiras_de_condicao"]
    assert _funcao(saida, "kva")["valor"] == pytest.approx(45.0), saida["funcoes"]
    assert _funcao(saida, "clientes")["valor"] == 1, saida["funcoes"]
    alcancados = {e["feicao_id"] for e in saida["elementos"]}
    assert f["trafo2"]["id"] in alcancados and f["trafo1"]["id"] not in alcancados, sorted(alcancados)


def test_barreira_de_filtro_estreita_sem_mudar_a_travessia(sessao_a, limpar_redes):
    """A barreira de FILTRO não muda o que foi percorrido: o traçado corre duas vezes e publica a interseção.
    Com a chave fusível só no filtro, o resultado é o mesmo do isolamento — mas `passagens` é 2, e o traçado
    sem o filtro (mesma configuração, lista vazia) devolve os dois transformadores."""
    rid = _criar_rede(sessao_a, "filtro", limpar_redes)
    f = _rede(sessao_a, rid)
    base = {"nome": "Com filtro", "tipo": "jusante",
            "config": {"funcoes": [{"codigo": "kva", "nome": "kVA", "funcao": "soma",
                                    "atributo": "pot_nom", "unidade": "kVA",
                                    "onde": [{"grupo": "transformador_de_distribuicao"}]}]}}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "codigo": "zt-sem-filtro"})
    assert r.status_code == 201, r.text
    sem = _tracar(sessao_a, rid, r.json()["id"], f["disjuntor"]["id"], terminal=2)

    corpo = {**base, "codigo": "zt-com-filtro"}
    corpo["config"] = {**base["config"],
                       "barreiras_filtro": [{"tipo": "chave_fusivel", "aplica_a": "ponto"}]}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo)
    assert r.status_code == 201, r.text
    com = _tracar(sessao_a, rid, r.json()["id"], f["disjuntor"]["id"], terminal=2)

    assert sem["passagens"] == 1 and com["passagens"] == 2, (sem["passagens"], com["passagens"])
    assert _funcao(sem, "kva")["valor"] == pytest.approx(120.0), sem["funcoes"]
    assert _funcao(com, "kva")["valor"] == pytest.approx(45.0), com["funcoes"]
    assert com["contagem"] < sem["contagem"], (com["contagem"], sem["contagem"])
    # a travessia não mudou: os nós alcançados da primeira passagem são os mesmos dos dois pedidos
    assert com["nos_alcancados"] == sem["nos_alcancados"], (com["nos_alcancados"], sem["nos_alcancados"])


def test_filtro_de_saida_por_fase_e_categoria(sessao_a, limpar_redes):
    """`trechos_sem_fase_c` do pacote: dos trechos alcançados, só o MT2 (fase AB) não declara a fase C."""
    rid = _criar_rede(sessao_a, "fase", limpar_redes)
    f = _rede(sessao_a, rid)
    configs = _configs(sessao_a, rid)
    saida = _tracar(sessao_a, rid, configs["trechos_sem_fase_c"]["id"], f["disjuntor"]["id"], terminal=2)
    assert saida["tipo"] == "conectado", saida["tipo"]
    assert saida["contagem"] == 1, saida["elementos"]
    assert _funcao(saida, "extensao")["valor"] == pytest.approx(200.0), saida["funcoes"]


def test_tipo_de_resultado_geometria_e_conectividade(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "resultado", limpar_redes)
    f = _rede(sessao_a, rid)
    configs = _configs(sessao_a, rid)
    geo = _tracar(sessao_a, rid, configs["alimentador_inteiro"]["id"], f["disjuntor"]["id"], terminal=2)
    assert geo["tipo_resultado"] == "geometria" and geo["elementos"] == [], geo["tipo_resultado"]
    assert geo["geometria"] and geo["geometria"]["type"], geo["geometria"]

    corpo = {"codigo": "zt-conect", "nome": "Conectividade", "tipo": "conectado",
             "config": {"tipo_resultado": "conectividade"}}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo)
    assert r.status_code == 201, r.text
    con = _tracar(sessao_a, rid, r.json()["id"], f["disjuntor"]["id"], terminal=2)
    assert con["tipo_resultado"] == "conectividade" and con["geometria"] is None
    assert len(con["conectividade"]) >= 4, con["conectividade"]
    for par in con["conectividade"]:
        assert par["no_origem"] and par["no_destino"], par


def test_incluir_estrutura_traz_o_poste_coincidente(sessao_a, limpar_redes):
    """O poste não tem terminal e nunca é percorrido; com `incluir_estrutura` ele entra no resultado por
    coincidir, dentro da tolerância da rede, com um nó alcançado."""
    rid = _criar_rede(sessao_a, "estrutura", limpar_redes)
    f = _rede(sessao_a, rid)
    corpo = {"codigo": "zt-estrutura", "nome": "Com estrutura", "tipo": "conectado",
             "config": {"filtro_saida": {"incluir_estrutura": True}}}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo)
    assert r.status_code == 201, r.text
    com = _tracar(sessao_a, rid, r.json()["id"], f["disjuntor"]["id"], terminal=2)
    assert com["estruturas_incluidas"] == 1, com["estruturas_incluidas"]
    assert f["poste"]["id"] in {e["feicao_id"] for e in com["elementos"]}, com["elementos"]

    corpo2 = {"codigo": "zt-sem-estrutura", "nome": "Sem estrutura", "tipo": "conectado", "config": {}}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json=corpo2)
    assert r.status_code == 201, r.text
    sem = _tracar(sessao_a, rid, r.json()["id"], f["disjuntor"]["id"], terminal=2)
    assert sem["estruturas_incluidas"] == 0
    assert f["poste"]["id"] not in {e["feicao_id"] for e in sem["elementos"]}


# --- cláusula 5: recusas ------------------------------------------------------------------------------------

def test_recusa_atributo_inexistente_e_operador_invalido(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "recusa", limpar_redes)
    base = {"codigo": "zt-ruim", "nome": "ruim", "tipo": "conectado"}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"barreiras_condicao": [
            {"atributo": "nao_existe_no_pacote", "operador": "=", "valor": "x"}]}})
    assert r.status_code == 422 and r.json()["erro"] == "atributo_inexistente", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"barreiras_condicao": [
            {"atributo": "pot_nom", "operador": "aproximadamente", "valor": 1}]}})
    assert r.status_code == 422 and r.json()["erro"] == "operador_invalido", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"barreiras_condicao": [{"categoria": "nao_existe"}]}})
    assert r.status_code == 422 and r.json()["erro"] == "categoria_inexistente", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"barreiras_condicao": [
            {"atributo": "pot_nom", "categoria": "consumo", "operador": "="}]}})
    assert r.status_code == 422 and r.json()["erro"] == "condicao_invalida", r.text


def test_recusa_funcao_e_resultado_desconhecidos(sessao_a, limpar_redes):
    rid = _criar_rede(sessao_a, "recusa2", limpar_redes)
    base = {"codigo": "zt-ruim2", "nome": "ruim", "tipo": "conectado"}
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"funcoes": [{"codigo": "x", "funcao": "mediana", "atributo": "pot_nom"}]}})
    assert r.status_code == 422 and r.json()["erro"] == "funcao_invalida", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"funcoes": [{"codigo": "x", "funcao": "soma", "atributo": "nao_existe"}]}})
    assert r.status_code == 422 and r.json()["erro"] == "atributo_inexistente", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        **base, "config": {"tipo_resultado": "planilha"}})
    assert r.status_code == 422 and r.json()["erro"] == "tipo_resultado_invalido", r.text

    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={**base, "tipo": "lacos", "config": {}})
    assert r.status_code == 422, r.text     # o tipo de traçado sem ponto de partida não é configurável


# --- cláusula 6: a configuração não atravessa inquilino ------------------------------------------------------

def test_configuracao_nao_aparece_em_outro_inquilino(sessao_a, sessao_b, limpar_redes):
    rid = _criar_rede(sessao_a, "inquilino", limpar_redes)
    r = sessao_a.post(f"/api/rede/{rid}/config_tracado", json={
        "codigo": "zt-so-de-a", "nome": "só de A", "tipo": "conectado", "config": {},
        "compartilhada": True})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    # compartilhada = para todo o inquilino A; o inquilino B nem enxerga a rede
    assert sessao_b.get(f"/api/rede/{rid}/config_tracado").status_code == 404
    assert sessao_b.get(f"/api/rede/{rid}/config_tracado/{cid}").status_code == 404

"""Traçado de ISOLAMENTO (item L4-02-c-isolamento), na mesma rota `POST /api/rede/{id}/tracar`.

A rede sintética destes testes tem TRÊS CHAVES (chave_faca: CH1, CH2, CH3) e DOIS FUSÍVEIS (chave_fusivel:
FUS1, FUS2), que é a rede que o portão do item pede, mais uma subestação (categoria `fonte`), dois
transformadores e duas cargas. O desenho, de oeste para leste, com um ramo ao norte:

    SE --l1-- CH1 --l2-- J2 --l3-- FUS1 --l4a-- PJ --l4b-- CH2 --l5-- TR1 --l6(BT)-- UC1
                          |
                         l7
                          |
                        FUS2 --l8-- CH3 --l9-- TR2 --l10(BT)-- UC2

`PJ` é um vértice de junção no meio do trecho FUS1—CH2: é o PONTO COM FALHA de quase todos os testes, e é
resolvido por coordenada (o operador clica no mapa), não por feição.

O que cada teste prova, na ordem das cláusulas do portão:

1. `tipo=isolamento` devolve `{dispositivos_a_abrir, elementos_isolados, resumo}` com clientes, trafos e km
   por nível (`test_conjunto_exato_*`, `test_resumo_*`);
2. a rede de 3 chaves e 2 fusíveis dá EXATAMENTE o conjunto esperado, contado à mão
   (`test_conjunto_exato_um_fusivel`, `test_dois_dispositivos_quando_ha_duas_fontes`);
3. a opção `ignorar_inoperante` muda o conjunto (`test_fusivel_sem_estado_*`), que é também a refutação do
   adversário: um fusível marcado como "sem estado" não é considerado operável;
4. o conjunto é MÍNIMO por inclusão, não qualquer conjunto suficiente
   (`test_conjunto_exato_um_fusivel` prova que a chave a jusante fica de fora, e
   `test_dois_dispositivos_quando_ha_duas_fontes` prova que a segunda entra quando é necessária);
5. o que o produto NÃO afirma: sem caminho de manobra a resposta é `isolavel=false`
   (`test_sem_dispositivo_no_caminho_nao_e_isolavel`) e ponto já sem energia é dito com esse nome
   (`test_ponto_ja_sem_fonte`).

A cláusula de tempo e a da cooperativa de teste ficam em `test_rede_isolamento_medida.py`."""

import pytest

from tests.api.test_rede_tracado import (  # noqa: F401 — fixtures/auxiliares reusados por nome
    _criar_rede,
    _habilitar,
    _importar_eletrica,
    _linha,
    _offset,
    _ponto,
    limpar_redes,
)

LON0, LAT0 = 30.000, 21.000
PASSO = 0.001  # ~104 m em longitude nesta latitude
FECHADO = {"estado": "fechado"}


def _x(i: int) -> float:
    return LON0 + i * PASSO


def _y(i: int) -> float:
    return LAT0 + i * PASSO


def _isolar(sessao, rid, ponto, **kw):
    return sessao.post(f"/api/rede/{rid}/tracar",
                       json={"tipo": "isolamento", "pontos_partida": [ponto], **kw})


def _rede_3_chaves_2_fusiveis(sessao, env, limpar, sufixo, atributos_fus1=None, atributos_ch1=None):
    """A rede do portão. Devolve (rid, ids, ponto_de_falha) com o ponto de falha (PJ) já no formato de
    entrada do traçado (coordenada com tolerância de 1 m: PJ é o único nó a menos de 100 m dali)."""
    rid = _criar_rede(sessao, sufixo, limpar)
    _importar_eletrica(sessao, rid)

    def chave(lon, lat, tipo_codigo, atributos):
        oeste = _offset(env, lon, lat, 0.049, 270)
        leste = _offset(env, lon, lat, 0.049, 90)
        p = _ponto(sessao, rid, lon, lat, "chave_de_media_tensao", tipo_codigo=tipo_codigo,
                   atributos=atributos)
        return p, oeste, leste

    def chave_ns(lon, lat, tipo_codigo, atributos):
        sul = _offset(env, lon, lat, 0.049, 180)
        norte = _offset(env, lon, lat, 0.049, 0)
        p = _ponto(sessao, rid, lon, lat, "chave_de_media_tensao", tipo_codigo=tipo_codigo,
                   atributos=atributos)
        return p, sul, norte

    se = _ponto(sessao, rid, _x(0), LAT0, "subestacao")
    ch1, ch1_o, ch1_l = chave(_x(1), LAT0, 1, atributos_ch1 or FECHADO)
    fus1, fus1_o, fus1_l = chave(_x(3), LAT0, 2, atributos_fus1 if atributos_fus1 is not None else FECHADO)
    ch2, ch2_o, ch2_l = chave(_x(5), LAT0, 1, FECHADO)
    fus2, fus2_s, fus2_n = chave_ns(_x(2), _y(1), 2, FECHADO)
    ch3, ch3_s, ch3_n = chave_ns(_x(2), _y(2), 1, FECHADO)

    mt = "trecho_de_media_tensao"
    l1 = _linha(sessao, rid, [[_x(0), LAT0], list(ch1_o)], mt)
    l2 = _linha(sessao, rid, [list(ch1_l), [_x(2), LAT0]], mt)
    l3 = _linha(sessao, rid, [[_x(2), LAT0], list(fus1_o)], mt)
    l4a = _linha(sessao, rid, [list(fus1_l), [_x(4), LAT0]], mt)
    l4b = _linha(sessao, rid, [[_x(4), LAT0], list(ch2_o)], mt)
    l5 = _linha(sessao, rid, [list(ch2_l), [_x(6), LAT0]], mt)
    tr1 = _ponto(sessao, rid, _x(6), LAT0, "transformador_de_distribuicao")
    l6 = _linha(sessao, rid, [[_x(6), LAT0], [_x(7), LAT0]], "trecho_de_baixa_tensao")
    uc1 = _ponto(sessao, rid, _x(7), LAT0, "ponto_de_iluminacao_publica")

    l7 = _linha(sessao, rid, [[_x(2), LAT0], list(fus2_s)], mt)
    l8 = _linha(sessao, rid, [list(fus2_n), list(ch3_s)], mt)
    l9 = _linha(sessao, rid, [list(ch3_n), [_x(2), _y(3)]], mt)
    tr2 = _ponto(sessao, rid, _x(2), _y(3), "transformador_de_distribuicao")
    l10 = _linha(sessao, rid, [[_x(2), _y(3)], [_x(2), _y(4)]], "trecho_de_baixa_tensao")
    uc2 = _ponto(sessao, rid, _x(2), _y(4), "ponto_de_iluminacao_publica")

    _habilitar(sessao, rid)
    ids = {"se": se["id"], "ch1": ch1["id"], "ch2": ch2["id"], "ch3": ch3["id"], "fus1": fus1["id"],
           "fus2": fus2["id"], "tr1": tr1["id"], "tr2": tr2["id"], "uc1": uc1["id"], "uc2": uc2["id"],
           "l1": l1["id"], "l2": l2["id"], "l3": l3["id"], "l4a": l4a["id"], "l4b": l4b["id"],
           "l5": l5["id"], "l6": l6["id"], "l7": l7["id"], "l8": l8["id"], "l9": l9["id"], "l10": l10["id"]}
    ponto_de_falha = {"lon": _x(4), "lat": LAT0, "tolerancia_m": 1.0}
    return rid, ids, ponto_de_falha


@pytest.fixture
def rede(sessao_a, env, limpar_redes):  # noqa: F811
    return _rede_3_chaves_2_fusiveis(sessao_a, env, limpar_redes, "isolamento")


# --- cláusulas 1, 2 e 4: conjunto exato, formato da resposta e mínimo por inclusão -----------------------

def test_conjunto_exato_um_fusivel(sessao_a, rede):
    """Falha no trecho entre FUS1 e CH2. Contado à mão: saindo do ponto, o primeiro dispositivo em direção à
    subestação é FUS1 e o primeiro no outro sentido é CH2 — os dois formam a fronteira. Só FUS1 é
    NECESSÁRIO: com FUS1 aberto e CH2 fechada, o ponto não alcança fonte nenhuma (a leste de CH2 só há
    transformador e carga). O conjunto mínimo por inclusão é, portanto, {FUS1}, e CH2 fica de fora — é isso
    que separa o mínimo de "qualquer conjunto suficiente".

    Elementos isolados (sem `incluir_isolados`): a zona entre dispositivos = os dois trechos l4a e l4b mais o
    terminal de FUS1 e o de CH2 que dão para ela. Nada a oeste de FUS1, nada a leste de CH2."""
    rid, ids, falha = rede
    r = _isolar(sessao_a, rid, falha)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["isolavel"] is True and j["motivo"] is None, j
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["fus1"]], j["dispositivos_a_abrir"]
    assert j["dispositivos_a_abrir"][0]["tipo_chave"] == "chave_fusivel"
    assert {e["feicao_id"] for e in j["elementos_isolados"]} == {
        ids["fus1"], ids["ch2"], ids["l4a"], ids["l4b"]}, j["elementos_isolados"]
    assert j["contagem"] == 4, j
    assert j["resumo"]["clientes"] == 0 and j["resumo"]["trafos"] == 0, j["resumo"]
    assert set(j["resumo"]["km_por_nivel"]) == {"trecho_de_media_tensao"}, j["resumo"]
    assert j["geometria"] is not None and j["geometria_dispositivos"] is not None


def test_incluir_isolados_traz_o_que_fica_sem_energia_alem_dos_dispositivos(sessao_a, rede):
    """Com `incluir_isolados`, a resposta deixa de ser o trecho de trabalho e passa a ser tudo o que apaga:
    CH2 continua FECHADA, então o transformador, o trecho de baixa tensão e a carga a leste dela perdem a
    fonte junto. O resumo passa a contar 1 cliente e 1 transformador, e ganha o nível de baixa tensão. Nada
    do ramo norte entra: ele continua alimentado pela subestação."""
    rid, ids, falha = rede
    j = _isolar(sessao_a, rid, falha, incluir_isolados=True).json()
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["fus1"]], j
    achados = {e["feicao_id"] for e in j["elementos_isolados"]}
    assert achados == {ids["fus1"], ids["l4a"], ids["l4b"], ids["ch2"], ids["l5"], ids["tr1"], ids["l6"],
                       ids["uc1"]}, achados
    assert j["resumo"]["clientes"] == 1 and j["resumo"]["trafos"] == 1, j["resumo"]
    assert set(j["resumo"]["km_por_nivel"]) == {"trecho_de_media_tensao", "trecho_de_baixa_tensao"}
    assert j["resumo"]["km_total"] == pytest.approx(
        sum(j["resumo"]["km_por_nivel"].values()), rel=1e-9)
    for chave_norte in (ids["fus2"], ids["ch3"], ids["tr2"], ids["uc2"], ids["l7"]):
        assert chave_norte not in achados, achados


def test_km_por_nivel_bate_com_o_comprimento_dos_trechos(sessao_a, rede):
    """Os quilômetros do resumo são a soma do comprimento dos trechos isolados, por grupo de camada — aqui,
    l4a + l4b, cada um com um passo de 0,001 grau de longitude (~104 m nesta latitude)."""
    rid, _ids, falha = rede
    j = _isolar(sessao_a, rid, falha).json()
    km_mt = j["resumo"]["km_por_nivel"]["trecho_de_media_tensao"]
    assert 0.19 < km_mt < 0.22, j["resumo"]  # dois trechos de ~104 m, menos os 4,9 cm de folga da chave
    assert j["resumo"]["km_total"] == pytest.approx(km_mt, rel=1e-9)


def test_categorias_do_pedido_escolhem_quem_pode_abrir(sessao_a, rede):
    """Pedindo só `dispositivo_de_protecao`, as chaves-faca deixam de ser ponto de corte: FUS1 continua
    sendo o dispositivo a abrir, mas a zona isolada cresce para leste, porque CH2 já não a fecha."""
    rid, ids, falha = rede
    j = _isolar(sessao_a, rid, falha, categorias_isolamento=["dispositivo_de_protecao"]).json()
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["fus1"]], j
    achados = {e["feicao_id"] for e in j["elementos_isolados"]}
    assert {ids["ch2"], ids["l5"], ids["tr1"], ids["uc1"]} <= achados, achados
    assert j["resumo"]["clientes"] == 1, j["resumo"]


def test_dois_dispositivos_quando_ha_duas_fontes(sessao_a, env, limpar_redes):  # noqa: F811
    """Rede com fonte nas DUAS pontas: SE1 — CH1 — PJ — CH2 — SE2. Agora as duas chaves são necessárias, e
    tirar qualquer uma delas deixaria o ponto energizado pelo outro lado — a resposta tem duas."""
    rid = _criar_rede(sessao_a, "isolamento-duas-fontes", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    ch1_o = _offset(env, _x(1), LAT0, 0.049, 270)
    ch1_l = _offset(env, _x(1), LAT0, 0.049, 90)
    ch2_o = _offset(env, _x(3), LAT0, 0.049, 270)
    ch2_l = _offset(env, _x(3), LAT0, 0.049, 90)
    _ponto(sessao_a, rid, _x(0), LAT0, "subestacao")
    ch1 = _ponto(sessao_a, rid, _x(1), LAT0, "chave_de_media_tensao", atributos=FECHADO)
    ch2 = _ponto(sessao_a, rid, _x(3), LAT0, "chave_de_media_tensao", atributos=FECHADO)
    _ponto(sessao_a, rid, _x(4), LAT0, "subestacao")
    mt = "trecho_de_media_tensao"
    _linha(sessao_a, rid, [[_x(0), LAT0], list(ch1_o)], mt)
    _linha(sessao_a, rid, [list(ch1_l), [_x(2), LAT0]], mt)
    _linha(sessao_a, rid, [[_x(2), LAT0], list(ch2_o)], mt)
    _linha(sessao_a, rid, [list(ch2_l), [_x(4), LAT0]], mt)
    _habilitar(sessao_a, rid)

    j = _isolar(sessao_a, rid, {"lon": _x(2), "lat": LAT0, "tolerancia_m": 1.0}).json()
    assert j["isolavel"] is True, j
    assert sorted(d["feicao_id"] for d in j["dispositivos_a_abrir"]) == sorted([ch1["id"], ch2["id"]]), j


# --- cláusula 3 e refutação: barreira de condição (dispositivo inoperante) --------------------------------

def test_fusivel_sem_estado_nao_e_considerado_operavel(sessao_a, env, limpar_redes):  # noqa: F811
    """Refutação do adversário: um fusível cujo cadastro não declara `estado` não pode ser contado como
    ponto de corte — não se sabe a posição dele. O traçado passa por FUS1 e vai até o próximo dispositivo
    operável em direção à fonte, que é CH1. O fusível aparece nomeado em `dispositivos_inoperantes`, com o
    motivo, em vez de sumir sem explicação."""
    rid, ids, falha = _rede_3_chaves_2_fusiveis(sessao_a, env, limpar_redes, "isolamento-sem-estado",
                                                atributos_fus1={"cod_id": "zt-fus1"})
    j = _isolar(sessao_a, rid, falha).json()
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["ch1"]], j["dispositivos_a_abrir"]
    inoperantes = {d["feicao_id"]: d["motivo_inoperante"] for d in j["dispositivos_inoperantes"]}
    assert inoperantes == {ids["fus1"]: "sem_estado"}, j["dispositivos_inoperantes"]


def test_ignorar_inoperante_falso_volta_a_contar_com_o_fusivel(sessao_a, env, limpar_redes):  # noqa: F811
    """A mesma rede do teste anterior, com `ignorar_inoperante=false`: o pedido abre mão da exigência de
    estado declarado e o conjunto muda de {CH1} para {FUS1}. É a cláusula "a opção muda o conjunto"."""
    rid, ids, falha = _rede_3_chaves_2_fusiveis(sessao_a, env, limpar_redes, "isolamento-inoperante-off",
                                                atributos_fus1={"cod_id": "zt-fus1"})
    padrao = _isolar(sessao_a, rid, falha).json()
    sem_exigencia = _isolar(sessao_a, rid, falha, ignorar_inoperante=False).json()
    assert [d["feicao_id"] for d in padrao["dispositivos_a_abrir"]] == [ids["ch1"]], padrao
    assert [d["feicao_id"] for d in sem_exigencia["dispositivos_a_abrir"]] == [ids["fus1"]], sem_exigencia
    assert sem_exigencia["dispositivos_inoperantes"] == [], sem_exigencia


def test_dispositivo_com_operavel_negado_tambem_sai(sessao_a, env, limpar_redes):  # noqa: F811
    """`operavel: nao` no cadastro (dispositivo emperrado, sem acesso, em manutenção) tem o mesmo efeito de
    não ter estado: o traçado procura o próximo."""
    rid, ids, falha = _rede_3_chaves_2_fusiveis(sessao_a, env, limpar_redes, "isolamento-nao-operavel",
                                                atributos_fus1={"estado": "fechado", "operavel": "nao"})
    j = _isolar(sessao_a, rid, falha).json()
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["ch1"]], j
    assert [d["motivo_inoperante"] for d in j["dispositivos_inoperantes"]] == ["operavel_negado"], j


# --- cláusula 5: o que o produto não afirma ---------------------------------------------------------------

def test_sem_dispositivo_no_caminho_nao_e_isolavel(sessao_a, env, limpar_redes):  # noqa: F811
    """Rede sem nenhuma chave entre o ponto e a subestação: não existe manobra que desenergize o ponto. A
    resposta é `isolavel=false` com o motivo, nunca um conjunto que não isola."""
    rid = _criar_rede(sessao_a, "isolamento-sem-chave", limpar_redes)
    _importar_eletrica(sessao_a, rid)
    _ponto(sessao_a, rid, _x(0), LAT0, "subestacao")
    _linha(sessao_a, rid, [[_x(0), LAT0], [_x(1), LAT0]], "trecho_de_media_tensao")
    _linha(sessao_a, rid, [[_x(1), LAT0], [_x(2), LAT0]], "trecho_de_media_tensao")
    _habilitar(sessao_a, rid)
    j = _isolar(sessao_a, rid, {"lon": _x(1), "lat": LAT0, "tolerancia_m": 1.0}).json()
    assert j["isolavel"] is False and j["motivo"] == "caminho_sem_dispositivo", j
    assert j["dispositivos_a_abrir"] == [], j


def test_ponto_ja_sem_fonte(sessao_a, env, limpar_redes):  # noqa: F811
    """Com CH1 aberta, o ponto de falha já não alcança a subestação: nenhum dispositivo precisa ser aberto, e
    a resposta diz isso com esse nome em vez de devolver um conjunto vazio sem explicação."""
    rid, _ids, falha = _rede_3_chaves_2_fusiveis(sessao_a, env, limpar_redes, "isolamento-ja-sem-fonte",
                                                 atributos_ch1={"estado": "aberto"})
    j = _isolar(sessao_a, rid, falha).json()
    assert j["isolavel"] is True and j["motivo"] == "ponto_ja_sem_fonte", j
    assert j["dispositivos_a_abrir"] == [], j


def test_categoria_de_fonte_inexistente_e_recusada(sessao_a, rede):
    rid, _ids, falha = rede
    r = _isolar(sessao_a, rid, falha, categoria_controlador="nao_existe_no_pacote")
    assert r.status_code == 422 and r.json()["erro"] == "categoria_controlador_sem_feicao", r.text


def test_isolamento_exige_ponto_de_partida(sessao_a, rede):
    rid, _ids, _falha = rede
    r = sessao_a.post(f"/api/rede/{rid}/tracar", json={"tipo": "isolamento", "pontos_partida": []})
    assert r.status_code == 422 and r.json()["erro"] == "sem_ponto_de_partida", r.text


def test_barreira_do_pedido_corta_a_zona(sessao_a, rede):
    """Barreira é do CHAMADOR, e vale aqui como nos outros traçados: pondo uma barreira no terminal de CH2
    que dá para a zona, o dispositivo deixa de ser alcançado e some da fronteira — o conjunto continua
    {FUS1}, e a zona encolhe para o trecho que resta."""
    rid, ids, falha = rede
    j = _isolar(sessao_a, rid, falha, barreiras=[{"lon": _x(5), "lat": LAT0, "tolerancia_m": 1.0}]).json()
    assert [d["feicao_id"] for d in j["dispositivos_a_abrir"]] == [ids["fus1"]], j
    assert ids["ch2"] not in {e["feicao_id"] for e in j["elementos_isolados"]}, j

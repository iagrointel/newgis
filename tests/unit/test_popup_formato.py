"""Formatação do servidor para o popup em tempo de execução (item L2-01-d-popup-runtime). Só o que o
SERVIDOR formata (campo `servidor: true` e expressão); o campo lido direto do tile é formatado no
navegador com as mesmas regras (`web/js/mapa/formato.js`), sem round-trip — ver docstring de
`app/mapa/popup.py`."""

from app.mapa import popup


def test_numero_grande_com_duas_casas_e_separador_ptbr():
    # a cláusula literal do portão: "1234567.891" -> "1.234.567,89"
    assert popup.formatar_numero_ptbr(1234567.891, 2) == "1.234.567,89"


def test_numero_negativo_e_zero():
    assert popup.formatar_numero_ptbr(-1234.5, 1) == "-1.234,5"
    assert popup.formatar_numero_ptbr(0, 2) == "0,00"


def test_numero_sem_milhar():
    assert popup.formatar_numero_ptbr(42, 0) == "42"


def test_moeda_brl():
    assert popup.formatar_moeda_brl(1234567.891) == "R$ 1.234.567,89"


def test_data_no_fuso_do_inquilino():
    # o mesmo instante (ms desde a época, convenção do L2-10-c) muda de TEXTO conforme o fuso pedido;
    # a bancada do item usa este valor exato (DATA_EVENTO_MS em scripts/mapa_demo_popup.py)
    ms = 1772614800000
    assert popup.formatar_data(ms, "UTC") == "04/03/2026 09:00"
    assert popup.formatar_data(ms, "America/Sao_Paulo") == "04/03/2026 06:00"
    # o mesmo instante, dois fusos, duas horas diferentes — é isso que o portão pede provar
    assert popup.formatar_data(ms, "UTC") != popup.formatar_data(ms, "America/Sao_Paulo")


def test_fuso_desconhecido_cai_no_padrao_sem_derrubar():
    ms = 1772614800000
    assert popup.formatar_data(ms, "Nao/Existe") == popup.formatar_data(ms, popup.FUSO_PADRAO)


def test_formatar_valor_nulo_e_none_sempre_none():
    assert popup.formatar(None, "numero", 2, "UTC") is None
    assert popup.formatar(None, "data", None, "UTC") is None


def test_normalizar_sem_configuracao_cai_no_padrao_por_campo_do_catalogo():
    dados = {"campos": [{"nome": "a", "tipo": "text"}, {"nome": "b", "tipo": "double precision"}]}
    cfg = popup.normalizar(dados)
    assert {c["nome"] for c in cfg["campos"]} == {"a", "b"}
    assert all(c["tipo"] == "texto" and not c["servidor"] for c in cfg["campos"])
    assert cfg["expressoes"] == []
    assert cfg["tem_servidor"] is False


def test_normalizar_titulo_com_chave_desconhecida_nao_derruba():
    dados = {"campos": [], "popup": {"titulo": "{nome}", "campos": "não é lista", "expressoes": [1, {}]}}
    cfg = popup.normalizar(dados)
    assert cfg["titulo"] == "{nome}"
    assert cfg["campos"] == []
    assert cfg["expressoes"] == []


def test_normalizar_campo_servidor_marcado():
    dados = {"campos": [], "popup": {"campos": [{"nome": "x", "servidor": True}]}}
    cfg = popup.normalizar(dados)
    assert cfg["campos"][0]["servidor"] is True
    assert cfg["tem_servidor"] is True


def test_normalizar_decimais_fora_da_faixa_cai_no_padrao():
    dados = {"campos": [], "popup": {"campos": [{"nome": "x", "formato": {"tipo": "numero", "decimais": 99}}]}}
    cfg = popup.normalizar(dados)
    assert cfg["campos"][0]["decimais"] == 2

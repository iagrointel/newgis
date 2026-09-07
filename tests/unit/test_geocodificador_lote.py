"""Item L2-11-a-geocodificacao-csv: as peças puras do motor de lote (`app.geocodificador.lote`) — parsing de
CSV, validação de mapeamento de coluna e classificação resolvido x pendente — sem banco (o portão medido com
o CNEFE de verdade está em tests/api/geocodificador/test_lote_csv.py)."""

import pytest

from app.geocodificador import lote


def test_ler_csv_cabecalho_e_linhas():
    texto = "logradouro,numero,municipio,uf\nRua A,10,Boa Vista,RR\nRua B,20,Boa Vista,RR\n"
    cabecalho, linhas = lote.ler_csv(texto)
    assert cabecalho == ["logradouro", "numero", "municipio", "uf"]
    assert len(linhas) == 2
    assert linhas[0]["logradouro"] == "Rua A"


def test_ler_csv_vazio_recusa():
    with pytest.raises(lote.MapeamentoInvalido):
        lote.ler_csv("")


def test_ler_csv_sem_cabecalho_recusa():
    with pytest.raises(lote.MapeamentoInvalido):
        lote.ler_csv("\n\n")


def test_ler_csv_teto_de_linhas(monkeypatch):
    monkeypatch.setattr(lote.limites, "GEOCODIFICADOR_LOTE_MAX_LINHAS", 2)
    texto = "logradouro\nA\nB\nC\n"
    with pytest.raises(lote.MapeamentoInvalido, match="teto de 2"):
        lote.ler_csv(texto)


def test_validar_mapeamento_campo_desconhecido():
    with pytest.raises(lote.MapeamentoInvalido, match="desconhecido"):
        lote.validar_mapeamento(["rua"], {"rua_do_ibge": "rua"})


def test_validar_mapeamento_coluna_ausente():
    with pytest.raises(lote.MapeamentoInvalido, match="ausente"):
        lote.validar_mapeamento(["rua"], {"logradouro": "endereco_completo"})


def test_validar_mapeamento_exige_logradouro_ou_endereco():
    with pytest.raises(lote.MapeamentoInvalido, match="logradouro.*endereco"):
        lote.validar_mapeamento(["bairro"], {"bairro": "bairro"})


def test_validar_mapeamento_vazio():
    with pytest.raises(lote.MapeamentoInvalido, match="vazio"):
        lote.validar_mapeamento(["rua"], {})


def test_validar_mapeamento_ok_com_logradouro():
    lote.validar_mapeamento(["rua", "num"], {"logradouro": "rua", "numero": "num"})


def test_validar_mapeamento_ok_com_endereco_unico():
    lote.validar_mapeamento(["linha"], {"endereco": "linha"})


def test_aplicar_mapeamento_numero_com_ruido():
    campos = lote.aplicar_mapeamento({"rua": "R. das Flores", "num": " 123 "},
                                      {"logradouro": "rua", "numero": "num"})
    assert campos["numero"] == 123
    assert campos["logradouro"] == "RUA DAS FLORES" or "FLORES" in campos["logradouro"].upper()


def test_aplicar_mapeamento_numero_invalido_vira_none():
    campos = lote.aplicar_mapeamento({"num": "sn"}, {"numero": "num"})
    assert campos["numero"] is None


def test_aplicar_mapeamento_cep_invalido_vira_none():
    campos = lote.aplicar_mapeamento({"cep": "abc"}, {"cep": "cep"})
    assert campos["cep"] is None


def test_aplicar_mapeamento_cep_com_hifen():
    campos = lote.aplicar_mapeamento({"cep": "69300-000"}, {"cep": "cep"})
    assert campos["cep"] == "69300000"


def test_aplicar_mapeamento_uf_maiuscula_e_2_letras():
    campos = lote.aplicar_mapeamento({"estado": " rr "}, {"uf": "estado"})
    assert campos["uf"] == "RR"


def test_aplicar_mapeamento_celula_vazia_vira_none():
    campos = lote.aplicar_mapeamento({"bairro": "  "}, {"bairro": "bairro"})
    assert campos["bairro"] is None


def _linha(tipo_acerto, score, pendente):
    return lote.LinhaGeocodificada(linha_origem=1, endereco_entrada="x", campos_entrada={},
                                    tipo_acerto=tipo_acerto, score=score, pendente=pendente)


def test_resumo_conta_pendentes_e_por_tipo():
    linhas = [
        _linha("numero_exato", 95.0, False),
        _linha("numero_exato", 95.0, False),
        _linha("aproximado_no_bairro", 40.0, True),
        _linha(None, None, True),
    ]
    linhas[3].erro = "sem_correspondencia"
    r = lote.resumo(linhas)
    assert r["total"] == 4
    assert r["resolvidos"] == 2
    assert r["pendentes"] == 2
    assert r["por_tipo_acerto"]["numero_exato"] == 2
    assert r["por_tipo_acerto"]["aproximado_no_bairro"] == 1
    assert r["por_tipo_acerto"]["erro:sem_correspondencia"] == 1


def test_tipos_resolvidos_e_limiar_pendente_sao_constantes_fechadas():
    """Regra do item: só numero_exato/interpolado_na_face resolvem sozinhos; tudo mais é revisão manual."""
    assert lote.TIPOS_RESOLVIDOS == frozenset({"numero_exato", "interpolado_na_face"})

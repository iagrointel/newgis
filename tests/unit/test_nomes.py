"""Normalização de nomes de campo/camada (ADR 0005 seção 8; item L0-04-ingest-vetor). Tabela literal da seção 8
do ADR, mais os casos de duplicata/reservado/comprimento que a carga depende para nunca colidir com as colunas
obrigatórias."""

from app.ingestao import nomes


def test_tabela_da_secao_8():
    usados: set[str] = set()
    casos = [
        ("Código IBGE", "codigo_ibge", None),
        ("Área km²", "area_km2", None),
        ("select", "select_", "reservado"),
        ("Município", "municipio", None),
        ("Município", "municipio_2", "duplicado"),
        ("fid", "fid_", "reservado"),
        ("123abc", "c_123abc", "digito_inicial"),
        ("Layer", "layer", None),
    ]
    for origem, esperado, motivo_esperado in casos:
        nome, motivo = nomes.normalizar(origem, usados)
        assert nome == esperado, f"{origem!r} -> {nome!r} (esperado {esperado!r})"
        if motivo_esperado is not None:
            assert motivo == motivo_esperado, f"{origem!r}: motivo {motivo!r} != {motivo_esperado!r}"


def test_caractere_invalido_e_controle():
    usados: set[str] = set()
    nome, motivo = nomes.normalizar("mun\x01icipios", usados)
    assert nome == "mun_icipios"
    assert motivo == "caractere_invalido"

    usados2: set[str] = set()
    nome2, motivo2 = nomes.normalizar("C�digo", usados2)
    assert nome2 == "c_digo"
    assert motivo2 == "caractere_invalido"


def test_comprimento_63_bytes():
    usados: set[str] = set()
    longo = "área " + "a" * 70  # com acento, gera bytes extras na normalização antes do corte
    nome, motivo = nomes.normalizar(longo, usados)
    assert len(nome.encode("utf-8")) <= 63
    assert motivo == "comprimento"


def test_colunas_obrigatorias_levam_sufixo():
    for col in ("globalid", "tenant_id", "geom", "criado_em", "versao"):
        usados: set[str] = set()
        nome, motivo = nomes.normalizar(col, usados)
        assert nome == col + "_"
        assert motivo == "reservado"


def test_nome_vazio_vira_campo_posicional():
    usados: set[str] = set()
    nome, motivo = nomes.normalizar("", usados, posicao=3)
    assert nome == "campo_3"
    assert motivo == "nome_vazio"


def test_duplicatas_triplas():
    usados: set[str] = set()
    n1, _ = nomes.normalizar("Nome", usados)
    n2, m2 = nomes.normalizar("Nome", usados)
    n3, m3 = nomes.normalizar("nome", usados)  # já minúsculo: colide igual
    assert (n1, n2, n3) == ("nome", "nome_2", "nome_3")
    assert m2 == m3 == "duplicado"


def test_normalizar_titulo_preserva_acento_e_caixa():
    assert nomes.normalizar_titulo("Município de Teste") == "Município de Teste"
    assert nomes.normalizar_titulo("  com   espaço  \x01demais ") == "com espaço demais"
    assert nomes.normalizar_titulo("") == "camada"

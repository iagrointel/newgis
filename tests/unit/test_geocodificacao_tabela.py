"""Leitura da tabela enviada para geocodificar (item L2-11-a-geocodificacao-csv, `app.geocodificador.tabela`).
Testes sem banco: teto de tamanho, linha malformada que NÃO derruba o resto, mapeamento por nome de coluna,
separador `;`, latin-1, XLSX e o teto de linhas."""

import io

import pytest

from app import limites
from app.geocodificador import tabela


def _csv(linhas: list[str], fim="\n") -> bytes:
    return fim.join(linhas).encode("utf-8")


def test_teto_de_tamanho_recusa_antes_de_ler():
    tabela.conferir_tamanho(limites.GEOCOD_ARQUIVO_BYTES_MAX)
    with pytest.raises(tabela.ArquivoGrandeDemais) as e:
        tabela.conferir_tamanho(limites.GEOCOD_ARQUIVO_BYTES_MAX + 1)
    assert "teto" in str(e.value)


def test_colunas_propoe_mapeamento_por_nome_de_cabecalho():
    dados = _csv(["Logradouro;Número;Bairro;Cidade;UF;CEP;Cliente", "R. A;10;Centro;Boa Vista;RR;69301000;x"])
    saida = tabela.colunas(dados)
    assert saida["colunas"][0] == "Logradouro"
    assert saida["mapeamento_proposto"] == {
        "logradouro": "Logradouro", "numero": "Número", "bairro": "Bairro", "municipio": "Cidade",
        "uf": "UF", "cep": "CEP",
    }


def test_coluna_unica_de_endereco_e_reconhecida():
    dados = _csv(["endereco completo,cliente", "Rua A 10 Boa Vista RR,x"])
    assert tabela.colunas(dados)["mapeamento_proposto"] == {"endereco": "endereco completo"}


def test_linha_malformada_nao_derruba_as_outras():
    """Portão do turno: 'linha malformada não derruba o trabalho todo'. Quatro linhas ruins e três boas no
    mesmo arquivo: as boas saem íntegras, as ruins saem com motivo em português."""
    dados = _csv([
        "logradouro,numero,municipio,uf",
        "Rua A,10,Boa Vista,RR",          # 1 boa
        "Rua B,,Boa Vista,RR",            # 2 boa (sem número)
        "Rua C",                          # 3 ruim: faltam colunas
        ",,,",                            # 4 ruim: linha em branco
        "Rua D,dez,Boa Vista,RR",         # 5 número sem dígito -> aviso, segue sem número
        "Rua E,20,Boa Vista,RR",          # 6 boa
        ",,Boa Vista,RR",                 # 7 boa (só município/UF: o motor recua para o município)
    ])
    linhas = list(tabela.linhas(dados, {"logradouro": "logradouro", "numero": "numero",
                                         "municipio": "municipio", "uf": "uf"}))
    assert [li.n for li in linhas] == [1, 2, 3, 4, 5, 6, 7]
    assert linhas[0].campos == {"logradouro": "Rua A", "numero": 10, "municipio": "Boa Vista", "uf": "RR"}
    assert linhas[2].motivo and "coluna" in linhas[2].motivo
    assert linhas[3].motivo == "linha em branco"
    assert linhas[4].motivo is None and "numero" not in linhas[4].campos
    assert any("dígito" in a for a in linhas[4].avisos)
    assert linhas[5].campos["numero"] == 20
    assert linhas[6].campos == {"municipio": "Boa Vista", "uf": "RR"}
    assert sum(1 for li in linhas if li.motivo) == 2


def test_separador_ponto_e_virgula_e_latin1():
    """Separador `;` e arquivo em latin-1 (o que sai do Excel brasileiro). MEDIDO nesta sessão: o
    `charset_normalizer` usado por `app.ingestao.csv_normalizar._decodificar` erra a codificação em amostra
    MUITO curta (duas linhas com dois acentos viraram `Rua S?o Jo?o`); com um arquivo do tamanho de um
    cadastro real ele acerta. A fronteira fica escrita aqui: arquivo latin-1 minúsculo pode ser lido com
    acento errado — o endereço ainda geocodifica, porque a comparação no banco passa por `unaccent`."""
    corpo = "\n".join(f"Rua São João {i};Boa Vista;RR" for i in range(1, 40))
    dados = ("logradouro;municipio;uf\n" + corpo + "\n").encode("latin-1")
    linhas = list(tabela.linhas(dados, {"logradouro": "logradouro", "municipio": "municipio", "uf": "uf"}))
    assert linhas[0].campos["logradouro"] == "Rua São João 1"
    assert linhas[0].campos["municipio"] == "Boa Vista"


def test_mapeamento_com_coluna_inexistente_e_recusado():
    dados = _csv(["logradouro,municipio", "Rua A,Boa Vista"])
    with pytest.raises(ValueError, match="coluna inexistente"):
        list(tabela.linhas(dados, {"logradouro": "logradouro", "cep": "cep_do_cliente"}))


def test_mapeamento_so_com_numero_e_uf_e_recusado():
    with pytest.raises(ValueError, match="localizam"):
        tabela.conferir_mapeamento({"numero": "n", "uf": "uf"}, ["n", "uf"])


def test_arquivo_vazio_e_ilegivel():
    with pytest.raises(tabela.ArquivoIlegivel):
        tabela.colunas(b"")


def test_teto_de_linhas_para_o_lote(monkeypatch):
    monkeypatch.setattr(limites, "GEOCOD_LINHAS_MAX", 3)
    dados = _csv(["municipio"] + ["Boa Vista"] * 5)
    gerador = tabela.linhas(dados, {"municipio": "municipio"})
    lidas = []
    with pytest.raises(tabela.LinhasDemais):
        for li in gerador:
            lidas.append(li)
    assert len(lidas) == 3


def test_xlsx_lido_pelo_conteudo_e_nao_pela_extensao():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Logradouro", "Numero", "Cidade", "UF"])
    ws.append(["Rua A", 10, "Boa Vista", "RR"])
    ws.append([None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    dados = buf.getvalue()
    assert tabela.e_xlsx(dados) is True
    saida = tabela.colunas(dados)
    assert saida["mapeamento_proposto"]["municipio"] == "Cidade"
    linhas = list(tabela.linhas(dados, saida["mapeamento_proposto"]))
    assert linhas[0].campos == {"logradouro": "Rua A", "numero": 10, "municipio": "Boa Vista", "uf": "RR"}
    assert linhas[1].motivo == "linha em branco"


def test_zip_que_nao_e_planilha_nao_passa_por_xlsx():
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("qualquer.txt", "nada")
    assert tabela.e_xlsx(buf.getvalue()) is False


def test_celula_gigante_e_truncada_com_aviso():
    grande = "A" * (limites.GEOCOD_CAMPO_TEXTO_MAX + 50)
    dados = _csv(["logradouro,municipio", f"{grande},Boa Vista"])
    linha = next(iter(tabela.linhas(dados, {"logradouro": "logradouro", "municipio": "municipio"})))
    assert len(linha.campos["logradouro"]) == limites.GEOCOD_CAMPO_TEXTO_MAX
    assert any("truncado" in a for a in linha.avisos)

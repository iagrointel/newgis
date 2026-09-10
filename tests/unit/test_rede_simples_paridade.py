"""O documento da rede simples (`docs/rede/REDE_SIMPLES.md`) é parte do portão do item
L4-18-rede-simples-trace-network — a cláusula "paridade contra trace network escrita". Este teste impede que
ele vire enfeite: confere que a tabela de paridade existe, cobre as capacidades que o item promete, que o
vocabulário de direção do documento é o MESMO do código, e que o catálogo mínimo descrito no documento é o
que o código gera. Não roda contra banco nenhum."""

import re
from pathlib import Path

from app.rede_utilidades import fluxo, simples

DOC = Path(__file__).resolve().parents[2] / "docs" / "rede" / "REDE_SIMPLES.md"
CAPACIDADES = (
    "rede sem pacote de ativos",
    "origem em feature classes existentes",
    "direção de fluxo por atributo",
    "atributos de rede",
    "traçado conectado",
    "traçado a montante / a jusante",
    "caminho mais curto",
    "barreiras",
    "áreas sujas",
    "promover a utility network",
)


def texto() -> str:
    return DOC.read_text(encoding="utf-8")


def test_documento_existe_e_cita_as_fontes_da_esri():
    t = texto()
    for fonte in ("what-is-a-trace-network-.htm", "network-attributes.htm",
                  "dirty-areas-in-a-trace-network.htm", "trace-network-service/"):
        assert fonte in t, f"o documento não cita a fonte {fonte}"


def test_tabela_de_paridade_cobre_as_capacidades_do_item():
    t = texto()
    for capacidade in CAPACIDADES:
        assert re.search(rf"^\| {re.escape(capacidade)} \|", t, re.M), f"falta a linha {capacidade!r}"


def test_toda_linha_da_tabela_declara_um_estado_do_vocabulario():
    estados = set()
    for linha in texto().splitlines():
        if linha.startswith("| ") and linha.count("|") == 5 and "capacidade |" not in linha \
                and not linha.startswith("|---"):
            # o estado é a primeira palavra da coluna; o resto da célula é a ressalva ("parcial: ...")
            estados.add(linha.rsplit("|", 2)[1].strip().split(":")[0].split("(")[0].strip())
    assert estados, "a tabela de paridade não foi encontrada"
    assert estados <= {"feito", "parcial", "fora", "além"}, estados


def test_vocabulario_de_direcao_do_documento_e_o_do_codigo():
    t = texto()
    for valor in fluxo.DIRECOES:
        assert f"`{valor}`" in t, f"o documento não descreve a direção {valor!r}"
    assert set(fluxo.DIRECOES) == set(simples.DIRECOES)
    assert fluxo.CHAVE_DIRECAO == simples.CAMPO_DIRECAO_INTERNO
    assert fluxo.PADRAO == simples.DIRECAO_PADRAO == "digitalizada"


def test_catalogo_minimo_do_documento_e_o_que_o_codigo_gera():
    doc = simples.doc_minimo("agua", "rede de teste interno")
    assert [d["codigo"] for d in doc["dominios"]] == ["rede"]
    assert [t["codigo"] for t in doc["tiers"]] == ["unico"]
    assert doc["categorias"] == []
    assert [t["codigo"] for t in doc["terminais"]] == ["juncao-simples"]
    assert doc["terminais"][0]["caminhos_validos"] == [], \
        "caminho válido faria o traçado atravessar dispositivo; rede simples não tem dispositivo"
    assert len(doc["terminais"][0]["terminais"]) == 1
    assert {g["codigo"]: g["geometria"] for g in doc["grupos"]} == {"juncao": "ponto", "trecho": "linha"}
    assert len(doc["tipos"]) == 2 and len(doc["regras"]) == 1
    assert [a["codigo"] for a in doc["atributos"]] == [simples.CAMPO_DIRECAO_INTERNO]
    t = texto()
    assert "1 domínio (`rede`), 1 tier (`unico`), 0 categorias" in t


def test_catalogo_minimo_passa_no_validador_do_pacote():
    """O pacote mínimo que `promover` carimba é validado pelo mesmo `pacote.ler` de qualquer pacote — aqui,
    sem banco, direto na forma canônica."""
    from app.rede_utilidades import pacote as pacote_mod

    doc = simples.doc_minimo("agua", "rede de teste interno")
    lido = pacote_mod.ler(pacote_mod.canonizar(doc))
    assert lido["pacote"]["codigo"] == "rede-simples"

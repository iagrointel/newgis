"""Pacote de ativos da rede de utilidades (item L4-01-a-pacote-de-ativos): forma canônica, validação de esquema,
conferência de referência e localizador de linha. Sem banco — o que precisa de banco está em
tests/api/test_rede_pacote.py.

Cláusulas do portão provadas aqui: "validação de esquema JSON recusa pacote sem tier ou com tipo sem grupo";
"pacote 'elétrica-BR' com os grupos/tipos que cobrem as 13 camadas de rede da BDGD Módulo 10"; "pacote
'água-EPANET' com junction/pipe/pump/valve/tank/reservoir"; e a metade de "round-trip" que não depende de banco
(o arquivo entregue já está na forma canônica)."""

import copy
import json

import pytest

from app.rede_utilidades import instalados, localizador
from app.rede_utilidades import pacote as pacote_mod

# as 13 camadas de rede da BDGD citadas no portão do item (UCBT/UCMT e UGBT/UGMT contam como uma cada)
CAMADAS_BDGD = [
    "SUB", "CTMT", "SSDMT", "SSDBT", "UNTRMT", "UNSEMT", "UNCRMT", "UNREMT", "RAMLIG",
    ("UCBT_tab", "UCMT_tab"), ("UGBT_tab", "UGMT_tab"), "PIP", "PONNOT",
]
GRUPOS_EPANET = ("no", "tubulacao", "bomba", "valvula",
                 "reservatorio_de_nivel_variavel", "reservatorio_de_nivel_fixo")


def _doc(codigo: str) -> dict:
    return pacote_mod.ler(instalados.bruto(codigo))


def _bytes_de(doc: dict) -> bytes:
    """Serializa SEM canonizar (é assim que um pacote chega de fora: ordem qualquer, recuo qualquer)."""
    return (json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _recusa(doc: dict) -> list[dict]:
    with pytest.raises(pacote_mod.ErroPacote) as exc:
        pacote_mod.ler(_bytes_de(doc))
    return exc.value.problemas


def _linha_do_texto(bruto: bytes, linha: int) -> str:
    return bruto.decode("utf-8").splitlines()[linha - 1]


# --- forma canônica e ida e volta ------------------------------------------------------------------

@pytest.mark.parametrize("codigo", ["eletrica-br", "agua-epanet"])
def test_pacote_instalado_esta_na_forma_canonica(codigo):
    bruto = instalados.bruto(codigo)
    assert pacote_mod.canonizar(pacote_mod.ler(bruto)) == bruto


@pytest.mark.parametrize("codigo", ["eletrica-br", "agua-epanet"])
def test_forma_canonica_nao_depende_da_ordem_do_arquivo(codigo):
    """O mesmo pacote com as listas embaralhadas e as chaves em outra ordem dá os MESMOS bytes canônicos."""
    doc = _doc(codigo)
    bagunca = {}
    for chave in reversed(list(doc)):
        valor = doc[chave]
        bagunca[chave] = list(reversed(valor)) if isinstance(valor, list) else valor
    assert pacote_mod.canonizar(bagunca) == instalados.bruto(codigo)


# --- validação: o que o portão manda recusar --------------------------------------------------------

def test_pacote_sem_tier_e_recusado():
    doc = _doc("agua-epanet")
    del doc["tiers"]
    problemas = _recusa(doc)
    assert any(p["erro"] == "esquema" and "tiers" in p["mensagem"] for p in problemas), problemas


def test_pacote_com_lista_de_tiers_vazia_e_recusado():
    doc = _doc("agua-epanet")
    doc["tiers"] = []
    problemas = _recusa(doc)
    assert [p["caminho"] for p in problemas] == ["tiers"]
    assert problemas[0]["erro"] == "esquema"


def test_tipo_sem_a_chave_grupo_e_recusado():
    doc = _doc("agua-epanet")
    del doc["tipos"][0]["grupo"]
    problemas = _recusa(doc)
    assert any(p["caminho"] == "tipos[0]" and "grupo" in p["mensagem"] for p in problemas), problemas


def test_tipo_apontando_grupo_que_nao_existe_e_recusado_com_a_linha():
    doc = _doc("agua-epanet")
    doc["tipos"][2]["grupo"] = "grupo-que-nao-existe"
    bruto = _bytes_de(doc)
    with pytest.raises(pacote_mod.ErroPacote) as exc:
        pacote_mod.ler(bruto)
    problemas = [p for p in exc.value.problemas if p["erro"] == "grupo_inexistente"]
    assert len(problemas) == 1, exc.value.problemas
    assert problemas[0]["caminho"] == "tipos[2].grupo"
    assert "grupo-que-nao-existe" in _linha_do_texto(bruto, problemas[0]["linha"])


def test_tier_apontando_dominio_que_nao_existe_e_recusado_com_a_linha():
    """Primeira metade da refutação do item."""
    doc = _doc("agua-epanet")
    doc["tiers"][1]["dominio"] = "dominio-fantasma"
    bruto = _bytes_de(doc)
    with pytest.raises(pacote_mod.ErroPacote) as exc:
        pacote_mod.ler(bruto)
    problemas = [p for p in exc.value.problemas if p["erro"] == "dominio_inexistente"]
    assert [p["caminho"] for p in problemas] == ["tiers[1].dominio"]
    assert "dominio-fantasma" in _linha_do_texto(bruto, problemas[0]["linha"])


def test_dois_tipos_com_o_mesmo_codigo_no_mesmo_grupo_sao_recusados_com_as_duas_linhas():
    """Segunda metade da refutação do item: a mensagem aponta a linha da repetição E a da primeira ocorrência."""
    doc = _doc("agua-epanet")
    gemeo = copy.deepcopy(doc["tipos"][0])
    gemeo["chave"] = "chave-diferente-mesmo-codigo"
    doc["tipos"].append(gemeo)
    bruto = _bytes_de(doc)
    with pytest.raises(pacote_mod.ErroPacote) as exc:
        pacote_mod.ler(bruto)
    problemas = [p for p in exc.value.problemas if p["erro"] == "codigo_repetido"]
    assert len(problemas) == 1, exc.value.problemas
    p = problemas[0]
    assert p["linha"] is not None and p["linha_anterior"] is not None and p["linha"] > p["linha_anterior"]
    # a linha apontada abre o elemento repetido; a chave que o distingue está nas linhas seguintes do bloco
    linhas = bruto.decode("utf-8").splitlines()
    assert "chave-diferente-mesmo-codigo" in "\n".join(linhas[p["linha"] - 1:p["linha"] + 12])
    assert "chave-diferente-mesmo-codigo" not in "\n".join(linhas[:p["linha_anterior"] + 12])


def test_referencia_a_tier_de_outro_dominio_e_recusada():
    doc = _doc("eletrica-br")
    tipo = next(t for t in doc["tipos"] if t["grupo"] == "ponto_notavel")
    tipo["tier"] = "media_tensao"  # o grupo é do domínio 'estrutura', o tier é do 'eletrica_distribuicao'
    problemas = [p for p in _recusa(doc) if p["erro"] == "tier_de_outro_dominio"]
    assert len(problemas) == 1, problemas


def test_todos_os_problemas_saem_de_uma_vez():
    """Quem manda um pacote errado recebe a lista inteira, não um erro por vez."""
    doc = _doc("agua-epanet")
    doc["tipos"][0]["grupo"] = "nao-existe-1"
    doc["tipos"][1]["terminal"] = "nao-existe-2"
    doc["tiers"][0]["dominio"] = "nao-existe-3"
    problemas = _recusa(doc)
    assert {p["erro"] for p in problemas} >= {"grupo_inexistente", "terminal_inexistente", "dominio_inexistente"}


def test_json_quebrado_devolve_a_linha_do_erro():
    with pytest.raises(pacote_mod.ErroPacote) as exc:
        pacote_mod.ler(b'{\n "esquema": "plat.rede.pacote",\n "esquema_versao": 1,\n')
    assert exc.value.problemas[0]["erro"] == "json_invalido"
    assert exc.value.problemas[0]["linha"] is not None


# --- localizador de linha ---------------------------------------------------------------------------

def test_localizador_acha_a_linha_no_arquivo_entregue():
    bruto = instalados.bruto("agua-epanet")
    texto = bruto.decode("utf-8")
    for i, tipo in enumerate(pacote_mod.ler(bruto)["tipos"]):
        linha = localizador.linha(texto, ["tipos", i, "chave"])
        assert tipo["chave"] in texto.splitlines()[linha - 1]


def test_localizador_devolve_none_para_caminho_inexistente():
    assert localizador.linha('{"a": 1}', ["b"]) is None
    assert localizador.linha('{"a": [1]}', ["a", 5]) is None


def test_texto_do_caminho():
    assert localizador.texto_do_caminho(["tipos", 3, "grupo"]) == "tipos[3].grupo"
    assert localizador.texto_do_caminho([]) == "(raiz)"


# --- cobertura das camadas prometidas no portão ------------------------------------------------------

def test_eletrica_br_cobre_as_13_camadas_de_rede_da_bdgd():
    doc = _doc("eletrica-br")
    declaradas = {c for g in doc["grupos"] for c in g["camadas_fonte"]}
    faltando = []
    for camada in CAMADAS_BDGD:
        nomes = (camada,) if isinstance(camada, str) else camada
        if not set(nomes) & declaradas:
            faltando.append(camada)
    assert faltando == [], f"camadas da BDGD sem grupo no pacote: {faltando}"


def test_eletrica_br_mapeia_coluna_a_coluna_cada_camada():
    """Toda camada citada por um grupo tem pelo menos COD_ID mapeado; cada atributo diz se a origem foi conferida."""
    doc = _doc("eletrica-br")
    por_camada: dict[str, set] = {}
    for a in doc["atributos"]:
        assert a["origem"]["esquema"] == "bdgd_modulo_10", a
        por_camada.setdefault(a["origem"]["camada"], set()).add(a["origem"]["coluna"])
    for grupo in doc["grupos"]:
        for camada in grupo["camadas_fonte"]:
            assert "COD_ID" in por_camada.get(camada, set()), camada
    conferidas = {a["origem"]["camada"] for a in doc["atributos"] if a["origem"]["conferida"]}
    nao_conferidas = {a["origem"]["camada"] for a in doc["atributos"] if not a["origem"]["conferida"]}
    # fronteira honesta declarada no próprio dado: 5 camadas ainda sem conferência contra extração real
    assert nao_conferidas == {"SUB", "UNSEMT", "UNCRMT", "UNREMT", "UGMT_tab"}
    assert len(conferidas) == 11 and not (conferidas & nao_conferidas)


def test_agua_epanet_tem_os_seis_grupos_do_modelo():
    doc = _doc("agua-epanet")
    assert {g["codigo"] for g in doc["grupos"]} == set(GRUPOS_EPANET)
    tipos_valvula = {t["codigos_fonte"][0] for t in doc["tipos"] if t["grupo"] == "valvula"}
    assert tipos_valvula == {"PRV", "PSV", "PBV", "FCV", "TCV", "GPV"}


def test_o_mesmo_formato_serve_para_duas_disciplinas():
    """A hipótese do item: elétrica e água usam o MESMO esquema, sem campo condicionado à disciplina."""
    assert {_doc(c)["pacote"]["disciplina"] for c in ("eletrica-br", "agua-epanet")} == {"eletrica", "agua"}
    assert {_doc(c)["esquema"] for c in ("eletrica-br", "agua-epanet")} == {"plat.rede.pacote"}


def test_documento_do_pacote_bate_com_os_arquivos_entregues():
    """docs/PACOTE_REDE.md é gerado do dado; se o pacote mudar e o documento não, isto reprova."""
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, "docs/gerar_pacote_rede.py", "--check"],
                       cwd=raiz, capture_output=True, check=False)
    assert r.returncode == 0, r.stderr.decode("utf-8")

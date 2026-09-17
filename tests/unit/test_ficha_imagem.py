"""Unidade da ficha de metadado e licença da imagem (item L1-27): a tabela de licenças, a validação da ficha,
a projeção para propriedades STAC e a exportação ISO 19115-2 validada contra o XSD cacheado.

Nada aqui toca banco: a ficha é uma estrutura de dados e a decisão de licença é função pura — é o que permite
que a mesma regra seja chamada do compartilhamento, da tela e do exportador sem uma segunda cópia da tabela.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re

import pytest
from lxml import etree

from app.catalogo import metadado_imagem
from app.erros import ErroAPI
from app.imagens import ficha as fi

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ITEM = "L1-27-ficha-de-metadado-e-licenca-da-imagem"

BASE = {
    "plataforma": "sentinel-2b",
    "instrumentos": ["msi"],
    "gsd": 10,
    "data_aquisicao": "2026-05-01T13:00:00Z",
    "fornecedor": "agência de teste interno",
    "licenca": "copernicus",
    "fonte": "upload",
    "atribuicao": "atribuição de teste interno",
}


def ficha_de(**mudancas):
    return fi.validar({**BASE, **mudancas})


# ------------------------------------------------------------------ a tabela é única e fechada
def test_tabela_de_licencas_cobre_a_lista_da_casa(medida):
    esperado = {
        "copernicus", "cc-by-4.0", "cc-by-sa-4.0", "dominio-publico", "odbl-1.0",
        "comercial-eula", "sem-licenca-escrita",
    }
    assert {lic.codigo for lic in fi.LICENCAS} == esperado
    assert len(fi.POR_CODIGO) == len(fi.LICENCAS), "código de licença repetido na tabela"
    assert fi.LICENCA_PADRAO == "sem-licenca-escrita"
    medida(ITEM)("licencas_na_tabela", len(fi.LICENCAS), "licenças",
                 "len(app.imagens.ficha.LICENCAS) — a única tabela de licenças do repositório")


def test_catalogo_de_licencas_e_a_mesma_tabela():
    """`catalogo_licencas` é o que a API devolve à tela: tem de ser projeção da tabela, não uma segunda lista."""
    catalogo = fi.catalogo_licencas()
    assert [c["codigo"] for c in catalogo] == [lic.codigo for lic in fi.LICENCAS]
    for c, lic in zip(catalogo, fi.LICENCAS, strict=True):
        assert (c["rotulo"], c["stac"], c["redistribuicao"], c["vendavel"]) == (
            lic.rotulo, lic.stac, lic.redistribuicao, lic.vendavel
        )


def test_nenhum_outro_arquivo_do_repositorio_repete_a_lista_de_licencas():
    """Cláusula do portão: "lista de licenças lida do código (uma só tabela)". Se um segundo arquivo escrever
    os códigos de licença, ele vira uma tabela paralela que envelhece calada — e este teste reprova."""
    codigos = [lic.codigo for lic in fi.LICENCAS]
    padrao = re.compile("|".join(re.escape(c) for c in codigos))
    permitidos = {
        "app/imagens/ficha.py",                       # a tabela
        "tests/unit/test_ficha_imagem.py",            # este teste
        "tests/api/imagens/test_ficha_api.py",        # os testes de API do item
        "tests/api/cruzado_casos.py",                 # o caso da varredura cruzada
        "tests/e2e/test_ficha_imagem.py",             # o e2e do editor
    }
    ofensores = []
    for caminho in [*(RAIZ / "app").rglob("*.py"), *(RAIZ / "web").rglob("*.js"),
                    *(RAIZ / "db" / "migracoes").glob("*.sql")]:
        rel = str(caminho.relative_to(RAIZ))
        if rel in permitidos or "__pycache__" in rel:
            continue
        if padrao.search(caminho.read_text(encoding="utf-8", errors="ignore")):
            ofensores.append(rel)
    assert ofensores == [], f"a lista de licenças foi repetida fora da tabela: {ofensores}"


@pytest.mark.parametrize("codigo,publico", [
    ("copernicus", True), ("cc-by-4.0", True), ("cc-by-sa-4.0", True), ("dominio-publico", True),
    ("odbl-1.0", True), ("comercial-eula", False), ("sem-licenca-escrita", False),
])
def test_redistribuicao_decide_link_publico_e_exportacao_em_massa(codigo, publico):
    assert fi.permite_link_publico(codigo) is publico
    assert fi.permite_exportacao_em_massa(codigo) is publico


def test_licenca_desconhecida_ou_ausente_cai_no_padrao_auditavel():
    """Nunca o contrário: código que a casa não conhece não pode virar 'livre' por omissão."""
    for codigo in (None, "", "cc-by-nc-4.0", "licenca-que-nao-existe"):
        assert fi.licenca(codigo).codigo == fi.LICENCA_PADRAO
        assert fi.permite_link_publico(codigo) is False
        assert fi.vendavel(codigo) is False


def test_d17_item_sem_licenca_escrita_e_auditavel_nao_vendavel():
    lic = fi.POR_CODIGO["sem-licenca-escrita"]
    assert lic.vendavel is False and lic.redistribuicao == "restrita"
    assert "não vendável" in " ".join(fi.avisos(ficha_de(licenca="sem-licenca-escrita")))
    assert all(x.vendavel for x in fi.LICENCAS if x.codigo != "sem-licenca-escrita")


def test_item_sem_ficha_conta_como_sem_licenca_escrita():
    assert fi.do_item(None) is None
    assert fi.do_item({}) is None
    assert fi.licenca_do_item({"colecao": "1-imagens"}) == "sem-licenca-escrita"
    assert fi.avisos(None) and "não vendável" in fi.avisos(None)[0]


def test_ficha_gravada_invalida_nao_vira_licenca_livre():
    """Um jsonb editado à mão com licença livre mas ficha quebrada não pode destravar o link público."""
    quebrada = {"ficha": {"licenca": "cc-by-4.0"}}  # sem plataforma/instrumentos/gsd/data/fornecedor/fonte
    assert fi.do_item(quebrada) is None
    assert fi.permite_link_publico(fi.licenca_do_item(quebrada)) is False


# ------------------------------------------------------------------ validação
@pytest.mark.parametrize("campo", fi.OBRIGATORIOS)
def test_campo_obrigatorio_ausente_reprova(campo):
    bruto = {k: v for k, v in BASE.items() if k != campo}
    with pytest.raises(ErroAPI) as e:
        fi.validar(bruto)
    assert e.value.status_code == 422 and e.value.detalhe["campo"] == campo


def test_licenca_que_exige_atribuicao_reprova_sem_o_texto():
    with pytest.raises(ErroAPI) as e:
        fi.validar({**BASE, "atribuicao": None})
    assert e.value.detalhe["campo"] == "atribuicao"
    # a única da tabela que não exige atribuição passa sem ela
    assert fi.validar({**BASE, "licenca": "dominio-publico", "atribuicao": None}).atribuicao is None


@pytest.mark.parametrize("mudanca,campo", [
    ({"gsd": -1}, "gsd"),
    ({"nuvem_pct": 140}, "nuvem_pct"),
    ({"sol_elevacao": 120}, "sol_elevacao"),
    ({"angulo_off_nadir": 91}, "angulo_off_nadir"),
    ({"orbita_estado": "de lado"}, "orbita_estado"),
    ({"fonte": "correio"}, "fonte"),
    ({"licenca": "cc-by-nc-4.0"}, "licenca"),
    ({"data_aquisicao": "primeiro de maio"}, "data_aquisicao"),
    ({"instrumentos": []}, "instrumentos"),
])
def test_valor_fora_da_faixa_reprova_com_o_campo(mudanca, campo):
    with pytest.raises(ErroAPI) as e:
        fi.validar({**BASE, **mudanca})
    assert e.value.status_code == 422 and e.value.detalhe["campo"] == campo


def test_intervalo_de_aquisicao_invertido_reprova():
    with pytest.raises(ErroAPI) as e:
        fi.validar({**BASE, "data_aquisicao_fim": "2026-04-01T13:00:00Z"})
    assert e.value.detalhe["campo"] == "data_aquisicao_fim"


def test_data_com_outro_fuso_e_normalizada_para_utc():
    f = ficha_de(data_aquisicao="2026-05-01T10:00:00-03:00")
    assert f.data_aquisicao == "2026-05-01T13:00:00Z"


def test_instrumentos_aceita_texto_separado_por_virgula():
    assert ficha_de(instrumentos="msi, oli").instrumentos == ["msi", "oli"]


# ------------------------------------------------------------------ projeção STAC
def test_projecao_stac_usa_os_nomes_das_extensoes():
    props = fi.para_stac(ficha_de(
        constelacao="sentinel-2", nuvem_pct=3.2, angulo_off_nadir=4.1, angulo_incidencia=8.0,
        sol_azimute=40.0, sol_elevacao=55.1, orbita_estado="descending", orbita_relativa=24,
        orbita_absoluta=48123,
    ))
    assert props["platform"] == "sentinel-2b"
    assert props["instruments"] == ["msi"]
    assert props["constellation"] == "sentinel-2"
    assert props["gsd"] == 10.0
    assert props["datetime"] == "2026-05-01T13:00:00Z"
    assert props["eo:cloud_cover"] == 3.2
    assert props["view:off_nadir"] == 4.1
    assert props["view:incidence_angle"] == 8.0
    assert props["view:sun_azimuth"] == 40.0
    assert props["view:sun_elevation"] == 55.1
    assert props["sat:orbit_state"] == "descending"
    assert props["sat:relative_orbit"] == 24
    assert props["sat:absolute_orbit"] == 48123
    assert props["providers"] == [{"name": BASE["fornecedor"], "roles": ["producer", "licensor"]}]
    assert props["license"] == fi.POR_CODIGO["copernicus"].stac
    assert props["plat:atribuicao"] == BASE["atribuicao"]


def test_intervalo_de_aquisicao_vira_start_end_com_datetime_nulo():
    """STAC 1.0: quando a aquisição é um intervalo, `datetime` é null e o par start/end carrega a informação."""
    props = fi.para_stac(ficha_de(data_aquisicao_fim="2026-05-01T13:10:00Z"))
    assert props["datetime"] is None
    assert props["start_datetime"] == "2026-05-01T13:00:00Z"
    assert props["end_datetime"] == "2026-05-01T13:10:00Z"


def test_link_de_licenca_so_existe_quando_a_licenca_tem_endereco():
    assert fi.links_stac(ficha_de())[0]["rel"] == "license"
    assert fi.links_stac(ficha_de(licenca="comercial-eula")) == []


def test_ida_e_volta_pelo_json_guardado_preserva_a_ficha():
    f = ficha_de(nuvem_pct=3.2, orbita_relativa=24, observacao="cena de teste interno")
    assert fi.para_json(fi.validar(fi.para_json(f))) == fi.para_json(f)


# ------------------------------------------------------------------ ISO 19115-2
def linha_de_item(dados: dict) -> dict:
    agora = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.UTC)
    return {
        "id": "11111111-2222-3333-4444-555555555555", "titulo": "cena de teste interno",
        "resumo": "cena de teste interno", "descricao": None, "tags": ["teste"], "creditos": None,
        "status": "autoritativo", "dono_nome": "pessoa de teste", "miniatura_chave": None,
        "termos_de_uso": None, "criado_em": agora, "modificado_em": agora,
        "xmin": -47.0, "ymin": -16.0, "xmax": -46.0, "ymax": -15.0, "dados": dados, "tipo": "raster",
    }


def test_iso_19115_2_valida_contra_o_xsd(medida):
    f = ficha_de(nuvem_pct=3.2, sol_elevacao=55.1, sol_azimute=40.0, orbita_estado="descending",
                 orbita_relativa=24, constelacao="sentinel-2")
    xml = metadado_imagem.gerar_xml(linha_de_item({"ficha": fi.para_json(f)}), f, "inquilino de teste",
                                    "https://exemplo.invalido")
    metadado_imagem.validar(xml)  # levanta ErroMetadadoInvalido se não validar
    medida(ITEM)(
        "iso_19115_2_valida_no_xsd", 1, "0=reprovou,1=passou",
        "app.catalogo.metadado_imagem.validar(gerar_xml(...)) contra "
        "docs/xsd/cache/www.isotc211.org/2005/gmi/gmi.xsd (cache offline de docs/xsd/baixar_iso19139.py)",
    )
    doc = etree.fromstring(xml)
    assert doc.tag == f"{{{metadado_imagem.GMI}}}MI_Metadata"
    assert doc.find(f"{{{metadado_imagem.GMI}}}acquisitionInformation") is not None


@pytest.mark.parametrize("codigo", [lic.codigo for lic in fi.LICENCAS])
def test_iso_valida_para_toda_licenca_da_tabela(codigo):
    f = ficha_de(licenca=codigo)
    xml = metadado_imagem.gerar_xml(linha_de_item({"ficha": fi.para_json(f)}), f, "inquilino de teste",
                                    "https://exemplo.invalido")
    metadado_imagem.validar(xml)


def test_licenca_e_data_do_iso_batem_com_o_stac():
    """Refutação do item: exportar o ISO e conferir que licença e data são as MESMAS do item STAC."""
    for codigo in [lic.codigo for lic in fi.LICENCAS]:
        f = ficha_de(licenca=codigo, data_aquisicao="2026-03-17T09:30:00Z")
        xml = metadado_imagem.gerar_xml(linha_de_item({"ficha": fi.para_json(f)}), f, "inquilino de teste",
                                        "https://exemplo.invalido")
        stac, casa, data = metadado_imagem.licenca_e_data_do_xml(xml)
        props = fi.para_stac(f)
        assert stac == props["license"], codigo
        assert casa == props["plat:licenca"] == codigo
        assert data == props["datetime"]


def test_iso_traz_a_atribuicao_e_o_aviso_de_nao_vendavel():
    f = ficha_de(licenca="sem-licenca-escrita")
    xml = metadado_imagem.gerar_xml(linha_de_item({"ficha": fi.para_json(f)}), f, "inquilino de teste",
                                    "https://exemplo.invalido").decode("utf-8")
    assert BASE["atribuicao"] in xml
    assert "auditável, não vendável" in xml


def test_perfil_generico_do_l0_09_continua_valendo_para_o_mesmo_item():
    """O gerador do L0-09 não foi tocado: o mesmo item sai em ISO 19139/GMD quando o perfil é o genérico."""
    from app.catalogo import metadado

    xml = metadado.gerar_xml(linha_de_item({}), "inquilino de teste", "https://exemplo.invalido")
    metadado.validar(xml)
    assert etree.fromstring(xml).tag == f"{{{metadado.GMD}}}MD_Metadata"


# ------------------------------------------------------------------ a tela lê a tabela, não a repete
def test_tela_da_ficha_nao_escreve_licenca_nenhuma():
    js = (RAIZ / "web" / "js" / "imagens" / "ficha.js").read_text(encoding="utf-8")
    assert "/api/imagens/licencas" in js, "a tela tem de ler a tabela da API"
    for lic in fi.LICENCAS:
        assert lic.rotulo not in js and lic.codigo not in js


def test_a_migracao_do_tipo_raster_nao_repete_a_lista():
    """O JSON Schema de `plat.tipo_item` guarda só `ficha: object`; a lista fechada fica no código."""
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (RAIZ / "db" / "migracoes").glob("*_ficha_imagem.sql"))
    assert '"type":"object"' in sql
    for lic in fi.LICENCAS:
        assert lic.codigo not in sql


def test_medidas_do_item_existem_e_batem_com_a_tabela():
    caminho = RAIZ / "tests" / "medidas" / "L1-27-ficha-de-metadado-e-licenca-da-imagem.json"
    if not caminho.exists():
        pytest.skip("medidas ainda não gravadas nesta árvore")
    medidas = json.loads(caminho.read_text(encoding="utf-8"))
    assert medidas["medidas"]["licencas_na_tabela"]["valor"] == len(fi.LICENCAS)

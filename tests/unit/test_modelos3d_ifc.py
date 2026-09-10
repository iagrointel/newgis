"""Leitura do IFC aberto da buildingSMART e montagem do glTF (item L2-09-c).

Cláusula do portão coberta aqui: "IFC de exemplo aberto convertido com N elementos = N linhas na tabela".
A parte "N linhas na tabela" é do teste de API; aqui se prova que N é o número de elementos do arquivo, e
que cada um traz GUID, tipo, pavimento e propriedades.
"""

import hashlib

import pytest

from app.modelos3d import glb, ifc, montagem
from tests.apoio_modelos3d import IFC_ABERTO

SHA256_ARQUIVO = "8790a1e193e82b8e7e7f337ec2633cd40f2120590317a1443503a25b079e2e80"
ELEMENTOS_ESPERADOS = 13          # medido no arquivo; ver tests/dados/FONTES_MODELOS3D.md
COM_FORMA_ESPERADOS = 11          # os 2 restantes (chimney, roof) são conjuntos sem forma própria no IFC
GUID_LAJE = "3zR0BOEcLADRKln4HYporH"   # 'floor', a laje do térreo


@pytest.fixture(scope="module")
def modelo():
    dados = IFC_ABERTO.read_bytes()
    assert hashlib.sha256(dados).hexdigest() == SHA256_ARQUIVO, "o IFC de teste mudou; refazer a ficha de fonte"
    return ifc.carregar(dados)


def test_esquema_e_unidade_saem_do_arquivo(modelo):
    assert modelo.esquema == "IFC4"
    assert modelo.unidade_m == pytest.approx(0.001)  # FILE declara milímetro


def test_conta_os_elementos_do_arquivo(modelo):
    assert len(modelo.elementos) == ELEMENTOS_ESPERADOS
    assert sum(1 for e in modelo.elementos if e.tem_geometria) == COM_FORMA_ESPERADOS
    assert len(modelo.sem_geometria) == ELEMENTOS_ESPERADOS - COM_FORMA_ESPERADOS


def test_todo_elemento_tem_identificador_global_unico(modelo):
    guids = [e.guid for e in modelo.elementos]
    assert len(set(guids)) == len(guids)
    assert all(len(g) == 22 for g in guids)


def test_estrutura_espacial_nao_vira_elemento(modelo):
    tipos = {e.tipo for e in modelo.elementos}
    assert not (tipos & {"IFCPROJECT", "IFCSITE", "IFCBUILDING", "IFCBUILDINGSTOREY", "IFCSPACE"})
    assert {"IFCWALL", "IFCSLAB"} <= tipos


def test_pavimento_vem_da_estrutura_espacial(modelo):
    paredes = [e for e in modelo.elementos if e.tipo == "IFCWALL"]
    assert paredes
    assert all(e.pavimento == "00 groundfloor" for e in paredes)


def test_propriedades_saem_por_conjunto(modelo):
    laje = next(e for e in modelo.elementos if e.guid == GUID_LAJE)
    assert laje.tipo == "IFCSLAB"
    assert laje.propriedades["Pset_SlabCommon"]["FireRating"] == "REI30"
    assert laje.propriedades["Pset_SlabCommon"]["IsExternal"] is True
    assert laje.propriedades["Pset_SlabCommon"]["LoadBearing"] is False
    assert laje.propriedades["Qto_SlabBaseQuantities"]["Depth"] == pytest.approx(250.0)


def test_geometria_sai_em_metros(modelo):
    """O arquivo é em milímetro; a casa toda trabalha em metro. Uma casa de 40 m, não de 40.000."""
    com_forma = [e for e in modelo.elementos if e.tem_geometria]
    xs = [v for e in com_forma for v in e.vertices[0::3]]
    zs = [v for e in com_forma for v in e.vertices[2::3]]
    assert 1.0 < (max(xs) - min(xs)) < 200.0
    assert 0.5 < (max(zs) - min(zs)) < 100.0


def test_indices_apontam_para_vertice_existente(modelo):
    for e in modelo.elementos:
        if e.tem_geometria:
            assert len(e.indices) % 3 == 0
            assert max(e.indices) < len(e.vertices) // 3


def test_arquivo_que_nao_e_ifc_e_recusado():
    with pytest.raises(ifc.IfcInvalido):
        ifc.carregar(b"nada a ver com STEP")


def test_teto_de_tamanho_e_respeitado():
    with pytest.raises(ifc.IfcInvalido) as e:
        ifc.carregar(IFC_ABERTO.read_bytes(), max_bytes=1000)
    assert "teto" in str(e.value)


def test_esquema_declarado_diferente_de_ifc_e_recusado():
    texto = IFC_ABERTO.read_text(errors="replace").replace("FILE_SCHEMA(('IFC4')", "FILE_SCHEMA(('AP203')")
    with pytest.raises(ifc.IfcInvalido):
        ifc.carregar(texto)


# ------------------------------------------------------------------ montagem do glTF
@pytest.fixture(scope="module")
def montado(modelo):
    return montagem.montar(modelo.elementos, "casa-de-teste")


def test_um_no_por_elemento_com_forma(montado, modelo):
    dados, resumo = montado
    gltf, binario = glb.ler(dados)
    assert len(gltf["nodes"]) == COM_FORMA_ESPERADOS == resumo["elementos_com_forma"]
    assert resumo["elementos"] == ELEMENTOS_ESPERADOS


def test_cada_no_carrega_o_guid_do_elemento(montado, modelo):
    dados, _ = montado
    gltf, _ = glb.ler(dados)
    guids_no_gltf = {n["extras"]["guid"] for n in gltf["nodes"]}
    guids_com_forma = {e.guid for e in modelo.elementos if e.tem_geometria}
    assert guids_no_gltf == guids_com_forma


def test_o_glb_montado_nao_tem_recurso_externo(montado):
    dados, _ = montado
    gltf, _ = glb.ler(dados)
    assert glb.recursos_externos(gltf) == []
    glb.exigir_embutido(gltf)


def test_o_glb_montado_e_relido_pelo_proprio_leitor(montado):
    dados, resumo = montado
    gltf, binario = glb.ler(dados)
    minimo, maximo = glb.caixa(gltf, binario)
    assert [round(v, 4) for v in minimo] == resumo["caixa_minima"]
    assert [round(v, 4) for v in maximo] == resumo["caixa_maxima"]
    assert minimo[1] == pytest.approx(0.0, abs=1e-6)  # origem no canto mínimo


def test_conversao_e_deterministica(modelo):
    """Duas conversões do mesmo arquivo dão o MESMO byte: cor por tipo é derivada, nunca sorteada."""
    a, _ = montagem.montar(modelo.elementos, "casa-de-teste")
    b, _ = montagem.montar(modelo.elementos, "casa-de-teste")
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_sem_elemento_com_forma_nao_monta():
    with pytest.raises(ValueError):
        montagem.montar([], "vazio")

"""Registro de CRS (item L2-17-crs-transformacoes): a lista curada aparece primeiro (a mesma ordem que a
rota /api/crs devolve e que o seletor do navegador não reordena), cada entrada curada existe de verdade
no banco EPSG do PROJ desta máquina, e proj4() devolve texto não vazio para os códigos curados."""

from app.crs import registro
from app.crs.curada import CURADA


def test_curada_aparece_primeiro_na_lista():
    lista = registro.listar()
    n = len(CURADA)
    assert [d.epsg for d in lista[:n]] == [e.epsg for e in CURADA]
    assert all(d.curada for d in lista[:n])
    assert not any(d.curada for d in lista[n:])


def test_cada_entrada_curada_existe_no_proj_desta_maquina():
    for entrada in CURADA:
        d = registro.obter(entrada.epsg)
        assert d is not None, f"EPSG:{entrada.epsg} não existe no banco EPSG do PROJ"
        assert d.nome, entrada.epsg


def test_lista_nao_tem_epsg_duplicado():
    lista = registro.listar()
    codigos = [d.epsg for d in lista]
    assert len(codigos) == len(set(codigos))


def test_proj4_de_cada_curada_nao_e_vazio_e_e_parseavel_pelo_pyproj():
    from pyproj import CRS

    for entrada in CURADA:
        texto = registro.proj4(entrada.epsg)
        assert texto, entrada.epsg
        # ida e volta: o texto devolvido tem de descrever um CRS válido de novo
        assert CRS.from_proj4(texto) is not None, (entrada.epsg, texto)


def test_obter_epsg_inexistente_devolve_none():
    assert registro.obter(999999) is None


def test_curada_cobre_exatamente_o_conjunto_utm_sirgas_do_epsg():
    """Documenta a correção sobre a hipótese do item (ver app/crs/curada.py): o conjunto real de zonas
    UTM SIRGAS2000 do Brasil, medido no banco EPSG, é 31965-31985 (21 zonas), não "31981-31985 e
    31965-31975" como o texto original do item dizia."""
    from pyproj.database import query_crs_info

    esperado = {
        int(r.code) for r in query_crs_info(auth_name="EPSG")
        if r.name and "SIRGAS 2000 / UTM zone" in r.name and 31960 <= int(r.code) <= 31990
    }
    curados_utm = {e.epsg for e in CURADA if e.grupo == "utm"}
    assert curados_utm == esperado
    assert curados_utm == set(range(31965, 31986))

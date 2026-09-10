"""Proxy raster do OSM (item L2-01-e-mapas-base): validação de z/x/y, escolha de host sempre dentro da lista
fixa e o cache em disco (HIT no 2º pedido, poda por tamanho). Não sobe servidor nem toca rede — `buscar_ladrilho`
é chamado com o host já respondendo do cache local nos testes de cache; o teste de rede real (upstream de
verdade) fica no e2e, que tem orçamento de tempo para isso."""

import os

import pytest

from app import limites
from app.erros import ErroAPI
from app.mapas_base import proxy_osm


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(proxy_osm, "CACHE_DIR", tmp_path / "mapa_base_osm")
    yield


def test_validar_zxy_aceita_a_faixa_do_slippy_map():
    proxy_osm.validar_zxy(0, 0, 0)
    proxy_osm.validar_zxy(19, 2**19 - 1, 2**19 - 1)


@pytest.mark.parametrize("z,x,y", [
    (-1, 0, 0), (20, 0, 0), (0, 1, 0), (0, 0, 1), (5, 32, 0), (5, 0, 32), (5, -1, 0),
])
def test_validar_zxy_recusa_fora_da_faixa(z, x, y):
    with pytest.raises(ErroAPI) as exc:
        proxy_osm.validar_zxy(z, x, y)
    assert exc.value.status_code == 422


def test_host_do_ladrilho_nunca_sai_da_lista_fixa():
    """Refutação do item: nenhuma combinação de z/x/y escolhe host fora de limites.MAPA_BASE_OSM_HOSTS —
    o único jeito de mudar o host de saída é editar o código, nunca um parâmetro de requisição."""
    vistos = set()
    for z in range(0, 6):
        for x in range(0, 2**z):
            for y in range(0, 2**z):
                vistos.add(proxy_osm._host_do_ladrilho(z, x, y))
    assert vistos, "nenhum host escolhido"
    assert vistos <= set(limites.MAPA_BASE_OSM_HOSTS), vistos - set(limites.MAPA_BASE_OSM_HOSTS)


def test_cache_hit_no_segundo_pedido(monkeypatch):
    chamadas = {"n": 0}

    class FalsoResultado:
        ok = True
        mensagem = "http_200"
        corpo = b"\x89PNG-fake-bytes"

    def falso_buscar_seguro(url, **kw):
        chamadas["n"] += 1
        return FalsoResultado()

    monkeypatch.setattr(proxy_osm.seguranca, "buscar_seguro", falso_buscar_seguro)

    corpo1, veio_do_cache1 = proxy_osm.buscar_ladrilho(3, 2, 1)
    corpo2, veio_do_cache2 = proxy_osm.buscar_ladrilho(3, 2, 1)

    assert veio_do_cache1 is False and veio_do_cache2 is True
    assert corpo1 == corpo2 == FalsoResultado.corpo
    assert chamadas["n"] == 1, "2º pedido não podia ir à rede"


def test_upstream_falhou_vira_erro_502_nao_cacheia(monkeypatch):
    class FalsoResultadoRuim:
        ok = False
        mensagem = "tempo_esgotado"
        corpo = b""

    monkeypatch.setattr(proxy_osm.seguranca, "buscar_seguro", lambda url, **kw: FalsoResultadoRuim())
    with pytest.raises(ErroAPI) as exc:
        proxy_osm.buscar_ladrilho(4, 1, 1)
    assert exc.value.status_code == 502
    assert not proxy_osm._caminho_cache(4, 1, 1).exists()


def test_abrir_espaco_apaga_o_mais_antigo_primeiro(monkeypatch):
    monkeypatch.setattr(limites, "MAPA_BASE_OSM_CACHE_BYTES_MAX", 400)
    proxy_osm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    antigo = proxy_osm._caminho_cache(1, 0, 0)
    novo = proxy_osm._caminho_cache(1, 1, 0)
    for caminho, mtime in ((antigo, 1_000_000), (novo, 2_000_000)):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"x" * 150)
        os.utime(caminho, (mtime, mtime))  # mtime explícito: nunca depende da resolução do relógio do FS
    proxy_osm._abrir_espaco(200)  # 150+150+200 > 400: apaga só o mais velho para caber
    assert not antigo.exists(), "o arquivo mais antigo tinha de ser apagado primeiro"
    assert novo.exists(), "o mais novo não devia ser tocado"


def test_resposta_ladrilho_marca_cache_no_cabecalho(monkeypatch):
    class FalsoResultado:
        ok = True
        mensagem = "http_200"
        corpo = b"\x89PNG-fake-bytes-2"

    monkeypatch.setattr(proxy_osm.seguranca, "buscar_seguro", lambda url, **kw: FalsoResultado())
    r1 = proxy_osm.resposta_ladrilho(2, 1, 1)
    r2 = proxy_osm.resposta_ladrilho(2, 1, 1)
    assert r1.headers["X-Cache"] == "MISS"
    assert r2.headers["X-Cache"] == "HIT"
    assert r1.media_type == "image/png"

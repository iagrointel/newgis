"""SDK × catálogo: listar/iterar com paginação por cursor, abrir, criar, atualizar, substituir dados
e apagar — sempre por HTTP de verdade com token de serviço (o doctest do módulo repete o caminho
feliz; aqui ficam os cantos: RLS entre inquilinos, item inexistente e a lixeira)."""

import secrets

import pytest
from plat import NaoEncontrado

from tests.sdk.conftest import PREFIXO

TIPO = "ferramenta_resultado"  # migração 20260908T1847: tipo simples sem dado físico


def _dados_basico() -> dict:
    return {"ferramenta": "ferramentas.buffer", "parametros": {"distancia_m": 100.0, "srid": 31983},
            "resultado": {"area_m2": 31214.4}, "procedencia": {"biblioteca": "shapely"}}


def test_listar_pagina_e_iterar_permanecem_no_inquilino(pla):
    pagina = pla.catalogo.listar(limite=3)
    assert pagina.total >= len(pagina.itens) >= 0
    ids = [i["id"] for i in pla.catalogo.iterar(limite=3)]
    assert len(ids) >= len(pagina.itens)
    assert len(set(ids)) == len(ids)  # gerador não repete página nem pula item


def test_criar_abrir_atualizar_apagar_redondo(pla, limpar_itens):
    titulo = f"{PREFIXO}redondo-{secrets.token_hex(3)}"
    item = pla.catalogo.criar(tipo=TIPO, titulo=titulo, dados=_dados_basico(), tags=["zt-sdk"])
    assert item["tipo"] == TIPO and item["titulo"] == titulo
    limpar_itens.append(item["id"])

    aberto = pla.catalogo.abrir(item["id"])
    assert aberto["dados"]["resultado"]["area_m2"] == 31214.4

    alterado = pla.catalogo.atualizar(item["id"], {"resumo": "criado pelo SDK"})
    assert alterado["resumo"] == "criado pelo SDK"

    substituido = pla.catalogo.substituir_dados(item["id"], _dados_basico() | {"resultado": {"area_m2": 1.0}})
    assert substituido["dados"]["resultado"]["area_m2"] == 1.0

    pla.catalogo.apagar(item["id"])
    with pytest.raises(NaoEncontrado):
        pla.catalogo.abrir(item["id"])  # fora da lixeira, o GET volta 404
    limpar_itens.remove(item["id"])


def test_tipo_fora_do_vocabulario_e_422_tipado(pla):
    from plat import ErroValidacao

    with pytest.raises(ErroValidacao) as erro:
        pla.catalogo.criar(tipo=f"{PREFIXO}tipo-inexistente", titulo="x", dados={})
    assert erro.value.status == 422


def test_item_de_outro_inquilino_e_404_tipado(pla, pla_demo2, limpar_itens):
    """Refutação do item: token do inquilino A lendo item do inquilino B — 404 tipado (RLS),
    nunca 403 que confirmaria a existência do objeto."""
    item = pla.catalogo.criar(tipo=TIPO, titulo=f"{PREFIXO}rls-{secrets.token_hex(3)}",
                              dados=_dados_basico())
    limpar_itens.append(item["id"])
    with pytest.raises(NaoEncontrado) as erro:
        pla_demo2.catalogo.abrir(item["id"])
    assert erro.value.status == 404


def test_item_inexistente_e_404(pla):
    with pytest.raises(NaoEncontrado):
        pla.catalogo.abrir("00000000-0000-0000-0000-000000000000")

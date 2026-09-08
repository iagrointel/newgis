"""Unidade do item `L5-32-vistas-de-camada`: fronteira de entrada da definição de vista e coerência entre o
que o código grava em `plat.item.dados` e o JSON Schema que a migração registra para o tipo `vista_de_camada`.

Sem banco: o que precisa de banco (a VIEW, o filtro congelado, a recusa de escrita) está em
tests/api/catalogo/test_vista_camada.py. Aqui fica o que quebra em silêncio — o esquema do tipo e o código
que o preenche seguindo caminhos diferentes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.catalogo.vista_camada import CONTROLE, VistaEntrada, _dados_da_vista

RAIZ = Path(__file__).resolve().parents[2]
MIGRACAO = RAIZ / "db" / "migracoes" / "20260908T1046_vista_de_camada.sql"


def _esquema_do_tipo() -> dict:
    """JSON Schema do tipo `vista_de_camada` lido da migração (a fonte é o arquivo aplicado, não uma cópia)."""
    texto = MIGRACAO.read_text(encoding="utf-8")
    bruto = re.search(r"'(\{\"\$schema\".*?\})'::jsonb", texto, re.S)
    assert bruto, "a migração do L5-32 não tem o JSON Schema do tipo vista_de_camada"
    return json.loads(bruto.group(1))


DADOS_MAE = {"schema": "d_demo", "tabela": "c_0123456789abcdef", "geometria": "Point", "srid": 4674}


def _dados(**kw) -> dict:
    campos = {"titulo": "vista", "filtro": "uf = 'SP'", "campos_ocultos": ["cpf"], "somente_leitura": True}
    campos.update(kw)
    corpo = VistaEntrada(**campos)
    return _dados_da_vista("11111111-2222-3333-4444-555555555555", DADOS_MAE, "c_fedcba9876543210", corpo,
                           [{"nome": "nome", "tipo_pg": "text"}, {"nome": "uf", "tipo_pg": "text"}])


def test_dados_da_vista_valem_contra_o_esquema_do_tipo():
    Draft202012Validator(_esquema_do_tipo()).validate(_dados())


def test_dados_da_vista_com_extensao_e_estilo_tambem_valem():
    d = _dados(extent=[-47.0, -24.0, -46.0, -23.0], estilo={"cor": "#123456"}, popup={"titulo": "{nome}"})
    Draft202012Validator(_esquema_do_tipo()).validate(d)
    assert d["extent"] == [-47.0, -24.0, -46.0, -23.0]


def test_vista_editavel_grava_edicao_habilitada():
    assert _dados(somente_leitura=False)["edicao"] == {"habilitada": True}
    assert _dados(somente_leitura=True)["edicao"] == {"habilitada": False}
    assert _dados(somente_leitura=True)["somente_leitura"] is True


def test_campo_oculto_com_nome_fora_do_padrao_e_recusado():
    for ruim in ('cpf"; DROP TABLE plat.item; --', "Nome Do Campo", "uf-2", ""):
        with pytest.raises(ValidationError):
            VistaEntrada(titulo="v", campos_ocultos=[ruim])


def test_extensao_invertida_e_recusada():
    with pytest.raises(ValidationError):
        VistaEntrada(titulo="v", extent=[-46.0, -23.0, -47.0, -24.0])
    with pytest.raises(ValidationError):
        VistaEntrada(titulo="v", extent=[-47.0, -24.0, -46.0])


def test_controle_cobre_as_colunas_que_camada_preparar_cria():
    """`plat.camada_preparar` acrescenta essas colunas a toda camada; se uma delas ficasse de fora da view, a
    vista deixaria de ser atualizável (fid) ou perderia a coluna que a RLS lê (tenant_id)."""
    sql = (RAIZ / "db" / "migracoes" / "029_ingestao_vetor.sql").read_text(encoding="utf-8")
    corpo = sql.split("FUNCTION plat.camada_preparar", 1)[1]
    for coluna in re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", corpo):
        assert coluna in CONTROLE, f"{coluna} nasce em toda camada e sumiria da vista"
    assert {"fid", "geom"} <= set(CONTROLE)

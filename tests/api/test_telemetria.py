"""Telemetria opcional do appliance (item L7-11-c-telemetria-opcional; docs/APPLIANCE.md §5). Portão: com
telemetria desligada, 0 pedidos de rede; ligada, o JSON enviado é idêntico ao que a tela mostrou; o receptor
recusa chave desconhecida; o documento lista os campos. Refutação: qualquer campo além dos listados, ou envio
com chave de outro appliance, reprova.

O "envio" é capturado no lugar de `httpx.post` (o destino de verdade é a instalação da casa; aqui a mesma app
faz de receptora pelo TestClient). Contar chamadas a `httpx.post` é a medida "0 pedidos de rede": desligada, o
job não chega nem a montar o relatório."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from app import telemetria

ITEM = "L7-11-c-telemetria-opcional"
RAIZ = Path(__file__).resolve().parents[2]


class _Captura:
    def __init__(self, status: int = 200):
        self.chamadas: list[dict] = []
        self.status = status

    def __call__(self, url, json=None, headers=None, timeout=None, trust_env=None):
        self.chamadas.append({"url": url, "json": json, "headers": dict(headers or {})})
        return httpx.Response(self.status, request=httpx.Request("POST", url))


@pytest.fixture
def desligada(sessao_plat):
    r = sessao_plat.put("/api/telemetria", json={"ligada": False})
    assert r.status_code == 200, r.text
    yield
    sessao_plat.put("/api/telemetria", json={"ligada": False})


def test_desligada_por_padrao_e_zero_pedidos_de_rede(sessao_plat, desligada, monkeypatch, medida):
    estado = sessao_plat.get("/api/telemetria").json()
    assert estado["ligada"] is False and re.fullmatch(r"[0-9a-f]{48}", estado["chave"])
    captura = _Captura()
    monkeypatch.setattr(telemetria.httpx, "post", captura)
    resultado = telemetria.enviar_se_ligada()
    assert resultado["enviado"] is False and "desligada" in resultado["motivo"]
    r = sessao_plat.post("/api/telemetria/enviar")
    assert r.status_code == 200 and r.json()["enviado"] is False
    assert captura.chamadas == []
    medida(ITEM)("pedidos_de_rede_desligada", len(captura.chamadas), "pedidos",
                 "chamadas a httpx.post com a telemetria desligada (job + POST /api/telemetria/enviar)")


@pytest.fixture
def destino(monkeypatch):
    """PLAT_TELEMETRIA_URL sem tocar o objeto congelado: troca a referência `settings` vista pelo módulo."""
    import dataclasses

    novo = dataclasses.replace(telemetria.settings, PLAT_TELEMETRIA_URL="http://destino.exemplo/api/telemetria/receber")
    monkeypatch.setattr(telemetria, "settings", novo)
    return novo.PLAT_TELEMETRIA_URL


def test_previa_e_o_que_sai_e_so_os_campos_listados(sessao_plat, desligada, destino, monkeypatch, medida):
    captura = _Captura()
    monkeypatch.setattr(telemetria.httpx, "post", captura)
    r = sessao_plat.put("/api/telemetria", json={"ligada": True, "nome_instalacao": "sig de teste interno"})
    assert r.status_code == 200 and r.json()["ligada"] is True and r.json()["ligada_por"]
    previa = sessao_plat.get("/api/telemetria").json()["previa"]
    r = sessao_plat.post("/api/telemetria/enviar")
    assert r.status_code == 200, r.text
    assert r.json()["enviado"] is True and r.json()["status"] == 200
    assert len(captura.chamadas) == 1
    enviado = captura.chamadas[0]["json"]
    assert captura.chamadas[0]["url"] == destino
    assert captura.chamadas[0]["headers"]["X-Plat-Chave"] == previa["chave"]
    # idêntico ao que a tela mostrou, fora o instante do envio
    tira = {"enviado_em"}
    assert {k: v for k, v in enviado.items() if k not in tira} == {k: v for k, v in previa.items() if k not in tira}
    assert list(enviado) == list(telemetria.CAMPOS) and telemetria.conferir_campos(enviado) == []
    assert set(enviado["contagens"]) == set(telemetria.CAMPOS_CONTAGENS)
    # gravado byte a byte
    guardado = sessao_plat.get("/api/telemetria").json()["ultimo_relatorio"]
    assert guardado == enviado
    # nunca identidade: nada do relatório é login, slug de inquilino ou título
    texto = json.dumps(enviado, ensure_ascii=False)
    for marca in ("demo2", "@", "admin"):
        assert marca not in texto.replace("sig de teste interno", ""), marca
    m = medida(ITEM)
    m("campos_do_relatorio", len(telemetria.CAMPOS), "campos",
      "app/telemetria.py::CAMPOS (os mesmos de docs/APPLIANCE.md §5)")
    m("previa_igual_ao_enviado", True, "bool",
      "GET /api/telemetria previa == corpo capturado de httpx.post, fora enviado_em")


def test_documento_lista_os_campos():
    doc = (RAIZ / "docs" / "APPLIANCE.md").read_text(encoding="utf-8")
    for campo in telemetria.CAMPOS + telemetria.CAMPOS_CONTAGENS:
        assert f"`{campo}`" in doc, f"campo {campo} não documentado em docs/APPLIANCE.md §5"


def test_receptor_recusa_chave_desconhecida_e_campo_a_mais(cliente, sessao_plat, desligada):
    previa = sessao_plat.get("/api/telemetria").json()["previa"]
    chave = previa["chave"]
    # sem registrar: 403 e nada gravado
    r = cliente.post("/api/telemetria/receber", json=previa, headers={"X-Plat-Chave": chave})
    assert r.status_code == 403 and r.json()["erro"] == "chave_desconhecida", r.text
    assert cliente.post("/api/telemetria/receber", json=previa).status_code == 401
    # registra este appliance na "casa" (a mesma app) e recebe
    r = sessao_plat.post("/api/telemetria/appliances", json={"chave": chave, "nome": "appliance de teste"})
    assert r.status_code == 201, r.text
    try:
        r = cliente.post("/api/telemetria/receber", json=previa, headers={"X-Plat-Chave": chave})
        assert r.status_code == 200 and r.json()["appliance"] == "appliance de teste", r.text
        lista = sessao_plat.get("/api/telemetria/appliances").json()
        meu = next(a for a in lista if a["chave"] == chave)
        assert meu["recebidos"] >= 1 and meu["ultimo_relatorio"]["chave"] == chave
        # chave de OUTRO appliance no cabeçalho (registrada) com corpo deste: recusado
        outra = "f" * 48
        sessao_plat.post("/api/telemetria/appliances", json={"chave": outra, "nome": "outro"})
        r = cliente.post("/api/telemetria/receber", json=previa, headers={"X-Plat-Chave": outra})
        assert r.status_code == 422 and r.json()["erro"] == "relatorio_fora_do_contrato"
        sessao_plat.delete(f"/api/telemetria/appliances/{outra}")
        # campo a mais (o que o adversário procura): recusado antes de gravar
        r = cliente.post("/api/telemetria/receber", json={**previa, "logins": ["x"]}, headers={"X-Plat-Chave": chave})
        assert r.status_code == 422 and r.json()["detalhe"]["extras"] == ["logins"]
        r = cliente.post("/api/telemetria/receber", json={**previa, "contagens": {**previa["contagens"], "nomes": 1}},
                         headers={"X-Plat-Chave": chave})
        assert r.status_code == 422 and r.json()["detalhe"]["extras"] == ["contagens.nomes"]
    finally:
        assert sessao_plat.delete(f"/api/telemetria/appliances/{chave}").status_code == 204


def test_admin_comum_nao_ve_a_telemetria(sessao_a):
    assert sessao_a.get("/api/telemetria").status_code == 404
    assert sessao_a.put("/api/telemetria", json={"ligada": True}).status_code == 404

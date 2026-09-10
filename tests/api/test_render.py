"""`POST /api/render/mapa`, `/api/render/token`, `/api/render/interno/eco` (item L2-12-a-motor-render-servidor):
ponta a ponta contra um `uvicorn app.main:app` real (nunca o transporte ASGI do TestClient — a rota chama o
motor de render, que sobe um chromium de verdade e navega por HTTP de verdade até `/render/mapa`).

Marcado `lento`: sobe servidor + chromium. `tests/render_apoio.py` escolhe uma porta livre e mata só pelo PID.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from tests.e2e.apoio import credenciais, totp
from tests.render_apoio import derrubar_servidor, subir_servidor

pytestmark = pytest.mark.lento

RAIZ = Path(__file__).resolve().parents[2]
CREDENCIAIS_TOTP = Path(os.environ.get("PLAT_CREDENCIAIS_TOTP_ARQUIVO") or (RAIZ / "tests" / "credenciais_totp.txt"))


def _totp_de(slug: str, login: str) -> str | None:
    if not CREDENCIAIS_TOTP.exists():
        return None
    for linha in CREDENCIAIS_TOTP.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[0] == slug and partes[1] == login:
            return partes[2]
    return None


@pytest.fixture(scope="module")
def servidor():
    proc, base_url = subir_servidor()
    yield base_url
    derrubar_servidor(proc)


@pytest.fixture(scope="module")
def sessao(servidor):
    """Sessão HTTP de verdade (não o TestClient em processo) contra o admin do inquilino `plataforma` — o
    ambiente de trilha semeia esta conta com 2FA LIGADO (achado rodando de verdade: o primeiro `POST
    /api/login` aqui devolve `exige_2fa` em vez de `ok`), então o login completa em dois passos quando o
    segredo TOTP está disponível (`tests/api/conftest.py` guarda o mesmo padrão para os testes do catálogo)."""
    creds = credenciais()
    if "plataforma" not in creds:
        pytest.skip("sem credencial do inquilino 'plataforma' (rode laco/trilha_ambiente.sh)")
    login, senha = creds["plataforma"]
    cli = httpx.Client(base_url=servidor, timeout=30)
    r = cli.post("/api/login", json={"inquilino": "plataforma", "login": login, "senha": senha})
    assert r.status_code == 200, r.text
    corpo = r.json()
    if corpo.get("exige_2fa"):
        segredo = _totp_de("plataforma", login)
        assert segredo, "conta 'plataforma' exige 2FA e o segredo não está em PLAT_CREDENCIAIS_TOTP_ARQUIVO"
        r2 = cli.post("/api/login/2fa", json={"desafio": corpo["desafio"], "codigo": totp(segredo)})
        if r2.status_code == 401 and r2.json().get("erro") == "codigo_invalido":
            # anti-replay: outra fixture da suíte (tests/api/conftest.py) já usou o código deste passo de
            # 30s para a MESMA conta — espera o próximo passo e refaz o login (mesmo padrão de
            # tests/api/conftest.py::entrar)
            time.sleep(30 - (time.time() % 30) + 0.5)
            r = cli.post("/api/login", json={"inquilino": "plataforma", "login": login, "senha": senha})
            corpo = r.json()
            r2 = cli.post("/api/login/2fa", json={"desafio": corpo["desafio"], "codigo": totp(segredo)})
        assert r2.status_code == 200 and r2.json().get("ok") is True, r2.text
    else:
        assert corpo.get("ok") is True, r.text
    yield cli
    cli.close()


def test_render_mapa_devolve_png_do_tamanho_pedido(sessao):
    r = sessao.post("/api/render/mapa", json={"largura": 640, "altura": 480, "formato": "png"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    im = Image.open(io.BytesIO(r.content))
    assert im.size == (640, 480)


def test_render_mapa_devolve_pdf(sessao):
    r = sessao.post("/api/render/mapa", json={"largura": 800, "altura": 600, "formato": "pdf"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_render_mapa_exige_sessao(servidor):
    cli = httpx.Client(base_url=servidor, timeout=30)
    r = cli.post("/api/render/mapa", json={"largura": 640, "altura": 480})
    assert r.status_code in (400, 401)
    cli.close()


def test_render_mapa_limite_de_pixel(sessao):
    r = sessao.post("/api/render/mapa", json={"largura": 999999, "altura": 480})
    assert r.status_code == 422, r.text


def test_saude_render_reporta_pool(sessao):
    r = sessao.get("/api/render/saude")
    assert r.status_code == 200, r.text
    corpo = r.json()
    for chave in ("em_execucao", "fila_atual", "falhas_total", "sucesso_total", "tempo_medio_ms", "tamanho_pool",
                  "ativo"):
        assert chave in corpo, corpo


def test_token_interno_expira_e_trava_por_host(sessao, servidor):
    r = sessao.post("/api/render/token")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["ttl_s"] <= 60
    tok = corpo["token"]

    # do mesmo host (127.0.0.1, onde o teste roda): passa
    cli_local = httpx.Client(base_url=servidor, timeout=10)
    r2 = cli_local.get("/api/render/interno/eco", params={"token": tok})
    assert r2.status_code == 200, r2.text
    cli_local.close()

    # token com assinatura adulterada: recusado mesmo vindo do host certo
    r3 = sessao.get("/api/render/interno/eco", params={"token": tok[:-4] + "0000"})
    assert r3.status_code == 401, r3.text


def test_render_de_camada_de_documento_e_fronteira_declarada(sessao):
    """Documento com uma camada real: hoje devolve 501 com o motivo escrito (sem servidor de tiles nesta
    máquina) — nunca um PNG fingindo desenhar algo que não existe. Cria o item de catálogo mínimo pela
    própria API para não depender de dado semeado."""
    r_camada = sessao.post("/api/itens", json={
        "tipo": "camada_vetorial", "titulo": "zt render camada",
        "dados": {"schema": "plat_trabalho", "tabela": "zt_render_inexistente", "geometria": "Point",
                  "srid": 4326, "campos": [{"nome": "a", "tipo": "text"}], "fonte": "hospedada"},
    })
    assert r_camada.status_code == 201, r_camada.text
    camada_id = r_camada.json()["id"]
    try:
        from tests.api.catalogo.conftest import documento_mapa

        r_mapa = sessao.post("/api/mapas", json={"titulo": "zt render mapa", "dados": documento_mapa(camada_id)})
        assert r_mapa.status_code == 201, r_mapa.text
        mapa_id = r_mapa.json()["id"]
        try:
            r = sessao.post("/api/render/mapa", json={"mapa_id": mapa_id, "largura": 640, "altura": 480})
            assert r.status_code == 501, r.text
            assert "render_de_camada_nao_suportado" in r.text
        finally:
            sessao.delete(f"/api/itens/{mapa_id}")
    finally:
        sessao.delete(f"/api/itens/{camada_id}")

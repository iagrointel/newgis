"""Cláusula 3 do item L1-01-a: a landing page conforma `core`/`item-search`/`filter`/`sort` — validado
pelo `stac-api-validator` oficial (pacote `stac-api-validator`, o mesmo CLI citado no portão de pronto e
na refutação: "roda o validador STAC API oficial e reprova qualquer não-conformidade de `core`"). Este
teste NÃO existia no que o Kimi entregou (ele só validava `conformsTo` por inspeção do JSON, nunca com o
validador de verdade rodando ponta a ponta) — escrito na entrega porque cláusula sem comando que a prove
vira fronteira honesta, nunca item entregue.

Sobe a API real por uvicorn com HTTPS de verdade (autoassinado, gerado na hora): `app/settings.py` recusa
`PLAT_URL_PUBLICA` que não comece por `https://` (validação de propósito, para pegar URL de produção
gravada errado), e o `stac-api-validator` segue de verdade os links `self`/`root`/`queryables` que a API
devolve — então não dá para simplesmente apontar essa variável para o `http://127.0.0.1:<porta>` do
subprocesso de teste. O certificado autoassinado vai para `REQUESTS_CA_BUNDLE` do subprocesso do CLI
(que usa `requests`, que honra essa variável) em vez de desligar verificação de TLS."""

import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.api.imagens.conftest import item_stac


def _achar_stac_api_validator() -> str | None:
    """O CLI é um console-script instalado DENTRO do venv (`venv/bin/stac-api-validator`), não no PATH
    do sistema (diferente do `gdalinfo`, binário do SO) — procurar ao lado do próprio interpretador que
    está rodando o pytest antes de desistir com `shutil.which`."""
    candidato = Path(sys.executable).with_name("stac-api-validator")
    if candidato.exists():
        return str(candidato)
    return shutil.which("stac-api-validator")


STAC_API_VALIDATOR = _achar_stac_api_validator()
RAIZ_REPO = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    STAC_API_VALIDATOR is None, reason="stac-api-validator não está instalado nesta máquina (venv)"
)


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _gerar_cert_local(pasta: Path) -> tuple[Path, Path]:
    """Certificado autoassinado para 127.0.0.1, gerado com o `openssl` do sistema (mesmo padrão dos
    outros testes de ponta a ponta desta suíte: nunca um binário fixo em outro caminho)."""
    cert, chave = pasta / "cert.pem", pasta / "key.pem"
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl não está instalado nesta máquina")
    subprocess.run(
        [
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(chave), "-out", str(cert),
            "-days", "2", "-nodes", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        check=True, capture_output=True,
    )
    return cert, chave


def _esperar_de_pe(url: str, cert: Path, processo: subprocess.Popen, limite_s: float = 60.0) -> None:
    import http.client
    from urllib.parse import urlsplit

    ctx = ssl.create_default_context(cafile=str(cert))
    t0 = time.monotonic()
    while time.monotonic() - t0 < limite_s:
        if processo.poll() is not None:
            raise RuntimeError(f"uvicorn morreu ao subir (código {processo.returncode})")
        try:
            alvo = urlsplit(url)
            con = http.client.HTTPSConnection(alvo.hostname, alvo.port, timeout=2, context=ctx)
            con.request("GET", alvo.path)
            resp = con.getresponse()
            resp.read()
            con.close()
            if resp.status == 200:
                return
        except OSError:
            pass
        time.sleep(0.3)
    raise RuntimeError(f"uvicorn não respondeu 200 em {limite_s}s em {url}")


@pytest.fixture(scope="module")
def infra_validador(tmp_path_factory, token_stac_a):
    import os

    from fastapi.testclient import TestClient

    from app.main import app

    pasta = tmp_path_factory.mktemp("stac_validador")
    cert, chave = _gerar_cert_local(pasta)

    c = TestClient(app, base_url="http://testserver")
    ta = token_stac_a["token"]
    slug = f"validador-{secrets.token_hex(4)}"  # sufixo aleatório: pgstac é global e persiste entre rodadas
    r = c.post(f"/svc/{ta}/stac/collections", params={"slug": slug}, json={"title": "Prova stac-api-validator"})
    assert r.status_code == 201, r.text
    colecao = r.json()["id"]
    ri = c.post(
        f"/svc/{ta}/stac/collections/{colecao}/items",
        json=item_stac("item-validador-1", colecao),
    )
    assert ri.status_code == 201, ri.text

    porta = _porta_livre()
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ_REPO, capture_output=True, text=True).stdout.strip()
    base = f"https://127.0.0.1:{porta}"
    ambiente = {**os.environ, "PLAT_GIT_SHA": sha or "validador-prova", "PLAT_URL_PUBLICA": base}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(porta),
            "--ssl-certfile", str(cert), "--ssl-keyfile", str(chave),
        ],
        cwd=RAIZ_REPO, env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        root = f"{base}/svc/{ta}/stac"
        _esperar_de_pe(f"{root}/", cert, proc)
        yield {"root": root, "colecao": colecao, "cert": cert}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def _rodar_validador(infra: dict, conformances: list[str], usar_colecao: bool = False) -> subprocess.CompletedProcess:
    import os

    cmd = [STAC_API_VALIDATOR, "--root-url", infra["root"]]
    for c in conformances:
        cmd += ["--conformance", c]
    if usar_colecao:
        cmd += ["--collection", infra["colecao"]]
    # `requests` (usado pelo CLI e pelo pystac por baixo) honra REQUESTS_CA_BUNDLE para validar um
    # certificado que não está na cadeia pública do sistema — nunca desligar verificação de TLS.
    ambiente = {**os.environ, "REQUESTS_CA_BUNDLE": str(infra["cert"])}
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=ambiente)


def test_validador_stac_api_core(infra_validador, medida):
    r = _rodar_validador(infra_validador, ["core"])
    assert r.returncode == 0, f"stac-api-validator --conformance core reprovou:\n{r.stdout}\n{r.stderr}"
    versao = subprocess.run([STAC_API_VALIDATOR, "--version"], capture_output=True, text=True).stdout.strip()
    comando = (
        f"stac-api-validator --root-url https://<api>/svc/<token>/stac --conformance core  ({versao}; API "
        "real por uvicorn+TLS autoassinado, coleção+item semeados via TestClient, o mesmo cenário exigido "
        "pelo portão)"
    )
    medida("L1-01-a")("stac_api_validator_core", 1, "0=reprovou,1=passou", comando)


def test_validador_stac_api_item_search(infra_validador):
    r = _rodar_validador(infra_validador, ["item-search"], usar_colecao=True)
    assert r.returncode == 0, f"stac-api-validator --conformance item-search reprovou:\n{r.stdout}\n{r.stderr}"


def test_validador_stac_api_collections(infra_validador):
    r = _rodar_validador(infra_validador, ["collections"], usar_colecao=True)
    assert r.returncode == 0, f"stac-api-validator --conformance collections reprovou:\n{r.stdout}\n{r.stderr}"


def test_validador_stac_api_filter(infra_validador):
    r = _rodar_validador(infra_validador, ["filter"], usar_colecao=True)
    assert r.returncode == 0, f"stac-api-validator --conformance filter reprovou:\n{r.stdout}\n{r.stderr}"


def test_validador_stac_api_item_search_sort(infra_validador):
    r = _rodar_validador(infra_validador, ["item-search#sort"], usar_colecao=True)
    assert r.returncode == 0, (
        f"stac-api-validator --conformance item-search#sort reprovou:\n{r.stdout}\n{r.stderr}"
    )

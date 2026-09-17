"""Furo 4 — segredo de homologação idêntico ao de produção (achado `L7-31-ambiente-homologacao`).

ACHADO (adversário, turno 3, `laco/handoffs/T3/ataque-g6-ADVERSARIO.md`, achado 11): o
`PLAT_GARAGE_ADMIN_TOKEN` de homologação era byte a byte o mesmo de produção, e com ele o adversário
listou e leu os baldes de produção pela API de administração do Garage.

Este arquivo NUNCA imprime, ecoa nem grava valor de credencial: toda comparação é por sha256, e o que
sai em mensagem de falha é o NOME da chave, jamais o valor. Nenhuma chamada aqui escreve, cria ou apaga
nada — o único método usado contra o Garage é GET.

`tests/unit/test_isolamento_homologacao.py` já cobre a mesma cláusula, mas o arquivo inteiro PULA nesta
máquina: a fixture `env` da suíte exige `PLAT_DSN` no `.env`, e desde o item L7-19 o `.env` de produção
não tem segredo nenhum (eles vivem em `/etc/plat/segredos`, entregues por `LoadCredential=` do systemd).
As provas abaixo não dependem de `PLAT_DSN` e por isso rodam de fato.

Par de provas:
  ATAQUE   — nenhuma credencial de homologação vale como token de administração do Garage (403/401);
  LEGÍTIMO — a credencial S3 PRÓPRIA de homologação continua funcionando (ListBuckets 200), ou seja o
             isolamento não foi obtido simplesmente quebrando a homologação.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

RAIZ_INSTALADA = Path("/home/dev/plataforma/enterprise")
ENV_HOMOLOG = RAIZ_INSTALADA / "var" / "homolog" / "homolog.env"
TEMPO_LIMITE_S = 10.0
BUCKETS_DE_PRODUCAO = ("plat-demo", "plat-demo2")


def _sha(valor: str) -> str:
    return hashlib.sha256(valor.strip().encode()).hexdigest()


@pytest.fixture(scope="module")
def homolog() -> dict[str, str]:
    if not ENV_HOMOLOG.is_file():
        pytest.skip(f"ambiente de homologação não instalado (sem {ENV_HOMOLOG})")
    return {c: (v or "") for c, v in dotenv_values(ENV_HOMOLOG).items()}


@pytest.fixture(scope="module")
def admin_url(homolog) -> str:
    url = (homolog.get("PLAT_GARAGE_ADMIN_URL") or "http://127.0.0.1:3903").rstrip("/")
    try:
        requests.get(url, timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"API de administração do Garage fora do ar em {url} ({type(e).__name__})")
    return url


def test_homologacao_nao_declara_token_de_administracao(homolog):
    """A raiz do achado: com token de administração, homologação administra o armazenamento inteiro —
    inclusive os baldes de produção. O arquivo precisa declarar a chave VAZIA (não bastaria omitir: o
    `.env` da raiz, que em máquina instalada é o de produção, é lido antes e seria herdado)."""
    assert "PLAT_GARAGE_ADMIN_TOKEN" in homolog, (
        "var/homolog/homolog.env precisa declarar PLAT_GARAGE_ADMIN_TOKEN= (vazio) para anular a herança "
        "do .env de produção"
    )
    assert not homolog["PLAT_GARAGE_ADMIN_TOKEN"].strip(), (
        "var/homolog/homolog.env voltou a ter PLAT_GARAGE_ADMIN_TOKEN preenchido"
    )


def test_ataque_credencial_de_homologacao_nao_administra_o_garage(homolog, admin_url):
    """ATAQUE: usar cada credencial longa de homologação como Bearer da API de administração — a mesma
    chamada que o adversário usou para enumerar produção. Todas têm de ser recusadas."""
    tentadas = 0
    for nome, valor in homolog.items():
        valor = valor.strip()
        if len(valor) < 16 or valor.startswith(("http://", "https://", "postgresql://")):
            continue  # endereço e valor curto não são credencial
        tentadas += 1
        r = requests.get(
            f"{admin_url}/v2/ListBuckets",
            headers={"Authorization": f"Bearer {valor}"},
            timeout=TEMPO_LIMITE_S,
        )
        assert r.status_code in (401, 403), (
            f"{nome} (sha256 {_sha(valor)[:12]}) foi aceito como token de administração do Garage: "
            f"{r.status_code}"
        )
    assert tentadas > 0, "homologação sem nenhuma credencial para testar: o arquivo não prova nada assim"


def test_legitimo_credencial_propria_de_homologacao_continua_funcionando(homolog):
    """CONTROLE POSITIVO: o isolamento não pode ter sido obtido deixando homologação sem armazenamento.
    A chave S3 própria dela lista os PRÓPRIOS baldes (GET, nada é criado), e nenhum balde de produção
    aparece nessa lista."""
    from app.garage import ClienteS3

    chave_id = (homolog.get("PLAT_GARAGE_CHAVE_ID") or "").strip()
    segredo = (homolog.get("PLAT_GARAGE_CHAVE_SEGREDO") or "").strip()
    if not (chave_id and segredo):
        pytest.fail(
            "homologação não tem credencial própria de armazenamento (PLAT_GARAGE_CHAVE_ID/"
            "PLAT_GARAGE_CHAVE_SEGREDO): rode scripts/garage_homolog_provisionar.sh"
        )
    url = (homolog.get("PLAT_GARAGE_URL") or "http://127.0.0.1:3900").rstrip("/")
    try:
        requests.get(url, timeout=TEMPO_LIMITE_S)
    except requests.RequestException as e:
        pytest.skip(f"Garage fora do ar em {url} ({type(e).__name__})")
    cliente = ClienteS3(url, chave_id, segredo, homolog.get("PLAT_GARAGE_REGIAO") or "garage")
    r = cliente._requisicao("GET", "")
    assert r.status_code == 200, f"ListBuckets com a chave de homologação: {r.status_code}"
    vistos = [n for n in BUCKETS_DE_PRODUCAO if f"<Name>{n}</Name>" in r.text]
    assert vistos == [], f"a credencial de homologação enxerga balde de produção: {vistos}"

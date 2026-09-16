"""Adversário de linha L1 imagens (parte 2, turno 9) — item
`L1-02-e-cog-direto-por-https-e-endpoint-s3-para-o-pro`, ENTREGUE (sem sha no ledger). A própria
hipótese do item diz que são "duas portas" (COG por HTTPS + endpoint S3 compatível por inquilino
para o ArcGIS Pro), "por isso as duas portas". A última nota do ledger só fala da Porta 1
("Porta 1 construida por GPT-5.6 Sol ... AUDITADA rodando"). A Porta 2 e o documento que o portão
exige não existem:

1. Portão: "documento `docs/PRO_CONEXAO.md` com o passo a passo do `.acs`" — o arquivo não existe no
   repositório.
2. Portão: "endpoint S3 compatível por inquilino (`s3.<dominio>` → Garage, chave só-leitura própria)
   ... `AWS_S3_ENDPOINT` + chave do inquilino: `gdalinfo /vsis3/<balde>/...` abre; chave do inquilino
   A não abre balde do B" — não existe, em nenhuma rota da aplicação (`app/imagens/*.py`,
   `app/rotas_arquivos.py`), um endpoint que emita/exponha uma chave S3 só-leitura por inquilino
   para uso externo (o único cliente do `ClienteAdmin`/`ClienteS3` de `app/garage.py` é a própria
   aplicação, para armazenamento interno).

Reprodução: `bash /home/dev/plataforma/laco/roda_teste.sh tests/unit/test_l1_adv2_cog_s3_gate.py -q -rxX`."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-e CAI: docs/PRO_CONEXAO.md (exigido literalmente pelo portao, 'passo a passo do .acs') "
    "nao existe no repositorio."
))
def test_documento_pro_conexao_existe():
    assert (ROOT / "docs" / "PRO_CONEXAO.md").exists(), (
        "docs/PRO_CONEXAO.md não existe — a Porta 2 do item (endpoint S3 para o ArcGIS Pro) não tem "
        "o documento de passo a passo que o portão exige")


@pytest.mark.xfail(strict=True, reason=(
    "L1-02-e CAI: nao existe nenhuma rota que emita uma chave S3 so-leitura por inquilino para uso "
    "externo (Porta 2 da hipotese do item). app/garage.py tem ClienteAdmin.criar_chave/permitir "
    "(ler/escrever/dono) mas nenhuma rota de app/imagens ou app/rotas_arquivos chama esse caminho "
    "para o inquilino final — o Garage so e usado como armazenamento INTERNO da propria aplicacao."
))
def test_endpoint_s3_por_inquilino_existe():
    alvos = list((ROOT / "app").rglob("rotas_*.py")) + [ROOT / "app" / "rotas_arquivos.py"]
    achados = []
    for caminho in alvos:
        if not caminho.exists():
            continue
        texto = caminho.read_text(encoding="utf-8", errors="ignore")
        if ("s3" in texto.lower() and
                ("somente_leitura" in texto.lower() or "so_leitura" in texto.lower()
                 or "read_only" in texto.lower() or "readonly" in texto.lower())):
            achados.append(str(caminho.relative_to(ROOT)))
    assert achados, (
        "nenhuma rota expõe um endpoint/credencial S3 só-leitura por inquilino para o ArcGIS Pro "
        "(Create Cloud Storage Connection File) — a Porta 2 do item não existe")

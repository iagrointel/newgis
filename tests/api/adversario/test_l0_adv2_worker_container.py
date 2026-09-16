"""Adversário de linha L0 (rodada 2, wt/f2-adv-l02) — achado sobre `L0-05-e-worker-em-container`. Laudo
completo em `laco/handoffs/T9/linha-L0-laudo-adversario-2.md`.

Portão literal (ADR 0010 seção 10, o texto que substitui o provisório em `estado.json`): "Um contêiner subido
pelo `deploy/docker-compose.worker.yml` pega, na MESMA fila `plat.job` da unidade systemd, um job
`ingestao.inspecionar` e um `ingestao.carregar` de arquivo real, e produz a mesma proposta e a mesma contagem
de feições que o executor por processo [...] Matar o contêiner no meio de um job devolve o job à fila e não
deixa tabela órfã."

Duas coisas confirmadas nesta rodada:
1. `git merge-base --is-ancestor 0230efa HEAD` (na wt/f2advl02, base wt/uniao) devolve falso — o commit que
   fechou o item só existe em `wt/g3fix`/`wt/il004ffgdbp`, nunca foi juntado. `deploy/Dockerfile.worker` e o
   ADR chegaram a `wt/uniao` por OUTRO commit, mas sem a prova de execução.
2. `tests/medidas/L0-05-e-worker-em-container.json` (o próprio arquivo de evidência do item) só registra
   paridade de LEITURA de arquivo por `ogrinfo` (13/13 formatos, host × contêiner) — não uma única medida do
   job de fila rodando dentro do contêiner. O próprio `bloqueio` do item em `estado.json` admite isto:
   "Aberto: job real da fila pego DENTRO do conteiner e comparado ao executor por processo (nao rodado)".
   Nenhuma imagem `plat-worker` existe hoje neste host (`docker images` vazio) e nenhuma linha em
   `plat_tuniao.worker`/`plat_tuniao.job` tem `PLAT_WORKER_NOME` de um executor em contêiner.

A cláusula central do portão — a única que prova que o executor alternativo FUNCIONA, não só que a imagem lê
arquivos GDAL corretamente — nunca foi exercitada."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MEDIDA = ROOT / "tests" / "medidas" / "L0-05-e-worker-em-container.json"
CHAVES_QUE_PROVARIAM_EXECUCAO = (
    "job_inspecionar_container", "job_carregar_container", "paridade_proposta_container_x_processo",
    "job_devolvido_a_fila_apos_sigkill_container",
)


@pytest.mark.xfail(
    strict=True,
    reason="L0-05-e: o portão literal (ADR 0010 seção 10) exige um job real (ingestao.inspecionar e "
    "ingestao.carregar) executado DENTRO do contêiner e comparado ao executor por processo, e um teste de "
    "matar o contêiner no meio do job. tests/medidas/L0-05-e-worker-em-container.json só tem paridade de "
    "leitura ogrinfo (host x container); nenhuma chave sobre job de fila existe. O próprio bloqueio do item "
    "em estado.json confirma: 'job real da fila pego DENTRO do conteiner ... (nao rodado)'. Sem imagem "
    "plat-worker construída hoje neste host (docker images vazio) e sem ancestralidade do commit que fechou "
    "o item (0230efa não é ancestral de wt/uniao).",
)
def test_medida_do_item_prova_execucao_de_job_dentro_do_container():
    dados = json.loads(MEDIDA.read_text(encoding="utf-8"))
    medidas = dados.get("medidas", {})
    provadas = [c for c in CHAVES_QUE_PROVARIAM_EXECUCAO if c in medidas]
    assert provadas, (
        f"tests/medidas/L0-05-e-worker-em-container.json não tem nenhuma medida de job executado dentro do "
        f"contêiner (só {sorted(medidas)}); a cláusula central do portão nunca foi provada"
    )
    imagens = subprocess.run(["docker", "images", "-q", "plat-worker"], capture_output=True, text=True).stdout
    assert imagens.strip(), "nenhuma imagem plat-worker construída neste host — a prova, se existiu, foi apagada e não é reproduzível"

"""Adversário L2 (linha, parte 3) — item `L2-16-b-jupyter-por-inquilino-isolado`.

A hipótese e o portão prometem `ativos_max` (padrão 1, `app/notebooks/config.py::ATIVOS_MAX`) como o
que impede a máquina de estourar RAM com contêineres de notebook demais ao mesmo tempo ("a máquina tem
~3 GB livres medidos, logo padrão 1 contêiner ativo por vez e fila"). A trava que aplica esse teto em
`app/notebooks/contenedor.py::levantar` é `_TRAVA = threading.Lock()` — um objeto de memória de UM
processo Python.

`deploy/plat-api.service` sobe a API com `--workers 2` (dois processos uvicorn distintos, medido nesta
rodada). Dois pedidos `POST /api/notebooks/<slug>/abrir` para DOIS inquilinos diferentes, um atendido
por cada worker, entram cada um no SEU PRÓPRIO `_TRAVA`, verificam `_ativos_brutos(cfg) < ativos_max`
(ambos veem zero) e os dois seguem para `docker run` — o teto de "1 contêiner por vez" nunca existiu
fora de um único processo. É a mesma classe de bug que o ADR de `chave_lock_pesado` (item F5, achado
histórico da linha L2 do turno 3) já documentou para o job pesado — mas ali foi corrigida com um
advisory lock do Postgres (recurso do CLUSTER, atravessa processo); aqui a trava continua sendo só
`threading.Lock()`.

Prova sem Docker (não precisa de container real; só prova que o mecanismo de exclusão não atravessa
processo, que é a causa raiz): dois processos de sistema operacional distintos (não threads do mesmo
interpretador) tentam `acquire()` a MESMA seção crítica ao mesmo tempo. Se a trava fosse eficaz entre
processos (advisory lock do Postgres, arquivo com `flock`, ou semáforo de SO nomeado), o segundo teria
de esperar; hoje os dois conseguem porque cada processo Python (`fork`) tem seu próprio objeto
`threading.Lock` em memória, não compartilhado.

Reprodução:

    set -a; source /home/dev/plataforma/laco/var/trilha/uniao.env; set +a
    bash /home/dev/plataforma/laco/roda_teste.sh \
        tests/api/adversario/test_l2_16b_notebooks_trava_entre_processos.py -q -rxX
"""

from __future__ import annotations

import multiprocessing
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def _confirma_workers_2_em_producao() -> bool:
    """`deploy/plat-api.service` sobe a API real com `--workers 2`: confere no arquivo do repositório
    (não depende de systemd estar instalado nesta máquina de teste)."""
    texto = (ROOT / "deploy" / "plat-api.service").read_text()
    m = re.search(r"--workers\s+(\d+)", texto)
    return bool(m) and int(m.group(1)) >= 2


def _tenta_acquire(hold_s: float, fila: multiprocessing.Queue) -> None:
    """Roda em processo FILHO separado (fork): importa o módulo de novo, tenta pegar a trava do
    módulo carregado NESTE processo (que é um objeto diferente do do processo pai/irmão) e reporta se
    conseguiu."""
    from app.notebooks import contenedor

    conseguiu = contenedor._TRAVA.acquire(timeout=0.01)
    fila.put(conseguiu)
    if conseguiu:
        time.sleep(hold_s)
        contenedor._TRAVA.release()


# REMEDIADO (wt/l02, 18/09/2026): `_TRAVA` deixou de ser `threading.Lock()` e passou a ser
# `TravaEntreProcessos`, um `flock` sobre um arquivo por instalacao. O recurso protegido e o docker do
# HOST, entao a trava e do host: atravessa os `--workers 2` da unidade, e o nucleo a solta sozinho se o
# processo dono morrer (uma trava gravada em tabela deixaria a fila presa nesse caso).
# A interface continua a de threading.Lock, e este teste continua exercendo exatamente o que exercia:
# dois processos irmaos tentando `acquire(timeout=0.01)` ao mesmo tempo, so um pode conseguir.
def test_l2_16b_trava_de_ativos_max_nao_atravessa_processo():
    assert _confirma_workers_2_em_producao(), "premissa mudou: plat-api.service não sobe mais com --workers >= 2"

    ctx = multiprocessing.get_context("fork")
    fila: multiprocessing.Queue = ctx.Queue()
    p1 = ctx.Process(target=_tenta_acquire, args=(0.5, fila))
    p2 = ctx.Process(target=_tenta_acquire, args=(0.5, fila))
    p1.start()
    time.sleep(0.05)  # p1 entra primeiro "de verdade" antes de p2 tentar
    p2.start()
    p1.join(timeout=5)
    p2.join(timeout=5)
    resultados = sorted(fila.get(timeout=1) for _ in range(2))

    # se a trava fosse efetiva ENTRE processos, o segundo teria de falhar o acquire (a seção crítica
    # do primeiro ainda estaria "aberta" por 0,5s): resultados == [False, True]. Hoje os dois
    # conseguem, porque cada processo tem seu próprio Lock — nunca há disputa de verdade.
    assert resultados == [False, True], (
        "a trava de 'ativos_max' deveria impedir dois processos de entrarem juntos na seção crítica "
        f"de levantar() um notebook; os dois conseguiram acquire() ao mesmo tempo: {resultados}"
    )

"""Desempenho em escala do motor multicritério (item L3-16-desempenho-escala).

Este módulo é o CONTRATO DE ESCALA do motor. Ele responde a três perguntas, uma vez só, no mesmo lugar:

1. **Onde a combinação roda?** `onde_combinar(n)` devolve `'navegador'` até
   `limites.AMC_COMBINAR_NAVEGADOR_MAX` unidades e `'servidor'` acima disso, com o motivo escrito. O
   mesmo número está em `web/js/amc/combinacao.js`, que RECUSA acima dele (código
   `unidades_demais_para_o_navegador`) em vez de combinar pela metade ou travar a aba.
2. **De quanto em quanto o servidor lê?** `plano(n_unidades, n_fatores)` divide o trabalho em blocos de
   `limites.AMC_BLOCO_UNIDADES` unidades. A propriedade que interessa — e que o teste prova — é que o
   PICO estimado de RAM não cresce com `n_unidades`: só o número de blocos cresce. É o que permite
   afirmar um teto de RAM para uma grade de 1 milhão de células sem medir 1 milhão.
3. **Quanta RAM o job pode pedir?** `orcamento_mb()` é o MENOR entre o teto declarado do produto
   (`limites.AMC_EXTRACAO_MEMORIA_MB`, 4 GB) e o teto real da máquina (`PLAT_WORKER_MEMORIA_MB`). Quem
   aplica o teto de verdade é `app/jobs/filho.py` (RLIMIT_DATA, item L0-05-e): aqui só se decide o
   número e se recusa, ANTES de começar, o plano que não cabe nele.

Fronteira honesta: o pico estimado é um MODELO com constantes medidas (`BYTES_*` abaixo), não uma
adivinhação e não uma medição do caso completo. `medir_pico_mb()` existe para o teste comparar o modelo
com o pico REAL de um bloco (`ru_maxrss`), e a diferença fica registrada em tests/medidas. Estimativa que
não é conferida contra medida é palpite, e palpite não entra em portão.

O módulo não abre banco nem lê arquivo: recebe um iterador de blocos de quem tem a conexão. Isso o torna
testável sem servidor e mantém a leitura em blocos (cursor nomeado) na camada que já tem a transação.
"""

from __future__ import annotations

import resource

import numpy as np

from app import limites
from app.amc.combinacao import combinar

# Constantes do modelo de memória. MEDIDAS, não estimadas: ver tests/unit/test_amc_escala.py
# (test_modelo_de_memoria_nao_subestima_o_pico_real_de_um_bloco), que compara o modelo com o pico real
# de `ru_maxrss` num bloco cheio e reprova se o modelo ficar ABAIXO do medido.
BYTES_POR_VALOR = 8          # float64 da matriz de fatores (numpy)
COPIAS_DA_MATRIZ = 8         # cópias simultâneas da matriz dentro de `combinar` (entrada, máscara de presença,
                             # peso×presença, trabalho, valores, saída e os temporários do numpy). MEDIDO em
                             # 07/09/2026 num bloco cheio de 50.000 × 15: o pico real cresceu 35,76 MB, o que
                             # dá 5,2 cópias descontados os identificadores; declara-se 8 para o modelo ficar
                             # ACIMA do medido — subestimar o pico é o único erro que não se pode cometer aqui
BYTES_POR_UNIDADE_ID = 96    # identificador de unidade em texto na lista Python (str curto + ponteiro)
BASE_MB = 256                # interpretador, numpy, psycopg2 e a conexão já carregados antes do primeiro bloco


def _fatores_max_do_esquema() -> int:
    """Teto de fatores do esquema publicado (`docs/esquemas/amc_modelo.v1.json`, `fatores.maxItems`): o
    número já existe lá e não se repete aqui à mão — é lido do arquivo na importação."""
    import json
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "docs" / "esquemas" / "amc_modelo.v1.json"
    return int(json.loads(caminho.read_text(encoding="utf-8"))["properties"]["fatores"]["maxItems"])


FATORES_MAX = _fatores_max_do_esquema()


class ErroEscala(ValueError):
    """Plano recusado ANTES de começar. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None) -> None:
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe or {}


def orcamento_mb() -> int:
    """Teto de RAM que um job do motor pode pedir nesta instalação: o MENOR entre o teto declarado do
    produto e o teto da máquina. Nunca promete os 4 GB do portão numa máquina que só tem 1 GB por job."""
    from app.settings import settings

    return min(int(limites.AMC_EXTRACAO_MEMORIA_MB), int(settings.PLAT_WORKER_MEMORIA_MB))


def onde_combinar(n_unidades: int) -> dict:
    """`{'onde': 'navegador'|'servidor', 'limite': N, 'motivo': '...'}`. Um lugar só decide isso."""
    n = int(n_unidades)
    limite = int(limites.AMC_COMBINAR_NAVEGADOR_MAX)
    if n <= limite:
        motivo = (f"{n} unidades cabem no navegador (limite {limite}); a combinação é imediata, "
                  "sem ida ao servidor e sem gastar job")
        return {"onde": "navegador", "limite": limite, "motivo": motivo}
    motivo = (f"{n} unidades passam do limite do navegador ({limite}); a combinação vai para o servidor, "
              "em blocos, como job")
    return {"onde": "servidor", "limite": limite, "motivo": motivo}


def pico_estimado_mb(n_no_bloco: int, n_fatores: int) -> float:
    """Pico de RAM de UM bloco, em MB. Não depende do total de unidades — é a propriedade do item."""
    matriz = n_no_bloco * n_fatores * BYTES_POR_VALOR * COPIAS_DA_MATRIZ
    ids = n_no_bloco * BYTES_POR_UNIDADE_ID
    return round(BASE_MB + (matriz + ids) / (1024 * 1024), 2)


def tempo_projetado_extracao_s(n_unidades: int, n_fatores: int) -> float:
    """Quanto uma extração de `n_unidades × n_fatores` deve levar, à taxa MEDIDA em
    tests/medidas/L3-16-desempenho-escala.json (`limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR`). É projeção,
    não medida do caso completo — e é o que permite recusar antes de gastar meia hora de máquina."""
    return round(int(n_unidades) * int(n_fatores) * limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR / 1e6, 1)


def plano(n_unidades: int, n_fatores: int, *, tarefa: str = "recombinacao", bloco: int | None = None,
          orcamento: int | None = None) -> dict:
    """Plano de execução em blocos, ou `ErroEscala` quando o trabalho não cabe nos limites declarados.

    Recusa (nunca corta em silêncio): mais unidades que `AMC_UNIDADES_MAX`, mais fatores que o esquema
    do modelo admite (64, `docs/esquemas/amc_modelo.v1.json`), bloco cujo pico estimado passa do orçamento
    de RAM e — só quando `tarefa='extracao'` — trabalho cujo tempo PROJETADO passa do prazo do job. A
    saída é o que o job registra no seu relatório e o que o teste confere.
    """
    n_unidades, n_fatores = int(n_unidades), int(n_fatores)
    if n_unidades <= 0:
        raise ErroEscala("sem_unidades", "o conjunto não tem nenhuma unidade de análise")
    if n_fatores <= 0:
        raise ErroEscala("sem_fatores", "o modelo não tem nenhum fator")
    if n_unidades > limites.AMC_UNIDADES_MAX:
        raise ErroEscala(
            "unidades_demais",
            f"{n_unidades} unidades passam do teto de {limites.AMC_UNIDADES_MAX} por conjunto; "
            "aumente o lado da célula ou reduza a área de estudo",
            {"n_unidades": n_unidades, "teto": limites.AMC_UNIDADES_MAX},
        )
    if n_fatores > FATORES_MAX:
        raise ErroEscala(
            "fatores_demais",
            f"{n_fatores} fatores passam do teto de {FATORES_MAX} do esquema do modelo",
            {"n_fatores": n_fatores, "teto": FATORES_MAX},
        )
    bloco = int(bloco or limites.AMC_BLOCO_UNIDADES)
    if bloco <= 0:
        raise ErroEscala("bloco_invalido", "o bloco tem de ter pelo menos uma unidade")
    bloco = min(bloco, n_unidades)
    teto = int(orcamento if orcamento is not None else orcamento_mb())
    pico = pico_estimado_mb(bloco, n_fatores)
    if pico > teto:
        raise ErroEscala(
            "bloco_nao_cabe_no_orcamento",
            f"um bloco de {bloco} unidades × {n_fatores} fatores precisa de ~{pico} MB e o orçamento do job "
            f"é {teto} MB; reduza o bloco (AMC_BLOCO_UNIDADES) ou o número de fatores",
            {"bloco": bloco, "pico_estimado_mb": pico, "orcamento_mb": teto},
        )
    projetado_s = tempo_projetado_extracao_s(n_unidades, n_fatores)
    if tarefa == "extracao" and projetado_s > limites.AMC_EXTRACAO_TIMEOUT_S:
        raise ErroEscala(
            "prazo_projetado_estourado",
            f"extrair {n_unidades} unidades × {n_fatores} fatores deve levar ~{projetado_s:.0f} s à taxa "
            f"medida ({limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR} µs por unidade e fator) e o prazo do job "
            f"é {limites.AMC_EXTRACAO_TIMEOUT_S} s; reduza a grade ou o número de fatores em vez de gastar "
            f"meia hora de máquina para o relógio matar o job no fim",
            {"tempo_projetado_s": projetado_s, "timeout_s": limites.AMC_EXTRACAO_TIMEOUT_S,
             "us_por_unidade_fator": limites.AMC_EXTRACAO_US_POR_UNIDADE_FATOR},
        )
    n_blocos = (n_unidades + bloco - 1) // bloco
    return {
        "tarefa": tarefa,
        "tempo_projetado_extracao_s": projetado_s,
        "n_unidades": n_unidades,
        "n_fatores": n_fatores,
        "bloco": bloco,
        "n_blocos": n_blocos,
        "pico_estimado_mb": pico,
        "orcamento_mb": teto,
        "timeout_s": int(limites.AMC_EXTRACAO_TIMEOUT_S),
        "onde_combinar": onde_combinar(n_unidades)["onde"],
    }


def medir_pico_mb() -> float:
    """Pico de RSS do processo em MB (`ru_maxrss`). Serve ao teste que confere o modelo contra a realidade."""
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)


def combinar_em_blocos(blocos, pesos, **opcoes):
    """Percorre `blocos` — iterável de `(ids, matriz)` — combinando um de cada vez e devolvendo, por bloco,
    `(ids, Resultado)`. É um gerador de propósito: nada do conjunto inteiro fica em memória ao mesmo tempo,
    e quem chama grava cada bloco antes de pedir o próximo. É a diferença entre 1 milhão de unidades caber
    ou não no orçamento de RAM do job."""
    for ids, matriz in blocos:
        m = np.asarray(matriz, dtype=np.float64)
        if m.shape[0] != len(ids):
            raise ErroEscala(
                "bloco_incoerente",
                f"o bloco traz {len(ids)} identificadores e {m.shape[0]} linhas de fator",
                {"ids": len(ids), "linhas": int(m.shape[0])},
            )
        yield ids, combinar(m, pesos, **opcoes)

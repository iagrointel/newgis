"""Ponte entre uma execução do motor multicritério e o motor de traçado (item L3-10-corredor-custo-minimo).

O motor de `app/amc/corredor.py` é puro: recebe duas matrizes (custo e veto) e devolve células. Aqui elas são
MONTADAS a partir de uma execução já feita — as notas 0-100 por célula da grade — pela regra declarada abaixo,
e o resultado volta para o mundo do mapa (linha em EPSG:4326, corredor em células).

REGRA DE CUSTO, declarada e reversível (é o que o manifesto publica):
    custo = 1 + (100 - nota)/100 × (custo_maximo - 1)
Nota 100 (a melhor) custa 1; nota 0 custa `custo_maximo`. Linear porque a nota já é a favorabilidade combinada
do motor multicritério: aplicar outra curva aqui esconderia a transformação que o usuário escolheu lá.

VETO, em três origens, todas declaradas na resposta:
  1. buraco da grade (célula que a execução não gerou, ou sem nota) — `sem_dado`, padrão `veto`;
  2. `veto_abaixo_de`: nota abaixo do limiar;
  3. `veto_nao_aprovadas`: célula que a execução não aprovou.
Ponto de partida ou de chegada em cima de veto é ERRO, nunca "o mais perto livre": mover o ponto do usuário em
silêncio é a maneira mais fácil de entregar um traçado que ninguém pediu (é a refutação do item)."""

from __future__ import annotations

import numpy as np

from app.amc import corredor as motor

SEM_DADO = ("veto", "custo_maximo")


class ErroCorredorExecucao(ValueError):
    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe or {}


def superficie(celulas: list[dict], colunas: int, linhas: int, *, custo_maximo: float = 10.0,
               sem_dado: str = "veto", veto_abaixo_de: float | None = None,
               veto_nao_aprovadas: bool = False) -> tuple[np.ndarray, np.ndarray, dict]:
    """Monta (custo, veto) da grade inteira a partir das linhas `{col, lin, nota, aprovada}` da execução."""
    if not (1.0 < custo_maximo <= 1000.0):
        raise ErroCorredorExecucao("custo_maximo_invalido", "o custo máximo vai de 1 (exclusive) a 1000",
                                   {"pedido": custo_maximo})
    if sem_dado not in SEM_DADO:
        raise ErroCorredorExecucao("sem_dado_invalido", f"`sem_dado` é um de {SEM_DADO}", {"pedido": sem_dado})
    if veto_abaixo_de is not None and not (0.0 <= veto_abaixo_de <= 100.0):
        raise ErroCorredorExecucao("limiar_invalido", "o limiar de veto é uma nota de 0 a 100",
                                   {"pedido": veto_abaixo_de})
    custo = np.full((linhas, colunas), float(custo_maximo), dtype=np.float32)
    veto = np.ones((linhas, colunas), dtype=bool) if sem_dado == "veto" else np.zeros((linhas, colunas), dtype=bool)
    sem_nota = 0
    for c in celulas:
        li, co = int(c["lin"]), int(c["col"])
        if not (0 <= li < linhas and 0 <= co < colunas):
            continue
        nota = c["nota"]
        if nota is None:
            sem_nota += 1
            continue
        custo[li, co] = 1.0 + (100.0 - float(nota)) / 100.0 * (float(custo_maximo) - 1.0)
        vetada = bool(veto_abaixo_de is not None and float(nota) < veto_abaixo_de)
        vetada = vetada or bool(veto_nao_aprovadas and not c["aprovada"])
        veto[li, co] = vetada
    diagnostico = {
        "celulas_da_grade": int(colunas * linhas),
        "celulas_com_nota": int(len(celulas) - sem_nota),
        "celulas_sem_nota": int(sem_nota),
        "celulas_vetadas": int(veto.sum()),
        "custo_maximo": float(custo_maximo),
        "custo_no_melhor": 1.0,
        "regra": "custo = 1 + (100 - nota)/100 * (custo_maximo - 1)",
        "sem_dado": sem_dado,
        "veto_abaixo_de": veto_abaixo_de,
        "veto_nao_aprovadas": bool(veto_nao_aprovadas),
    }
    return custo, veto, diagnostico


def celula_do_ponto(x_m: float, y_m: float, origem_x_m: float, origem_y_m: float, resolucao_m: float,
                    colunas: int, linhas: int, nome: str) -> tuple[int, int]:
    """Ponto no CRS de trabalho → (lin, col) da grade. Fora da grade é erro, nunca a borda mais perto."""
    col = int(np.floor((x_m - origem_x_m) / resolucao_m))
    lin = int(np.floor((y_m - origem_y_m) / resolucao_m))
    if not (0 <= col < colunas and 0 <= lin < linhas):
        raise ErroCorredorExecucao("ponto_fora_da_area", f"o ponto de {nome} está fora da área de estudo",
                                   {"col": col, "lin": lin, "colunas": colunas, "linhas": linhas})
    return lin, col


def tracar(custo: np.ndarray, veto: np.ndarray, a: tuple[int, int], b: tuple[int, int], *,
           vizinhanca: int = 16, epsilon: float | None = 0.05, resolucao_m: float = 100.0,
           motor_caminho: str = "esparso") -> dict:
    """Caminho + corredor + métricas, com os erros do motor traduzidos para o vocabulário desta camada."""
    try:
        linha = motor.caminho(custo, veto, a, b, vizinhanca=vizinhanca, motor=motor_caminho)
        medidas = motor.metricas(linha["celulas"], custo, resolucao_m)
        faixa = motor.corredor(custo, veto, a, b, epsilon=epsilon, vizinhanca=vizinhanca,
                               motor=motor_caminho) if epsilon is not None else None
    except motor.ErroCorredor as e:
        raise ErroCorredorExecucao(e.codigo, e.mensagem, e.detalhe) from e
    return {"linha": linha, "metricas": medidas, "corredor": faixa}

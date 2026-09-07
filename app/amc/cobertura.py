"""Cobertura por fator do motor multicritério (item L3-14-cobertura-dado-ausente).

Este módulo mede, para CADA fator de um modelo (uma coluna da matriz unidade × fator que
`app.amc.combinacao` recebe), duas frações independentes:

- ``fracao_unidades``: quantas unidades de análise têm dado válido naquele fator, sobre o total;
- ``fracao_area``: quando a área de cada unidade é informada, quanta ÁREA do território (não
  contagem de polígono) tem dado válido naquele fator — o mesmo raciocínio de peso de área que
  `app.amc.zonal` já aplica dentro de uma única unidade, aqui somado entre unidades.

Fator com `fracao_unidades` abaixo do limiar declarado (`LIMIAR_PADRAO`, 80 %) sai marcado — não é
removido do modelo nem escondido, é sinalizado para quem lê o relatório decidir. A política de dado
ausente do modelo (excluir/nulo/pessimista, ver `app.amc.combinacao.POLITICAS_AUSENTE`) é obrigatória
de declarar em todo relatório que usa este módulo (ver `app.amc.relatorio`); este módulo em si não
decide política, só mede presença.

Regra dura que este módulo nunca viola: ausência de dado (``None``/``nan`` na matriz de entrada)
NUNCA vira 0 nem 100 na cobertura. Cobertura é a fração de PRESENÇA, calculada só a partir da máscara
`np.isfinite`; nenhuma conta aqui soma ou tira média do VALOR do fator (isso é trabalho da combinação),
então não existe caminho em que um valor ausente entre como zero numérico.

O módulo é PURO: não abre banco, não lê arquivo, não usa relógio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LIMIAR_PADRAO = 0.8


class ErroCobertura(ValueError):
    """Erro de contrato da cobertura. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class CoberturaFator:
    """Cobertura medida de um único fator. `area_total`/`area_coberta`/`fracao_area` ficam `None`
    quando o chamador não informou área por unidade — a ausência de área não vira zero de área."""

    id_fator: str
    n_total: int
    n_presentes: int
    fracao_unidades: float
    area_total: float | None
    area_coberta: float | None
    fracao_area: float | None
    limiar: float
    abaixo_do_limiar: bool

    def como_dicionario(self) -> dict:
        return {
            "id_fator": self.id_fator,
            "n_total": self.n_total,
            "n_presentes": self.n_presentes,
            "fracao_unidades": self.fracao_unidades,
            "area_total": self.area_total,
            "area_coberta": self.area_coberta,
            "fracao_area": self.fracao_area,
            "limiar": self.limiar,
            "abaixo_do_limiar": self.abaixo_do_limiar,
        }


def _matriz(fatores) -> np.ndarray:
    """Mesma leitura tolerante de `app.amc.combinacao._matriz`: `None` vira `nan`, nunca 0."""
    if isinstance(fatores, np.ndarray):
        m = fatores.astype(np.float64, copy=True)
    else:
        m = np.array(
            [[np.nan if v is None else v for v in linha] for linha in fatores],
            dtype=np.float64,
        )
    if m.ndim != 2:
        raise ErroCobertura("matriz_invalida", "a matriz de fatores precisa ter duas dimensões (unidade × fator)")
    return m


def _valida_ids(ids, n_fatores: int) -> list[str]:
    if ids is None:
        return [f"fator_{i}" for i in range(n_fatores)]
    ids = list(ids)
    if len(ids) != n_fatores:
        raise ErroCobertura("ids_incompativeis", f"são {n_fatores} fatores e {len(ids)} identificadores")
    return ids


def cobertura_por_fator(
    fatores,
    ids_fatores=None,
    *,
    areas=None,
    limiar: float = LIMIAR_PADRAO,
) -> list[CoberturaFator]:
    """Cobertura de cada fator (coluna) da matriz `fatores` (unidade × fator; `None`/`nan` = sem dado).

    `areas`, se informado, é a área de cada unidade (mesma ordem das linhas); a cobertura de área de
    um fator é ``soma(área das unidades com dado) / soma(área de todas as unidades)``. Sem `areas`,
    `area_total`/`area_coberta`/`fracao_area` saem `None` — a ausência de área é declarada, não vira 0.

    `limiar` (padrão 80 %) só marca `abaixo_do_limiar`; não filtra nem descarta nada.
    """
    m = _matriz(fatores)
    n_unidades, n_fatores = m.shape
    if n_fatores == 0:
        raise ErroCobertura("sem_fatores", "o modelo não tem nenhum fator")
    ids = _valida_ids(ids_fatores, n_fatores)
    if not np.isfinite(limiar) or not (0.0 <= limiar <= 1.0):
        raise ErroCobertura("limiar_fora_da_faixa", "o limiar de cobertura tem de estar entre 0 e 1")

    area_arr = None
    if areas is not None:
        area_arr = np.asarray(areas, dtype=np.float64)
        if area_arr.shape != (n_unidades,):
            raise ErroCobertura("areas_incompativeis", f"são {n_unidades} unidades e {area_arr.size} áreas")
        if not np.all(np.isfinite(area_arr)):
            raise ErroCobertura("area_nao_finita", "área ausente, infinita ou NaN não é aceita — omita `areas` "
                                                    "inteiro se não houver área para nenhuma unidade")
        if np.any(area_arr < 0):
            raise ErroCobertura("area_negativa", "área negativa não é aceita")

    presente = np.isfinite(m)
    resultado: list[CoberturaFator] = []
    area_total_geral = float(area_arr.sum()) if area_arr is not None else None
    for j, id_fator in enumerate(ids):
        coluna_presente = presente[:, j]
        n_presentes = int(coluna_presente.sum())
        fracao_unidades = n_presentes / n_unidades
        area_coberta = fracao_area = None
        if area_arr is not None:
            area_coberta = float(area_arr[coluna_presente].sum())
            # soma de área é 0 só quando TODAS as unidades têm área 0 declarada — não confundir com
            # "sem informação de área", que já saiu como `areas is None` acima.
            fracao_area = (area_coberta / area_total_geral) if area_total_geral > 0 else None
        resultado.append(
            CoberturaFator(
                id_fator=id_fator,
                n_total=n_unidades,
                n_presentes=n_presentes,
                fracao_unidades=fracao_unidades,
                area_total=area_total_geral,
                area_coberta=area_coberta,
                fracao_area=fracao_area,
                limiar=limiar,
                abaixo_do_limiar=fracao_unidades < limiar,
            )
        )
    return resultado

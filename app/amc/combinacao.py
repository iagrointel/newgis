"""Combinação do motor multicritério: transforma a matriz de fatores já transformados (uma linha por
unidade de análise, uma coluna por fator, escala 0-100) em uma nota de favorabilidade por unidade.

Decisões de conceito que este módulo executa (laco/decomposicao/L3L6_CONCEITO.md, itens A3, A5, A6, A9):

- escala 0-100 em ponto flutuante; ausência de dado é NULL (``nan``), nunca zero;
- combinador padrão = soma ponderada normalizada sobre os fatores QUE TÊM dado,
  ``Σ w·f / Σ w``, o mesmo que o motor logístico da casa faz em SQL
  (``sum(a*f)/NULLIF(sum(a) FILTER (WHERE f IS NOT NULL),0)``);
- veto é objeto separado do peso: entra como fração vetada da unidade e multiplica a nota por
  ``(1 − fração vetada)``; fração 1 zera a nota e grava o motivo, sem depender de peso nenhum;
- os pesos são ESCOLHIDOS PELO USUÁRIO por projeto. Não são medidos, calculados nem otimizados por
  este código. Todo resultado carrega essa frase em ``aviso_pesos``.

O módulo é PURO: não abre banco, não lê arquivo, não usa relógio. É chamado uma vez por interação do
usuário e N vezes pela robustez (item L3-02), por isso trabalha vetorizado em numpy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

AVISO_PESOS = "pesos escolhidos pelo usuário, não medidos"

# Combinadores declarados. A chave é o nome gravado no modelo; o texto é o que a explicação mostra.
COMBINADORES: dict[str, str] = {
    "soma_ponderada": "soma ponderada normalizada Σ w·f / Σ w sobre os fatores com dado (padrão)",
    "percentual": "soma com pesos em porcentagem que fecham 100, arredondada ao inteiro (paridade "
                  "com o Weighted Overlay; perde precisão, não é a recomendação da casa)",
    "media_geometrica": "média geométrica ponderada exp(Σ w·ln f / Σ w); um fator em zero anula a nota",
    "minimo": "mínimo dos fatores com dado (E fuzzy); ignora os pesos por definição",
    "maximo": "máximo dos fatores com dado (OU fuzzy); ignora os pesos por definição",
    "produto": "produto fuzzy Π f, na escala 0-1; ignora os pesos por definição",
    "soma_fuzzy": "soma fuzzy 1 − Π(1 − f), na escala 0-1; ignora os pesos por definição",
    "gama": "gama fuzzy (soma fuzzy)^γ · (produto)^(1−γ); ignora os pesos por definição",
}
# Combinadores que, por definição matemática, não usam peso. A explicação tem de dizer isso.
SEM_PESO = frozenset({"minimo", "maximo", "produto", "soma_fuzzy", "gama"})

# Política de dado ausente na unidade.
POLITICAS_AUSENTE: dict[str, str] = {
    "excluir": "o fator sai da conta naquela unidade e a cobertura cai (padrão)",
    "nulo": "a unidade inteira fica sem nota quando falta qualquer fator",
    "pessimista": "o fator ausente recebe a nota 0, declarada como estimativa pessimista",
}

ESCALA_MIN, ESCALA_MAX = 0.0, 100.0
TOLERANCIA_PERCENTUAL = 1e-6  # soma dos percentuais tem de fechar 100


class ErroCombinacao(ValueError):
    """Erro de contrato da combinação. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass
class Resultado:
    """Saída da combinação. `fav` traz ``nan`` onde a unidade ficou sem nota — nunca 0 por falta de dado."""

    fav: np.ndarray
    vetado: np.ndarray
    cobertura: np.ndarray
    motivo: list[str | None]
    combinador: str
    politica_ausente: str
    pesos_normalizados: list[float]
    aviso_pesos: str = AVISO_PESOS
    observacoes: list[str] = field(default_factory=list)

    def como_dicionario(self) -> dict:
        """Forma serializável (API, PDF, explicação). Guarda a frase dos pesos junto dos números."""
        return {
            "aviso_pesos": self.aviso_pesos,
            "combinador": self.combinador,
            "descricao_combinador": COMBINADORES[self.combinador],
            "politica_ausente": self.politica_ausente,
            "pesos_normalizados": self.pesos_normalizados,
            "observacoes": list(self.observacoes),
            "fav": [None if not np.isfinite(v) else float(v) for v in self.fav],
            "vetado": [bool(v) for v in self.vetado],
            "cobertura": [float(c) for c in self.cobertura],
            "motivo": list(self.motivo),
        }


def _matriz(fatores) -> np.ndarray:
    """Aceita lista de listas com None ou array numpy; devolve float64 com ``nan`` no ausente."""
    if isinstance(fatores, np.ndarray):
        m = fatores.astype(np.float64, copy=True)
    else:
        m = np.array(
            [[np.nan if v is None else v for v in linha] for linha in fatores],
            dtype=np.float64,
        )
    if m.ndim != 2:
        raise ErroCombinacao("matriz_invalida", "a matriz de fatores precisa ter duas dimensões (unidade × fator)")
    return m


def _valida_pesos(pesos, n_fatores: int, combinador: str) -> np.ndarray:
    w = np.asarray(pesos, dtype=np.float64)
    if w.ndim != 1 or w.size != n_fatores:
        raise ErroCombinacao(
            "pesos_incompativeis",
            f"são {n_fatores} fatores e {w.size if w.ndim == 1 else '?'} pesos; um peso por fator",
        )
    if not np.all(np.isfinite(w)):
        raise ErroCombinacao("peso_nao_finito", "peso ausente, infinito ou NaN não é aceito")
    if np.any(w < 0):
        raise ErroCombinacao("peso_negativo", "peso negativo não é aceito; o peso é multiplicador ≥ 0")
    soma = float(w.sum())
    if soma <= 0:
        raise ErroCombinacao("soma_de_pesos_zero", "a soma dos pesos é zero; não há como normalizar")
    if combinador == "percentual" and abs(soma - 100.0) > TOLERANCIA_PERCENTUAL:
        raise ErroCombinacao(
            "percentual_nao_soma_100",
            f"no modo percentual os pesos têm de somar 100; somaram {soma:.6f}",
            {"soma": soma},
        )
    return w


def _valida_ids(ids, n_fatores: int) -> list[str]:
    if ids is None:
        return [f"fator_{i}" for i in range(n_fatores)]
    ids = list(ids)
    if len(ids) != n_fatores:
        raise ErroCombinacao("ids_incompativeis", f"são {n_fatores} fatores e {len(ids)} identificadores")
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ErroCombinacao(
            "fator_duplicado",
            "o mesmo fator aparece mais de uma vez no modelo: " + ", ".join(map(str, repetidos)),
            {"repetidos": repetidos},
        )
    return ids


def _valida_valores(m: np.ndarray) -> None:
    finitos = np.isfinite(m)
    if np.any(np.isinf(m)):
        raise ErroCombinacao("valor_nao_finito", "fator infinito não é aceito; ausência de dado é NULL")
    fora = finitos & ((m < ESCALA_MIN) | (m > ESCALA_MAX))
    if np.any(fora):
        linha, coluna = (int(x[0]) for x in np.nonzero(fora))
        raise ErroCombinacao(
            "valor_fora_da_escala",
            f"fator fora da escala 0-100 na unidade {linha}, fator {coluna}: {m[linha, coluna]}",
            {"unidade": linha, "fator": coluna, "valor": float(m[linha, coluna])},
        )


def _aplica_politica(m: np.ndarray, politica: str) -> tuple[np.ndarray, np.ndarray]:
    """Devolve (matriz de trabalho, máscara de presença) segundo a política de dado ausente."""
    presente = np.isfinite(m)
    if politica == "excluir":
        return m, presente
    if politica == "pessimista":
        trabalho = np.where(presente, m, ESCALA_MIN)
        return trabalho, np.ones_like(presente)
    if politica == "nulo":
        completa = presente.all(axis=1)
        trabalho = np.where(presente, m, np.nan)
        # unidade incompleta sai como NULL: zera a presença da linha inteira
        return trabalho, presente & completa[:, None]
    raise ErroCombinacao(
        "politica_ausente_desconhecida",
        "política de dado ausente desconhecida: " + str(politica),
        {"aceitas": sorted(POLITICAS_AUSENTE)},
    )


def combinar(
    fatores,
    pesos,
    *,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    gama: float = 0.5,
    fracao_vetada=None,
    motivo_veto=None,
    ids_fatores=None,
) -> Resultado:
    """Combina a matriz `fatores` (unidade × fator, escala 0-100, ``None``/``nan`` = sem dado).

    `pesos` é a escolha do usuário para o projeto: multiplicador ≥ 0, ou porcentagem que fecha 100 no
    combinador ``percentual``. `fracao_vetada` é a fração de cada unidade coberta por restrição (0 a 1) e
    multiplica a nota por ``(1 − fração)``; fração 1 zera a nota, marca ``vetado`` e grava o motivo.
    """
    if combinador not in COMBINADORES:
        raise ErroCombinacao(
            "combinador_desconhecido",
            "combinador desconhecido: " + str(combinador),
            {"aceitos": sorted(COMBINADORES)},
        )
    m = _matriz(fatores)
    n_unidades, n_fatores = m.shape
    if n_fatores == 0:
        raise ErroCombinacao("sem_fatores", "o modelo não tem nenhum fator")
    _valida_ids(ids_fatores, n_fatores)
    w = _valida_pesos(pesos, n_fatores, combinador)
    _valida_valores(m)
    if not np.isfinite(gama) or not (0.0 <= gama <= 1.0):
        raise ErroCombinacao("gama_fora_da_faixa", "o parâmetro gama tem de estar entre 0 e 1")

    trabalho, presente = _aplica_politica(m, politica_ausente)
    valores = np.where(presente, trabalho, 0.0)  # o zero só entra onde a máscara já exclui

    soma_pesos_total = float(w.sum())
    peso_presente = presente * w[None, :]
    soma_peso_presente = peso_presente.sum(axis=1)
    cobertura = soma_peso_presente / soma_pesos_total
    tem_dado = presente.any(axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        fav = _aplica_combinador(combinador, valores, presente, peso_presente, soma_peso_presente, gama)
    fav = np.where(tem_dado, fav, np.nan)

    vetado = np.zeros(n_unidades, dtype=bool)
    motivo: list[str | None] = [None] * n_unidades
    observacoes: list[str] = []
    if fracao_vetada is not None:
        f = np.asarray(fracao_vetada, dtype=np.float64)
        if f.shape != (n_unidades,):
            raise ErroCombinacao("fracao_vetada_incompativel", "uma fração vetada por unidade de análise")
        if not np.all(np.isfinite(f)) or np.any(f < 0) or np.any(f > 1):
            raise ErroCombinacao("fracao_vetada_invalida", "a fração vetada tem de estar entre 0 e 1")
        fav = fav * (1.0 - f)
        vetado = f >= 1.0
        # unidade sem nenhum dado continua sem nota mesmo quando vetada: veto marca, não inventa número
        fav = np.where(vetado & tem_dado, 0.0, fav)
        padrao = "unidade inteiramente coberta por restrição declarada no modelo"
        for i in np.nonzero(vetado)[0]:
            motivo[int(i)] = (motivo_veto[int(i)] if motivo_veto is not None else None) or padrao
        if vetado.any():
            observacoes.append(
                f"{int(vetado.sum())} de {n_unidades} unidades zeradas por restrição, não por peso"
            )

    if combinador in SEM_PESO:
        observacoes.append(
            "o combinador " + combinador + " não usa peso por definição matemática; "
            "os pesos escolhidos pelo usuário não entram nesta conta"
        )
    if combinador == "percentual":
        observacoes.append(
            "modo de paridade com o Weighted Overlay: a nota é arredondada ao inteiro e perde precisão"
        )
    sem_nota = int((~tem_dado).sum())
    if sem_nota:
        observacoes.append(f"{sem_nota} de {n_unidades} unidades ficaram sem nota por falta de dado")

    return Resultado(
        fav=fav,
        vetado=vetado,
        cobertura=cobertura,
        motivo=motivo,
        combinador=combinador,
        politica_ausente=politica_ausente,
        pesos_normalizados=[float(x) for x in (w / soma_pesos_total)],
        observacoes=observacoes,
    )


def _aplica_combinador(nome, valores, presente, peso_presente, soma_peso_presente, gama) -> np.ndarray:
    if nome in ("soma_ponderada", "percentual"):
        fav = (peso_presente * valores).sum(axis=1) / soma_peso_presente
        return np.round(fav) if nome == "percentual" else fav
    if nome == "media_geometrica":
        zerado = (presente & (valores <= 0.0)).any(axis=1)
        seguro = np.where(presente & (valores > 0.0), valores, 1.0)
        log = (peso_presente * np.log(seguro)).sum(axis=1) / soma_peso_presente
        return np.where(zerado, 0.0, np.exp(log))
    if nome == "minimo":
        return np.where(presente, valores, np.inf).min(axis=1)
    if nome == "maximo":
        return np.where(presente, valores, -np.inf).max(axis=1)
    u = np.where(presente, valores / ESCALA_MAX, np.nan)
    if nome == "produto":
        return np.nanprod(np.where(presente, u, 1.0), axis=1) * ESCALA_MAX
    if nome == "soma_fuzzy":
        return (1.0 - np.prod(np.where(presente, 1.0 - u, 1.0), axis=1)) * ESCALA_MAX
    if nome == "gama":
        produto = np.prod(np.where(presente, u, 1.0), axis=1)
        soma = 1.0 - np.prod(np.where(presente, 1.0 - u, 1.0), axis=1)
        return (soma**gama) * (produto ** (1.0 - gama)) * ESCALA_MAX
    raise ErroCombinacao("combinador_desconhecido", "combinador desconhecido: " + str(nome))

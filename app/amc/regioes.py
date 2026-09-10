"""Localizar regiões (item L3-05-localizar-regioes): a partir da grade de favorabilidade do motor multicritério,
encontrar N regiões CONTÍGUAS que somem uma área alvo, respeitando área mínima e máxima por região, distância
mínima e máxima entre regiões, e um compromisso declarado entre FORMA e UTILIDADE.

Equivalente da casa ao `Locate Regions` do ArcGIS Pro (paridade parâmetro a parâmetro em `docs/PARIDADE.md`,
página lida em 08/09/2026). O que este módulo NÃO faz é tão importante quanto o que faz: não escolhe pesos, não
decide o alvo de área e não inventa dado — recebe a favorabilidade já combinada (item L3-01-e) e os parâmetros
do usuário, e devolve as regiões com as estatísticas de cada uma.

Como funciona, em uma frase por passo:
1. **Sementes**: as células candidatas são ordenadas por favorabilidade e amostradas de forma espalhada (uma
   semente por bloco da grade), em número declarado por `sementes`; nenhuma vem de sorteio cego — o gerador
   aleatório é semeado (`semente_aleatoria`) e só desempata, por isso duas execuções iguais dão o MESMO
   resultado (refutação do item).
2. **Crescimento**: cada semente cresce por uma fila de prioridade sobre a fronteira; a prioridade de uma célula
   é `(1 − c)·utilidade + c·forma`, com `c = compromisso/100`. `utilidade` é a favorabilidade normalizada 0-1 e
   `forma` é o quanto a célula ainda cabe na forma-alvo (círculo, quadrado ou hexágono) de mesma área centrada
   no centróide corrente. Compromisso 0 = só utilidade; 100 = só forma.
3. **Avaliação**: cada região candidata recebe uma nota pelo `metodo` (maior média, maior soma, mediana ou maior
   área de núcleo — núcleo = células que não tocam a borda da região).
4. **Seleção**: `sequencial` toma a melhor candidata, descarta as que se sobrepõem ou violam a distância mínima
   e repete; `combinatoria` (só para N pequeno) prova as combinações e fica com a de maior nota somada que
   respeita as distâncias.
5. **Ajuste de área**: a área total é distribuída entre as N regiões (`area_total/N`), presa entre `area_min` e
   `area_max`; a soma final fica dentro da tolerância declarada ou o pedido é recusado com o motivo.
Célula vetada ou sem dado (`nan`) é intransponível: nunca entra em região.

O módulo é PURO: numpy e scipy.ndimage, sem banco, sem arquivo e sem relógio."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

N_REGIOES_MAX = 30
COMPROMISSO_MIN, COMPROMISSO_MAX = 0, 100
TOLERANCIA_AREA = 0.05  # 5 %: a soma das áreas das regiões fica a esta distância do alvo (portão do item)

FORMAS: dict[str, str] = {
    "circulo": "círculo (padrão; o Locate Regions chama CIRCLE)",
    "quadrado": "quadrado (SQUARE)",
    "hexagono": "hexágono (HEXAGON)",
}
AVALIACOES: dict[str, str] = {
    "maior_media": "maior favorabilidade média (HIGHEST_AVERAGE_VALUE, o padrão da referência)",
    "maior_soma": "maior soma de favorabilidade (HIGHEST_SUM)",
    "mediana": "maior mediana de favorabilidade (HIGHEST_MEDIAN_VALUE)",
    "maior_area_nucleo": "maior área de núcleo, células que não tocam a borda da região (GREATEST_CORE_AREA)",
}
SELECOES: dict[str, str] = {
    "sequencial": "toma a melhor candidata, descarta as incompatíveis e repete (SEQUENTIAL)",
    "combinatoria": "prova as combinações de candidatas e fica com a melhor soma (COMBINATORIAL; N pequeno)",
}
SEMENTES: dict[str, int] = {"auto": 0, "poucas": 16, "medias": 64, "muitas": 256, "maximo": 1024}
RESOLUCOES: dict[str, int] = {"auto": 0, "baixa": 4, "media": 2, "alta": 1, "maxima": 1}
VIZINHANCAS = (4, 8)
COMBINATORIA_CANDIDATAS_MAX = 20  # acima disto a combinatória explode; a recusa é explícita


class ErroRegioes(ValueError):
    """Recusa nomeada: `codigo` entra no corpo do erro da API sem tradução."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe or {}


@dataclass(frozen=True)
class Pedido:
    """Os parâmetros do usuário. Área e distância em UNIDADES DE CÉLULA quando `area_celula`/`lado_celula` não
    são informados; com eles, em metros quadrados e metros."""

    n_regioes: int = 1
    area_total: float | None = None
    area_min: float | None = None
    area_max: float | None = None
    distancia_min: float | None = None
    distancia_max: float | None = None
    compromisso: int = 50
    forma: str = "circulo"
    metodo: str = "maior_media"
    selecao: str = "sequencial"
    vizinhanca: int = 8
    sem_ilhas: bool = True
    sementes: str = "auto"
    resolucao_crescimento: str = "auto"
    semente_aleatoria: int = 0
    area_celula: float = 1.0   # m² por célula (1.0 = contar em células)
    lado_celula: float = 1.0   # m por lado da célula (1.0 = contar em células)


@dataclass
class Regiao:
    indice: int
    celulas: int
    area: float
    media: float
    soma: float
    mediana: float
    area_nucleo: float
    compacidade: float
    centroide: tuple[float, float]   # (linha, coluna) em índice de célula
    nota: float


@dataclass
class Resultado:
    rotulos: np.ndarray              # int32, 0 = fora de região, 1..N = região
    regioes: list[Regiao]
    area_total: float
    area_alvo: float
    parametros: dict
    observacoes: list[str] = field(default_factory=list)

    def como_dicionario(self) -> dict:
        return {
            "parametros": self.parametros,
            "area_alvo": self.area_alvo,
            "area_total": self.area_total,
            "n_regioes": len(self.regioes),
            "observacoes": list(self.observacoes),
            "regioes": [
                {
                    "indice": r.indice, "celulas": r.celulas, "area": r.area, "media": r.media, "soma": r.soma,
                    "mediana": r.mediana, "area_nucleo": r.area_nucleo, "compacidade": r.compacidade,
                    "centroide_lin": r.centroide[0], "centroide_col": r.centroide[1], "nota": r.nota,
                }
                for r in self.regioes
            ],
        }


# ---------------------------------------------------------------- validação
def _validar(p: Pedido, fav: np.ndarray) -> tuple[float, float, float, float]:
    if fav.ndim != 2 or fav.size == 0:
        raise ErroRegioes("grade_invalida", "a favorabilidade tem de ser uma grade 2-D não vazia")
    if not (1 <= p.n_regioes <= N_REGIOES_MAX):
        raise ErroRegioes("n_regioes_fora_do_limite",
                          f"o número de regiões tem de estar entre 1 e {N_REGIOES_MAX}",
                          {"pedido": p.n_regioes, "maximo": N_REGIOES_MAX})
    if p.forma not in FORMAS:
        raise ErroRegioes("forma_desconhecida", f"forma-alvo desconhecida: {p.forma!r}",
                          {"aceitas": sorted(FORMAS)})
    if p.metodo not in AVALIACOES:
        raise ErroRegioes("metodo_desconhecido", f"método de avaliação desconhecido: {p.metodo!r}",
                          {"aceitos": sorted(AVALIACOES)})
    if p.selecao not in SELECOES:
        raise ErroRegioes("selecao_desconhecida", f"método de seleção desconhecido: {p.selecao!r}",
                          {"aceitos": sorted(SELECOES)})
    if not (COMPROMISSO_MIN <= p.compromisso <= COMPROMISSO_MAX):
        raise ErroRegioes("compromisso_fora_do_limite", "o compromisso forma × utilidade vai de 0 a 100",
                          {"pedido": p.compromisso})
    if p.vizinhanca not in VIZINHANCAS:
        raise ErroRegioes("vizinhanca_invalida", "a vizinhança é 4 ou 8", {"pedido": p.vizinhanca})
    if p.sementes not in SEMENTES:
        raise ErroRegioes("sementes_invalidas", f"número de sementes desconhecido: {p.sementes!r}",
                          {"aceitos": sorted(SEMENTES)})
    if p.resolucao_crescimento not in RESOLUCOES:
        raise ErroRegioes("resolucao_invalida", f"resolução de crescimento desconhecida: {p.resolucao_crescimento!r}",
                          {"aceitas": sorted(RESOLUCOES)})
    if p.area_celula <= 0 or p.lado_celula <= 0:
        raise ErroRegioes("celula_invalida", "área e lado da célula têm de ser positivos")

    disponiveis = int(np.count_nonzero(np.isfinite(fav)))
    if disponiveis == 0:
        raise ErroRegioes("sem_area_disponivel", "nenhuma célula com favorabilidade (tudo vetado ou sem dado)")
    area_disponivel = disponiveis * p.area_celula
    alvo = float(p.area_total) if p.area_total is not None else area_disponivel * 0.1  # padrão da referência: 10 %
    if alvo <= 0:
        raise ErroRegioes("area_total_invalida", "a área total tem de ser positiva", {"pedido": alvo})
    if alvo > area_disponivel:
        raise ErroRegioes(
            "area_maior_que_a_disponivel",
            "a área total pedida é maior que a área não vetada da grade",
            {"area_pedida": alvo, "area_disponivel": area_disponivel, "celulas_disponiveis": disponiveis},
        )
    a_min = float(p.area_min) if p.area_min is not None else 0.0
    a_max = float(p.area_max) if p.area_max is not None else float("inf")
    if a_min > a_max:
        raise ErroRegioes("area_min_maior_que_max", "a área mínima por região é maior que a máxima",
                          {"area_min": a_min, "area_max": a_max})
    if p.n_regioes * a_min > alvo * (1 + TOLERANCIA_AREA):
        raise ErroRegioes("area_min_impossivel",
                          "N × área mínima por região é maior que a área total pedida",
                          {"n_regioes": p.n_regioes, "area_min": a_min, "area_total": alvo})
    if math.isfinite(a_max) and p.n_regioes * a_max < alvo * (1 - TOLERANCIA_AREA):
        raise ErroRegioes("area_max_impossivel",
                          "N × área máxima por região é menor que a área total pedida",
                          {"n_regioes": p.n_regioes, "area_max": a_max, "area_total": alvo})
    if p.distancia_min is not None and p.distancia_max is not None and p.distancia_min > p.distancia_max:
        raise ErroRegioes("distancia_min_maior_que_max", "a distância mínima entre regiões é maior que a máxima",
                          {"distancia_min": p.distancia_min, "distancia_max": p.distancia_max})
    return alvo, a_min, a_max, area_disponivel


# ---------------------------------------------------------------- forma-alvo
def _raio_equivalente(celulas: int, forma: str) -> float:
    """Raio (em células) da forma-alvo de mesma área que a região: o crescimento mede a distância a esse contorno."""
    if celulas <= 0:
        return 0.0
    if forma == "circulo":
        return math.sqrt(celulas / math.pi)
    if forma == "quadrado":
        return math.sqrt(celulas) / 2.0
    # hexágono regular de área A: circunraio R = sqrt(2A / (3·sqrt(3)))
    return math.sqrt(2.0 * celulas / (3.0 * math.sqrt(3.0)))


def _dentro_da_forma(dlin: np.ndarray, dcol: np.ndarray, raio: float, forma: str) -> np.ndarray:
    """Máscara: o deslocamento (dlin, dcol) em relação ao centro cai dentro da forma-alvo de raio `raio`?"""
    if forma == "circulo":
        return (dlin * dlin + dcol * dcol) <= raio * raio
    if forma == "quadrado":
        return (np.abs(dlin) <= raio) & (np.abs(dcol) <= raio)
    # hexágono regular (topo plano) de circunraio `raio`
    x, y = np.abs(dcol), np.abs(dlin)
    return (x <= raio) & (y <= (math.sqrt(3.0) / 2.0) * raio) & ((math.sqrt(3.0) * x + y) <= math.sqrt(3.0) * raio)


def _norma_forma(dlin: float, dcol: float, forma: str) -> float:
    """Raio da forma-alvo que passa por (dlin, dcol): é a distância na MÉTRICA da forma. Círculo = distância
    euclidiana; quadrado = distância de Chebyshev; hexágono = a métrica do hexágono regular de topo plano."""
    x, y = abs(dcol), abs(dlin)
    if forma == "circulo":
        return math.hypot(dlin, dcol)
    if forma == "quadrado":
        return max(x, y)
    return max(x, x + y / math.sqrt(3.0), 2.0 * y / math.sqrt(3.0))


def compacidade(mascara: np.ndarray, forma: str = "circulo") -> float:
    """Fração das células da região que cabem na forma-alvo de MESMA ÁREA centrada no centróide da região.
    1,0 = a região é exatamente a forma-alvo. Medida em célula, não em perímetro: o perímetro de uma forma
    digitalizada é uma escada e superestima o contorno, o que faria um disco perfeito 'perder' compacidade."""
    lins, cols = np.nonzero(mascara)
    if lins.size == 0:
        return 0.0
    centro_lin, centro_col = lins.mean(), cols.mean()
    raio = _raio_equivalente(int(lins.size), forma)
    dentro = _dentro_da_forma(lins - centro_lin, cols - centro_col, raio, forma)
    return float(np.count_nonzero(dentro) / lins.size)


# ---------------------------------------------------------------- sementes e crescimento
def _passos(vizinhanca: int) -> list[tuple[int, int]]:
    quatro = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if vizinhanca == 4:
        return quatro
    return quatro + [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def _n_sementes(p: Pedido, disponiveis: int) -> int:
    if p.sementes != "auto":
        return SEMENTES[p.sementes]
    # auto: sementes suficientes para cobrir a grade sem explodir o custo (o crescimento é O(sementes × área))
    return int(min(256, max(16, p.n_regioes * 8)))


def _sementes(fav: np.ndarray, p: Pedido, n: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    """Uma semente por bloco da grade, na célula de maior favorabilidade do bloco (empate desfeito pelo gerador
    semeado). Espalha as candidatas: sementes proporcionais à favorabilidade que caíssem todas no mesmo pico
    devolveriam N vezes a mesma região."""
    lin, col = fav.shape
    lado = max(1, int(math.ceil(math.sqrt((lin * col) / max(n, 1)))))
    escolhidas: list[tuple[float, int, int]] = []
    for i0 in range(0, lin, lado):
        for j0 in range(0, col, lado):
            bloco = fav[i0:i0 + lado, j0:j0 + lado]
            if not np.any(np.isfinite(bloco)):
                continue
            achatado = np.where(np.isfinite(bloco), bloco, -np.inf)
            melhor = np.argmax(achatado)
            di, dj = np.unravel_index(melhor, bloco.shape)
            valor = float(achatado[di, dj])
            if not np.isfinite(valor):
                continue
            escolhidas.append((valor + float(rng.random()) * 1e-9, i0 + int(di), j0 + int(dj)))
    escolhidas.sort(key=lambda t: -t[0])
    return [(i, j) for _, i, j in escolhidas[: max(n, p.n_regioes)]]


def _crescer(fav: np.ndarray, semente: tuple[int, int], alvo_celulas: int, p: Pedido,
             faixa: tuple[float, float]) -> np.ndarray | None:
    """Cresce até `alvo_celulas` e, com `sem_ilhas`, fecha os buracos. Fechar buraco ACRESCENTA célula, então a
    área final passaria do alvo; por isso o crescimento é repetido com o alvo descontado do excedente até a área
    final encostar no pedido (no máximo 5 voltas, cada uma barata). Devolve a máscara mais próxima do alvo, ou
    None quando nem a primeira volta alcança a área (bolsão pequeno demais ou cercado de veto)."""
    melhor: np.ndarray | None = None
    melhor_erro = math.inf
    pedido_interno = alvo_celulas
    for _ in range(5):
        if pedido_interno <= 0:
            break
        mascara = _crescer_uma_vez(fav, semente, pedido_interno, p, faixa)
        if mascara is None:
            break
        n = int(np.count_nonzero(mascara))
        erro = abs(n - alvo_celulas)
        if erro < melhor_erro:
            melhor, melhor_erro = mascara, erro
        if n <= alvo_celulas:
            break
        pedido_interno -= (n - alvo_celulas)
    return melhor


def _crescer_uma_vez(fav: np.ndarray, semente: tuple[int, int], alvo_celulas: int, p: Pedido,
                     faixa: tuple[float, float]) -> np.ndarray | None:
    """Uma volta de crescimento: fila de prioridade a partir da semente até `alvo_celulas` células."""
    lin, col = fav.shape
    dentro = np.zeros(fav.shape, dtype=bool)
    visitado = np.zeros(fav.shape, dtype=bool)
    i0, j0 = semente
    if not np.isfinite(fav[i0, j0]):
        return None
    baixo, alto = faixa
    escala = (alto - baixo) or 1.0
    c = p.compromisso / 100.0
    passos = _passos(p.vizinhanca)
    n = 0
    fila: list[tuple[float, int, int, int]] = []
    contador = 0
    # o termo de FORMA mede a distância à semente na métrica da forma-alvo, normalizada pelo raio da forma de
    # área FINAL (não da área corrente): com compromisso 100 a frente de crescimento é a própria forma-alvo, e
    # a região sai com a compacidade dela. Normalizar pelo raio corrente faria o termo saturar nas primeiras
    # células (raio ~ 0,5) e o crescimento perderia a forma — medido: compacidade 0,61 contra 0,95.
    raio_final = max(_raio_equivalente(alvo_celulas, p.forma), 1e-9)

    def prioridade(i: int, j: int) -> float:
        util = (float(fav[i, j]) - baixo) / escala
        forma = 1.0 - min(_norma_forma(i - i0, j - j0, p.forma) / raio_final, 1.0)
        return -((1.0 - c) * util + c * forma)  # heapq é fila de MENOR: prioridade negativa

    heapq.heappush(fila, (prioridade(i0, j0), contador, i0, j0))
    visitado[i0, j0] = True
    while fila and n < alvo_celulas:
        _, _, i, j = heapq.heappop(fila)
        if dentro[i, j]:
            continue
        dentro[i, j] = True
        n += 1
        for di, dj in passos:
            vi, vj = i + di, j + dj
            if 0 <= vi < lin and 0 <= vj < col and not visitado[vi, vj] and np.isfinite(fav[vi, vj]):
                visitado[vi, vj] = True
                contador += 1
                heapq.heappush(fila, (prioridade(vi, vj), contador, vi, vj))
    if n < alvo_celulas:
        return None
    if p.sem_ilhas:
        dentro = ndimage.binary_fill_holes(dentro)
        dentro &= np.isfinite(fav)  # nunca engolir célula vetada ao fechar buraco
    return dentro


# ---------------------------------------------------------------- avaliação e seleção
def _estatisticas(fav: np.ndarray, mascara: np.ndarray, p: Pedido, indice: int) -> Regiao:
    valores = fav[mascara]
    lins, cols = np.nonzero(mascara)
    erodida = ndimage.binary_erosion(mascara, structure=np.ones((3, 3), dtype=bool), border_value=0)
    celulas = int(valores.size)
    return Regiao(
        indice=indice, celulas=celulas, area=celulas * p.area_celula,
        media=float(np.mean(valores)), soma=float(np.sum(valores)), mediana=float(np.median(valores)),
        area_nucleo=float(int(np.count_nonzero(erodida)) * p.area_celula),
        compacidade=compacidade(mascara, p.forma),
        centroide=(float(lins.mean()), float(cols.mean())), nota=0.0,
    )


def _nota(r: Regiao, metodo: str) -> float:
    return {"maior_media": r.media, "maior_soma": r.soma, "mediana": r.mediana,
            "maior_area_nucleo": r.area_nucleo}[metodo]


def _distancia(a: Regiao, b: Regiao, lado: float) -> float:
    return math.dist(a.centroide, b.centroide) * lado


def _compativel(cand: Regiao, escolhidas: list[Regiao], mascaras: dict[int, np.ndarray], p: Pedido) -> bool:
    for e in escolhidas:
        if np.any(mascaras[cand.indice] & mascaras[e.indice]):
            return False
        d = _distancia(cand, e, p.lado_celula)
        if p.distancia_min is not None and d < p.distancia_min:
            return False
        if p.distancia_max is not None and d > p.distancia_max:
            return False
    return True


def _selecionar(candidatas: list[Regiao], mascaras: dict[int, np.ndarray], p: Pedido) -> list[Regiao]:
    ordenadas = sorted(candidatas, key=lambda r: (-r.nota, r.indice))
    if p.selecao == "combinatoria":
        if len(ordenadas) > COMBINATORIA_CANDIDATAS_MAX:
            ordenadas = ordenadas[:COMBINATORIA_CANDIDATAS_MAX]
        from itertools import combinations
        melhor: list[Regiao] = []
        melhor_nota = -math.inf
        for combo in combinations(ordenadas, min(p.n_regioes, len(ordenadas))):
            ok = True
            for i, a in enumerate(combo):
                if not _compativel(a, list(combo[:i]), mascaras, p):
                    ok = False
                    break
            if not ok:
                continue
            soma = sum(r.nota for r in combo)
            if soma > melhor_nota:
                melhor_nota, melhor = soma, list(combo)
        return melhor
    escolhidas: list[Regiao] = []
    for cand in ordenadas:
        if len(escolhidas) >= p.n_regioes:
            break
        if _compativel(cand, escolhidas, mascaras, p):
            escolhidas.append(cand)
    return escolhidas


# ---------------------------------------------------------------- entrada única
def localizar(fav: np.ndarray, pedido: Pedido | None = None) -> Resultado:
    """Encontra as regiões. `fav` é a grade de favorabilidade 0-100 com `nan` onde não há dado ou há veto."""
    p = pedido or Pedido()
    fav = np.asarray(fav, dtype=float)
    alvo, a_min, a_max, area_disponivel = _validar(p, fav)
    finitos = fav[np.isfinite(fav)]
    faixa = (float(finitos.min()), float(finitos.max()))
    observacoes: list[str] = []

    por_regiao = alvo / p.n_regioes
    if por_regiao < a_min:
        por_regiao = a_min
        observacoes.append("área por região elevada até a área mínima pedida")
    if por_regiao > a_max:
        por_regiao = a_max
        observacoes.append("área por região limitada pela área máxima pedida")
    alvo_celulas = max(1, int(round(por_regiao / p.area_celula)))

    rng = np.random.default_rng(p.semente_aleatoria)
    n_sementes = _n_sementes(p, int(np.count_nonzero(np.isfinite(fav))))
    sementes = _sementes(fav, p, n_sementes, rng)
    if not sementes:
        raise ErroRegioes("sem_semente", "nenhuma célula com dado para semear o crescimento")

    candidatas: list[Regiao] = []
    mascaras: dict[int, np.ndarray] = {}
    for s in sementes:
        mascara = _crescer(fav, s, alvo_celulas, p, faixa)
        if mascara is None:
            continue
        r = _estatisticas(fav, mascara, p, indice=len(candidatas) + 1)
        if r.area < a_min or r.area > a_max:
            continue
        r.nota = _nota(r, p.metodo)
        candidatas.append(r)
        mascaras[r.indice] = mascara
    if not candidatas:
        raise ErroRegioes("sem_regiao_possivel",
                          "nenhuma região contígua alcançou a área pedida (bolsões pequenos demais ou vetos)",
                          {"area_por_regiao": por_regiao, "celulas_por_regiao": alvo_celulas})

    escolhidas = _selecionar(candidatas, mascaras, p)
    if not escolhidas:
        raise ErroRegioes("sem_combinacao_possivel",
                          "nenhuma combinação de regiões respeita as distâncias pedidas",
                          {"candidatas": len(candidatas), "distancia_min": p.distancia_min,
                           "distancia_max": p.distancia_max})
    if len(escolhidas) < p.n_regioes:
        observacoes.append(f"{len(escolhidas)} região(ões) de {p.n_regioes} pedidas: as demais violariam "
                           "sobreposição, distância mínima ou área")

    rotulos = np.zeros(fav.shape, dtype=np.int32)
    regioes: list[Regiao] = []
    for novo, r in enumerate(escolhidas, start=1):
        rotulos[mascaras[r.indice]] = novo
        r.indice = novo
        regioes.append(r)
    area_total = float(sum(r.area for r in regioes))
    if abs(area_total - alvo) > alvo * TOLERANCIA_AREA:
        observacoes.append(f"área total {area_total:g} fora da tolerância de {TOLERANCIA_AREA:.0%} sobre o alvo "
                           f"{alvo:g} (limitada por área mínima/máxima, vetos ou distância)")
    parametros = {
        "n_regioes": p.n_regioes, "area_total_pedida": alvo, "area_min": p.area_min, "area_max": p.area_max,
        "distancia_min": p.distancia_min, "distancia_max": p.distancia_max, "compromisso": p.compromisso,
        "forma": p.forma, "forma_descricao": FORMAS[p.forma], "metodo": p.metodo,
        "metodo_descricao": AVALIACOES[p.metodo], "selecao": p.selecao, "selecao_descricao": SELECOES[p.selecao],
        "vizinhanca": p.vizinhanca, "sem_ilhas": p.sem_ilhas, "sementes": p.sementes,
        "resolucao_crescimento": p.resolucao_crescimento, "semente_aleatoria": p.semente_aleatoria,
        "area_celula": p.area_celula, "lado_celula": p.lado_celula, "area_disponivel": area_disponivel,
        "candidatas": len(candidatas), "tolerancia_area": TOLERANCIA_AREA,
    }
    return Resultado(rotulos=rotulos, regioes=regioes, area_total=area_total, area_alvo=alvo,
                     parametros=parametros, observacoes=observacoes)


__all__ = ["ErroRegioes", "FORMAS", "AVALIACOES", "Pedido", "Regiao", "Resultado", "SELECOES", "SEMENTES",
           "N_REGIOES_MAX", "compacidade", "localizar"]

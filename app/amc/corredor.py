"""Motor de traçado linear: superfície de custo declarada, caminho de custo mínimo e corredor-epsilon
(item L3-10-corredor-custo-minimo; equivalente da casa ao par `Distance Accumulation` + `Optimal Path as Line`).

A REGRA DE COMPOSIÇÃO é a do motor de traçado da casa (rs-coop/tracado-lt, v1.1), reproduzida aqui e conferida
bit a bit contra a superfície oficial no teste:
1. penalidade por MÁXIMO sobre as camadas de custo (`max(cost, peso onde a máscara vale)`): comutativa, o
   resultado não depende da ordem da lista;
2. curva de relevo (declividade → fator) entra pelo mesmo máximo — é modelagem declarada, não norma;
3. densidade de edificação entra por uma rampa declarada, também por máximo;
4. compressão de AMPLITUDE opcional: `custo ** alfa`, com `alfa = ln(alvo)/ln(max medido fora do veto)` —
   monótona (a hierarquia dos pesos sobrevive), ponto fixo em 1,0, e o alfa é DERIVADO do dado, nunca digitado;
5. atração (co-locação) como passada FINAL multiplicativa, com piso: `cost × prod(valores)`, nunca abaixo de
   `min_atracao`. Passada final porque desconto aplicado no meio do máximo é engolido pela penalidade seguinte;
6. veto por último: célula vetada recebe custo proibitivo e o roteador nunca entra nela.

O CAMINHO é Dijkstra em 16 vizinhos (as 8 usuais mais os 8 saltos de cavalo), com **aresta íntegra**: um salto
que passa por cima de célula vetada não existe, e a diagonal exige um vizinho ortogonal livre (não se espreme
entre dois vetos). O custo de uma aresta é a média dos custos das pontas vezes o comprimento em células — a
mesma régua do motor de referência. Sem custo de deflexão (ângulo) — é métrica, não custo, e vai declarado.

O CORREDOR-epsilon são as células por onde passa algum caminho com custo até `(1+ε)` do ótimo: `dist_A(c) +
dist_B(c) ≤ (1+ε)·ótimo`, com as duas distâncias de custo mínimo calculadas do mesmo jeito.

Módulo PURO: numpy + heapq, sem banco, sem arquivo e sem relógio."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np

CUSTO_VETO = 1e6           # o "HARD" do motor de referência: célula vetada nunca é atravessada
MIN_ATRACAO_PADRAO = 0.55  # piso do desconto de co-locação (motor de referência)
CURVA_RELEVO_PADRAO = ((3, 1.00), (8, 1.10), (20, 1.35), (45, 1.90), (float("inf"), 2.60))
VIZINHANCAS = (4, 8, 16)
# 8 vizinhos usuais + 8 saltos de cavalo (o 16 do item): (dlin, dcol)
PASSOS_8 = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
PASSOS_CAVALO = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))


class ErroCorredor(ValueError):
    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe or {}


@dataclass(frozen=True)
class Camada:
    """Uma camada declarada da superfície. `papel`: custo (peso), atrai (valor < 1) ou veto."""
    id: str
    papel: str
    mascara: np.ndarray
    peso: float | None = None
    valor: float | None = None


@dataclass
class Superficie:
    custo: np.ndarray
    veto: np.ndarray
    diagnostico: dict = field(default_factory=dict)


def curva_relevo(declividade: np.ndarray, curva=CURVA_RELEVO_PADRAO) -> np.ndarray:
    """Declividade (%) → fator de custo, pela curva declarada (última faixa é o padrão)."""
    limites = [lim for lim, _ in curva[:-1]]
    fatores = [f for _, f in curva]
    return np.select([declividade < lim for lim in limites], fatores[:-1], default=fatores[-1]).astype(np.float32)


def comprimir_amplitude(pen: np.ndarray, veto: np.ndarray | None = None,
                        alvo: float | None = None) -> tuple[np.ndarray, dict]:
    """`custo ** alfa` com `alfa = ln(alvo)/ln(max)`, medido FORA do veto (célula que vira veto não puxa o
    expoente: o desvio que ela compraria não existe). Monótona e com ponto fixo em 1,0."""
    livre = pen if veto is None else pen[~veto]
    mx = float(np.nanmax(livre)) if livre.size else 1.0
    mn = float(np.nanmin(livre)) if livre.size else 1.0
    diag = {"alvo_amplitude": alvo, "max_medido": round(mx, 4), "min_medido": round(mn, 4),
            "amplitude_antes": round(mx / mn, 4) if mn > 0 else None,
            "medido_em": "celulas fora do veto" if veto is not None else "janela inteira"}
    if not alvo or alvo <= 1.0 or not np.isfinite(mx) or mx <= 1.0 or alvo >= mx:
        diag.update(aplicada=False, alfa=1.0, motivo="alvo desligado ou amplitude já abaixo do alvo",
                    amplitude_depois=diag["amplitude_antes"])
        return pen, diag
    alfa = math.log(alvo) / math.log(mx)
    fora = np.power(pen, np.float32(alfa)).astype(np.float32)
    lv = fora if veto is None else fora[~veto]
    diag.update(aplicada=True, alfa=round(alfa, 6), forma="custo ** alfa (monótona, ponto fixo em 1,0)",
                max_depois=round(float(np.nanmax(lv)), 4), min_depois=round(float(np.nanmin(lv)), 4),
                amplitude_depois=round(float(np.nanmax(lv) / np.nanmin(lv)), 4))
    return fora, diag


def compor(camadas: list[Camada], *, forma: tuple[int, int] | None = None,
           declividade: np.ndarray | None = None, curva=CURVA_RELEVO_PADRAO,
           rampas: list[tuple[np.ndarray, float, float]] | None = None,
           alvo_amplitude: float | None = None, min_atracao: float = MIN_ATRACAO_PADRAO,
           custo_veto: float = CUSTO_VETO) -> Superficie:
    """Superfície de custo pela regra declarada (ver o cabeçalho). `rampas` são pares
    (valor por célula, teto, peso) que viram `1 + clip(valor, 0, teto) * (peso/teto)` — a densidade de
    edificação do motor de referência é uma delas."""
    if forma is None:
        for c in camadas:
            forma = c.mascara.shape
            break
        if forma is None and declividade is not None:
            forma = declividade.shape
    if forma is None:
        raise ErroCorredor("sem_forma", "nenhuma camada, declividade ou forma informada")
    custo = np.ones(forma, dtype=np.float32)
    for c in camadas:
        if c.papel != "custo":
            continue
        peso = np.float32(c.peso if c.peso is not None else 2.0)
        custo = np.maximum(custo, np.where(c.mascara, peso, np.float32(1.0)))
    if declividade is not None:
        d = np.where(declividade < 0, 0, declividade)
        custo = np.maximum(custo, curva_relevo(d, curva))
    for valores, teto, peso in rampas or []:
        custo = np.maximum(custo, (1.0 + np.clip(valores, 0, teto) * (peso / teto)).astype(np.float32))
    veto = np.zeros(forma, dtype=bool)
    for c in camadas:
        if c.papel == "veto":
            veto |= c.mascara
    custo, diag = comprimir_amplitude(custo, veto=veto, alvo=alvo_amplitude)
    atracao = np.ones(forma, dtype=np.float32)
    for c in camadas:
        if c.papel != "atrai":
            continue
        atracao = np.where(c.mascara, atracao * np.float32(c.valor if c.valor is not None else 1.0), atracao)
    atracao = np.maximum(atracao, np.float32(min_atracao))
    custo = (custo * atracao).copy()
    custo[veto] = np.float32(custo_veto)
    diag.update(camadas_custo=sum(1 for c in camadas if c.papel == "custo"),
                camadas_atrai=sum(1 for c in camadas if c.papel == "atrai"),
                camadas_veto=sum(1 for c in camadas if c.papel == "veto"),
                min_atracao=min_atracao, custo_veto=custo_veto)
    return Superficie(custo=custo, veto=veto, diagnostico=diag)


# ---------------------------------------------------------------- caminho de custo mínimo
def _passos(vizinhanca: int) -> tuple[tuple[int, int], ...]:
    if vizinhanca == 4:
        return PASSOS_8[:4]
    if vizinhanca == 8:
        return PASSOS_8
    return PASSOS_8 + PASSOS_CAVALO


def _interiores(dl: int, dc: int) -> tuple[tuple[int, int], ...]:
    """Células que o SALTO DE CAVALO atravessa: elas têm de estar livres E entram na média do peso da aresta
    (a "aresta íntegra"). Passo reto e diagonal não atravessam célula nenhuma."""
    if abs(dl) == 2 and abs(dc) == 1:
        return ((dl // 2, 0), (dl // 2, dc))
    if abs(dl) == 1 and abs(dc) == 2:
        return ((0, dc // 2), (dl, dc // 2))
    return ()


def _ortogonais(dl: int, dc: int) -> tuple[tuple[int, int], ...]:
    """A diagonal exige que ao MENOS UM dos dois vizinhos ortogonais esteja livre — não se espreme entre dois
    vetos. Eles NÃO entram no peso da aresta (a diagonal não passa por dentro deles)."""
    if abs(dl) == 1 and abs(dc) == 1:
        return ((dl, 0), (0, dc))
    return ()


def _valida_ponto(nome: str, ponto, forma, veto) -> tuple[int, int]:
    if not (isinstance(ponto, (tuple, list)) and len(ponto) == 2):
        raise ErroCorredor("ponto_invalido", f"{nome} tem de ser (linha, coluna)")
    li, co = int(ponto[0]), int(ponto[1])
    if not (0 <= li < forma[0] and 0 <= co < forma[1]):
        raise ErroCorredor("ponto_fora_da_grade", f"{nome} está fora da grade",
                           {"ponto": [li, co], "forma": list(forma)})
    if veto[li, co]:
        raise ErroCorredor("ponto_em_veto", f"{nome} está numa célula vetada: escolha outro ponto",
                           {"ponto": [li, co]})
    return li, co


def _piso(custo: np.ndarray, veto: np.ndarray) -> float:
    """Menor custo entre as células livres: é o que torna a heurística do A* admissível (nenhuma aresta pode
    custar menos que isso por célula percorrida)."""
    livres = custo[~veto]
    return float(np.min(livres)) if livres.size else 0.0


def _dijkstra(custo: np.ndarray, veto: np.ndarray, origem: tuple[int, int], vizinhanca: int,
              destino: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Distância de custo mínimo a partir de `origem` e o antecessor de cada célula.

    Com `destino`, vira A* com a heurística `piso × distância euclidiana` — ADMISSÍVEL e CONSISTENTE (nenhum
    caminho custa menos que o piso por célula), logo o caminho encontrado é o MESMO da busca sem heurística,
    só que visitando menos células. Sem `destino` (o caso do corredor, que precisa do campo inteiro), a
    heurística é zero e o algoritmo é Dijkstra puro."""
    lin, col = custo.shape
    dist = np.full(custo.shape, np.inf, dtype=np.float64)
    de = np.full(custo.shape, -1, dtype=np.int64)
    passos = _passos(vizinhanca)
    comprimentos = {p: math.hypot(p[0], p[1]) for p in passos}
    interiores = {p: _interiores(*p) for p in passos}
    ortogonais = {p: _ortogonais(*p) for p in passos}
    piso = _piso(custo, veto) if destino is not None else 0.0

    def h(i: int, j: int) -> float:
        if destino is None or piso <= 0.0:
            return 0.0
        return piso * math.hypot(i - destino[0], j - destino[1])

    dist[origem] = 0.0
    fila: list[tuple[float, int, int]] = [(h(*origem), origem[0], origem[1])]
    visitado = np.zeros(custo.shape, dtype=bool)
    while fila:
        _, i, j = heapq.heappop(fila)
        if visitado[i, j]:
            continue
        visitado[i, j] = True
        if destino is not None and (i, j) == destino:
            break
        d = dist[i, j]
        ci = custo[i, j]
        for p in passos:
            vi, vj = i + p[0], j + p[1]
            if not (0 <= vi < lin and 0 <= vj < col) or veto[vi, vj] or visitado[vi, vj]:
                continue
            atravessa = interiores[p]
            if atravessa:
                bloqueado = False
                soma_interna = 0.0
                for di, dj in atravessa:
                    mi, mj = i + di, j + dj
                    if not (0 <= mi < lin and 0 <= mj < col) or veto[mi, mj]:
                        bloqueado = True
                        break
                    soma_interna += float(custo[mi, mj])
                if bloqueado:
                    continue
                media = (float(ci) + float(custo[vi, vj]) + soma_interna) / (2.0 + len(atravessa))
            else:
                livres = ortogonais[p]
                if livres:
                    algum = False
                    for di, dj in livres:
                        mi, mj = i + di, j + dj
                        if 0 <= mi < lin and 0 <= mj < col and not veto[mi, mj]:
                            algum = True
                            break
                    if not algum:
                        continue
                media = (float(ci) + float(custo[vi, vj])) / 2.0
            novo = d + media * comprimentos[p]
            if novo < dist[vi, vj]:
                dist[vi, vj] = novo
                de[vi, vj] = i * col + j  # antecessor achatado: linha × colunas + coluna
                heapq.heappush(fila, (novo + h(vi, vj), vi, vj))
    return dist, de


def _meia_vizinhanca(vizinhanca: int) -> tuple[tuple[int, int], ...]:
    """Metade dos deslocamentos (um de cada par oposto). O peso da aresta e a regra de integridade são
    simétricos, logo montar meio grafo e resolver como NÃO DIRIGIDO dá o mesmo resultado com metade das
    arestas — é o que mantém a montagem dentro do teto de memória."""
    return tuple((dl, dc) for dl, dc in _passos(vizinhanca) if dl > 0 or (dl == 0 and dc > 0))


def _grafo_esparso(custo: np.ndarray, veto: np.ndarray, vizinhanca: int):
    """Grafo esparso das células livres, montado de uma vez por deslocamento — a MESMA regra da fila (salto de
    cavalo só com as células de dentro livres e entrando na média, diagonal com ao menos um ortogonal livre e
    fora da média, peso = média × comprimento), só que vetorizada. Devolve (grafo CSR não dirigido, índice da
    célula, máscara de livres).

    Custa memória: metade das arestas, índice de 32 bits e vetores pré-alocados de uma vez (nunca uma lista
    concatenada no fim, que dobraria o pico). É o motor `esparso`; quem tem pouca memória usa o motor `fila`."""
    from scipy.sparse import coo_matrix

    lin, col = custo.shape
    livre = ~veto
    n = int(livre.sum())
    if n > np.iinfo(np.int32).max:
        raise ErroCorredor("grade_grande_demais", "grade acima do que o motor esparso indexa; use motor=fila",
                           {"celulas_livres": n})
    indice = np.full(custo.shape, -1, dtype=np.int32)
    indice[livre] = np.arange(n, dtype=np.int32)
    passos = _meia_vizinhanca(vizinhanca)
    teto = n * len(passos)
    src = np.empty(teto, dtype=np.int32)
    dst = np.empty(teto, dtype=np.int32)
    peso = np.empty(teto, dtype=np.float32)
    fim = 0
    for dl, dc in passos:
        comprimento = math.hypot(dl, dc)
        l0, l1 = max(0, -dl), lin - max(0, dl)
        c0, c1 = max(0, -dc), col - max(0, dc)
        if l0 >= l1 or c0 >= c1:
            continue

        def janela(m: np.ndarray, ml: int = 0, mc: int = 0, _b=(l0, l1, c0, c1)):
            return m[_b[0] + ml:_b[1] + ml, _b[2] + mc:_b[3] + mc]

        a_, b_ = janela(indice), janela(indice, dl, dc)
        m = (a_ >= 0) & (b_ >= 0)
        interiores = _interiores(dl, dc)
        if interiores:
            soma = janela(custo).astype(np.float32) + janela(custo, dl, dc)
            for ml, mc in interiores:
                m &= janela(livre, ml, mc)
                soma += janela(custo, ml, mc)
            w = soma * (comprimento / (2 + len(interiores)))
        else:
            orto = _ortogonais(dl, dc)
            if orto:
                (o1l, o1c), (o2l, o2c) = orto
                m &= janela(livre, o1l, o1c) | janela(livre, o2l, o2c)
            w = (janela(custo).astype(np.float32) + janela(custo, dl, dc)) * (comprimento / 2)
        quantos = int(m.sum())
        src[fim:fim + quantos] = a_[m]
        dst[fim:fim + quantos] = b_[m]
        peso[fim:fim + quantos] = w[m]
        fim += quantos
    grafo = coo_matrix((peso[:fim], (src[:fim], dst[:fim])), shape=(n, n)).tocsr()
    return grafo, indice, livre


def _janela(forma, a, b, margem: int) -> tuple[int, int, int, int]:
    """Recorte retangular em volta das duas pontas, com `margem` células de folga.

    ATENÇÃO, e está no documento: a janela é uma ESCOLHA DECLARADA, não uma prova. O caminho ótimo DENTRO da
    janela pode ser mais caro que o ótimo da grade inteira, porque o desvio bom pode estar do lado de fora.
    Medido na superfície de referência: janela de 40 km devolve o mesmo traçado e o mesmo custo da grade
    inteira; janela de 10 km devolve traçado 9 % mais caro sem sequer encostar na borda (ou seja, encostar na
    borda não serve de aviso). Por isso o padrão é a grade inteira e a janela só entra quando alguém pede."""
    lin, col = forma
    l0 = max(0, min(a[0], b[0]) - margem)
    l1 = min(lin, max(a[0], b[0]) + margem + 1)
    c0 = max(0, min(a[1], b[1]) - margem)
    c1 = min(col, max(a[1], b[1]) + margem + 1)
    return l0, l1, c0, c1


def _refazer(indice: np.ndarray, livre: np.ndarray, antes: np.ndarray, s: int, t: int) -> np.ndarray:
    lins, cols = np.nonzero(livre)
    celulas = []
    atual = t
    while atual != s:
        celulas.append((int(lins[atual]), int(cols[atual])))
        atual = int(antes[atual])
        if atual < 0:
            raise ErroCorredor("sem_caminho", "o caminho se perdeu ao voltar do destino")
    celulas.append((int(lins[s]), int(cols[s])))
    celulas.reverse()
    return np.array(celulas, dtype=np.int64)


def _caminho_esparso(custo: np.ndarray, veto: np.ndarray, a, b, vizinhanca: int,
                     margem_celulas: int | None = None) -> dict:
    from scipy.sparse.csgraph import dijkstra as _sp_dijkstra

    if margem_celulas is None:
        l0, c0 = 0, 0
        recorte_custo, recorte_veto = custo, veto
    else:
        l0, l1, c0, c1 = _janela(custo.shape, a, b, int(margem_celulas))
        recorte_custo = np.ascontiguousarray(custo[l0:l1, c0:c1])
        recorte_veto = np.ascontiguousarray(veto[l0:l1, c0:c1])
    grafo, indice, livre = _grafo_esparso(recorte_custo, recorte_veto, vizinhanca)
    s = int(indice[a[0] - l0, a[1] - c0])
    t = int(indice[b[0] - l0, b[1] - c0])
    dist, antes = _sp_dijkstra(grafo, directed=False, indices=s, return_predecessors=True)
    if not np.isfinite(dist[t]):
        raise ErroCorredor("sem_caminho", "não há caminho livre de veto entre os dois pontos",
                           {"origem": list(a), "destino": list(b)})
    pontos = _refazer(indice, livre, antes, s, t) + np.array([l0, c0], dtype=np.int64)
    passos = np.hypot(*np.diff(pontos.astype(float), axis=0).T)
    return {"celulas": pontos, "custo": float(dist[t]), "celulas_percorridas": int(pontos.shape[0]),
            "comprimento_celulas": float(passos.sum()), "motor": "esparso",
            "janela_celulas": margem_celulas}


def caminho(custo: np.ndarray, veto: np.ndarray, origem, destino, vizinhanca: int = 16,
            motor: str = "esparso", margem_celulas: int | None = None) -> dict:
    """Caminho de custo mínimo entre dois pontos da grade. Devolve as células, o custo e o comprimento.

    `motor="esparso"` monta o grafo de uma vez e resolve com scipy: é o padrão, gasta memória e devolve o ótimo
    da grade inteira. `motor="fila"` é A* em heap, gasta pouca memória e é muito mais lento em grade grande.
    Os dois obedecem à mesma regra de aresta e dão o mesmo custo (conferido no teste).
    `margem_celulas` recorta a busca em volta das pontas: acelera e NÃO garante o ótimo (ver `_janela`)."""
    if vizinhanca not in VIZINHANCAS:
        raise ErroCorredor("vizinhanca_invalida", f"a vizinhança é uma de {VIZINHANCAS}",
                           {"pedido": vizinhanca})
    if custo.shape != veto.shape:
        raise ErroCorredor("formas_diferentes", "custo e veto têm formas diferentes")
    if motor not in ("fila", "esparso"):
        raise ErroCorredor("motor_invalido", "o motor é `fila` (pouca memória) ou `esparso` (rápido)",
                           {"pedido": motor})
    a = _valida_ponto("origem", origem, custo.shape, veto)
    b = _valida_ponto("destino", destino, custo.shape, veto)
    if motor == "esparso":
        return _caminho_esparso(custo, veto, a, b, vizinhanca, margem_celulas)
    if margem_celulas is not None:
        raise ErroCorredor("janela_sem_motor", "a janela (`margem_celulas`) é do motor esparso")
    dist, de = _dijkstra(custo, veto, a, vizinhanca, destino=b)
    if not np.isfinite(dist[b]):
        raise ErroCorredor("sem_caminho", "não há caminho livre de veto entre os dois pontos",
                           {"origem": list(a), "destino": list(b)})
    col = custo.shape[1]
    celulas = [b]
    atual = b
    while atual != a:
        plano = int(de[atual])
        if plano < 0:
            raise ErroCorredor("sem_caminho", "o caminho se perdeu ao voltar do destino")
        atual = (plano // col, plano % col)
        celulas.append(atual)
    celulas.reverse()
    pontos = np.array(celulas, dtype=np.int64)
    passos_km = np.hypot(*np.diff(pontos.astype(float), axis=0).T)
    return {"celulas": pontos, "custo": float(dist[b]), "celulas_percorridas": int(pontos.shape[0]),
            "comprimento_celulas": float(passos_km.sum()), "motor": "fila", "janela_celulas": None}


def corredor(custo: np.ndarray, veto: np.ndarray, origem, destino, epsilon: float = 0.05,
             vizinhanca: int = 16, motor: str = "esparso") -> dict:
    """Corredor-epsilon: células por onde passa algum caminho de custo até `(1+ε)` do ótimo.

    Precisa dos DOIS campos de distância inteiros (de A e de B), logo nunca aceita janela: recortar a grade
    cortaria justamente as alternativas que o corredor existe para mostrar. No motor esparso o grafo é montado
    uma vez só e as duas distâncias saem da mesma chamada."""
    if not (0.0 <= epsilon <= 1.0):
        raise ErroCorredor("epsilon_fora_do_limite", "o epsilon do corredor vai de 0 a 1",
                           {"pedido": epsilon})
    a = _valida_ponto("origem", origem, custo.shape, veto)
    b = _valida_ponto("destino", destino, custo.shape, veto)
    if motor not in ("fila", "esparso"):
        raise ErroCorredor("motor_invalido", "o motor é `fila` (pouca memória) ou `esparso` (rápido)",
                           {"pedido": motor})
    if motor == "esparso":
        from scipy.sparse.csgraph import dijkstra as _sp_dijkstra

        grafo, indice, livre = _grafo_esparso(custo, veto, vizinhanca)
        campos = _sp_dijkstra(grafo, directed=False, indices=[int(indice[a]), int(indice[b])])
        ida = np.full(custo.shape, np.inf)
        volta = np.full(custo.shape, np.inf)
        ida[livre] = campos[0]
        volta[livre] = campos[1]
    else:
        ida, _ = _dijkstra(custo, veto, a, vizinhanca)
        volta, _ = _dijkstra(custo, veto, b, vizinhanca)
    otimo = float(ida[b])
    if not np.isfinite(otimo):
        raise ErroCorredor("sem_caminho", "não há caminho livre de veto entre os dois pontos")
    total = ida + volta
    dentro = np.isfinite(total) & (total <= otimo * (1.0 + epsilon)) & ~veto
    return {"mascara": dentro, "celulas": int(np.count_nonzero(dentro)), "otimo": otimo,
            "teto": otimo * (1.0 + epsilon), "epsilon": epsilon, "motor": motor}


# ---------------------------------------------------------------- métricas
def sinuosidade(celulas: np.ndarray) -> float:
    """Comprimento do caminho ÷ distância em linha reta entre as pontas. 1,0 = reta."""
    pontos = np.asarray(celulas, dtype=float)
    if pontos.shape[0] < 2:
        return 1.0
    comprimento = float(np.hypot(*np.diff(pontos, axis=0).T).sum())
    reta = float(math.dist(pontos[0], pontos[-1]))
    return comprimento / reta if reta > 0 else float("inf")


def metricas(celulas: np.ndarray, custo: np.ndarray, resolucao_m: float,
             camadas: list[Camada] | None = None) -> dict:
    """Comprimento, custo, sinuosidade e quilômetros dentro de cada camada declarada, no EIXO."""
    pontos = np.asarray(celulas, dtype=np.int64)
    passos = np.hypot(*np.diff(pontos.astype(float), axis=0).T)
    comprimento_m = float(passos.sum() * resolucao_m)
    linhas, colunas = pontos[:, 0], pontos[:, 1]
    saida = {
        "comprimento_km": round(comprimento_m / 1000.0, 3),
        "celulas": int(pontos.shape[0]),
        "sinuosidade": round(sinuosidade(pontos), 4),
        "custo_medio_no_eixo": round(float(np.mean(custo[linhas, colunas])), 4),
        "resolucao_m": resolucao_m,
        "km_por_camada": {},
    }
    for c in camadas or []:
        dentro = c.mascara[linhas[:-1], colunas[:-1]] if pontos.shape[0] > 1 else c.mascara[linhas, colunas]
        km = float(np.sum(passos[dentro]) * resolucao_m / 1000.0) if pontos.shape[0] > 1 else 0.0
        saida["km_por_camada"][c.id] = round(km, 3)
    return saida


__all__ = ["CUSTO_VETO", "CURVA_RELEVO_PADRAO", "Camada", "ErroCorredor", "MIN_ATRACAO_PADRAO", "Superficie",
           "VIZINHANCAS", "caminho", "compor", "comprimir_amplitude", "corredor", "curva_relevo", "metricas",
           "sinuosidade"]

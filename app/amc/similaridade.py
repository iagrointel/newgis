"""Localização semelhante (item L3-17-similaridade, linha L3 motor AMC) — equivalente a "Find Similar
Locations" / "Similarity Search": dadas 1-N unidades de REFERÊNCIA (que "deram certo"), ranqueia as demais
unidades por parecença com elas, sobre um conjunto de fatores padronizados por z-score.

Este módulo é PURO (sem banco, sem FastAPI): recebe a matriz fator×unidade já pronta — de onde ela vier (uma
execução do motor AMC de L3-01, um upload, uma tabela qualquer) — e devolve o ranking. `app/amc/rotas_similaridade.py`
expõe isto como serviço HTTP sem estado (mesmo padrão de `app/rede/rotas.py`: sem tabela `plat.*` própria, porque
o item não guarda nada, só calcula sobre o que o pedido trouxe).

## O cálculo, passo a passo

1. **Padronização (z-score)**: para cada fator escolhido, média e desvio-padrão POPULACIONAL (ddof=0) são
   calculados só sobre as unidades que TÊM valor não nulo naquele fator. `z = (valor - média) / desvio`. Fator
   com desvio zero (todas as unidades com o mesmo valor) não discrimina nada: por convenção o z desse fator é
   0,0 para toda unidade que tenha valor (o eixo fica "desligado" da comparação, nunca vira divisão por zero).
2. **Unidade incompleta**: unidade sem valor em algum dos fatores escolhidos SAI do ranking (nunca entra com
   z=0 no lugar do dado que falta — a mesma regra de "NULL é sem dado, nunca 0" do resto do motor AMC) e
   aparece à parte, em `excluidas`, com o motivo.
3. **Vetor de referência**: centroide (média aritmética, fator a fator) dos vetores padronizados das unidades
   de referência. Com uma referência só, o centroide é o próprio vetor dela.
4. **Similaridade**: cosseno (ângulo entre o vetor da unidade e o centroide de referência — American Community
   Survey/Esri usam o mesmo princípio) ou distância euclidiana no espaço padronizado.
   - cosseno: `indice = (cos + 1) / 2`, o que leva o intervalo [-1, 1] para [0, 1] sem mudar a ORDEM — cos=1
     (mesma direção e sentido) vira índice 1,0; cos=-1 (direção oposta) vira índice 0,0.
   - euclidiana: `indice = 1 / (1 + distância)`, distância 0 (unidades idênticas no espaço padronizado) vira
     índice 1,0 e cai assintoticamente para 0 conforme a distância cresce.
   Os dois casos dão exatamente **1,0** quando o vetor da unidade é idêntico ao centroide de referência — é
   a base da refutação do item: candidato = referência tem de sair com índice 1 e em 1º lugar.

   ⚠ Com **um único campo** escolhido, o cosseno degenera: em 1 dimensão `cos(a,b)` só enxerga o SINAL dos dois
   valores (vira +1 se são do mesmo lado da média, -1 se são de lados opostos), nunca a magnitude — toda unidade
   do mesmo lado da referência empata em índice 1,0 com ela. É matemática, não bug (cosseno mede ÂNGULO; em 1-D
   só existem dois ângulos possíveis). Por isso o desempate abaixo é por DISTÂNCIA, não só por id.
5. **Ranking**: ordena por índice decrescente; empata por distância euclidiana padronizada crescente (que
   distingue magnitude mesmo quando o cosseno de 1 campo não distingue) e, por fim, por `unidade_id` crescente
   (determinístico). É esse desempate que garante a refutação do item mesmo no caso degenerado de 1 campo com
   cosseno: a própria referência tem distância zero a si mesma, então nunca perde o 1º lugar por empate.
   A(s) própria(s) unidade(s) de referência entram no ranking como qualquer outra (não são removidas)."""

import math
from dataclasses import dataclass, field

METRICAS = ("cosseno", "euclidiana")


class ErroSimilaridade(Exception):
    """Falha de entrada (fatores/unidades/referências incoerentes). `codigo` é o mesmo texto usado no `erro`
    HTTP de `rotas_similaridade.py`; este módulo não conhece FastAPI, então não levanta ErroAPI diretamente."""

    def __init__(self, codigo: str, mensagem: str, detalhe: dict | None = None):
        super().__init__(mensagem)
        self.codigo, self.mensagem, self.detalhe = codigo, mensagem, detalhe or {}


@dataclass
class ResultadoSimilaridade:
    campos: list[str]
    metrica: str
    referencias: list[str]
    ranking: list[dict] = field(default_factory=list)   # [{unidade_id, indice_similaridade, posicao}]
    excluidas: list[dict] = field(default_factory=list)  # [{unidade_id, motivo}]
    estatisticas: dict[str, dict] = field(default_factory=dict)  # {campo: {media, desvio}}


def _numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _campos_da_matriz(unidades: dict[str, dict]) -> list[str]:
    vistos: dict[str, None] = {}
    for valores in unidades.values():
        for campo in valores:
            vistos.setdefault(campo, None)
    return sorted(vistos)


def _estatisticas(unidades: dict[str, dict], campos: list[str]) -> dict[str, tuple[float, float]]:
    """{campo: (média, desvio populacional)} calculados só sobre valores não nulos."""
    saida = {}
    for campo in campos:
        valores = [v[campo] for v in unidades.values() if _numero(v.get(campo))]
        if not valores:
            saida[campo] = (None, None)
            continue
        media = sum(valores) / len(valores)
        variancia = sum((x - media) ** 2 for x in valores) / len(valores)
        saida[campo] = (media, math.sqrt(variancia))
    return saida


def padronizar(unidades: dict[str, dict], campos: list[str]) -> tuple[dict[str, list[float]], list[str], dict]:
    """Devolve (vetores completos, ids excluídos por dado incompleto, estatísticas por campo). Um vetor só
    entra em `vetores` se cada um dos campos pedidos tiver valor numérico naquela unidade."""
    stats = _estatisticas(unidades, campos)
    for campo, (media, _) in stats.items():
        if media is None:
            raise ErroSimilaridade("fator_sem_dado", f"nenhuma unidade tem valor para o campo '{campo}'",
                                    {"campo": campo})
    vetores: dict[str, list[float]] = {}
    excluidas: list[str] = []
    for uid, valores in unidades.items():
        vetor = []
        completo = True
        for campo in campos:
            v = valores.get(campo)
            if not _numero(v):
                completo = False
                break
            media, desvio = stats[campo]
            vetor.append(0.0 if desvio == 0 else (v - media) / desvio)
        if completo:
            vetores[uid] = vetor
        else:
            excluidas.append(uid)
    return vetores, excluidas, stats


def _centroide(vetores: list[list[float]]) -> list[float]:
    n = len(vetores)
    return [sum(v[i] for v in vetores) / n for i in range(len(vetores[0]))]


def _norma(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _indice_cosseno(v: list[float], ref: list[float]) -> float:
    nv, nr = _norma(v), _norma(ref)
    if nv == 0.0 and nr == 0.0:
        cos = 1.0   # os dois são o vetor nulo (todo fator com desvio zero ou empatado na média): idênticos
    elif nv == 0.0 or nr == 0.0:
        cos = 0.0   # um é nulo e o outro não: sem direção comum, meio do caminho (nem parecido nem oposto)
    else:
        cos = sum(a * b for a, b in zip(v, ref, strict=True)) / (nv * nr)
        cos = max(-1.0, min(1.0, cos))  # ponto flutuante pode passar 1 por 1e-16; nunca sai do domínio do cosseno
    return (cos + 1.0) / 2.0


def _distancia(v: list[float], ref: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v, ref, strict=True)))


def _indice_euclidiana(v: list[float], ref: list[float]) -> float:
    return 1.0 / (1.0 + _distancia(v, ref))


def calcular(unidades: dict[str, dict], referencias: list[str], campos: list[str] | None = None,
             metrica: str = "cosseno") -> ResultadoSimilaridade:
    """`unidades`: {unidade_id: {campo: valor|None}}. `referencias`: 1-N ids que precisam estar em `unidades`.
    `campos`: subconjunto de fatores a usar (escolha de campos); default = união de todos os campos vistos.
    `metrica`: 'cosseno' (default) ou 'euclidiana'."""
    if not unidades:
        raise ErroSimilaridade("sem_unidades", "nenhuma unidade foi informada")
    if not referencias:
        raise ErroSimilaridade("sem_referencia", "é preciso ao menos uma unidade de referência")
    desconhecidas = [r for r in referencias if r not in unidades]
    if desconhecidas:
        raise ErroSimilaridade("referencia_desconhecida", f"referência(s) fora da matriz: {', '.join(desconhecidas)}",
                                {"desconhecidas": desconhecidas})
    if metrica not in METRICAS:
        raise ErroSimilaridade("metrica_invalida", f"métrica '{metrica}' não é uma das aceitas: {METRICAS}",
                                {"aceitas": list(METRICAS)})
    campos_usados = list(dict.fromkeys(campos)) if campos else _campos_da_matriz(unidades)
    if not campos_usados:
        raise ErroSimilaridade("sem_campos", "nenhum campo (fator) para comparar")

    vetores, excluidas_ids, stats = padronizar(unidades, campos_usados)
    faltando_ref = [r for r in referencias if r not in vetores]
    if faltando_ref:
        raise ErroSimilaridade("referencia_incompleta",
                                f"referência(s) sem valor em algum campo escolhido: {', '.join(faltando_ref)}",
                                {"incompletas": faltando_ref, "campos": campos_usados})

    centroide = _centroide([vetores[r] for r in referencias])
    calculo = _indice_cosseno if metrica == "cosseno" else _indice_euclidiana
    linhas = [
        {
            "unidade_id": uid,
            "indice_similaridade": calculo(v, centroide),
            "_distancia": _distancia(v, centroide),  # só para desempate; removido antes de devolver
        }
        for uid, v in vetores.items()
    ]
    # desempate por distância (não só por id): resolve o caso degenerado do cosseno com 1 campo, em que duas
    # unidades do mesmo lado da referência empatam em índice mas não são igualmente parecidas (ver docstring)
    linhas.sort(key=lambda linha: (-linha["indice_similaridade"], linha["_distancia"], linha["unidade_id"]))
    for posicao, linha in enumerate(linhas, start=1):
        linha["posicao"] = posicao
        del linha["_distancia"]

    excluidas = [{"unidade_id": uid, "motivo": "dado_incompleto"} for uid in sorted(excluidas_ids)]
    estatisticas = {c: {"media": m, "desvio": d} for c, (m, d) in stats.items()}
    return ResultadoSimilaridade(campos=campos_usados, metrica=metrica, referencias=list(referencias),
                                  ranking=linhas, excluidas=excluidas, estatisticas=estatisticas)


# ---------------------------------------------------------------- export (item L3-17, cláusula "export")
CAMPOS_CSV = ("posicao", "unidade_id", "indice_similaridade")


def exportar_csv(resultado: ResultadoSimilaridade) -> str:
    """CSV determinístico (vírgula, cabeçalho fixo, CRLF — RFC 4180) do ranking, na ordem de posição. Não
    inclui as excluídas (elas não têm posição nem índice): quem consome o CSV lê só quem entrou na comparação."""
    linhas = [",".join(CAMPOS_CSV)]
    for linha in resultado.ranking:
        linhas.append(f"{linha['posicao']},{linha['unidade_id']},{linha['indice_similaridade']:.10f}")
    return "\r\n".join(linhas) + "\r\n"


def exportar_geojson(resultado: ResultadoSimilaridade, geometrias: dict[str, dict] | None = None) -> dict:
    """FeatureCollection do ranking. `geometrias`: {unidade_id: geometria GeoJSON} opcional — quem não tiver
    geometria conhecida (mapa não é obrigatório para o item; o ranking em si já é o produto) sai com geometry
    null, nunca inventada."""
    geometrias = geometrias or {}
    feicoes = [
        {
            "type": "Feature",
            "geometry": geometrias.get(linha["unidade_id"]),
            "properties": {
                "unidade_id": linha["unidade_id"],
                "posicao": linha["posicao"],
                "indice_similaridade": linha["indice_similaridade"],
                "referencia": linha["unidade_id"] in resultado.referencias,
            },
        }
        for linha in resultado.ranking
    ]
    return {"type": "FeatureCollection", "features": feicoes}

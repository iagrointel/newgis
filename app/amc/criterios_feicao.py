"""Critérios sobre a PRÓPRIA FEIÇÃO (item L3-06-criterios-de-feicao).

Quando a unidade de análise não é a célula de uma grade, e sim uma feição do usuário (um imóvel, uma
loja, um lote), o critério deixa de ser "o que a grade mediu aqui" e passa a ser uma pergunta feita à
feição. Este módulo implementa as quatro perguntas do molde de análise de adequação:

- `atributo`                 — um atributo numérico que a própria feição carrega (área, faturamento, vagas);
- `contagem_raio`            — quantos pontos de outra camada existem a até `raio_m` da feição;
- `contagem_dentro`          — quantos pontos de outra camada caem dentro da feição (feição de área);
- `distancia_mais_proxima`   — distância, em metros, ao ponto mais próximo de outra camada.

Sobre cada valor bruto o usuário declara a INFLUÊNCIA, que é o sentido da preferência dele:

- `positiva`  — quanto maior, melhor (rampa crescente de `minimo` a `maximo`);
- `inversa`   — quanto menor, melhor (a mesma rampa, decrescente);
- `ideal`     — existe um `alvo`: nota máxima nele, caindo simetricamente para os dois lados.

⚠ `ideal` é SIMÉTRICO por definição: a queda usa um `alcance` único para os dois lados. Quando o alvo
não está no meio de [`minimo`, `maximo`], o alcance adotado é o do lado MAIS LONGO, então a nota chega a
zero no extremo mais distante e fica acima de zero no extremo mais próximo. Quem quer zero nas duas
pontas declara um alvo centrado (ou um `alcance` explícito). A escolha está gravada na ficha do critério,
nunca escondida.

FILTRO DE INCLUSÃO (`faixa_inclusao`) não é veto. A feição cujo valor bruto cai fora da faixa sai da
comparação com o estado `filtrada` e sem posição no ranque — ela não é reprovada, ela não foi perguntada.
Veto (decisão A6 do motor) continua sendo outra coisa: zera a nota de quem PERMANECE na comparação.
Valor ausente (`None`) nunca filtra: falta de dado não é "fora da faixa".

Reuso, não motor novo: a transformação valor → favorabilidade 0-100 é `app.amc.transformacoes` (a
influência vira um dicionário de transformação declarado, `linear` ou `linear_simetrica`); a nota final
é `app.amc.combinacao.combinar` (soma ponderada normalizada, aviso de pesos incluído); a medição sobre
a camada de pontos é `app.amc.vetorial` (o mesmo extrator que a grade usa). Este módulo só monta.

O módulo é PURO: sem banco, sem arquivo, sem relógio. Quem lê feição e camada do catálogo é a rota.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field

import numpy as np

from app import limites
from app.amc import combinacao as mod_combinacao
from app.amc import transformacoes as mod_transformacoes
from app.amc import vetorial as mod_vetorial

TIPOS = ("atributo", "contagem_raio", "contagem_dentro", "distancia_mais_proxima")
INFLUENCIAS = ("positiva", "inversa", "ideal")
EXTRATOR_POR_TIPO = {
    "contagem_raio": "vetor_contagem_raio",
    "contagem_dentro": "vetor_contagem",
    "distancia_mais_proxima": "vetor_distancia_mais_proxima",
}
ESTADO_INCLUIDA = "incluida"
ESTADO_FILTRADA = "filtrada"
BINS_HISTOGRAMA = 20


class ErroCriterio(ValueError):
    """Erro de contrato dos critérios de feição. `codigo` é curto e estável; `mensagem` é a frase em português."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# ------------------------------------------------------------------------------------ validação
def _numero(valor, codigo: str, mensagem: str, detalhe=None) -> float:
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(float(valor)):
        raise ErroCriterio(codigo, mensagem, detalhe)
    return float(valor)


def validar_criterio(criterio: dict) -> dict:
    """Confere um critério e devolve a ficha normalizada (sem tocar nos dados)."""
    if not isinstance(criterio, dict):
        raise ErroCriterio("criterio_invalido", "cada critério é um objeto JSON", {"recebido": type(criterio).__name__})
    cid = criterio.get("id")
    if not isinstance(cid, str) or not cid.strip():
        raise ErroCriterio("criterio_sem_id", "todo critério precisa de um 'id' de texto não vazio")
    tipo = criterio.get("tipo")
    if tipo not in TIPOS:
        raise ErroCriterio("tipo_desconhecido", f"tipo de critério desconhecido: {tipo!r}", {"aceitos": list(TIPOS)})
    influencia = criterio.get("influencia")
    if influencia not in INFLUENCIAS:
        raise ErroCriterio("influencia_desconhecida", f"influência desconhecida: {influencia!r}",
                           {"aceitas": list(INFLUENCIAS)})
    peso = criterio.get("peso", 1.0)
    peso = _numero(peso, "peso_invalido", f"o peso do critério {cid!r} tem de ser um número finito ≥ 0")
    if peso < 0:
        raise ErroCriterio("peso_invalido", f"o peso do critério {cid!r} tem de ser ≥ 0")

    if tipo == "atributo" and not criterio.get("campo"):
        raise ErroCriterio("campo_ausente", f"o critério {cid!r} é de atributo e exige 'campo'")
    if tipo != "atributo" and not criterio.get("camada"):
        raise ErroCriterio("camada_ausente", f"o critério {cid!r} ({tipo}) exige 'camada' (a outra camada, de pontos)")
    if tipo == "contagem_raio":
        raio = _numero(criterio.get("raio_m"), "raio_invalido",
                       f"o critério {cid!r} exige 'raio_m' numérico e finito")
        if raio <= 0:
            raise ErroCriterio("raio_invalido", f"o critério {cid!r} exige 'raio_m' maior que zero; "
                                                f"raio zero não mede nada", {"raio_m": raio})
        if raio > limites.AMC_CRITERIO_RAIO_M_MAX:
            raise ErroCriterio("raio_acima_do_teto",
                               f"o raio {raio:.0f} m passa do teto de {limites.AMC_CRITERIO_RAIO_M_MAX:.0f} m; "
                               f"acima disso a medição em uma única zona UTM deixa de valer",
                               {"raio_m": raio, "teto_m": limites.AMC_CRITERIO_RAIO_M_MAX})
    faixa = criterio.get("faixa_inclusao")
    if faixa is not None:
        if not isinstance(faixa, dict) or (faixa.get("minimo") is None and faixa.get("maximo") is None):
            raise ErroCriterio("faixa_invalida",
                               f"'faixa_inclusao' do critério {cid!r} precisa de ao menos um limite (minimo/maximo)")
        fmin = None if faixa.get("minimo") is None else _numero(
            faixa["minimo"], "faixa_invalida", f"o mínimo da faixa do critério {cid!r} não é número finito")
        fmax = None if faixa.get("maximo") is None else _numero(
            faixa["maximo"], "faixa_invalida", f"o máximo da faixa do critério {cid!r} não é número finito")
        if fmin is not None and fmax is not None and fmin > fmax:
            raise ErroCriterio("faixa_invertida",
                               f"a faixa do critério {cid!r} tem mínimo maior que o máximo", {"minimo": fmin,
                                                                                              "maximo": fmax})
    return {"id": cid, "tipo": tipo, "influencia": influencia, "peso": peso,
            "campo": criterio.get("campo"), "camada": criterio.get("camada"),
            "raio_m": criterio.get("raio_m"), "alvo": criterio.get("alvo"), "alcance": criterio.get("alcance"),
            "minimo": criterio.get("minimo"), "maximo": criterio.get("maximo"),
            "faixa_inclusao": criterio.get("faixa_inclusao")}


def validar_criterios(criterios) -> list[dict]:
    if not isinstance(criterios, list) or not criterios:
        raise ErroCriterio("sem_criterio", "é preciso ao menos um critério")
    if len(criterios) > limites.AMC_CRITERIOS_POR_AVALIACAO:
        raise ErroCriterio("criterios_demais",
                           f"no máximo {limites.AMC_CRITERIOS_POR_AVALIACAO} critérios por avaliação",
                           {"recebidos": len(criterios)})
    fichas = [validar_criterio(c) for c in criterios]
    vistos: set[str] = set()
    for f in fichas:
        if f["id"] in vistos:
            raise ErroCriterio("id_repetido", f"o id de critério {f['id']!r} aparece duas vezes")
        vistos.add(f["id"])
    return fichas


# ------------------------------------------------------------------------------------ valor bruto
def _geometria(feicao, indice: int):
    geom = feicao.get("geometry") if isinstance(feicao, dict) else None
    if not geom or not isinstance(geom, dict) or not geom.get("type") or geom.get("coordinates") in (None, []):
        raise ErroCriterio("feicao_sem_geometria",
                           f"a feição {_id_feicao(feicao, indice)!r} não tem geometria; sem geometria não há "
                           f"distância, raio nem contenção a medir", {"indice": indice})
    return geom


def _id_feicao(feicao, indice: int) -> str:
    if isinstance(feicao, dict):
        for chave in ("id", "ID"):
            if feicao.get(chave) not in (None, ""):
                return str(feicao[chave])
        props = feicao.get("properties") or {}
        if isinstance(props, dict) and props.get("id") not in (None, ""):
            return str(props["id"])
    return f"#{indice}"


def _atributo(feicoes, campo: str) -> list[float | None]:
    saida: list[float | None] = []
    for i, f in enumerate(feicoes):
        props = (f.get("properties") or {}) if isinstance(f, dict) else {}
        if campo not in props:
            saida.append(None)
            continue
        v = props[campo]
        if v is None or v == "":
            saida.append(None)
            continue
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise ErroCriterio("atributo_nao_numerico",
                               f"o campo {campo!r} da feição {_id_feicao(f, i)!r} vale {v!r}, que não é número; "
                               f"critério de atributo numérico não converte texto em silêncio",
                               {"campo": campo, "valor": str(v)[:120], "indice": i})
        if not math.isfinite(float(v)):
            raise ErroCriterio("atributo_nao_finito",
                               f"o campo {campo!r} da feição {_id_feicao(f, i)!r} não é finito",
                               {"campo": campo, "indice": i})
        saida.append(float(v))
    return saida


def valores_brutos(feicoes, ficha: dict, srid_trabalho: int, camadas: dict | None = None) -> list[float | None]:
    """Valor bruto de UM critério para cada feição, na ordem de entrada."""
    if ficha["tipo"] == "atributo":
        return _atributo(feicoes, ficha["campo"])
    camadas = camadas or {}
    nome = ficha["camada"]
    if nome not in camadas:
        raise ErroCriterio("camada_nao_fornecida",
                           f"o critério {ficha['id']!r} pede a camada {nome!r}, que não foi fornecida",
                           {"camada": nome, "fornecidas": sorted(camadas)})
    pares_unidade = [(_id_feicao(f, i), _geometria(f, i)) for i, f in enumerate(feicoes)]
    pares_camada = [(_id_feicao(f, i), _geometria(f, i), (f.get("properties") or {}))
                    for i, f in enumerate(camadas[nome])]
    parametros = {"raio_m": ficha["raio_m"]} if ficha["tipo"] == "contagem_raio" else {}
    saida = mod_vetorial.extrair(pares_unidade, pares_camada, EXTRATOR_POR_TIPO[ficha["tipo"]],
                                 srid_trabalho, parametros)
    return [saida[uid]["valor"] for uid, _ in pares_unidade]


# ------------------------------------------------------------------------------------ influência
def transformacao_da_influencia(ficha: dict, valores) -> dict:
    """Traduz a influência declarada em uma transformação de `app.amc.transformacoes`, resolvendo os limites
    que o usuário não declarou a partir dos valores observados (e dizendo, na ficha, que foram derivados)."""
    limpos = [float(v) for v in valores if v is not None and not (isinstance(v, float) and math.isnan(v))]
    minimo, maximo = ficha.get("minimo"), ficha.get("maximo")
    derivados = []
    if minimo is None:
        if not limpos:
            raise ErroCriterio("sem_dado_para_derivar",
                               f"o critério {ficha['id']!r} não declarou 'minimo' e nenhuma feição tem valor: "
                               f"não há de onde derivar a escala")
        minimo = min(limpos)
        derivados.append("minimo")
    if maximo is None:
        if not limpos:
            raise ErroCriterio("sem_dado_para_derivar",
                               f"o critério {ficha['id']!r} não declarou 'maximo' e nenhuma feição tem valor: "
                               f"não há de onde derivar a escala")
        maximo = max(limpos)
        derivados.append("maximo")
    minimo = _numero(minimo, "limite_invalido", f"'minimo' do critério {ficha['id']!r} não é número finito")
    maximo = _numero(maximo, "limite_invalido", f"'maximo' do critério {ficha['id']!r} não é número finito")
    if maximo < minimo:
        raise ErroCriterio("limites_invertidos", f"no critério {ficha['id']!r} o máximo é menor que o mínimo",
                           {"minimo": minimo, "maximo": maximo})

    if ficha["influencia"] in ("positiva", "inversa"):
        t = {"tipo": "linear", "minimo": minimo, "maximo": maximo,
             "direcao": "crescente" if ficha["influencia"] == "positiva" else "decrescente"}
        return {"transformacao": t, "limites_derivados": derivados}

    alvo = ficha.get("alvo")
    if alvo is None:
        raise ErroCriterio("alvo_ausente", f"o critério {ficha['id']!r} tem influência 'ideal' e exige 'alvo'")
    alvo = _numero(alvo, "alvo_invalido", f"o 'alvo' do critério {ficha['id']!r} não é número finito")
    alcance = ficha.get("alcance")
    if alcance is None:
        alcance = max(alvo - minimo, maximo - alvo)
        derivados.append("alcance")
    alcance = _numero(alcance, "alcance_invalido", f"o 'alcance' do critério {ficha['id']!r} não é número finito")
    if alcance <= 0:
        raise ErroCriterio("alcance_invalido",
                           f"o 'alcance' do critério {ficha['id']!r} tem de ser maior que zero",
                           {"alcance": alcance})
    t = {"tipo": "linear_simetrica", "minimo": alvo - alcance, "maximo": alvo + alcance, "abaixo": 0.0, "acima": 0.0}
    return {"transformacao": t, "limites_derivados": derivados,
            "nota": "queda simétrica: alcance único para os dois lados do alvo"}


# ------------------------------------------------------------------------------------ resultado
@dataclass
class Avaliacao:
    ids: list
    fichas: list
    brutos: np.ndarray            # feição × critério, nan onde falta dado
    favorabilidades: np.ndarray   # feição × critério, escala 0-100, nan onde falta dado
    notas: np.ndarray             # nan em feição filtrada ou sem nenhum critério com dado
    estado: list
    motivo_filtro: list
    posicao: list
    histogramas: list
    correlacao: dict
    aviso_pesos: str
    combinador: str
    avisos: list = field(default_factory=list)

    def como_dicionario(self) -> dict:
        linhas = []
        for i, fid in enumerate(self.ids):
            linhas.append({
                "id": fid,
                "estado": self.estado[i],
                "motivo_filtro": self.motivo_filtro[i],
                "posicao": self.posicao[i],
                "nota": None if not np.isfinite(self.notas[i]) else round(float(self.notas[i]), 4),
                "valores": {f["id"]: (None if not np.isfinite(self.brutos[i, j]) else float(self.brutos[i, j]))
                            for j, f in enumerate(self.fichas)},
                "favorabilidades": {
                    f["id"]: (None if not np.isfinite(self.favorabilidades[i, j])
                              else round(float(self.favorabilidades[i, j]), 4))
                    for j, f in enumerate(self.fichas)},
            })
        return {
            "aviso_pesos": self.aviso_pesos,
            "combinador": self.combinador,
            "criterios": self.fichas,
            "n_feicoes": len(self.ids),
            "n_incluidas": sum(1 for e in self.estado if e == ESTADO_INCLUIDA),
            "n_filtradas": sum(1 for e in self.estado if e == ESTADO_FILTRADA),
            "histogramas": self.histogramas,
            "correlacao": self.correlacao,
            "avisos": list(self.avisos),
            "linhas": linhas,
        }

    def csv(self) -> str:
        """Uma linha por feição, na ordem do ranque (filtradas no fim). Colunas: id, estado, motivo do filtro,
        posição, nota e, por critério, o valor bruto e a favorabilidade."""
        buf = io.StringIO()
        escritor = csv.writer(buf, lineterminator="\n")
        cabecalho = ["id", "estado", "motivo_filtro", "posicao", "nota"]
        for f in self.fichas:
            cabecalho += [f"{f['id']}_valor", f"{f['id']}_favorabilidade"]
        escritor.writerow(cabecalho)
        ordem = sorted(range(len(self.ids)),
                       key=lambda i: (self.posicao[i] is None, self.posicao[i] or 0, str(self.ids[i])))
        for i in ordem:
            linha = [self.ids[i], self.estado[i], self.motivo_filtro[i] or "",
                     "" if self.posicao[i] is None else self.posicao[i],
                     "" if not np.isfinite(self.notas[i]) else f"{float(self.notas[i]):.4f}"]
            for j in range(len(self.fichas)):
                bruto, fav = self.brutos[i, j], self.favorabilidades[i, j]
                linha += ["" if not np.isfinite(bruto) else f"{float(bruto):.6g}",
                          "" if not np.isfinite(fav) else f"{float(fav):.4f}"]
            escritor.writerow(linha)
        return buf.getvalue()


def _histograma(valores: np.ndarray, ficha: dict) -> dict:
    limpos = valores[np.isfinite(valores)]
    if limpos.size:
        contagens, bordas = np.histogram(limpos, bins=BINS_HISTOGRAMA)
        return {"criterio": ficha["id"], "contagens": contagens.tolist(), "bordas": bordas.tolist(),
                "n": int(limpos.size), "n_sem_dado": int(valores.size - limpos.size)}
    return {"criterio": ficha["id"], "contagens": [], "bordas": [], "n": 0, "n_sem_dado": int(valores.size)}


def matriz_correlacao(matriz: np.ndarray, ids: list) -> dict:
    """Correlação de Pearson entre critérios, par a par, sobre as linhas em que OS DOIS têm dado
    (`pairwise complete`). Par com menos de 3 linhas em comum, ou com um dos lados constante, devolve
    None — correlação sem variação não existe, e devolver 0 nesse caso seria inventar informação."""
    n = matriz.shape[1]
    saida = [[None] * n for _ in range(n)]
    pares = [[0] * n for _ in range(n)]
    for a in range(n):
        for b in range(a, n):
            comum = np.isfinite(matriz[:, a]) & np.isfinite(matriz[:, b])
            k = int(comum.sum())
            pares[a][b] = pares[b][a] = k
            valor = None
            if k >= 3:
                x, y = matriz[comum, a], matriz[comum, b]
                if x.std() > 0 and y.std() > 0:
                    valor = round(float(np.corrcoef(x, y)[0, 1]), 6)
            saida[a][b] = saida[b][a] = valor
    return {"metodo": "pearson", "sobre": "favorabilidade", "criterios": list(ids), "matriz": saida,
            "pares_com_dado": pares}


def avaliar(feicoes, criterios, srid_trabalho: int, camadas: dict | None = None, *,
            combinador: str = "soma_ponderada", politica_ausente: str = "excluir") -> Avaliacao:
    """Avalia `feicoes` (GeoJSON Feature, EPSG:4326) contra `criterios`, no CRS de trabalho `srid_trabalho`.

    `camadas` é `{nome: [Feature, ...]}` — as outras camadas citadas pelos critérios de raio, contenção e
    distância. Devolve a `Avaliacao`, com valores brutos, favorabilidades, nota, ranque, histogramas e a
    matriz de correlação entre critérios.
    """
    if not isinstance(feicoes, list) or not feicoes:
        raise ErroCriterio("sem_feicao", "é preciso ao menos uma feição")
    if len(feicoes) > limites.AMC_CRITERIOS_FEICAO_MAX:
        raise ErroCriterio("feicoes_demais",
                           f"{len(feicoes)} feições passam do teto de {limites.AMC_CRITERIOS_FEICAO_MAX} desta "
                           f"avaliação", {"recebidas": len(feicoes), "teto": limites.AMC_CRITERIOS_FEICAO_MAX})
    fichas = validar_criterios(criterios)
    ids = [_id_feicao(f, i) for i, f in enumerate(feicoes)]
    n, k = len(feicoes), len(fichas)

    brutos = np.full((n, k), np.nan)
    favor = np.full((n, k), np.nan)
    incluida = np.ones(n, dtype=bool)
    motivo_filtro: list[str | None] = [None] * n
    avisos: list[str] = []

    for j, ficha in enumerate(fichas):
        valores = valores_brutos(feicoes, ficha, srid_trabalho, camadas)
        col = np.array([np.nan if v is None else float(v) for v in valores], dtype=float)
        brutos[:, j] = col
        escala = transformacao_da_influencia(ficha, valores)
        ficha["transformacao"] = escala["transformacao"]
        ficha["limites_derivados"] = escala["limites_derivados"]
        if escala.get("nota"):
            ficha["nota"] = escala["nota"]
        favor[:, j] = mod_transformacoes.transformar(col, escala["transformacao"])

        faixa = ficha.get("faixa_inclusao")
        if faixa:
            fmin = faixa.get("minimo")
            fmax = faixa.get("maximo")
            fora = np.zeros(n, dtype=bool)
            if fmin is not None:
                fora |= np.isfinite(col) & (col < float(fmin))
            if fmax is not None:
                fora |= np.isfinite(col) & (col > float(fmax))
            for i in np.nonzero(fora & incluida)[0]:
                motivo_filtro[i] = (f"{ficha['id']}={col[i]:.6g} fora da faixa de inclusão "
                                    f"[{'-inf' if fmin is None else fmin}, {'+inf' if fmax is None else fmax}]")
            incluida &= ~fora

    notas = np.full(n, np.nan)
    pesos = [f["peso"] for f in fichas]
    if float(sum(pesos)) <= 0:
        raise ErroCriterio("soma_de_pesos_zero", "a soma dos pesos dos critérios é zero; não há como normalizar")
    resultado = mod_combinacao.combinar(favor[incluida], pesos, combinador=combinador,
                                        politica_ausente=politica_ausente, ids_fatores=[f["id"] for f in fichas])
    notas[incluida] = resultado.fav

    ordem = sorted((i for i in np.nonzero(incluida)[0] if np.isfinite(notas[i])),
                   key=lambda i: (-float(notas[i]), str(ids[i])))
    posicao: list[int | None] = [None] * n
    for lugar, i in enumerate(ordem, start=1):
        posicao[i] = lugar
    estado = [ESTADO_INCLUIDA if incluida[i] else ESTADO_FILTRADA for i in range(n)]
    n_filtradas = int((~incluida).sum())
    if n_filtradas:
        avisos.append(f"{n_filtradas} feição(ões) fora do filtro de inclusão: estado 'filtrada', sem posição no "
                      f"ranque; filtro não é veto")
    sem_nota = sum(1 for i in range(n) if incluida[i] and not np.isfinite(notas[i]))
    if sem_nota:
        avisos.append(f"{sem_nota} feição(ões) incluída(s) ficaram sem nota por não ter dado em nenhum critério")

    histogramas = [_histograma(brutos[:, j], fichas[j]) for j in range(k)]
    correlacao = matriz_correlacao(favor[incluida], [f["id"] for f in fichas])
    return Avaliacao(ids=ids, fichas=fichas, brutos=brutos, favorabilidades=favor, notas=notas, estado=estado,
                     motivo_filtro=motivo_filtro, posicao=posicao, histogramas=histogramas, correlacao=correlacao,
                     aviso_pesos=resultado.aviso_pesos, combinador=resultado.combinador, avisos=avisos)

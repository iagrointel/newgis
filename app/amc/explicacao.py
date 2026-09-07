"""Explicação de uma unidade do motor multicritério (item L3-01-f-explicacao): responde "por que esta unidade
tem nota N" com a tabela fator → valor bruto (com unidade de medida e fonte) → transformação aplicada →
favorabilidade → peso → contribuição, mais soma, veto e cobertura.

Decisão central (hipótese do item): a explicação é RECALCULADA a partir de `plat.amc_fator_bruto` na hora da
chamada — nunca lida de uma tabela própria de "explicação" gravada — para que ela seja sempre igual ao resultado
gravado em `plat.amc_resultado` (a prova disso é o portão de pronto: |Δ| ≤ 0,5 em 100 unidades sorteadas). O
combinador é o mesmo de `app/amc/combinacao.py` (item L3-01-e, ENTREGUE); este módulo só monta a matriz de entrada
(um fator transformado por unidade) e traduz o vocabulário do modelo (`docs/esquemas/amc_modelo.v1.json`, item
L3-01-a) para o vocabulário do combinador — os dois nasceram em trilhas diferentes com nomes diferentes para a
mesma coisa (achado deste item; ver docs/adr/20260907T1245-explicacao-amc.md).

Escopo da transformação valor bruto → favorabilidade: os quatro tipos DECLARATIVOS do esquema (`categoria`,
`faixas`, `linear`, `degraus`) são inequívocos a partir do próprio JSON Schema e estão implementados aqui por
inteiro. As doze funções contínuas do Rescale by Function (`exponencial`, `gaussiana`, `grande`, `logaritmo`,
`decaimento_logistico`, `crescimento_logistico`, `ms_grande`, `ms_pequena`, `proxima`, `potencia`, `pequena`,
`linear_simetrica`) são o objeto do item L3-01-d-transformacoes (pendente; portão dele exige que um adversário
implemente cada uma do zero contra a documentação do ArcGIS Pro 3.4 e compare) — fabricar essas fórmulas aqui,
sem essa verificação cruzada, arriscaria gravar um número errado na explicação de um fator que pesa numa decisão
de negócio. Por isso um fator com transformação contínua aparece na tabela com o valor bruto, a unidade e a fonte,
mas com `favorabilidade_fator = None` e uma observação nomeando a lacuna — nunca um número inventado."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.amc import combinacao

# tradução do vocabulário do modelo (esquema amc_modelo.v1, item L3-01-a) para o vocabulário do combinador
# (app/amc/combinacao.py, item L3-01-e): as duas trilhas nomearam a mesma escolha de forma diferente.
MAPA_COMBINADOR: dict[str, str] = {
    "soma_ponderada_normalizada": "soma_ponderada",
    "percentual": "percentual",
    "media_geometrica": "media_geometrica",
    "minimo": "minimo",
    "maximo": "maximo",
    "produto": "produto",
    "soma_fuzzy": "soma_fuzzy",
    "gama": "gama",
}
MAPA_POLITICA: dict[str, str] = {
    "excluir_fator": "excluir",
    "unidade_nula": "nulo",
    "nota_pessimista": "pessimista",
}
# combinadores para os quais a contribuição por fator é aditiva (soma das contribuições = favorabilidade da
# unidade); os demais (mínimo, máximo, produto, soma fuzzy, gama) são fuzzy e não decompõem por definição
# matemática — o mesmo que `combinacao.SEM_PESO` já documenta.
COMBINADORES_ADITIVOS = frozenset({"soma_ponderada", "percentual"})

TIPOS_TRANSFORMACAO_IMPLEMENTADOS = frozenset({"categoria", "faixas", "linear", "degraus"})


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v))


def _chave_categoria(valor: float) -> str:
    """`amc_fator_bruto.valor` é sempre `double precision`; uma categoria (código de classe) chega como número e
    a chave do JSON de notas é texto. `5.0` vira `"5"` (o mesmo número inteiro que quem escreveu o modelo digitou);
    um código fracionário usa a representação Python padrão (`"5.5"`)."""
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def aplicar_transformacao(valor: float | None, transformacao: dict) -> tuple[float | None, str | None]:
    """Valor bruto → favorabilidade 0-100 para um fator. Devolve `(favorabilidade, observação)`; observação só
    quando algo no caminho merece nota (tipo fora de escopo, valor fora da faixa sem nota declarada). `valor`
    ausente (NULL) sempre devolve `(None, None)`: ausência de dado não é um caso a explicar, é o padrão A3."""
    if valor is None or not _numero(valor):
        return None, None
    tipo = transformacao.get("tipo")
    abaixo = transformacao.get("abaixo")
    acima = transformacao.get("acima")

    if tipo not in TIPOS_TRANSFORMACAO_IMPLEMENTADOS:
        return None, (f"transformação '{tipo}' fora do escopo desta explicação: as funções contínuas do Rescale "
                       f"by Function são o item L3-01-d-transformacoes, hoje pendente")

    if tipo == "categoria":
        notas = transformacao.get("notas") or {}
        chave = _chave_categoria(valor)
        if chave in notas:
            return float(notas[chave]), None
        outros = transformacao.get("outros")
        if outros is not None:
            return float(outros), f"categoria '{chave}' sem nota própria; usada a nota de 'outros'"
        return None, f"categoria '{chave}' sem nota no modelo e sem nota de 'outros' declarada"

    if tipo == "faixas":
        quebras = transformacao["quebras"]
        notas = transformacao["notas"]
        if valor < quebras[0]:
            if abaixo is not None:
                return float(abaixo), "valor abaixo da primeira quebra; usada a nota declarada em 'abaixo'"
            return float(notas[0]), None
        if valor >= quebras[-1]:
            if acima is not None:
                return float(acima), "valor na última quebra ou acima; usada a nota declarada em 'acima'"
            return float(notas[-1]), None
        # a faixa i cobre [quebras[i-1], quebras[i]); notas[i] é a nota de quem caiu nela
        i = 1
        while i < len(quebras) and valor >= quebras[i]:
            i += 1
        return float(notas[i]), None

    if tipo == "linear":
        minimo, maximo = transformacao["minimo"], transformacao["maximo"]
        direcao = transformacao.get("direcao", "crescente")
        if valor < minimo:
            if abaixo is not None:
                return float(abaixo), "valor abaixo do mínimo declarado; usada a nota de 'abaixo'"
            fracao = 0.0
        elif valor > maximo:
            if acima is not None:
                return float(acima), "valor acima do máximo declarado; usada a nota de 'acima'"
            fracao = 1.0
        else:
            fracao = (valor - minimo) / (maximo - minimo)
        if direcao == "decrescente":
            fracao = 1.0 - fracao
        return round(fracao * 100.0, 10), None

    if tipo == "degraus":
        bandas = sorted(transformacao["bandas"], key=lambda b: b["ate"])
        for banda in bandas:
            if valor <= banda["ate"]:
                return float(banda["nota"]), None
        if acima is not None:
            return float(acima), "valor acima da última banda; usada a nota declarada em 'acima'"
        return float(bandas[-1]["nota"]), "valor acima da última banda; sem 'acima' declarado, usada a nota da última"

    return None, f"transformação '{tipo}' não reconhecida"  # defensivo; o esquema já barra isto antes


@dataclass
class LinhaFator:
    """Uma linha da tabela da explicação: um fator, do valor bruto até a contribuição na nota final."""

    fator_id: str
    nome: str
    criterio: str | None
    fonte: str
    unidade_medida: str
    direcao: str
    valor_bruto: float | None
    cobertura_extracao: float | None
    transformacao_tipo: str
    favorabilidade_fator: float | None
    peso: float
    presente: bool
    contribuicao: float | None
    observacao: str | None

    def como_dicionario(self) -> dict:
        return {
            "fator_id": self.fator_id, "nome": self.nome, "criterio": self.criterio, "fonte": self.fonte,
            "unidade_medida": self.unidade_medida, "direcao": self.direcao, "valor_bruto": self.valor_bruto,
            "cobertura_extracao": self.cobertura_extracao, "transformacao_tipo": self.transformacao_tipo,
            "favorabilidade_fator": self.favorabilidade_fator, "peso": self.peso, "presente": self.presente,
            "contribuicao": self.contribuicao, "observacao": self.observacao,
        }


@dataclass
class Explicacao:
    fatores: list[LinhaFator]
    combinador: str
    combinador_descricao: str
    contribuicoes_aditivas: bool
    favorabilidade_recalculada: float | None
    cobertura_recalculada: float | None
    favorabilidade_gravada: float | None
    cobertura_gravada: float | None
    delta: float | None
    vetado: bool
    motivo_veto: str | None
    aviso_pesos: str = combinacao.AVISO_PESOS
    observacoes: list[str] = field(default_factory=list)

    def como_dicionario(self) -> dict:
        return {
            "aviso_pesos": self.aviso_pesos,
            "combinador": self.combinador,
            "combinador_descricao": self.combinador_descricao,
            "contribuicoes_aditivas": self.contribuicoes_aditivas,
            "favorabilidade_recalculada": self.favorabilidade_recalculada,
            "cobertura_recalculada": self.cobertura_recalculada,
            "favorabilidade_gravada": self.favorabilidade_gravada,
            "cobertura_gravada": self.cobertura_gravada,
            "delta": self.delta,
            "vetado": self.vetado,
            "motivo_veto": self.motivo_veto,
            "observacoes": list(self.observacoes),
            "fatores": [f.como_dicionario() for f in self.fatores],
        }


class ErroExplicacao(ValueError):
    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


def montar_explicacao(definicao: dict, pesos: dict, fatores_brutos: dict,
                      resultado_gravado: dict | None = None) -> Explicacao:
    """Monta a explicação de uma unidade.

    `definicao` é o documento do modelo (`amc_modelo_versao.definicao`) na versão que a execução congelou.
    `pesos` é `amc_execucao.pesos` ({fator_id: peso}, já completo — a API de execução preenche o que faltar com o
    peso do modelo). `fatores_brutos` é {fator_id: {"valor": float|None, "cobertura": float|None}} lido de
    `plat.amc_fator_bruto` para esta (execução, unidade). `resultado_gravado` é a linha de `plat.amc_resultado`
    (favorabilidade, vetado, motivo, cobertura) quando existir — usada só para comparação e para os campos de
    veto, que este item lê e não recalcula (a avaliação de restrição é outro item)."""
    fatores_def = definicao.get("fatores") or []
    if not fatores_def:
        raise ErroExplicacao("sem_fatores", "o modelo não tem nenhum fator")

    linhas: list[LinhaFator] = []
    favor_vals: list[float | None] = []
    pesos_array: list[float] = []
    for f in fatores_def:
        fid = f["id"]
        bruto = fatores_brutos.get(fid)
        valor = bruto["valor"] if bruto else None
        cobertura_extracao = bruto.get("cobertura") if bruto else None
        fav, observacao = aplicar_transformacao(valor, f["transformacao"])
        peso = float(pesos.get(fid, f["peso"]))
        favor_vals.append(fav)
        pesos_array.append(peso)
        linhas.append(LinhaFator(
            fator_id=fid, nome=f["nome"], criterio=f.get("criterio"), fonte=f["fonte"], unidade_medida=f["unidade"],
            direcao=f["direcao"], valor_bruto=valor, cobertura_extracao=cobertura_extracao,
            transformacao_tipo=f["transformacao"]["tipo"], favorabilidade_fator=fav, peso=peso, presente=False,
            contribuicao=None, observacao=observacao,
        ))

    combinador_esquema = ((definicao.get("combinador") or {}).get("tipo")) or "soma_ponderada_normalizada"
    combinador = MAPA_COMBINADOR[combinador_esquema]
    politica_esquema = definicao.get("dado_ausente", "excluir_fator")
    politica = MAPA_POLITICA[politica_esquema]
    gama = (definicao.get("combinador") or {}).get("gama", 0.5)

    resultado = combinacao.combinar(
        fatores=[favor_vals], pesos=pesos_array, combinador=combinador, politica_ausente=politica,
        gama=gama if gama is not None else 0.5, ids_fatores=[f["id"] for f in fatores_def],
    )
    fav_recalc = resultado.fav[0]
    fav_recalc = None if not math.isfinite(fav_recalc) else float(fav_recalc)
    cobertura_recalc = float(resultado.cobertura[0])

    # presença efetiva por política, para decompor a contribuição da MESMA forma que `combinacao._aplica_politica`
    presente_bruto = [v is not None and _numero(v) for v in favor_vals]
    if politica == "pessimista":
        favor_efetivo = [v if p else 0.0 for v, p in zip(favor_vals, presente_bruto, strict=True)]
        presente_efetivo = [True] * len(favor_vals)
    elif politica == "nulo":
        completa = all(presente_bruto)
        presente_efetivo = presente_bruto if completa else [False] * len(favor_vals)
        favor_efetivo = favor_vals
    else:  # excluir
        presente_efetivo = presente_bruto
        favor_efetivo = favor_vals

    contribuicoes_aditivas = combinador in COMBINADORES_ADITIVOS
    soma_peso_presente = sum(w for w, p in zip(pesos_array, presente_efetivo, strict=True) if p)
    for linha, peso, presente, favp in zip(linhas, pesos_array, presente_efetivo, favor_efetivo, strict=True):
        linha.presente = presente
        if contribuicoes_aditivas and presente and soma_peso_presente > 0:
            linha.contribuicao = (peso * favp) / soma_peso_presente

    observacoes = list(resultado.observacoes)
    if not contribuicoes_aditivas:
        observacoes.append(
            f"combinador '{combinador}' é fuzzy e não decompõe em contribuições aditivas por fator; a soma das "
            f"contribuições exibidas não é igual à favorabilidade da unidade por definição matemática do combinador"
        )
    sem_transformacao = sorted({
        linha.transformacao_tipo for linha in linhas
        if linha.valor_bruto is not None and linha.favorabilidade_fator is None
        and linha.transformacao_tipo not in TIPOS_TRANSFORMACAO_IMPLEMENTADOS
    })
    if sem_transformacao:
        observacoes.append(
            "fatores com transformação ainda fora do escopo desta explicação (item L3-01-d-transformacoes, "
            "pendente): " + ", ".join(sem_transformacao)
        )

    vetado = bool(resultado_gravado["vetado"]) if resultado_gravado else False
    motivo_veto = resultado_gravado.get("motivo") if resultado_gravado else None
    fav_gravado_bruto = resultado_gravado.get("favorabilidade") if resultado_gravado else None
    fav_gravado = float(fav_gravado_bruto) if fav_gravado_bruto is not None else None
    cobertura_gravada_bruta = resultado_gravado.get("cobertura") if resultado_gravado else None
    cobertura_gravada = float(cobertura_gravada_bruta) if cobertura_gravada_bruta is not None else None
    delta = abs(fav_recalc - fav_gravado) if fav_recalc is not None and fav_gravado is not None else None

    return Explicacao(
        fatores=linhas, combinador=combinador, combinador_descricao=combinacao.COMBINADORES[combinador],
        contribuicoes_aditivas=contribuicoes_aditivas, favorabilidade_recalculada=fav_recalc,
        cobertura_recalculada=cobertura_recalc, favorabilidade_gravada=fav_gravado,
        cobertura_gravada=cobertura_gravada, delta=delta, vetado=vetado, motivo_veto=motivo_veto,
        observacoes=observacoes,
    )

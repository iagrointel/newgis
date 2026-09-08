"""Presets do motor multicritério (item L3-01-h-presets).

Conceito (hipótese do item): preset = conjunto nomeado de PESOS e VETOS de um modelo, salvo por
usuário (escopo ``usuario``) ou compartilhado no inquilino (escopo ``inquilino``), com autor, data
e descrição. O preset é AUTOCONTIDO: carrega a ordem declarada dos fatores do modelo, porque a
tabela de modelo (item L3-01-a) está refutada e não existe na base — o preset é o próprio contexto
de validação na importação e na aplicação.

Conteúdo validado (``validar_conteudo``)::

    {
      "fatores":  ["acesso_rodoviario", "custo_terreno"],   # ordem declarada do modelo
      "pesos":    {"acesso_rodoviario": 5.0, "custo_terreno": 2.0},  # multiplicador >= 0, soma > 0
      "vetos":    {"area_alagada": 1.0},        # fator -> fração vetada [0,1]; peso pode ser 0
      "combinador": "soma_ponderada",           # chave de COMBINADORES (app/amc/combinacao.py)
      "politica_ausente": "excluir",            # chave de POLITICAS_AUSENTE
      "gama": 0.5                               # só usado pelo combinador 'gama'
    }

``"pesos_iguais": true`` substitui fatores+pesos: o preset vale para QUALQUER matriz com o mesmo
peso (1) em todo fator — a hipótese do item diz que 'pesos iguais' existe sempre.

Presets INTEGRADOS: vivem aqui, não em tabela. Valem para todo inquilino, são somente leitura e
saem SEMPRE na listagem — o 'pesos iguais' por contrato do item, e os quatro exemplos migrados do
motor logístico da casa (galpão, última milha, indústria, custo mínimo) sobre NOMES DE FATOR
GENÉRICOS de dado aberto, sem nome de cliente (regra da casa).

Veto: a fração declarada é aplicada POR UNIDADE onde o fator de veto TEM dado (valor finito na
matriz). Unidade sem dado no fator de veto não é vetada por ele — veto marca, não inventa número
(mesmo contrato de app/amc/combinacao.py). O módulo é PURO: não abre banco, não lê arquivo, não
usa relógio; a recombinação é a ``combinar`` do combinador.
"""

from __future__ import annotations

import math

import numpy as np

from app.amc.combinacao import COMBINADORES, POLITICAS_AUSENTE

FORMATO = "plat/amc_preset"
VERSAO = 1
FATOR_NOME_MAX = 120
FATORES_MAX = 200          # espelho de limites.AMC_PRESET_FATORES_MAX (o limite vive em limites.py)
DESCRICAO_MAX = 2000       # mesmo teto do CHECK da migração


class ErroConteudo(ValueError):
    """Erro de contrato do conteúdo do preset. `codigo` é curto e estável; `detalhe` é a lista/lista de
    campos quando existe (a refutação do item exige RECUSA COM A LISTA do que falta)."""

    def __init__(self, codigo: str, mensagem: str, detalhe: object = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


# ------------------------------------------------------------------ presets integrados (código, não tabela)

_INTEGRADO_EXEMPLO = "exemplo migrado do motor logístico da casa; nomes de fator genéricos de dado aberto"

INTEGRADOS: dict[str, dict] = {
    "pesos_iguais": {
        "nome": "pesos iguais",
        "descricao": "todos os fatores com o mesmo peso; existe sempre, para qualquer modelo",
        "conteudo": {
            "pesos_iguais": True,
            "combinador": "soma_ponderada",
            "politica_ausente": "excluir",
        },
    },
    "logistica_galpao": {
        "nome": "logística: galpão",
        "descricao": f"pesos de escolha de galpão. {_INTEGRADO_EXEMPLO}",
        "conteudo": {
            "fatores": ["acesso_rodoviario", "polo_gerador_carga", "proximidade_porto",
                        "custo_terreno", "proximidade_aeroporto", "area_alagada"],
            "pesos": {"acesso_rodoviario": 5.0, "polo_gerador_carga": 4.0, "proximidade_porto": 3.0,
                      "custo_terreno": 2.0, "proximidade_aeroporto": 1.0, "area_alagada": 0.0},
            "vetos": {"area_alagada": 1.0},
        },
    },
    "logistica_ultima_milha": {
        "nome": "logística: última milha",
        "descricao": f"pesos de centro de distribuição urbano. {_INTEGRADO_EXEMPLO}",
        "conteudo": {
            "fatores": ["densidade_demanda", "acesso_urbano", "custo_imovel", "congestao"],
            "pesos": {"densidade_demanda": 5.0, "acesso_urbano": 4.0, "custo_imovel": 1.0,
                      "congestao": 2.0},
            "vetos": {},
        },
    },
    "logistica_industria": {
        "nome": "logística: indústria",
        "descricao": f"pesos de implantação industrial. {_INTEGRADO_EXEMPLO}",
        "conteudo": {
            "fatores": ["energia_disponivel", "acesso_rodoviario", "acesso_ferroviario",
                        "mao_de_obra", "proximidade_porto", "area_protegida"],
            "pesos": {"energia_disponivel": 4.0, "acesso_rodoviario": 4.0, "acesso_ferroviario": 3.0,
                      "mao_de_obra": 2.0, "proximidade_porto": 2.0, "area_protegida": 0.0},
            "vetos": {"area_protegida": 1.0},
        },
    },
    "logistica_custo_minimo": {
        "nome": "logística: custo mínimo",
        "descricao": f"pesos que dominam o custo total. {_INTEGRADO_EXEMPLO}",
        "conteudo": {
            "fatores": ["custo_terreno", "custo_implantacao", "custo_operacao", "acesso_rodoviario"],
            "pesos": {"custo_terreno": 5.0, "custo_implantacao": 4.0, "custo_operacao": 4.0,
                      "acesso_rodoviario": 2.0},
            "vetos": {},
        },
    },
}


def integrado_por_id(pid: str) -> dict | None:
    """Linha-normalizada do preset integrado pelo identificador de slug, ou None."""
    base = INTEGRADOS.get(pid)
    if base is None:
        return None
    return {
        "id": pid,
        "nome": base["nome"],
        "descricao": base["descricao"],
        "escopo": "inquilino",
        "integrado": True,
        "dono_id": None,
        "dono_login": None,
        "criado_em": None,
        "atualizado_em": None,
        "conteudo": dict(base["conteudo"]),
    }


# ------------------------------------------------------------------ validação do conteúdo


def _texto_fator(nome: object) -> str:
    if not isinstance(nome, str) or not nome.strip() or len(nome) > FATOR_NOME_MAX:
        raise ErroConteudo(
            "fator_invalido",
            f"nome de fator precisa ser texto de 1 a {FATOR_NOME_MAX} caracteres: {nome!r}",
        )
    return nome.strip()


def validar_conteudo(conteudo: object) -> dict:
    """Valida o conteúdo do preset e devolve o dicionário normalizado (padrões preenchidos).

    Recusa com ErroConteudo; o peso negativo, o fator repetido, a soma de pesos zero e o peso cujo
    fator não está na lista declarada são recusados aqui — a mesma classe de erro que o item
    L3-01-a exigia do modelo, agora carregada pelo preset.
    """
    if not isinstance(conteudo, dict):
        raise ErroConteudo("conteudo_invalido", "o conteúdo do preset é um objeto JSON")
    pesos_iguais = bool(conteudo.get("pesos_iguais", False))
    combinador = conteudo.get("combinador", "soma_ponderada")
    politica = conteudo.get("politica_ausente", "excluir")
    gama = conteudo.get("gama", 0.5)
    if combinador not in COMBINADORES:
        raise ErroConteudo(
            "combinador_desconhecido", "combinador desconhecido: " + str(combinador),
            {"aceitos": sorted(COMBINADORES)},
        )
    if politica not in POLITICAS_AUSENTE:
        raise ErroConteudo(
            "politica_ausente_desconhecida", "política de dado ausente desconhecida: " + str(politica),
            {"aceitas": sorted(POLITICAS_AUSENTE)},
        )
    try:
        gama = float(gama)
    except (TypeError, ValueError):
        raise ErroConteudo("gama_invalido", "gama precisa ser número entre 0 e 1") from None
    if not math.isfinite(gama) or not 0.0 <= gama <= 1.0:
        raise ErroConteudo("gama_invalido", "gama precisa ser número entre 0 e 1")

    if pesos_iguais:
        for chave in ("fatores", "pesos", "vetos"):
            if conteudo.get(chave):
                raise ErroConteudo(
                    "pesos_iguais_sem_fatores",
                    f"preset de pesos iguais não declara '{chave}': ele vale para qualquer modelo",
                )
        return {"pesos_iguais": True, "fatores": [], "pesos": {}, "vetos": {},
                "combinador": combinador, "politica_ausente": politica, "gama": gama}

    fatores_brutos = conteudo.get("fatores")
    if not isinstance(fatores_brutos, list) or not fatores_brutos:
        raise ErroConteudo(
            "fatores_ausentes",
            "o preset declara a lista de fatores do modelo ('fatores'); para valer para qualquer "
            "modelo use pesos_iguais",
        )
    if len(fatores_brutos) > FATORES_MAX:
        raise ErroConteudo(
            "fatores_demais",
            f"o preset aceita até {FATORES_MAX} fatores; recebeu {len(fatores_brutos)}",
        )
    fatores: list[str] = []
    for f in fatores_brutos:
        texto = _texto_fator(f)
        if texto in fatores:
            raise ErroConteudo("fator_duplicado", f"fator repetido na lista do modelo: {texto}",
                               {"repetido": texto})
        fatores.append(texto)

    pesos_brutos = conteudo.get("pesos")
    if not isinstance(pesos_brutos, dict) or not pesos_brutos:
        raise ErroConteudo("pesos_ausentes", "o preset declara um peso por fator ('pesos')")
    pesos: dict[str, float] = {}
    for chave, valor in pesos_brutos.items():
        nome = _texto_fator(chave)
        if nome not in fatores:
            raise ErroConteudo(
                "peso_fora_da_lista",
                f"o peso de '{nome}' não corresponde a nenhum fator da lista do modelo",
                {"faltando": [nome], "fatores": fatores},
            )
        try:
            peso = float(valor)
        except (TypeError, ValueError):
            raise ErroConteudo("peso_invalido", f"peso de '{nome}' precisa ser número") from None
        if not math.isfinite(peso) or peso < 0:
            raise ErroConteudo("peso_invalido", f"peso de '{nome}' precisa ser número >= 0")
        pesos[nome] = peso
    if sum(pesos.values()) <= 0:
        raise ErroConteudo("soma_de_pesos_zero", "a soma dos pesos é zero; não há como normalizar")

    vetos_brutos = conteudo.get("vetos") or {}
    if not isinstance(vetos_brutos, dict):
        raise ErroConteudo("vetos_invalidos", "'vetos' é um objeto fator -> fração entre 0 e 1")
    vetos: dict[str, float] = {}
    for chave, valor in vetos_brutos.items():
        nome = _texto_fator(chave)
        if nome not in fatores:
            raise ErroConteudo(
                "veto_fora_da_lista",
                f"o veto de '{nome}' não corresponde a nenhum fator da lista do modelo",
                {"faltando": [nome], "fatores": fatores},
            )
        try:
            fracao = float(valor)
        except (TypeError, ValueError):
            raise ErroConteudo("veto_invalido", f"fração de veto de '{nome}' precisa ser número") from None
        if not math.isfinite(fracao) or not 0.0 <= fracao <= 1.0:
            raise ErroConteudo("veto_invalido", f"fração de veto de '{nome}' precisa estar entre 0 e 1")
        vetos[nome] = fracao

    return {"pesos_iguais": False, "fatores": fatores, "pesos": pesos, "vetos": vetos,
            "combinador": combinador, "politica_ausente": politica, "gama": gama}


# ------------------------------------------------------------------ aplicação


def fatores_faltando(conteudo: dict, ids_fatores: list[str] | tuple) -> list[str]:
    """Fatores DECLARADOS no preset que a matriz de aplicação não traz — a lista da recusa."""
    if conteudo.get("pesos_iguais"):
        return []
    dados = {str(f).strip() for f in ids_fatores}
    return [f for f in conteudo["fatores"] if f not in dados]


def fracao_vetada_do_conteudo(conteudo: dict, m: np.ndarray, ids_fatores: list[str]) -> np.ndarray | None:
    """Fração vetada por unidade segundo os vetos DECLARADOS no preset.

    O veto do fator entra na unidade onde o fator TEM dado (valor finito); onde falta dado o veto
    não é inventado. Devolve None quando o preset não tem veto aplicável — aí ``combinar`` é
    chamado sem veto, como antes do item.
    """
    if not conteudo.get("vetos"):
        return None
    indice = {str(f).strip(): i for i, f in enumerate(ids_fatores)}
    fracao = np.zeros(m.shape[0], dtype=np.float64)
    aplicou = False
    for nome, valor in conteudo["vetos"].items():
        i = indice.get(nome)
        if i is None:
            continue
        presente = np.isfinite(m[:, i])
        if not presente.any():
            continue
        fracao = np.where(presente, np.minimum(1.0, fracao + float(valor)), fracao)
        aplicou = True
    return fracao if aplicou else None


def pesos_da_matriz(conteudo: dict, ids_fatores: list[str]) -> list[float]:
    """Peso de cada coluna da matriz na ordem dada (pesos iguais = 1 para todo fator).

    Recusa ErroConteudo 'peso_fora_da_lista' se a matriz traz fator que o preset não declara: o
    preset é o contexto do modelo; aplicá-lo sobre fator desconhecido é erro de chamada, não
    silêncio.
    """
    if conteudo.get("pesos_iguais"):
        return [1.0] * len(ids_fatores)
    desconhecidos = sorted(set(str(f).strip() for f in ids_fatores) - set(conteudo["pesos"]))
    if desconhecidos:
        raise ErroConteudo(
            "fator_fora_do_preset",
            "a matriz traz fator que o preset não declara: " + ", ".join(desconhecidos),
            {"faltando_no_preset": desconhecidos, "fatores_do_preset": conteudo["fatores"]},
        )
    return [float(conteudo["pesos"][str(f).strip()]) for f in ids_fatores]


# ------------------------------------------------------------------ exportação e importação


def documento_exportar(preset: dict) -> dict:
    """Documento de exportação (o que GET .../exportar devolve e POST /importar aceita)."""
    return {
        "formato": FORMATO,
        "versao": VERSAO,
        "nome": preset["nome"],
        "descricao": preset["descricao"],
        "escopo": preset["escopo"],
        "integrado": bool(preset.get("integrado")),
        "conteudo": preset["conteudo"],
    }


def documento_validar(doc: object) -> dict:
    """Valida o documento de importação e devolve {nome, descricao, escopo, conteudo normalizado}.

    O campo OPCIONAL 'fatores_modelo' (lista do modelo alvo) é conferido AQUI: preset que declara
    fator fora do modelo informado é recusado com a LISTA do que falta (refutação do item).
    """
    if not isinstance(doc, dict):
        raise ErroConteudo("documento_invalido", "o documento de importação é um objeto JSON")
    if doc.get("formato") != FORMATO:
        raise ErroConteudo("formato_desconhecido",
                           f"formato desconhecido: {doc.get('formato')!r}; esperado {FORMATO!r}")
    try:
        versao = int(doc.get("versao"))
    except (TypeError, ValueError):
        raise ErroConteudo("versao_invalida", "versão do documento precisa ser inteiro") from None
    if versao != VERSAO:
        raise ErroConteudo("versao_desconhecida",
                           f"versão {versao} não é aceita; esperada {VERSAO}")
    nome = doc.get("nome")
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 200:
        raise ErroConteudo("nome_invalido", "nome do preset precisa ser texto de 1 a 200 caracteres")
    descricao = doc.get("descricao") or ""
    if not isinstance(descricao, str) or len(descricao) > DESCRICAO_MAX:
        raise ErroConteudo("descricao_invalida",
                           f"descrição precisa ser texto de até {DESCRICAO_MAX} caracteres")
    escopo = doc.get("escopo") or "usuario"
    if escopo not in ("usuario", "inquilino"):
        raise ErroConteudo("escopo_invalido", "escopo precisa ser 'usuario' ou 'inquilino'")
    conteudo = validar_conteudo(doc.get("conteudo"))
    modelo = doc.get("fatores_modelo")
    faltando: list[str] = []
    if modelo is not None:
        if not isinstance(modelo, list) or any(not isinstance(f, str) for f in modelo):
            raise ErroConteudo("modelo_invalido", "'fatores_modelo' é a lista de fatores do modelo alvo")
        faltando = fatores_faltando(conteudo, modelo)
        if faltando:
            raise ErroConteudo(
                "fator_fora_do_modelo",
                "o preset declara fator que o modelo informado não tem: " + ", ".join(faltando),
                {"faltando": faltando, "fatores_do_modelo": [str(f).strip() for f in modelo]},
            )
    return {"nome": nome.strip(), "descricao": descricao, "escopo": escopo,
            "conteudo": conteudo, "faltando": faltando}

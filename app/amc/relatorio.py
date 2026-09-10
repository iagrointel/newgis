"""Relatório do motor multicritério (item L3-14-cobertura-dado-ausente): junta a combinação
(favorabilidade por unidade, `app.amc.combinacao`) com a cobertura por fator (`app.amc.cobertura`)
numa única estrutura serializável, para a explicação por unidade e para o relatório da execução.

`app.amc.combinacao.Resultado` já traz `cobertura` por UNIDADE (quanto peso do modelo aquela unidade
tem, entre os fatores presentes). Este módulo acrescenta a leitura complementar por FATOR (quantas
unidades e quanta área têm aquele fator, através de todo o conjunto) — as duas cabem lado a lado sem
se substituir: a de unidade explica "por que esta unidade tem nota baixa", a de fator explica "este
fator é confiável para o modelo inteiro".

A política de dado ausente e o aviso de que os pesos são escolha do usuário (nunca medição) são
sempre incluídos e nunca dependem de o chamador lembrar de pedir.
"""

from __future__ import annotations

from app.amc import cobertura as mod_cobertura
from app.amc import combinacao as mod_combinacao


def montar_relatorio(
    fatores,
    pesos,
    *,
    ids_fatores=None,
    areas=None,
    limiar_cobertura: float = mod_cobertura.LIMIAR_PADRAO,
    combinador: str = "soma_ponderada",
    politica_ausente: str = "excluir",
    gama: float = 0.5,
    fracao_vetada=None,
    motivo_veto=None,
) -> dict:
    """Executa a combinação e a cobertura por fator sobre a MESMA matriz e devolve um dicionário
    pronto para serializar (API, PDF, explicação por unidade): `resultado` (saída de `combinacao`),
    `cobertura_por_fator` (uma entrada por fator) e `fatores_abaixo_do_limiar` (ids marcados).
    """
    n_fatores = len(fatores[0]) if fatores else 0
    ids = ids_fatores if ids_fatores is not None else [f"fator_{i}" for i in range(n_fatores)]

    resultado = mod_combinacao.combinar(
        fatores,
        pesos,
        combinador=combinador,
        politica_ausente=politica_ausente,
        gama=gama,
        fracao_vetada=fracao_vetada,
        motivo_veto=motivo_veto,
        ids_fatores=ids,
    )
    coberturas = mod_cobertura.cobertura_por_fator(fatores, ids, areas=areas, limiar=limiar_cobertura)
    marcados = [c.id_fator for c in coberturas if c.abaixo_do_limiar]

    if marcados:
        aviso = (
            f"{len(marcados)} de {len(ids)} fator(es) abaixo do limiar de cobertura "
            f"({limiar_cobertura:.0%} das unidades): " + ", ".join(marcados) + ". "
            "O fator continua no modelo — a cobertura baixa é informação para quem lê o resultado, "
            "nunca é motivo para a ausência virar zero na conta."
        )
    else:
        aviso = f"todos os {len(ids)} fatores estão com cobertura de unidades >= {limiar_cobertura:.0%}"

    return {
        "ids_fatores": list(ids),
        "politica_ausente": politica_ausente,
        "politica_ausente_descricao": mod_combinacao.POLITICAS_AUSENTE[politica_ausente],
        "limiar_cobertura": limiar_cobertura,
        "cobertura_por_fator": [c.como_dicionario() for c in coberturas],
        "fatores_abaixo_do_limiar": marcados,
        "aviso_cobertura": aviso,
        "resultado": resultado.como_dicionario(),
    }

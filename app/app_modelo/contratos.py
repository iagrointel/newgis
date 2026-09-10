"""Contrato por TIPO de widget (eventos que emite, ações que aceita) — espelho em Python de
`web/js/widgets/registro.js` (item L5-01-e-acoes-configuraveis). A API recusa o que o construtor recusaria:
`tests/unit/test_app_acoes.py` compara este dicionário com o registro lido em node e reprova qualquer diferença."""

from __future__ import annotations

ACOES_DADO = ("filtrar", "selecionar", "limpar_filtro", "limpar_selecao")
EVENTOS_VISTA = ("filtro_mudou", "selecao_mudou", "vista_mudou", "dado_adicionado", "registros_carregados")

CONTRATOS: dict[str, dict[str, tuple[str, ...]]] = {
    "mapa": {
        "eventos": ("clique", "selecao_mudou", "extensao_mudou", "registros_carregados", "mapa.selecao",
                    "mapa.extensao_alterada"),
        "acoes": (*ACOES_DADO, "zoom", "pan", "piscar", "popup", "mapa.enquadrar", "mapa.destacar"),
    },
    "legenda": {"eventos": ("legenda.item_acionado",), "acoes": ("legenda.definir",)},
    "tabela": {
        "eventos": ("clique", "selecao_mudou", "registros_carregados", "tabela.linha_selecionada"),
        "acoes": (*ACOES_DADO, "piscar", "tabela.definir", "tabela.filtrar"),
    },
    "grafico": {
        "eventos": ("clique", "selecao_mudou", "filtro_mudou", "registros_carregados"),
        "acoes": (*ACOES_DADO, "piscar"),
    },
    "texto": {"eventos": (), "acoes": ("texto.definir", "definir_parametro")},
    "botao": {"eventos": ("clique", "botao.acionado"), "acoes": ("botao.habilitar", "abrir", "fechar")},
    "filtro": {"eventos": ("filtro_mudou", "filtro.alterado"),
               "acoes": ("filtro.definir", "limpar_filtro", "definir_parametro")},
}

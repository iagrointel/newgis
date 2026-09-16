"""Contrato por TIPO de widget (eventos que emite, ações que aceita) — espelho em Python de
`web/js/widgets/registro.js` (item L5-01-e-acoes-configuraveis; widgets de dado ampliados pelo L5-01-c
— tabela 2/gráfico 2/filtro 2/lista/consulta/seleção/info-feicao/adicionar-dado — e widgets de página
pelo L5-01-d — imagem/cartão/incorporar/divisor/menu/controlador/compartilhar/login/idioma/tema — mais
`tabela.exportada`/`grafico.desenhado`/`texto.feicao` da varredura de 15/09). A API recusa o que o
construtor recusaria: `tests/unit/test_app_acoes.py` compara este dicionário com o registro lido em
node e reprova qualquer diferença — atualizar aqui sempre que `registro.js` ganhar evento/ação novos."""

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
        "eventos": ("clique", "selecao_mudou", "registros_carregados", "tabela.linha_selecionada",
                    "tabela.exportada"),
        "acoes": (*ACOES_DADO, "piscar", "tabela.definir", "tabela.filtrar", "tabela.ordenar", "tabela.pagina"),
    },
    "grafico": {
        "eventos": ("clique", "selecao_mudou", "filtro_mudou", "registros_carregados", "grafico.desenhado"),
        "acoes": (*ACOES_DADO, "piscar", "grafico.definir"),
    },
    "lista": {
        "eventos": ("clique", "selecao_mudou", "lista.item_selecionado"),
        "acoes": (*ACOES_DADO, "piscar", "lista.pagina"),
    },
    "consulta": {
        "eventos": ("filtro_mudou", "consulta.executada"),
        "acoes": ("limpar_filtro", "consulta.executar", "definir_parametro"),
    },
    "selecao": {
        "eventos": ("selecao_mudou", "selecao.alterada"),
        "acoes": ("selecionar", "limpar_selecao", "selecao.por_atributo", "selecao.tudo", "selecao.inverter"),
    },
    "info-feicao": {
        "eventos": ("info.mostrada",),
        "acoes": ("piscar", "info.mostrar", "abrir", "fechar"),
    },
    "adicionar-dado": {
        "eventos": ("dado_adicionado", "adicionar.carregado", "adicionar.erro"),
        "acoes": ("adicionar.carregar",),
    },
    "texto": {"eventos": (), "acoes": ("texto.definir", "texto.feicao", "definir_parametro")},
    "imagem": {
        "eventos": ("imagem.acionada",),
        "acoes": ("imagem.definir", "imagem.feicao", "definir_parametro"),
    },
    "botao": {
        "eventos": ("clique", "botao.acionado", "botao.pagina"),
        "acoes": ("botao.habilitar", "abrir", "fechar", "definir_parametro"),
    },
    "cartao": {"eventos": ("cartao.acionado", "cartao.pagina"), "acoes": ("cartao.feicao", "definir_parametro")},
    "incorporar": {"eventos": (), "acoes": ("incorporar.definir", "definir_parametro")},
    "divisor": {"eventos": (), "acoes": ("definir_parametro",)},
    "menu": {
        "eventos": ("menu.pagina", "menu.acionado"),
        "acoes": ("menu.definir", "definir_parametro"),
    },
    "controlador": {
        "eventos": ("controlador.alternado",),
        "acoes": ("controlador.abrir", "controlador.fechar", "definir_parametro"),
    },
    "compartilhar": {"eventos": (), "acoes": ("definir_parametro",)},
    "login": {"eventos": ("login.mudou",), "acoes": ("login.atualizar", "definir_parametro")},
    "idioma": {"eventos": ("idioma.mudou",), "acoes": ("idioma.definir", "definir_parametro")},
    "tema": {"eventos": ("tema.mudou",), "acoes": ("tema.definir", "definir_parametro")},
    "filtro": {"eventos": ("filtro_mudou", "filtro.alterado"),
               "acoes": ("filtro.definir", "limpar_filtro", "definir_parametro")},
}

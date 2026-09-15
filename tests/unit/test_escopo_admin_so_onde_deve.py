"""Guarda de regressão do item de seguimento de L0-04-a/L0-11 (achado do adversário, mesma causa raiz):
`admin:inquilino` só pode aparecer em `web/js/` nos arquivos desta lista fechada — a tela de escolha de
escopo (que já filtra a opção por `admin`) e os dois módulos de upload que documentam, em comentário, por
que NUNCA usá-lo (achado original de L0-04-a). Qualquer OUTRO arquivo `.js` que passe a mencionar
`admin:inquilino` — inclusive um novo consumidor das rotas de catálogo/campo/rede/exportação corrigidas
neste item — reprova aqui: é o mesmo defeito voltando (um front-end pedindo o escopo que só perfil admin
consegue emitir, para uma operação de conteúdo que qualquer usuário com o privilégio adequado deveria
fazer).

`tests/api/uploads/test_uploads.py::test_front_uploads_nunca_pede_token_admin_inquilino` já cobre o padrão
literal `escopos: ['admin:inquilino']` só dentro de `web/js/uploads/`; este teste é o de VARREDURA GERAL
(toda a árvore `web/js/`, qualquer forma de menção) — os dois se complementam, não se substituem."""

import re
from pathlib import Path

RAIZ_WEB_JS = Path(__file__).resolve().parents[2] / "web" / "js"

# Lista FECHADA: só estes arquivos podem mencionar "admin:inquilino" em web/js/. Acrescentar um nome aqui
# exige justificar por quê (o commit que acrescenta tem de dizer o quê e por quê, igual a esta tabela).
PERMITIDOS = frozenset({
    # tela de emissão de token: é o próprio seletor de escopo, já filtrado por `admin` no template
    # (`ESCOPOS.filter((e) => e !== 'admin:inquilino' || admin)`) — quem não é admin nunca vê a opção.
    "auth/tokens.js",
    # documentam em comentário, para quem for mexer depois, por que NÃO usar admin:inquilino no upload
    # (achado original de L0-04-a) — não pedem o escopo, citam-no como o erro a não repetir.
    "uploads/nucleo.js",
    "uploads/enviar.js",
})

_MENCIONA = re.compile(r"admin:inquilino")


def _arquivos_js() -> list[Path]:
    return sorted(RAIZ_WEB_JS.rglob("*.js"))


def test_varredura_achou_arquivo_js():
    assert _arquivos_js(), "o varredor não achou nenhum .js em web/js/; o caminho mudou?"


def test_admin_inquilino_so_nos_arquivos_permitidos():
    fora = []
    for caminho in _arquivos_js():
        rel = caminho.relative_to(RAIZ_WEB_JS).as_posix()
        if _MENCIONA.search(caminho.read_text(encoding="utf-8")) and rel not in PERMITIDOS:
            fora.append(rel)
    assert not fora, (
        f"arquivo(s) fora da lista fechada mencionam admin:inquilino: {fora} -- se é um NOVO consumidor "
        "pedindo esse escopo para uma rota de conteúdo, é o mesmo achado de L0-04-a/L0-11 voltando "
        "(escopo que só perfil admin emite, para operação que o privilégio do usuário já cobre); se é "
        "justificado (ex.: novo seletor de escopo administrativo de verdade), acrescente à lista PERMITIDOS "
        "com a mesma justificativa desta tabela."
    )


def test_lista_permitidos_nao_tem_arquivo_fantasma():
    """Os dois testes de cima só reprovam para MAIS arquivos que o esperado; este reprova para MENOS —
    um nome na lista que não existe mais (ou nunca existiu) esconderia a lista ficando frouxa sem ninguém
    notar."""
    existentes = {p.relative_to(RAIZ_WEB_JS).as_posix() for p in _arquivos_js()}
    fantasmas = sorted(PERMITIDOS - existentes)
    assert not fantasmas, f"em PERMITIDOS mas não existe mais em web/js/: {fantasmas}"

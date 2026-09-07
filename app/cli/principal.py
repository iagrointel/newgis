"""Montagem do `argparse` da linha de comando `plat` e o ponto de entrada (item L0-14-cli-admin).

O parser é o ÚNICO lugar onde os comandos são descritos: a ajuda em português, o `docs/CLI.md` e o
teste de cobertura de subcomandos saem todos daqui, então acrescentar comando sem documentá-lo é
impossível por construção.
"""

from __future__ import annotations

import argparse
import sys

from app.cli import comandos as c
from app.cli.rede import ErroCLI, recusar_senha_em_argv

DESCRICAO = (
    "Administração da plataforma pela linha de comando: inquilino, usuário, token, camada, job, evento, "
    "segredo e saúde. Todo comando fala com a mesma API que o navegador usa, com a mesma sessão e os "
    "mesmos privilégios — nada aqui escreve no banco por fora."
)
EPILOGO = (
    "As credenciais saem de um arquivo modo 600 no formato 'inquilino login senha' (--credenciais). "
    "Senha NUNCA entra por argumento: use --senha-stdin ou --senha-arquivo."
)


# argparse fala inglês; a ajuda que o operador vê é em português como todo o resto do produto. Em vez de
# instalar catálogo gettext (dependência e arquivo binário no repositório), o texto formatado passa por esta
# tabela — pequena, fechada e coberta por teste (nenhuma palavra em inglês sai de `plat --help`).
TRADUCAO = {
    "usage: ": "uso: ",
    "positional arguments:": "argumentos posicionais:",
    "options:": "opções:",
    "optional arguments:": "opções:",
    "show this help message and exit": "mostra esta ajuda e sai",
    "default: ": "padrão: ",
    "error: ": "erro: ",
    "the following arguments are required:": "faltam argumentos obrigatórios:",
    "unrecognized arguments:": "argumentos desconhecidos:",
    "invalid choice:": "valor inválido:",
    "choose from": "escolha entre",
    "expected one argument": "esperava um valor",
    "invalid int value:": "valor inteiro inválido:",
    "invalid float value:": "valor numérico inválido:",
    "not allowed with argument": "não pode vir junto de",
    "argument ": "argumento ",
    "is required": "é obrigatório",
    "cannot be used with": "não pode ser usado com",
}


def traduzir(texto: str) -> str:
    for ingles, portugues in TRADUCAO.items():
        texto = texto.replace(ingles, portugues)
    return texto


class ParserPT(argparse.ArgumentParser):
    """`ArgumentParser` com a ajuda e as mensagens de erro em português (os subparsers herdam a classe)."""

    def format_help(self) -> str:
        return traduzir(super().format_help())

    def format_usage(self) -> str:
        return traduzir(super().format_usage())

    def error(self, message: str):  # noqa: D102 - contrato do argparse
        super().error(traduzir(message))


def _senha_sem_argv(p: argparse.ArgumentParser) -> None:
    """Duas maneiras de informar senha, as duas fora da lista de argumentos (achado 6a do adversário do T1)."""
    g = p.add_mutually_exclusive_group()
    g.add_argument("--senha-stdin", action="store_true", help="lê a senha da entrada padrão (uma linha)")
    g.add_argument("--senha-arquivo", metavar="ARQUIVO",
                   help="lê a senha da primeira linha deste arquivo, que precisa estar em modo 600")


def montar_parser() -> argparse.ArgumentParser:
    # nenhum valor que dependa do ambiente entra como `default`: a ajuda (e portanto docs/CLI.md) tem de ser a
    # mesma em qualquer máquina. O que falta é resolvido em app/cli/comandos.py na hora de usar.
    p = ParserPT(prog="plat", description=DESCRICAO, epilog=EPILOGO, add_help=False)
    p.add_argument("-h", "--ajuda", "--help", action="help", help="mostra esta ajuda e sai")
    p.add_argument("--base-url", default=None,
                   help="endereço da API; sem ele vale PLAT_CLI_URL, PLAT_URL_PUBLICA ou http://127.0.0.1:8150")
    p.add_argument("--credenciais", default=None,
                   help="arquivo modo 600 com 'inquilino login senha'; sem ele vale PLAT_CREDENCIAIS_ARQUIVO "
                        "ou tests/credenciais.txt")
    p.add_argument("--totp-arquivo", default=None,
                   help="arquivo modo 600 com o segredo do segundo fator; sem ele vale "
                        "PLAT_CREDENCIAIS_TOTP_ARQUIVO ou tests/credenciais_totp.txt")
    p.add_argument("--inquilino", help="identificador do inquilino em que o comando age")
    p.add_argument("--json", action="store_true", help="imprime a resposta da API em JSON")
    p.add_argument("--configurar-2fa", action="store_true",
                   help="quando a conta ainda precisa configurar o segundo fator, configura agora e guarda o "
                        "segredo no arquivo de --totp-arquivo (modo 600)")
    p.add_argument("--tempo-limite", type=float, default=60.0, help="segundos de espera por chamada (padrão: 60)")
    sub = p.add_subparsers(dest="grupo", required=True, metavar="GRUPO")

    # ---------------------------------------------------------------- inquilino
    inq = sub.add_parser("inquilino", help="inquilinos da plataforma (exige o operador da plataforma)")
    inq_sub = inq.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    inq_sub.add_parser("listar", help="lista os inquilinos").set_defaults(func=c.inquilino_listar)

    criar = inq_sub.add_parser("criar", help="cria um inquilino com o seu primeiro administrador")
    criar.add_argument("--slug", required=True, help="identificador curto (minúsculas, dígitos e hífen)")
    criar.add_argument("--nome", required=True, help="nome de exibição")
    criar.add_argument("--admin-login", required=True, help="login do primeiro administrador")
    criar.add_argument("--admin-nome", required=True, help="nome do primeiro administrador")
    criar.add_argument("--config", help="configuração inicial em JSON (centro, zoom, cotas)")
    criar.add_argument("--se-nao-existir", action="store_true",
                       help="não falha quando o inquilino já existe (é o que o install.sh usa)")
    _senha_sem_argv(criar)
    criar.set_defaults(func=c.inquilino_criar)

    susp = inq_sub.add_parser("suspender", help="suspende o inquilino (ninguém entra até reativar)")
    susp.add_argument("alvo", help="id ou identificador do inquilino")
    susp.set_defaults(func=c.inquilino_suspender)

    reat = inq_sub.add_parser("reativar", help="reativa um inquilino suspenso")
    reat.add_argument("alvo", help="id ou identificador do inquilino")
    reat.set_defaults(func=c.inquilino_reativar)

    cota = inq_sub.add_parser("cota", help="mostra ou muda a cota de armazenamento e de usuários")
    cota.add_argument("--bytes", type=int, help="nova cota de armazenamento, em bytes")
    cota.add_argument("--usuarios", type=int, help="nova cota de usuários")
    cota.set_defaults(func=c.inquilino_cota)

    # ---------------------------------------------------------------- usuário
    usu = sub.add_parser("usuario", help="usuários de um inquilino")
    usu_sub = usu.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    lista_u = usu_sub.add_parser("listar", help="lista os usuários do inquilino")
    lista_u.add_argument("--limite", type=int, default=50, help="quantos por página (padrão: 50)")
    lista_u.set_defaults(func=c.usuario_listar)

    criar_u = usu_sub.add_parser("criar", help="cria usuário")
    criar_u.add_argument("--login", required=True)
    criar_u.add_argument("--nome", required=True)
    criar_u.add_argument("--perfil", default="visualizador",
                         choices=["admin", "editor", "visualizador", "campo"], help="padrão: visualizador")
    criar_u.add_argument("--email", default=None)
    _senha_sem_argv(criar_u)
    criar_u.set_defaults(func=c.usuario_criar)

    red = usu_sub.add_parser("redefinir-senha", help="gera nova senha temporária e encerra as sessões do usuário")
    red.add_argument("alvo", help="id ou login")
    red.set_defaults(func=c.usuario_redefinir_senha)

    des = usu_sub.add_parser("desabilitar", help="desativa a conta sem apagá-la")
    des.add_argument("alvo", help="id ou login")
    des.set_defaults(func=c.usuario_desabilitar)

    rea = usu_sub.add_parser("reabilitar", help="reativa uma conta desativada")
    rea.add_argument("alvo", help="id ou login")
    rea.set_defaults(func=c.usuario_reabilitar)

    # ---------------------------------------------------------------- token
    tok = sub.add_parser("token", help="tokens de serviço do inquilino")
    tok_sub = tok.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    lista_t = tok_sub.add_parser("listar", help="lista os tokens")
    lista_t.add_argument("--todos", action="store_true", help="todos os tokens do inquilino, não só os seus")
    lista_t.set_defaults(func=c.token_listar)

    criar_t = tok_sub.add_parser("criar", help="cria token (o valor só aparece nesta saída)")
    criar_t.add_argument("--nome", required=True)
    criar_t.add_argument("--escopo", action="append", required=True, metavar="ESCOPO",
                         help="pode repetir; ex.: --escopo catalogo:ler")
    criar_t.add_argument("--validade-dias", type=int, default=None)
    criar_t.set_defaults(func=c.token_criar)

    rev = tok_sub.add_parser("revogar", help="revoga o token")
    rev.add_argument("id", type=int)
    rev.set_defaults(func=c.token_revogar)

    # ---------------------------------------------------------------- camada
    cam = sub.add_parser("camada", help="importação de camada vetorial")
    cam_sub = cam.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    imp = cam_sub.add_parser("importar", help="sobe o arquivo, inspeciona e publica a camada")
    imp.add_argument("arquivo", help="caminho do arquivo local (GeoPackage, GeoJSON, shapefile em zip, CSV)")
    imp.add_argument("--crs", type=int, default=None, metavar="SRID",
                     help="sistema de coordenadas a confirmar quando a inspeção perguntar")
    imp.add_argument("--formato", required=True,
                     help="formato do arquivo: gpkg, geojson, csv ou shapefile.zip (a API recusa o que não "
                          "souber ler, com a lista dos aceitos na mensagem)")
    imp.add_argument("--titulo", default=None, help="título do item de arquivo (padrão: nome do arquivo)")
    imp.add_argument("--codificacao", default="UTF-8", help="codificação do texto quando a inspeção perguntar")
    imp.add_argument("--sem-esperar", action="store_true", help="devolve assim que a inspeção é enfileirada")
    imp.add_argument("--espera", type=float, default=c.ESPERA_PADRAO_S,
                     help="segundos de espera por job (padrão: 180)")
    imp.set_defaults(func=c.camada_importar)

    # ---------------------------------------------------------------- job
    job = sub.add_parser("job", help="fila de trabalhos do inquilino")
    job_sub = job.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    lista_j = job_sub.add_parser("listar", help="lista os jobs")
    lista_j.add_argument("--estado", default=None, help="filtra por estado (pendente, rodando, concluido, ...)")
    lista_j.add_argument("--limite", type=int, default=50)
    lista_j.set_defaults(func=c.job_listar)
    canc = job_sub.add_parser("cancelar", help="cancela um job")
    canc.add_argument("id")
    canc.set_defaults(func=c.job_cancelar)
    rep = job_sub.add_parser("repetir", help="cria um job novo com a mesma entrada")
    rep.add_argument("id")
    rep.set_defaults(func=c.job_repetir)

    # ---------------------------------------------------------------- evento
    eve = sub.add_parser("evento", help="registro de eventos do inquilino")
    eve_sub = eve.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    exp = eve_sub.add_parser("exportar", help="exporta os eventos em JSON ou CSV")
    exp.add_argument("--desde", default=None, help="início da janela (ISO 8601)")
    exp.add_argument("--ate", default=None, help="fim da janela (ISO 8601)")
    exp.add_argument("--tipo", default=None, help="filtra por tipo de evento")
    exp.add_argument("--formato", default="json", choices=["json", "csv"])
    exp.add_argument("--saida", default=None, help="arquivo de destino (padrão: saída padrão)")
    exp.add_argument("--pagina", type=int, default=200, help="tamanho da página pedida à API")
    exp.add_argument("--maximo", type=int, default=100000, help="teto de eventos exportados")
    exp.set_defaults(func=c.evento_exportar)

    # ---------------------------------------------------------------- saúde, segredo, documentação
    sub.add_parser("saude", help="consulta /saude da API").set_defaults(func=c.saude)

    seg = sub.add_parser("segredo", help="rotação de segredo e certificado (repassa ao script do item L7-19)")
    seg_sub = seg.add_subparsers(dest="acao", required=True, metavar="AÇÃO")
    rot = seg_sub.add_parser("rotacionar", help="rotaciona um segredo; veja docs/RUNBOOKS/segredos.md")
    rot.add_argument("resto", nargs=argparse.REMAINDER,
                     help="nome do segredo e opções repassados a scripts/segredo_rotacionar.py")
    rot.set_defaults(func=c.segredo)

    doc = sub.add_parser("docs", help="regenera docs/CLI.md a partir desta descrição de comandos")
    doc.add_argument("--destino", default=None, help="caminho do arquivo gerado (padrão: docs/CLI.md)")
    doc.set_defaults(func=c.documentacao)

    return p


def main(argv: list[str] | None = None) -> int:
    argumentos = list(sys.argv[1:] if argv is None else argv)
    try:
        recusar_senha_em_argv(argumentos)
        args = montar_parser().parse_args(argumentos)
        return args.func(args)
    except ErroCLI as e:
        print(f"plat: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("plat: interrompido", file=sys.stderr)
        return 130

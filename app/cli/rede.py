"""Cliente HTTP da linha de comando `plat`: sessão com cookie, login (com segundo fator quando exigido),
leitura de credencial de arquivo com modo 600 e a regra de que senha nunca entra por argumento.

Biblioteca padrão apenas. Erros da rede e do arquivo viram `ErroCLI` com mensagem em português e sem
rastro de pilha: quem roda isto é operador, não programador, e a saída pode ir parar num log.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

TEMPO_LIMITE_S = 60


class ErroCLI(Exception):
    """Falha prevista: mensagem para o operador, sem rastro de pilha e sem segredo dentro."""


class Cliente:
    """Sessão HTTP contra a API do plat. Guarda o cookie de sessão em memória, nunca em disco."""

    def __init__(self, base_url: str, tempo_limite: float = TEMPO_LIMITE_S) -> None:
        self.base = base_url.rstrip("/")
        self.tempo_limite = tempo_limite
        self.pote = http.cookiejar.CookieJar()
        self.abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.pote))
        self.identidade: dict | None = None

    # ---------------------------------------------------------------- transporte
    def pedir(
        self,
        metodo: str,
        caminho: str,
        corpo: dict | list | None = None,
        *,
        bytes_corpo: bytes | None = None,
        content_type: str | None = None,
        cabecalhos: dict[str, str] | None = None,
    ) -> tuple[int, object]:
        """Devolve (status, corpo decodificado). Status de erro NÃO levanta: quem chama decide."""
        if corpo is not None and bytes_corpo is not None:
            raise ErroCLI("uso interno inválido: corpo JSON e corpo binário ao mesmo tempo")
        dados = bytes_corpo
        cab = dict(cabecalhos or {})
        if corpo is not None:
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            cab["Content-Type"] = "application/json"
        elif bytes_corpo is not None:
            cab["Content-Type"] = content_type or "application/octet-stream"
        pedido = urllib.request.Request(self.base + caminho, data=dados, method=metodo, headers=cab)
        try:
            with self.abridor.open(pedido, timeout=self.tempo_limite) as resposta:
                return resposta.status, _decodificar(resposta.read(), resposta.headers.get("content-type", ""))
        except urllib.error.HTTPError as e:
            return e.code, _decodificar(e.read(), e.headers.get("content-type", "") if e.headers else "")
        except urllib.error.URLError as e:
            raise ErroCLI(f"a API em {self.base} não respondeu ({e.reason}); confira --base-url e o serviço") from e
        except OSError as e:
            raise ErroCLI(f"falha de rede ao falar com {self.base}: {e}") from e

    def exigir(self, metodo: str, caminho: str, corpo=None, esperado: tuple[int, ...] = (200,), **kw) -> object:
        status, resposta = self.pedir(metodo, caminho, corpo, **kw)
        if status not in esperado:
            raise ErroCLI(f"{metodo} {caminho} devolveu {status}: {_mensagem_de_erro(resposta)}")
        return resposta

    # ---------------------------------------------------------------- identidade
    def entrar(self, slug: str, login: str, senha: str, segredo_totp: str | None = None) -> dict:
        status, corpo = self.pedir("POST", "/api/login", {"inquilino": slug, "login": login, "senha": senha})
        if status == 200 and isinstance(corpo, dict) and corpo.get("exige_2fa"):
            if not segredo_totp:
                raise ErroCLI(
                    f"{slug}/{login} exige segundo fator e nenhum segredo foi encontrado "
                    "(use --totp-arquivo ou PLAT_CREDENCIAIS_TOTP_ARQUIVO)"
                )
            from app.auth import totp  # importação tardia: só quem usa 2FA paga o custo

            desafio = corpo["desafio"]
            status, corpo = self.pedir("POST", "/api/login/2fa",
                                       {"desafio": desafio, "codigo": totp.codigo(segredo_totp)})
            if status == 401 and isinstance(corpo, dict) and corpo.get("erro") == "codigo_invalido":
                # anti-replay: o código deste passo de 30 s já foi gasto por outra execução. Espera o passo
                # seguinte e refaz o login inteiro (o desafio anterior morre junto). Uma vez só.
                import time

                time.sleep(totp.PASSO_S - (time.time() % totp.PASSO_S) + 0.5)
                status, corpo = self.pedir("POST", "/api/login",
                                           {"inquilino": slug, "login": login, "senha": senha})
                if status == 200 and isinstance(corpo, dict) and corpo.get("exige_2fa"):
                    status, corpo = self.pedir("POST", "/api/login/2fa",
                                               {"desafio": corpo["desafio"], "codigo": totp.codigo(segredo_totp)})
        if status != 200 or not isinstance(corpo, dict) or corpo.get("ok") is not True:
            raise ErroCLI(f"login de {slug}/{login} recusado ({status}): {_mensagem_de_erro(corpo)}")
        self.identidade = corpo.get("usuario") if isinstance(corpo.get("usuario"), dict) else None
        return corpo

    def sair(self) -> None:
        try:
            self.pedir("POST", "/api/logout", {})
        except ErroCLI:
            pass


def _decodificar(bruto: bytes, content_type: str) -> object:
    if not bruto:
        return None
    if "json" in content_type.lower():
        try:
            return json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return bruto.decode("utf-8", "replace")
    return bruto.decode("utf-8", "replace")


def _mensagem_de_erro(corpo: object) -> str:
    if isinstance(corpo, dict):
        return str(corpo.get("mensagem") or corpo.get("erro") or corpo)
    if corpo is None:
        return "sem corpo"
    return str(corpo)[:400]


# ---------------------------------------------------------------- credenciais em arquivo
def conferir_modo_600(caminho: Path) -> None:
    """Arquivo de credencial legível por grupo ou por outros é recusado (mesma regra do install.sh)."""
    try:
        modo = caminho.stat().st_mode
    except PermissionError as e:
        raise ErroCLI(f"sem permissão para ler {caminho}") from e
    except FileNotFoundError as e:
        raise ErroCLI(f"arquivo de credenciais {caminho} não existe") from e
    if modo & (stat.S_IRWXG | stat.S_IRWXO):
        raise ErroCLI(f"{caminho} está legível por grupo ou por outros; corrija com chmod 600 antes de usar")


def ler_credenciais(caminho: Path) -> dict[str, tuple[str, str]]:
    """`{slug: (login, senha)}` do arquivo `slug login senha` (o mesmo que o install.sh escreve, modo 600)."""
    conferir_modo_600(caminho)
    try:
        texto = caminho.read_text(encoding="utf-8")
    except PermissionError as e:
        raise ErroCLI(f"sem permissão para ler {caminho}") from e
    saida: dict[str, tuple[str, str]] = {}
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) >= 3:
            saida[partes[0]] = (partes[1], " ".join(partes[2:]))
    if not saida:
        raise ErroCLI(f"{caminho} não tem nenhuma linha no formato 'inquilino login senha'")
    return saida


def ler_totp(caminho: Path | None, slug: str) -> str | None:
    """Segredo do segundo fator guardado como `slug login segredo` (modo 600). Ausente = None."""
    if caminho is None or not caminho.exists():
        return None
    conferir_modo_600(caminho)
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if len(partes) == 3 and partes[0] == slug:
            return partes[2]
    return None


ARGUMENTOS_DE_SENHA_PROIBIDOS = ("--senha", "--password", "--pass", "-p")


def recusar_senha_em_argv(argv: list[str]) -> None:
    """Achado 6a do adversário do T1: senha em argumento aparece em `ps` e no journal do sudo. Recusa antes
    de qualquer chamada, com instrução do caminho certo (stdin ou arquivo 600)."""
    for arg in argv:
        raiz = arg.split("=", 1)[0]
        if raiz in ARGUMENTOS_DE_SENHA_PROIBIDOS:
            raise ErroCLI(
                f"{raiz} não existe de propósito: senha em argumento fica visível em `ps` e no journal. "
                "Use --senha-stdin (a senha entra pela entrada padrão) ou --senha-arquivo <arquivo modo 600>."
            )


def senha_de_entrada(args) -> str | None:
    """Senha pedida por --senha-stdin ou --senha-arquivo. Nunca por argumento."""
    if getattr(args, "senha_arquivo", None):
        caminho = Path(args.senha_arquivo)
        conferir_modo_600(caminho)
        try:
            valor = caminho.read_text(encoding="utf-8").splitlines()[0].strip()
        except PermissionError as e:
            raise ErroCLI(f"sem permissão para ler {caminho}") from e
        except IndexError as e:
            raise ErroCLI(f"{caminho} está vazio") from e
        if not valor:
            raise ErroCLI(f"a primeira linha de {caminho} está vazia")
        return valor
    if getattr(args, "senha_stdin", False):
        valor = sys.stdin.readline().strip()
        if not valor:
            raise ErroCLI("--senha-stdin: nada chegou pela entrada padrão")
        return valor
    return None


def caminho_de_env(nome: str, padrao: Path | None) -> Path | None:
    valor = os.environ.get(nome)
    return Path(valor) if valor else padrao

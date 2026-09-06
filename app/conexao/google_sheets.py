"""Google Sheets como fonte de camada (item L6-02-i-google-sheets).

Duas portas de entrada, as duas terminando na MESMA máquina do arquivo por URL (item L6-02-h — a planilha
sempre vira um CSV e segue o caminho `baixar -> detectar -> carregar` de `app/conexao/tarefas_arquivo.py`):

  1. planilha PUBLICADA na web: qualquer forma de URL de planilha do Google (`/spreadsheets/d/<id>/edit`,
     `/pubhtml`, `/export`, e a forma de publicação `/spreadsheets/d/e/<pac>/pub`) é normalizada para a URL
     canônica de exportação CSV (`export?format=csv` / `pub?output=csv&single=true`). Sem credencial — quem
     publicou a planilha já abriu o acesso.
  2. planilha PRIVADA: a credencial da conexão é o JSON da CONTA DE SERVIÇO do cliente (cifrado em repouso
     pelo mesmo `encconexao:v1:` do L6-02-a — nunca em claro no banco). Na hora da leitura, este módulo
     assina um JWT RS256 com a chave privada da conta e troca por um access token de curta duração no
     `token_uri` declarado NO PRÓPRIO JSON (fluxo `urn:ietf:params:oauth:grant-type:jwt-bearer` da RFC 7523,
     escopo `spreadsheets.readonly`, somente leitura). Sem biblioteca do Google: o JWT é assinado com a
     `cryptography`, que já é dependência, e a troca passa pela MESMA `app.conexao.seguranca.buscar_seguro`
     de sempre (defesa de SSRF intacta; o token nunca sai para outro host num redirect — ver
     `_sem_credencial_em_outro_host`).

Regra de credencial (cláusula do portão): a credencial NUNCA aparece em mensagem de erro, log ou resposta.
As exceções deste módulo carregam só o NOME do campo que faltou ou o código de erro do Google
(`invalid_grant` etc.) — nunca o e-mail da conta, nunca um trecho da chave, nunca o token.

`PLAT_SHEETS_EXPORTACAO_PREFIXO` (padrão `https://docs.google.com`) é a origem aceita para URLs de planilha
e é de onde se monta a URL de exportação. Em produção nunca se mexe; o teste de integração aponta para um
servidor local no IP público da máquina que fala os DOIS protocolos de verdade (exportação CSV e troca de
token OAuth2 com verificação RS256) — é a mesma técnica do `tests/servidor_arquivo.py` do L6-02-h.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.conexao import seguranca
from app.settings import settings

ESCOPO_SOMENTE_LEITURA = "https://www.googleapis.com/auth/spreadsheets.readonly"
GRANT_JWT_BEARER = "urn:ietf:params:oauth:grant-type:jwt-bearer"
TOKEN_TTL_S = 3600                    # máximo que o Google aceita para este fluxo
TOKEN_RENOVAR_COM_S = 60              # folga: token a menos disto do fim é trocado antes de usar
TOKEN_RESPOSTA_MAX_BYTES = 64 * 1024  # a resposta da troca é um JSON de ~1 KB; 64 KB já é folga enorme

_ID_PLANILHA = re.compile(r"^/spreadsheets/d/([A-Za-z0-9_-]{10,})(?:/|$)")
_ID_PUBLICADA = re.compile(r"^/spreadsheets/d/e/([A-Za-z0-9_-]{10,})(?:/|$)")
_GID = re.compile(r"^\d{1,12}$")

# cache de access token por (chave privada, token_uri): uma troca por hora por conta, não uma por passagem.
# O token NUNCA sai deste dicionário para log — só vai para o cabeçalho Authorization da busca seguinte.
_cache_token: dict[tuple[str, str], tuple[str, float]] = {}
_cache_trava = threading.Lock()


class ErroGoogleSheets(ValueError):
    """Recusa com motivo em português, pronto para a tela e para o `erro` do job. NUNCA carrega material de
    credencial: `motivo` é um código curto e `detalhe` é uma frase sem segredo."""

    def __init__(self, motivo: str, detalhe: str):
        self.motivo = motivo
        self.detalhe = detalhe
        super().__init__(detalhe)


# --------------------------------------------------------------------- URL da planilha
def _gid_da_url(partes) -> str | None:
    """O gid (a ABA da planilha) pode vir na query (`?gid=123`) ou no fragmento (`#gid=123`) das formas de
    URL de edição/visualização. Sem gid declarado, a exportação traz a primeira aba — que é o comportamento
    do próprio Google, então não inventamos um."""
    for bruto in (partes.query, partes.fragment):
        for valor in parse_qs(bruto).get("gid", []):
            if _GID.match(valor):
                return valor
    return None


def url_exportacao_csv(url: str, *, prefixo: str | None = None) -> str:
    """Normaliza QUALQUER forma de URL de planilha do Google para a URL canônica de exportação CSV.

    Aceita (host = o de `PLAT_SHEETS_EXPORTACAO_PREFIXO`, `docs.google.com` em produção):
      /spreadsheets/d/<id>[/edit|/view|/pubhtml|/export|...][?&#gid=N]
      /spreadsheets/d/e/<id-de-publicacao>[/pub|/pubhtml][?&#gid=N]
    Levanta `ErroGoogleSheets("url_nao_e_planilha_google")` para qualquer outra coisa — uma conexão do tipo
    `google_sheets` nunca fica registrada apontando para outro serviço."""
    origem = (prefixo or settings.PLAT_SHEETS_EXPORTACAO_PREFIXO).rstrip("/")
    host_esperado = (urlsplit(origem).hostname or "").lower()
    try:
        partes = urlsplit(url)
    except ValueError as e:
        raise ErroGoogleSheets("url_nao_e_planilha_google", f"URL malformada: {e}") from e
    if (partes.hostname or "").lower() != host_esperado:
        raise ErroGoogleSheets(
            "url_nao_e_planilha_google",
            f"a URL não é de uma planilha do Google (o endereço tem de ser do host {host_esperado})",
        )
    gid = _gid_da_url(partes)
    m = _ID_PLANILHA.match(partes.path)
    if m:
        saida = f"{origem}/spreadsheets/d/{m.group(1)}/export?format=csv"
        if gid:
            saida += f"&gid={gid}"
        return saida
    m = _ID_PUBLICADA.match(partes.path)
    if m:
        # forma "publicar na web": o CSV sai por /pub?output=csv (sem single=true o Google devolve um zip
        # com todas as abas quando há mais de uma — aqui queremos UMA aba, como no export?format=csv)
        saida = f"{origem}/spreadsheets/d/e/{m.group(1)}/pub?output=csv&single=true"
        if gid:
            saida += f"&gid={gid}"
        return saida
    raise ErroGoogleSheets(
        "url_nao_e_planilha_google",
        "a URL é do Google mas não tem o caminho de uma planilha "
        "(esperado /spreadsheets/d/<id> ou /spreadsheets/d/e/<id-de-publicacao>)",
    )


# --------------------------------------------------------------------- JSON da conta de serviço
def validar_conta_servico(texto_json: str) -> dict:
    """Confere o JSON da conta de serviço e devolve o dicionário com a chave já carregada
    (`_chave_rsa`, objeto da `cryptography`, pronto para assinar). Levanta `ErroGoogleSheets` nomeando
    apenas o CAMPO problemático — nunca o valor (a chave privada não aparece nem em pedaço)."""
    try:
        conta = json.loads(texto_json)
    except json.JSONDecodeError as e:
        raise ErroGoogleSheets("credencial_invalida", f"a credencial não é um JSON válido ({e.msg})") from e
    if not isinstance(conta, dict):
        raise ErroGoogleSheets("credencial_invalida", "a credencial não é um objeto JSON")
    if conta.get("type") != "service_account":
        raise ErroGoogleSheets(
            "credencial_invalida", "o JSON não é de uma conta de serviço (o campo 'type' não é 'service_account')"
        )
    for campo in ("client_email", "private_key", "token_uri"):
        if not isinstance(conta.get(campo), str) or not conta[campo].strip():
            raise ErroGoogleSheets("credencial_invalida", f"o campo obrigatório {campo!r} está ausente ou vazio")
    if "@" not in conta["client_email"]:
        raise ErroGoogleSheets("credencial_invalida", "o campo 'client_email' não é um endereço de e-mail")
    try:
        token_partes = urlsplit(conta["token_uri"])
    except ValueError as e:
        raise ErroGoogleSheets("credencial_invalida", "o campo 'token_uri' não é uma URL válida") from e
    if token_partes.scheme != "https" or not token_partes.hostname:
        raise ErroGoogleSheets("credencial_invalida", "o campo 'token_uri' tem de ser um endereço https")
    try:
        chave = serialization.load_pem_private_key(conta["private_key"].encode("utf-8"), password=None)
    except (ValueError, TypeError) as e:
        raise ErroGoogleSheets(
            "credencial_invalida", "o campo 'private_key' não é uma chave privada PEM legível"
        ) from e
    if not isinstance(chave, rsa.RSAPrivateKey):
        raise ErroGoogleSheets("credencial_invalida", "o campo 'private_key' não é uma chave RSA")
    conta["_chave_rsa"] = chave
    return conta


# --------------------------------------------------------------------- JWT RS256 (RFC 7519/7523)
def _b64url(bruto: bytes) -> str:
    return base64.urlsafe_b64encode(bruto).rstrip(b"=").decode("ascii")


def montar_jwt(conta: dict, *, agora: int | None = None) -> str:
    """Assertion do fluxo jwt-bearer: iss = e-mail da conta, scope = planilhas somente leitura,
    aud = token_uri, validade de 1 hora (o máximo que o Google aceita). Assinado RS256."""
    agora = agora if agora is not None else int(time.time())
    cabecalho = {"alg": "RS256", "typ": "JWT"}
    if isinstance(conta.get("private_key_id"), str) and conta["private_key_id"]:
        cabecalho["kid"] = conta["private_key_id"]
    corpo = {
        "iss": conta["client_email"],
        "scope": ESCOPO_SOMENTE_LEITURA,
        "aud": conta["token_uri"],
        "iat": agora,
        "exp": agora + TOKEN_TTL_S,
    }
    cab = _b64url(json.dumps(cabecalho, separators=(",", ":")).encode("utf-8"))
    pay = _b64url(json.dumps(corpo, separators=(",", ":")).encode("utf-8"))
    assinatura = conta["_chave_rsa"].sign(
        f"{cab}.{pay}".encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
    )
    return f"{cab}.{pay}.{_b64url(assinatura)}"


# --------------------------------------------------------------------- troca por access token
def trocar_por_token(conta: dict) -> str:
    """POST jwt-bearer no `token_uri` da conta, pela `buscar_seguro` (defesa de SSRF intacta). Devolve o
    access token. Conta revogada/desativada/sem acesso vira `ErroGoogleSheets("token_recusado")` com o
    código do Google — é exatamente o caso da refutação do item, e a mensagem nunca traz segredo."""
    chave_cache = (hashlib.sha256(conta["private_key"].encode("utf-8")).hexdigest(), conta["token_uri"])
    agora = time.time()
    with _cache_trava:
        guardado = _cache_token.get(chave_cache)
        if guardado and guardado[1] - TOKEN_RENOVAR_COM_S > agora:
            return guardado[0]

    assertion = montar_jwt(conta, agora=int(agora))
    corpo = (
        f"grant_type={GRANT_JWT_BEARER}&assertion={assertion}"
    ).encode("ascii")
    r = seguranca.buscar_seguro(
        conta["token_uri"], metodo="POST", conteudo=corpo,
        cabecalhos={"Content-Type": "application/x-www-form-urlencoded"},
        guardar_corpo=True, max_bytes=TOKEN_RESPOSTA_MAX_BYTES, max_redirects=0,
        timeout_ler=20.0,
    )
    if not r.ok or r.status != 200:
        detalhe_google = ""
        try:
            erro = json.loads(r.corpo.decode("utf-8", errors="replace")).get("error", "")
            if isinstance(erro, dict):
                erro = erro.get("code") or erro.get("message") or ""
            if erro and re.fullmatch(r"[a-z_0-9]+", str(erro)):
                detalhe_google = f" ({erro})"
        except (json.JSONDecodeError, AttributeError):
            pass
        if r.status in (400, 401, 403):
            raise ErroGoogleSheets(
                "token_recusado",
                "o Google recusou a conta de serviço"
                f"{detalhe_google}: confira se a conta continua ativa e se a planilha está compartilhada com ela",
            )
        raise ErroGoogleSheets(
            "troca_de_token_falhou", f"a troca do token de acesso falhou: {r.mensagem}"
        )
    try:
        resposta = json.loads(r.corpo.decode("utf-8"))
        token = resposta["access_token"]
        validade = min(int(resposta.get("expires_in", TOKEN_TTL_S)), TOKEN_TTL_S)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ErroGoogleSheets(
            "troca_de_token_falhou", "a resposta da troca de token não é o JSON esperado (sem access_token)"
        ) from e
    if not isinstance(token, str) or not token:
        raise ErroGoogleSheets("troca_de_token_falhou", "a resposta da troca de token veio sem access_token")
    with _cache_trava:
        _cache_token[chave_cache] = (token, agora + validade)
    return token


# --------------------------------------------------------------------- ponto único de autenticação
def cabecalhos_auth(tipo: str, credencial_em_claro: str | None) -> dict[str, str] | None:
    """Único lugar que decide COMO uma conexão autentica, para rota de teste de saúde, verificação
    periódica e sincronização de arquivo passarem pelo MESMO caminho:

      - `google_sheets` sem credencial: planilha publicada — sem cabeçalho (None).
      - `google_sheets` com credencial: a credencial é o JSON da conta de serviço; troca por access token
        (levanta `ErroGoogleSheets` em português quando o Google recusa — a camada NUNCA finge sucesso).
      - qualquer outro tipo com credencial: Bearer direto (comportamento que já existia nos itens
        L6-02-a/h/l, preservado aqui para não haver dois lugares montando Authorization).
    """
    if tipo == "google_sheets":
        if not credencial_em_claro:
            return None
        conta = validar_conta_servico(credencial_em_claro)
        return {"Authorization": f"Bearer {trocar_por_token(conta)}"}
    if credencial_em_claro:
        return {"Authorization": f"Bearer {credencial_em_claro}"}
    return None

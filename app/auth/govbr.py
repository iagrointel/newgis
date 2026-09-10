"""gov.br (Login Único) como provedor OIDC (item L0-08-c-govbr), sobre o provedor OIDC genérico do L0-08-a.
Roteiro técnico público (acesso.gov.br/roteiro-tecnico/iniciarintegracao.html): Authorization Code + PKCE S256,
escopos `openid email profile govbr_confiabilidades govbr_confiabilidades_idtoken`; `sub` do id_token é o CPF
(dado pessoal: nunca vai para log, evento, login nem `sujeito_externo` em claro — guardamos um pseudônimo SHA-256
do CPF com o issuer); `amr` traz os fatores (passwd, mfa, otp_offline...); com o escopo `_idtoken` o id_token
traz `reliability_info` {"level": "gold" | "silver" | "bronze", "reliabilities": [{"id": "801", ...}]}; sem ele, o
nível e os selos vêm da API de confiabilidades (`{api_base}/confiabilidades/v3/contas/{cpf}/niveis?response-type=ids`
e `/confiabilidades?response-type=ids`, Bearer access_token; ids "1 (Bronze)", "2 (Prata)", "3 (Ouro)").

O adaptador transforma tudo em VALORES do atributo de grupos — `nivel:bronze|prata|ouro`, `selo:<id>`,
`amr:<fator>` — e o mapeamento para perfil/papel/grupos é o do L0-08-e (valor exato, regra explícita). Nível de
conta forjado é impossível por construção: só o id_token assinado pelo issuer configurado (JWKS dele, `iss`,
`aud`, `nonce`) chega aqui (app/auth/oidc.py::validar_id_token); um id_token assinado por outro issuer com
'gold' dentro é 401 antes de qualquer leitura de claim (refutação do item, coberta em teste).

Cadastro do cliente no gov.br exige ofício do órgão (credencial real = decisão do dono, docs/PARIDADE.md);
o adaptador é provado contra um IdP sintético que reproduz o formato documentado (tests/govbr_fixture)."""

import hashlib
import logging
from typing import Any

import httpx

log = logging.getLogger("plat.govbr")

ISSUER_PRODUCAO = "https://sso.acesso.gov.br"
ISSUER_STAGING = "https://sso.staging.acesso.gov.br"
API_PRODUCAO = "https://api.acesso.gov.br"
API_STAGING = "https://api.staging.acesso.gov.br"
ESCOPOS_PADRAO = "openid email profile govbr_confiabilidades govbr_confiabilidades_idtoken"
NIVEIS = {"bronze": "bronze", "silver": "prata", "prata": "prata", "gold": "ouro", "ouro": "ouro"}
HTTP_TIMEOUT_S = 8.0
MAX_VALORES = 200


def pseudonimo(cpf: str) -> str:
    """Identificador estável sem o CPF em claro: SHA-256 dos dígitos (o mesmo cidadão dá o mesmo valor)."""
    digitos = "".join(ch for ch in str(cpf) if ch.isdigit()) or str(cpf)
    return hashlib.sha256(digitos.encode("utf-8")).hexdigest()


def nivel_de_texto(texto: Any) -> str | None:
    """'gold' | 'silver' | 'bronze' (claim) ou '3 (Ouro)' | '2' (API) -> ouro | prata | bronze."""
    if texto is None:
        return None
    t = str(texto).strip().lower()
    if t in NIVEIS:
        return NIVEIS[t]
    pares = (("ouro", "ouro"), ("prata", "prata"), ("bronze", "bronze"), ("gold", "ouro"), ("silver", "prata"))
    for chave, nome in pares:
        if chave in t:
            return nome
    if t.startswith("3"):
        return "ouro"
    if t.startswith("2"):
        return "prata"
    if t.startswith("1"):
        return "bronze"
    return None


def _id_selo(item: Any) -> str | None:
    if isinstance(item, dict):
        bruto = item.get("id")
    else:
        bruto = item
    if bruto is None:
        return None
    s = str(bruto).strip().split(" ", 1)[0]
    return s[:40] if s else None


def valores_do_id_token(claims: dict) -> list[str]:
    """Valores derivados só do id_token: nível e selos de `reliability_info`, fatores de `amr`."""
    valores: list[str] = []
    info = claims.get("reliability_info") or {}
    if isinstance(info, dict):
        nivel = nivel_de_texto(info.get("level"))
        if nivel:
            valores.append(f"nivel:{nivel}")
        for item in (info.get("reliabilities") or [])[:MAX_VALORES]:
            sid = _id_selo(item)
            if sid:
                valores.append(f"selo:{sid}")
    amr = claims.get("amr") or []
    if isinstance(amr, str):
        amr = [amr]
    for fator in list(amr)[:20]:
        f = str(fator).strip().lower()
        if f:
            valores.append(f"amr:{f}")
    return valores


def valores_da_api(api_base: str, cpf: str, access_token: str | None) -> list[str]:
    """Nível e selos pela API de confiabilidades (quando o id_token não trouxe `reliability_info`). Falha de
    rede/HTTP = lista vazia com aviso no log (o login segue com o que o id_token deu; nunca 500)."""
    if not api_base or not access_token:
        return []
    base = api_base.rstrip("/")
    cabecalhos = {"Authorization": f"Bearer {access_token}"}
    valores: list[str] = []
    try:
        r = httpx.get(
            f"{base}/confiabilidades/v3/contas/{cpf}/niveis", params={"response-type": "ids"},
            headers=cabecalhos, timeout=HTTP_TIMEOUT_S,
        )
        if r.status_code == 200:
            niveis = [nivel_de_texto(x.get("id") if isinstance(x, dict) else x) for x in (r.json() or [])]
            ordem = {"bronze": 1, "prata": 2, "ouro": 3}
            melhores = [n for n in niveis if n]
            if melhores:
                valores.append("nivel:" + max(melhores, key=lambda n: ordem[n]))
        else:
            log.warning("gov.br confiabilidades/niveis respondeu %s", r.status_code)
        r = httpx.get(
            f"{base}/confiabilidades/v3/contas/{cpf}/confiabilidades", params={"response-type": "ids"},
            headers=cabecalhos, timeout=HTTP_TIMEOUT_S,
        )
        if r.status_code == 200:
            for item in (r.json() or [])[:MAX_VALORES]:
                sid = _id_selo(item)
                if sid:
                    valores.append(f"selo:{sid}")
        else:
            log.warning("gov.br confiabilidades/confiabilidades respondeu %s", r.status_code)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("gov.br API de confiabilidades indisponível: %s", type(e).__name__)
    return valores


def valores_de(claims: dict, access_token: str | None, api_base: str | None) -> list[str]:
    """Todos os valores para o mapeamento: id_token primeiro; a API só quando o id_token não trouxe nível."""
    valores = valores_do_id_token(claims)
    if not any(v.startswith("nivel:") for v in valores) and api_base:
        valores += valores_da_api(api_base, str(claims.get("sub", "")), access_token)
    saida: list[str] = []
    for v in valores:
        if v not in saida:
            saida.append(v)
    return saida[:MAX_VALORES]


def login_de(claims: dict, sujeito_pseudonimo: str) -> str:
    """Login local nunca é o CPF: parte local do e-mail ou `govbr-<12 hex do pseudônimo>`."""
    email = claims.get("email")
    if email and "@" in email:
        base = email.split("@")[0].strip().lower().replace(" ", ".")[:120]
        if base:
            return base
    return "govbr-" + sujeito_pseudonimo[:12]

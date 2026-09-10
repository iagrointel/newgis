"""Política de autenticação por inquilino (ADR 0002 seções 6 e 11): lê `tenant.config.auth`, aplica padrões e
CORTA para a faixa (nunca deixa a política mais fraca que o padrão), valida senha nomeando a regra que falhou
(`detalhe.regra`), e valida um dicionário `auth` inteiro (esquema em Python, sem dependência) para a rota do
L0-07-a. `HASH_FANTASMA` é gerado na partida: o login verifica a senha contra ele quando o usuário não existe,
para gastar o mesmo tempo do pbkdf2 (tempo constante)."""

import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from app import limites
from app.senha import gerar_hash

log = logging.getLogger("plat.politica")
HASH_FANTASMA = gerar_hash(secrets.token_hex(16))
_LETRA = re.compile(r"[^\W\d_]", re.UNICODE)
_DIGITO = re.compile(r"\d")
_MAIUSCULA = re.compile(r"[A-ZÀ-ÖØ-Þ]")
_MINUSCULA = re.compile(r"[a-zß-öø-ÿ]")
_SIMBOLO = re.compile(r"[^\w\s]", re.UNICODE)
_DOMINIO = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

ESQUEMA_AUTH: dict[str, dict[str, Any]] = {
    chave: {"tipo": type(padrao), "padrao": padrao, "min": mn, "max": mx}
    for chave, (padrao, mn, mx) in limites.AUTH_PADROES.items()
}


@dataclass(frozen=True)
class Politica:
    senha_min: int = 10  # espelha limites.AUTH_PADROES["senha_min"][0]; piso configurável 8
    senha_maiuscula: bool = False
    senha_minuscula: bool = False
    senha_simbolo: bool = False
    senha_historico: int = 5
    senha_expira_dias: int = 0
    bloqueio_tentativas: int = 5
    bloqueio_minutos: int = 15
    bloqueio_janela_min: int = limites.BLOQUEIO_JANELA_MIN
    sessao_ociosa_horas: int = 12
    sessao_max_dias: int = 7
    exigir_2fa: bool = False
    token_max_dias: int = 365
    token_padrao_dias: int = 90
    dominios_email: tuple[str, ...] = field(default_factory=tuple)
    compartilhar_publico: bool = False

    def publica(self) -> dict:
        """O que o front precisa para repetir a regra ao vivo (nunca mais que isso)."""
        return {
            "senha_min": self.senha_min,
            "senha_maiuscula": self.senha_maiuscula,
            "senha_minuscula": self.senha_minuscula,
            "senha_simbolo": self.senha_simbolo,
            "exigir_2fa": self.exigir_2fa,
            "token_max_dias": self.token_max_dias,
            "token_padrao_dias": self.token_padrao_dias,
            "dominios_email": list(self.dominios_email),
        }


def _cortar(chave: str, valor: Any, slug: str) -> Any:
    """Valor fora da faixa vira o limite mais próximo, com aviso no journal; tipo errado vira o padrão."""
    esquema = ESQUEMA_AUTH[chave]
    padrao = esquema["padrao"]
    if isinstance(padrao, bool):
        return bool(valor) if isinstance(valor, bool) else padrao
    if isinstance(padrao, list):
        if not isinstance(valor, list) or not all(isinstance(v, str) for v in valor):
            return list(padrao)
        lista = [v.strip().lower() for v in valor if v.strip()]
        if len(lista) > esquema["max"]:
            log.warning(
                "config.auth.%s do inquilino %s tem %d entradas; cortado para %d",
                chave,
                slug,
                len(lista),
                esquema["max"],
            )
            lista = lista[: esquema["max"]]
        return lista
    if isinstance(valor, bool) or not isinstance(valor, int):
        return padrao
    if chave == "senha_expira_dias" and valor != 0 and valor < limites.SENHA_EXPIRA_MIN_DIAS:
        log.warning(
            "config.auth.senha_expira_dias do inquilino %s = %s fora de 0 ou %s–%s; cortado para %s",
            slug,
            valor,
            limites.SENHA_EXPIRA_MIN_DIAS,
            esquema["max"],
            limites.SENHA_EXPIRA_MIN_DIAS,
        )
        return limites.SENHA_EXPIRA_MIN_DIAS
    cortado = min(max(valor, esquema["min"]), esquema["max"])
    if cortado != valor:
        log.warning(
            "config.auth.%s do inquilino %s = %s fora de %s–%s; cortado para %s",
            chave,
            slug,
            valor,
            esquema["min"],
            esquema["max"],
            cortado,
        )
    return cortado


def politica_de(config: dict | None, slug: str = "?") -> Politica:
    """Política efetiva de um inquilino a partir de `tenant.config` (a chave `auth` pode faltar)."""
    auth = (config or {}).get("auth") or {}
    if not isinstance(auth, dict):
        auth = {}
    valores: dict[str, Any] = {}
    for chave, esquema in ESQUEMA_AUTH.items():
        valores[chave] = _cortar(chave, auth[chave], slug) if chave in auth else esquema["padrao"]
    if slug == "plataforma":
        valores["exigir_2fa"] = True  # inquilino técnico: 2FA obrigatório, não se desliga (ADR 0002 seção 10)
    valores["token_padrao_dias"] = min(valores["token_padrao_dias"], valores["token_max_dias"])
    valores["dominios_email"] = tuple(valores["dominios_email"])
    return Politica(**valores)


def validar_config_auth(auth: Any) -> list[dict]:
    """Erros de esquema de um dicionário `auth` como o L0-07-a receberá (422): lista vazia = válido."""
    erros = []
    if not isinstance(auth, dict):
        return [{"campo": "auth", "erro": "deve ser um objeto"}]
    for chave, valor in auth.items():
        if chave not in ESQUEMA_AUTH:
            erros.append({"campo": chave, "erro": "chave desconhecida"})
            continue
        esquema = ESQUEMA_AUTH[chave]
        padrao = esquema["padrao"]
        if isinstance(padrao, bool):
            if not isinstance(valor, bool):
                erros.append({"campo": chave, "erro": "deve ser verdadeiro ou falso"})
        elif isinstance(padrao, list):
            if not isinstance(valor, list) or not all(isinstance(v, str) and _DOMINIO.match(v.lower()) for v in valor):
                erros.append({"campo": chave, "erro": "deve ser uma lista de domínios"})
            elif len(valor) > esquema["max"]:
                erros.append({"campo": chave, "erro": f"no máximo {esquema['max']} domínios"})
        else:
            if isinstance(valor, bool) or not isinstance(valor, int):
                erros.append({"campo": chave, "erro": "deve ser um inteiro"})
            elif chave == "senha_expira_dias" and valor != 0 and not (limites.SENHA_EXPIRA_MIN_DIAS <= valor <= 365):
                erros.append({"campo": chave, "erro": "deve ser 0 ou entre 30 e 365"})
            elif not (esquema["min"] <= valor <= esquema["max"]):
                erros.append({"campo": chave, "erro": f"deve estar entre {esquema['min']} e {esquema['max']}"})
    if "token_padrao_dias" in auth and "token_max_dias" in auth and not erros:
        if auth["token_padrao_dias"] > auth["token_max_dias"]:
            erros.append({"campo": "token_padrao_dias", "erro": "não pode exceder token_max_dias"})
    return erros


def regra_da_senha(senha: str, politica: Politica, login: str = "", slug: str = "", nome: str = "") -> str | None:
    """Nome da regra violada (minimo, composicao, maximo, igual_login) ou None quando a senha passa.
    O histórico (`historico`) é conferido por quem tem os hashes (rotas), não aqui."""
    if not isinstance(senha, str) or len(senha) < politica.senha_min:
        return "minimo"
    if len(senha) > limites.SENHA_MAX:
        return "maximo"
    if not _LETRA.search(senha) or not _DIGITO.search(senha):
        return "composicao"
    if politica.senha_maiuscula and not _MAIUSCULA.search(senha):
        return "composicao"
    if politica.senha_minuscula and not _MINUSCULA.search(senha):
        return "composicao"
    if politica.senha_simbolo and not _SIMBOLO.search(senha):
        return "composicao"
    baixa = senha.strip().lower()
    for proibido in (login, slug, nome):
        if proibido and baixa == proibido.strip().lower():
            return "igual_login"
    return None


def mensagem_da_regra(regra: str, politica: Politica) -> str:
    composicao = ["letra", "número"]
    if politica.senha_maiuscula:
        composicao.append("maiúscula")
    if politica.senha_minuscula:
        composicao.append("minúscula")
    if politica.senha_simbolo:
        composicao.append("símbolo")
    base = f"a senha precisa de {politica.senha_min} caracteres com {' e '.join([', '.join(composicao[:-1]), composicao[-1]]) if len(composicao) > 1 else composicao[0]}"  # noqa: E501
    return {
        "minimo": base,
        "composicao": base,
        "maximo": f"a senha pode ter no máximo {limites.SENHA_MAX} caracteres",
        "igual_login": "a senha não pode ser igual ao usuário, ao inquilino ou ao nome",
        "historico": f"a senha não pode repetir nenhuma das {politica.senha_historico} últimas",
    }.get(regra, base)


def email_permitido(email: str | None, politica: Politica) -> bool:
    if not email or not politica.dominios_email:
        return True
    dominio = email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""
    return dominio in politica.dominios_email

"""Validação do pacote de widget externo (item L5-36): o espelho Python das regras de
`web/js/widgets/registro.js::validarManifesto` (o mesmo manifesto precisa passar nas duas pontas — na
instalação, aqui, e no carregamento, no navegador). Nome, elemento e semver seguem as MESMAS expressões;
`api_widget` diferente de 1 é recusado nomeando o widget (a acusação de API antiga)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.erros import ErroAPI

NOME_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
ELEMENTO_RE = re.compile(r"^plat-[a-z][a-z0-9-]*$")
VERSAO_RE = re.compile(r"^\d+\.\d+\.\d+$")
API_WIDGET_ATUAL = 1

# teto de pacote: widget é elemento de painel, não aplicação (o exemplo da casa tem ~2 kB)
LIMITE_MODULO_BYTES = 256 * 1024
LIMITE_I18N_CHAVES = 500
LIMITE_I18N_VALOR = 2000
CAMPOS_MANIFESTO = ("nome", "versao", "api_widget", "modulo", "elemento", "esquema_config", "eventos",
                    "acoes", "fontes", "i18n")


def _422(codigo: str, mensagem: str) -> ErroAPI:
    return ErroAPI(422, codigo, mensagem)


def validar_manifesto(m: Any) -> dict:
    """Devolve o manifesto validado (dict novo); levanta 422 nomeando o campo — a MESMA regra do
    `validarManifesto` do navegador, inclusive a recusa de API antiga."""
    if not isinstance(m, dict):
        raise _422("manifesto_invalido", "manifesto precisa ser um objeto")
    for campo in CAMPOS_MANIFESTO:
        if campo not in m:
            raise _422("manifesto_incompleto", f"manifesto sem o campo obrigatório: {campo}")
    nome = m["nome"]
    if not isinstance(nome, str) or not NOME_RE.match(nome):
        raise _422("manifesto_invalido", f"nome de widget inválido: {nome!r}")
    if not isinstance(m["elemento"], str) or not ELEMENTO_RE.match(m["elemento"]):
        raise _422("manifesto_invalido", f"elemento custom inválido: {m['elemento']!r} (precisa ser plat-*)")
    if not isinstance(m["versao"], str) or not VERSAO_RE.match(m["versao"]):
        raise _422("manifesto_invalido", f"versão não é semver: {m['versao']!r}")
    if m["api_widget"] != API_WIDGET_ATUAL:
        raise _422(
            "api_widget_incompativel",
            f"widget “{nome}” declara api_widget={m['api_widget']!r}; esta plataforma fala a API "
            f"{API_WIDGET_ATUAL} — atualize o pacote antes de instalar",
        )
    if not isinstance(m["modulo"], str) or not (m["modulo"].startswith("./") and m["modulo"].endswith(".js")):
        raise _422("manifesto_invalido", f"módulo relativo inválido: {m['modulo']!r} (forma ./algo.js)")
    for campo in ("eventos", "acoes"):
        if not isinstance(m[campo], list) or not all(isinstance(x, str) for x in m[campo]):
            raise _422("manifesto_invalido", f"manifesto.{campo} precisa ser lista de nomes")
    fontes = m["fontes"]
    if not isinstance(fontes, dict) or not isinstance(fontes.get("min"), int) or not isinstance(fontes.get("max"), int):
        raise _422("manifesto_invalido", "manifesto.fontes precisa de {min, max} inteiros")
    if fontes["min"] < 0 or fontes["max"] < fontes["min"]:
        raise _422("manifesto_invalido", "manifesto.fontes: min negativo ou max < min")
    if not isinstance(m["esquema_config"], dict):
        raise _422("manifesto_invalido", "manifesto.esquema_config precisa ser objeto (JSON Schema)")
    if not isinstance(m["i18n"], str) or not m["i18n"]:
        raise _422("manifesto_invalido", "manifesto.i18n precisa ser o prefixo das chaves do pacote")
    return {**m}


def validar_i18n(i18n: Any, prefixo: str) -> dict:
    """Chaves fora do namespace do próprio widget são recusadas — pacote nenhum sobrescreve tradução da
    casa nem de outro widget (o navegador repete a mesma regra antes de acrescentar ao dicionário)."""
    if i18n in (None, {}):
        return {}
    if not isinstance(i18n, dict):
        raise _422("i18n_invalido", "i18n precisa ser objeto {chave: texto}")
    if len(i18n) > LIMITE_I18N_CHAVES:
        raise _422("i18n_invalido", f"i18n com mais de {LIMITE_I18N_CHAVES} chaves")
    for chave, texto in i18n.items():
        if not isinstance(chave, str) or not chave.startswith(f"{prefixo}."):
            raise _422("i18n_invalido", f"chave fora do namespace do widget ({prefixo}.): {chave!r}")
        if not isinstance(texto, str) or len(texto) > LIMITE_I18N_VALOR:
            raise _422("i18n_invalido", f"texto de i18n vazio ou longo demais: {chave!r}")
    return {**i18n}


def validar_pacote(corpo: Any) -> tuple[dict, str, dict, bool]:
    """(manifesto, modulo, i18n, sandbox) a partir do corpo do POST; qualquer desvio é 422 nomeando."""
    if not isinstance(corpo, dict):
        raise _422("pacote_invalido", "o corpo precisa ser {manifesto, modulo, i18n?, sandbox?}")
    manifesto = validar_manifesto(corpo.get("manifesto"))
    modulo = corpo.get("modulo")
    if not isinstance(modulo, str) or not modulo.strip():
        raise _422("pacote_invalido", "o pacote precisa do código do módulo (modulo)")
    if len(modulo.encode("utf-8")) > LIMITE_MODULO_BYTES:
        raise _422("modulo_grande_demais",
                   f"modulo acima de {LIMITE_MODULO_BYTES // 1024} kB — widget é elemento de painel")
    i18n = validar_i18n(corpo.get("i18n"), manifesto["i18n"])
    sandbox = corpo.get("sandbox", manifesto.get("sandbox", False)) is True
    return manifesto, modulo, i18n, sandbox


def jsonb(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)

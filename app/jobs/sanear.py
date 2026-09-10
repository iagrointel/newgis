"""Saneamento do rastro de erro antes de ele virar linha de `plat.job_log` ou o campo `erro` de `plat.job`
(portão do L0-05-a: "termina falhou com o traceback SANEADO"; achado do adversário G3: a interface devolvia
`/home/dev/plataforma/...` a quem tem o privilégio `jobs.ver`).

O que sai: caminho absoluto do servidor, credencial dentro de URL e endereço de máquina interna. O que fica:
nome do arquivo, número da linha, nome da função, tipo e mensagem da exceção — que é o que serve para o
usuário relatar e para o operador achar o defeito. O caminho do repositório vira `<app>`, o da biblioteca
vira `<lib>` e o da biblioteca padrão vira `<python>`; qualquer outro caminho absoluto vira
`<oculto>/<último nome>`."""

from __future__ import annotations

import re
import sys
import sysconfig
from pathlib import Path

RAIZ_APP = str(Path(__file__).resolve().parents[2])
_LIB = sysconfig.get_paths().get("purelib") or ""
_PY = sysconfig.get_paths().get("stdlib") or ""
# do mais específico para o mais geral: purelib costuma estar DENTRO do prefixo do venv
_TROCAS: list[tuple[str, str]] = [(c, r) for c, r in (
    (_LIB, "<lib>"), (str(Path(sys.prefix).resolve()), "<venv>"), (_PY, "<python>"), (RAIZ_APP, "<app>"),
) if c]
_TROCAS.sort(key=lambda t: len(t[0]), reverse=True)

# credencial em URL (postgresql://usuario:senha@host, https://token@host)
_URL_CREDENCIAL = re.compile(r"(?P<esquema>[a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]*:?[^\s/@]*@")
# caminho absoluto que sobrou depois das trocas acima
_CAMINHO = re.compile(r"(?<![\w<])/(?:[A-Za-z0-9._+-]+/)+[A-Za-z0-9._+-]+")


def sanear(texto: str | None) -> str:
    """Devolve o texto sem caminho de servidor nem credencial. Nunca levanta: um saneador que quebra
    esconderia o erro de verdade."""
    if not texto:
        return "" if texto is None else texto
    try:
        s = str(texto)
        for caminho, rotulo in _TROCAS:
            s = s.replace(caminho, rotulo)
        s = _URL_CREDENCIAL.sub(lambda m: m.group("esquema") + "<credencial>@", s)
        return _CAMINHO.sub(lambda m: "<oculto>/" + m.group(0).rsplit("/", 1)[-1], s)
    except Exception:  # noqa: BLE001 — saneamento é auxiliar; texto cru nunca é melhor que texto saneado
        return "<rastro não pôde ser saneado>"

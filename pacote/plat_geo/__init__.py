"""SDK Python geoespacial da plataforma (item L2-16-a-sdk-python-geo). Camada "geo" sobre o SDK
genérico `plat` (`sdk/python`, item L7-08-b): catálogo, acervo, jobs e ferramentas por token de
serviço, com o vocabulário desta casa (`.catalogo`, `.acervo`, `Pagina`, `NaoEncontrado`, ...).

    from plat_geo import Plataforma
    pla = Plataforma("https://plataforma.exemplo", token="pt_…")
    pagina = pla.catalogo.listar(tipo="camada_vetorial", limite=10)
    for item in pagina.itens:
        print(item["titulo"])

Domínios: `pla.catalogo` (itens), `pla.acervo` (fontes da casa), `pla.jobs` (fila),
`pla.ferramentas` (ferramentas por job, ex.: `pla.ferramentas.buffer(geometria, 100.0)`).
Autenticação é sempre por token de serviço; toda recusa vira exceção tipada (`plat_geo.erros`).
`plat_geo.__versao__` é a versão do pacote instalado; num checkout sem instalação vale a VERSAO do
repositório lida do ambiente (PLAT_VERSAO) ou o marcador de desenvolvimento.

    >>> import plat_geo
    >>> isinstance(plat_geo.__versao__, str)
    True
    >>> sorted(n for n in plat_geo.__all__ if n.startswith("Erro"))[:2]
    ['ErroAutenticacao', 'ErroLimite']
"""

from __future__ import annotations

import importlib.metadata
import os

from plat_geo import erros
from plat_geo.acervo import Acervo
from plat_geo.catalogo import Catalogo, Pagina
from plat_geo.cliente import Plataforma
from plat_geo.erros import (
    Conflito,
    ErroAutenticacao,
    ErroLimite,
    ErroPermissao,
    ErroPlataforma,
    ErroServidor,
    ErroValidacao,
    FalhaJob,
    NaoEncontrado,
)
from plat_geo.ferramentas import Ferramentas
from plat_geo.jobs import Jobs

try:
    __versao__ = importlib.metadata.version("plat_geo")
except importlib.metadata.PackageNotFoundError:
    __versao__ = os.environ.get("PLAT_VERSAO") or "0.0.0.dev0"

__all__ = [
    "FalhaJob",
    "Acervo",
    "Catalogo",
    "Conflito",
    "ErroAutenticacao",
    "ErroLimite",
    "ErroPermissao",
    "ErroPlataforma",
    "ErroServidor",
    "ErroValidacao",
    "Ferramentas",
    "Jobs",
    "NaoEncontrado",
    "Pagina",
    "Plataforma",
    "__versao__",
    "erros",
]

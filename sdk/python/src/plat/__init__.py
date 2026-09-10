"""SDK Python `plat` da plataforma SIG (item L7-08-b-sdk-python).

Duas camadas:

- `plat_gerado`: cliente gerado por `openapi-python-client` a partir de `docs/openapi.json`
  (não editar à mão; regenerado por `scripts/gerar_sdk.sh`).
- `plat`: esta camada, escrita à mão, com a classe `Plataforma` ergonômica
  (`Plataforma(url, token).itens.listar()`, `.jobs.esperar()`, etc.) e os erros traduzidos.

Uso mínimo::

    from plat import Plataforma

    p = Plataforma("https://SEU-INQUILINO.exemplo/", token="plat_...")
    pagina = p.itens.listar(tipo="camada_vetorial")
    camada = p.camadas.criar(titulo="Minha camada", dados={})
"""

from .cliente import Plataforma
from .erros import ErroPlataforma

__all__ = ["Plataforma", "ErroPlataforma"]
__version__ = "0.1.0"

"""Import preguiçoso de biblioteca pesada (item L2-04-e, medido em 18/09/2026).

`import geopandas`/`scipy`/`pandas` no TOPO de um módulo montado pelo `app.main` custa dezenas de MB de
RSS em CADA worker, mesmo quando a requisição nunca chega perto da função que a usa — e o portão de
exportação em streaming mede o RSS total do worker. O proxy abaixo deixa o nome existir no módulo, mas o
pacote só é importado no primeiro uso real (atributo ou chamada). Depois do primeiro uso, o pacote fica
em `sys.modules` e o custo é uma consulta de dicionário.

Limitação deliberada: serve para chamar e ler atributo (`gpd.GeoDataFrame(...)`, `ndimage.zoom(...)`,
`cKDTree(a)`). NÃO serve para `isinstance`, `issubclass`, herança ou `pickle` contra o proxy — nesses
casos, importe de verdade dentro da função.
"""

import importlib


class Tardio:
    """Proxy de módulo (ou de um atributo dele) que importa o pacote no primeiro toque."""

    def __init__(self, alvo: str, atributo: str | None = None):
        self._alvo, self._atributo, self._valor = alvo, atributo, None

    def _carregar(self):
        if self._valor is None:
            mod = importlib.import_module(self._alvo)
            self._valor = getattr(mod, self._atributo) if self._atributo else mod
        return self._valor

    def __getattr__(self, nome: str):
        return getattr(self._carregar(), nome)

    def __call__(self, *args, **kwargs):
        return self._carregar()(*args, **kwargs)

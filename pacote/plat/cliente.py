"""Cliente HTTP do SDK: a classe `Plataforma(url, token)`. Uma instância por credencial; os domínios
(`pla.catalogo`, `pla.acervo`, `pla.jobs`, `pla.ferramentas`) são propriedades criadas na primeira
utilização. Autenticação sempre por token de serviço no cabeçalho `Authorization: Bearer` (o SDK
nunca faz login com senha: token se cria pela UI ou por `POST /api/tokens` numa sessão).

Exemplo (nos doctests a suíte injeta `pla`, uma `Plataforma` conectada à instalação de demo):

    >>> isinstance(pla, Plataforma)
    True
    >>> pagina = pla.catalogo.listar(limite=3)
    >>> pagina.total >= len(pagina.itens) >= 0
    True
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from plat import erros

TEMPO_PADRAO_S = 60.0


class Plataforma:
    """Ponto único de entrada do SDK. `verificar_tls=False` aceita só para instalação de teste com
    certificado da casa (nunca com a URL pública de produção)."""

    def __init__(self, url: str, token: str, *, timeout_s: float = TEMPO_PADRAO_S,
                 verificar_tls: bool = True, cabecalhos: dict[str, str] | None = None):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s
        self.cabecalhos = {"Authorization": f"Bearer {token}", **(cabecalhos or {})}
        self.sessao = requests.Session()
        self.sessao.verify = verificar_tls
        self._dominios: dict[str, Any] = {}

    # ------------------------------------------------------------------ HTTP
    def _pede(self, metodo: str, caminho: str, **kw) -> Any:
        """Requisição com mapeamento de status para exceção; devolve o JSON decodificado (ou None em 204)."""
        resposta = self.sessao.request(metodo, urljoin(self.url + "/", caminho.lstrip("/")),
                                       headers=self.cabecalhos, timeout=self.timeout_s, **kw)
        if resposta.status_code >= 400:
            try:
                corpo: Any = resposta.json()
            except ValueError:
                corpo = resposta.text[:500]
            raise erros.por_resposta(resposta.status_code, corpo)
        if resposta.status_code == 204 or not resposta.content:
            return None
        return resposta.json()

    def get(self, caminho: str, params: dict | None = None) -> Any:
        return self._pede("GET", caminho, params=params)

    def post(self, caminho: str, json: Any = None) -> Any:
        return self._pede("POST", caminho, json=json)

    def patch(self, caminho: str, json: Any = None) -> Any:
        return self._pede("PATCH", caminho, json=json)

    def put(self, caminho: str, json: Any = None) -> Any:
        return self._pede("PUT", caminho, json=json)

    def delete(self, caminho: str) -> Any:
        return self._pede("DELETE", caminho)

    # -------------------------------------------------------------- domínios
    @property
    def catalogo(self):
        """Catálogo de itens (`plat.catalogo.Catalogo`)."""
        if "catalogo" not in self._dominios:
            from plat.catalogo import Catalogo

            self._dominios["catalogo"] = Catalogo(self)
        return self._dominios["catalogo"]

    @property
    def acervo(self):
        """Acervo da casa (`plat.acervo.Acervo`)."""
        if "acervo" not in self._dominios:
            from plat.acervo import Acervo

            self._dominios["acervo"] = Acervo(self)
        return self._dominios["acervo"]

    @property
    def jobs(self):
        """Fila de jobs (`plat.jobs.Jobs`)."""
        if "jobs" not in self._dominios:
            from plat.jobs import Jobs

            self._dominios["jobs"] = Jobs(self)
        return self._dominios["jobs"]

    @property
    def ferramentas(self):
        """Ferramentas por job (`plat.ferramentas.Ferramentas`)."""
        if "ferramentas" not in self._dominios:
            from plat.ferramentas import Ferramentas

            self._dominios["ferramentas"] = Ferramentas(self)
        return self._dominios["ferramentas"]

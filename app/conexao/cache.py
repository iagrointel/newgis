"""Cache curto de resposta de serviço externo (item L6-02-c-wfs-ogcapi, modo REFERENCIADO).

O modo referenciado consulta o serviço a cada pedido do usuário. Sem cache, uma tela que arrasta o mapa vira
uma rajada de `GetFeature` no serviço do órgão — que é justamente o que faz um serviço público bloquear o
nosso endereço. O cache é de propósito CURTO (`CONEXAO_VETOR_CACHE_TTL_S`, hoje 30 s): o valor da camada
referenciada é ser ao vivo, então guardar por muito tempo trocaria o problema por outro (dado velho servido
como atual, que é pior).

Ele mora NO PROCESSO (dicionário com validade e teto de entradas), não em Redis nem no banco: cada processo
de API tem o seu, e a consequência — dois processos podem devolver respostas de instantes diferentes dentro
da mesma janela de 30 s — está escrita aqui e no MANUAL, nunca escondida. A chave inclui o inquilino e a
conexão, então uma consulta de um inquilino nunca serve resposta para outro.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from app import limites

_trava = threading.Lock()
_entradas: dict[tuple, tuple[float, Any]] = {}
_acertos = 0
_erros = 0


def obter(chave: tuple) -> Any | None:
    global _acertos, _erros
    agora = time.monotonic()
    with _trava:
        item = _entradas.get(chave)
        if item is None or item[0] < agora:
            if item is not None:
                _entradas.pop(chave, None)
            _erros += 1
            return None
        _acertos += 1
        return item[1]


def guardar(chave: tuple, valor: Any, ttl_s: float | None = None) -> None:
    ttl = limites.CONEXAO_VETOR_CACHE_TTL_S if ttl_s is None else ttl_s
    agora = time.monotonic()
    with _trava:
        if len(_entradas) >= limites.CONEXAO_VETOR_CACHE_ENTRADAS:
            # limpeza barata: tira o que já venceu; se nada venceu, tira a entrada que vence primeiro
            vencidas = [k for k, (ate, _) in _entradas.items() if ate < agora]
            for k in vencidas:
                _entradas.pop(k, None)
            if len(_entradas) >= limites.CONEXAO_VETOR_CACHE_ENTRADAS:
                mais_velha = min(_entradas, key=lambda k: _entradas[k][0])
                _entradas.pop(mais_velha, None)
        _entradas[chave] = (agora + ttl, valor)


def esquecer(prefixo: tuple) -> int:
    """Tira do cache tudo que começa com `prefixo` (usado quando a conexão muda de URL ou é apagada: servir a
    resposta da URL antiga depois da edição seria mentira, não cache)."""
    with _trava:
        alvos = [k for k in _entradas if k[: len(prefixo)] == prefixo]
        for k in alvos:
            _entradas.pop(k, None)
        return len(alvos)


def estatisticas() -> dict:
    with _trava:
        return {"entradas": len(_entradas), "acertos": _acertos, "erros": _erros}


def limpar() -> None:
    """Só para teste e para o desligamento; produção nunca chama."""
    global _acertos, _erros
    with _trava:
        _entradas.clear()
        _acertos = _erros = 0

"""Apoio à dupla-chave de `PLAT_SECRET` (item L7-19-segredos-e-certificados; docs/RUNBOOKS/segredos.md).

Quatro pontos da aplicação cifram em repouso com uma chave derivada de `PLAT_SECRET` (AES-GCM, cada um
com seu próprio prefixo e AAD): `app/auth/totp.py` (segredo TOTP), `app/conexao/credencial.py`
(credencial de conexão externa), `app/correio/cifra.py` (senha SMTP por inquilino) e `app/auth/ldap.py`
(senha de bind LDAP). Uma URL de objeto assinada (`app/objetos.py`) usa o mesmo segredo para HMAC, não
para cifra — trata a dupla-chave por conta própria, sem passar por aqui.

Quando `plat segredo rotacionar PLAT_SECRET` troca o valor, tudo que foi cifrado/assinado com o valor
ANTIGO fica ilegível para quem só tenta o valor NOVO. Por isso o valor antigo continua disponível por
24h em `PLAT_SECRET_ANTERIOR` (settings.py, LoadCredential=, nunca no `.env`): esta função tenta o atual
primeiro e cai para o anterior só se o atual falhar — nunca o contrário, para que tudo gravado depois da
rotação já use exclusivamente a chave nova."""

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def decifrar_com_rotacao(decifrar: Callable[[str, str], T], armazenado: str, atual: str, anterior: str | None) -> T:
    """`decifrar(armazenado, atual)`; se levantar (prefixo errado, AEAD `InvalidTag`, base64 inválido) e
    houver `anterior`, tenta `decifrar(armazenado, anterior)`. Sem `anterior`, a exceção original sobe —
    é o comportamento de sempre (usuário cai no caminho de "segredo ilegível" já existente em cada
    chamador, ex. `app/auth/rotas_login.py`)."""
    try:
        return decifrar(armazenado, atual)
    except Exception:
        if not anterior:
            raise
        return decifrar(armazenado, anterior)

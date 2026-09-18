from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/imagens/conexao-s3",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | None:
    if response.status_code == 200:
        return None

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Conexao S3

     Credencial S3 SÓ-LEITURA do balde DESTE inquilino, para o `Create Cloud Storage Connection File`
    do ArcGIS Pro e para `/vsis3/` do QGIS/GDAL — a "Porta 2" do item L1-02-e.

    Por que existe: o ArcGIS Pro não abre COG por URL direta (pedido aberto na comunidade Esri); o que
    ele abre é um armazenamento em nuvem configurado num `.acs`, com provedor "Amazon S3" e um
    `Service End Point` próprio. A chave só-leitura por inquilino JÁ era criada em
    `app/objetos.py::garantir_bucket` (`<alias>-ro`, `read=true, write=false, owner=false` no Garage);
    o que faltava era uma porta que a entregasse ao dono do dado. Passo a passo em
    `docs/PRO_CONEXAO.md`.

    Três travas deliberadas:
    1. SÓ SESSÃO (`so_sessao=True`): um token de serviço não emite credencial de armazenamento — senão
       um token de tiles viraria escada para o balde inteiro.
    2. Exige o privilégio `conteudo.publicar_camada` (quem publica dado do inquilino), não leitura.
    3. Devolve SEMPRE a chave `ro`, nunca a `rw`. A de escrita não sai deste servidor por rota nenhuma.

    O segredo vai no CORPO da resposta e em lugar nenhum mais: não entra em log (o registro de evento
    grava só que a credencial foi entregue, nunca o valor) e a resposta é `no-store`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[Any]:
    """Conexao S3

     Credencial S3 SÓ-LEITURA do balde DESTE inquilino, para o `Create Cloud Storage Connection File`
    do ArcGIS Pro e para `/vsis3/` do QGIS/GDAL — a "Porta 2" do item L1-02-e.

    Por que existe: o ArcGIS Pro não abre COG por URL direta (pedido aberto na comunidade Esri); o que
    ele abre é um armazenamento em nuvem configurado num `.acs`, com provedor "Amazon S3" e um
    `Service End Point` próprio. A chave só-leitura por inquilino JÁ era criada em
    `app/objetos.py::garantir_bucket` (`<alias>-ro`, `read=true, write=false, owner=false` no Garage);
    o que faltava era uma porta que a entregasse ao dono do dado. Passo a passo em
    `docs/PRO_CONEXAO.md`.

    Três travas deliberadas:
    1. SÓ SESSÃO (`so_sessao=True`): um token de serviço não emite credencial de armazenamento — senão
       um token de tiles viraria escada para o balde inteiro.
    2. Exige o privilégio `conteudo.publicar_camada` (quem publica dado do inquilino), não leitura.
    3. Devolve SEMPRE a chave `ro`, nunca a `rw`. A de escrita não sai deste servidor por rota nenhuma.

    O segredo vai no CORPO da resposta e em lugar nenhum mais: não entra em log (o registro de evento
    grava só que a credencial foi entregue, nunca o valor) e a resposta é `no-store`.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)

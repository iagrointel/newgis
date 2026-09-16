from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.lsa_entrada import LsaEntrada
from ...types import Response


def _get_kwargs(
    *,
    body: LsaEntrada,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/parcelas/fabrica/analyzeByLSA",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: LsaEntrada,
) -> Response[Any | HTTPValidationError]:
    """Analyze By Lsa

     AnalyzeByLSA (forma da doc `.../ParcelFabricServer/analyzeByLSA`): resolve a rede das
    parcelas pedidas e DEVOLVE O RELATÓRIO sem escrever nada — nem coordenada, nem precisão
    (a prova é o checksum da malha no teste). CONSISTENCY_CHECK devolve o mesmo relatório com
    a lista de suspeitas (|v/sigma| > 3) sem nunca mover ponto.

    Args:
        body (LsaEntrada): Analyze/apply na forma da doc (analysisType, convergenceTolerance,
            parcelFeatures). O
            campo `semLinhas` é extra declarado da casa (§13): medida excluída DA RODADA por ser
            grosseira — o ajuste não apaga medida, só deixa de usá-la.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: LsaEntrada,
) -> Any | HTTPValidationError | None:
    """Analyze By Lsa

     AnalyzeByLSA (forma da doc `.../ParcelFabricServer/analyzeByLSA`): resolve a rede das
    parcelas pedidas e DEVOLVE O RELATÓRIO sem escrever nada — nem coordenada, nem precisão
    (a prova é o checksum da malha no teste). CONSISTENCY_CHECK devolve o mesmo relatório com
    a lista de suspeitas (|v/sigma| > 3) sem nunca mover ponto.

    Args:
        body (LsaEntrada): Analyze/apply na forma da doc (analysisType, convergenceTolerance,
            parcelFeatures). O
            campo `semLinhas` é extra declarado da casa (§13): medida excluída DA RODADA por ser
            grosseira — o ajuste não apaga medida, só deixa de usá-la.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: LsaEntrada,
) -> Response[Any | HTTPValidationError]:
    """Analyze By Lsa

     AnalyzeByLSA (forma da doc `.../ParcelFabricServer/analyzeByLSA`): resolve a rede das
    parcelas pedidas e DEVOLVE O RELATÓRIO sem escrever nada — nem coordenada, nem precisão
    (a prova é o checksum da malha no teste). CONSISTENCY_CHECK devolve o mesmo relatório com
    a lista de suspeitas (|v/sigma| > 3) sem nunca mover ponto.

    Args:
        body (LsaEntrada): Analyze/apply na forma da doc (analysisType, convergenceTolerance,
            parcelFeatures). O
            campo `semLinhas` é extra declarado da casa (§13): medida excluída DA RODADA por ser
            grosseira — o ajuste não apaga medida, só deixa de usá-la.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: LsaEntrada,
) -> Any | HTTPValidationError | None:
    """Analyze By Lsa

     AnalyzeByLSA (forma da doc `.../ParcelFabricServer/analyzeByLSA`): resolve a rede das
    parcelas pedidas e DEVOLVE O RELATÓRIO sem escrever nada — nem coordenada, nem precisão
    (a prova é o checksum da malha no teste). CONSISTENCY_CHECK devolve o mesmo relatório com
    a lista de suspeitas (|v/sigma| > 3) sem nunca mover ponto.

    Args:
        body (LsaEntrada): Analyze/apply na forma da doc (analysisType, convergenceTolerance,
            parcelFeatures). O
            campo `semLinhas` é extra declarado da casa (§13): medida excluída DA RODADA por ser
            grosseira — o ajuste não apaga medida, só deixa de usá-la.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed

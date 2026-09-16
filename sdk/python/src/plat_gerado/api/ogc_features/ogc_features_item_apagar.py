from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    colecao_id: str,
    feature_id: str,
    *,
    if_match: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(if_match, Unset):
        headers["if-match"] = if_match

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/ogc/features/{item_id}/collections/{colecao_id}/items/{feature_id}".format(
            item_id=quote(str(item_id), safe=""),
            colecao_id=quote(str(colecao_id), safe=""),
            feature_id=quote(str(feature_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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
    item_id: str,
    colecao_id: str,
    feature_id: str,
    *,
    client: AuthenticatedClient | Client,
    if_match: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Item Apagar

    Args:
        item_id (str):
        colecao_id (str):
        feature_id (str):
        if_match (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        colecao_id=colecao_id,
        feature_id=feature_id,
        if_match=if_match,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    colecao_id: str,
    feature_id: str,
    *,
    client: AuthenticatedClient | Client,
    if_match: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Item Apagar

    Args:
        item_id (str):
        colecao_id (str):
        feature_id (str):
        if_match (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        colecao_id=colecao_id,
        feature_id=feature_id,
        client=client,
        if_match=if_match,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    colecao_id: str,
    feature_id: str,
    *,
    client: AuthenticatedClient | Client,
    if_match: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Item Apagar

    Args:
        item_id (str):
        colecao_id (str):
        feature_id (str):
        if_match (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        colecao_id=colecao_id,
        feature_id=feature_id,
        if_match=if_match,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    colecao_id: str,
    feature_id: str,
    *,
    client: AuthenticatedClient | Client,
    if_match: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Item Apagar

    Args:
        item_id (str):
        colecao_id (str):
        feature_id (str):
        if_match (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            colecao_id=colecao_id,
            feature_id=feature_id,
            client=client,
            if_match=if_match,
        )
    ).parsed

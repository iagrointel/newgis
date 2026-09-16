from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    *,
    relationship_id: str,
    object_ids: str | Unset = "",
    result_offset: int | Unset = 0,
    result_record_count: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["relationshipId"] = relationship_id

    params["objectIds"] = object_ids

    params["resultOffset"] = result_offset

    json_result_record_count: int | None | Unset
    if isinstance(result_record_count, Unset):
        json_result_record_count = UNSET
    else:
        json_result_record_count = result_record_count
    params["resultRecordCount"] = json_result_record_count

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/rest/services/{item_id}/FeatureServer/0/queryRelatedRecords".format(
            item_id=quote(str(item_id), safe=""),
        ),
        "params": params,
    }

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
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    relationship_id: str,
    object_ids: str | Unset = "",
    result_offset: int | Unset = 0,
    result_record_count: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Query Related Records

     Mesmo dado de `/api/camadas/{id}/relacionados/{rel}`, na forma que o ArcGIS Pro/Map Viewer esperam:
    `relationshipId` é o NOME direto/inverso (a Esri usa um inteiro pequeno estável; aqui o nome já é
    estável e o inteiro seria mais um mapeamento sem ganho — o portão pede paridade de DADO, não de
    forma
    de endereçar, e o teste de paridade confere os mesmos fids/valores nos dois formatos).

    Args:
        item_id (str):
        relationship_id (str):
        object_ids (str | Unset):  Default: ''.
        result_offset (int | Unset):  Default: 0.
        result_record_count (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        relationship_id=relationship_id,
        object_ids=object_ids,
        result_offset=result_offset,
        result_record_count=result_record_count,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    relationship_id: str,
    object_ids: str | Unset = "",
    result_offset: int | Unset = 0,
    result_record_count: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Query Related Records

     Mesmo dado de `/api/camadas/{id}/relacionados/{rel}`, na forma que o ArcGIS Pro/Map Viewer esperam:
    `relationshipId` é o NOME direto/inverso (a Esri usa um inteiro pequeno estável; aqui o nome já é
    estável e o inteiro seria mais um mapeamento sem ganho — o portão pede paridade de DADO, não de
    forma
    de endereçar, e o teste de paridade confere os mesmos fids/valores nos dois formatos).

    Args:
        item_id (str):
        relationship_id (str):
        object_ids (str | Unset):  Default: ''.
        result_offset (int | Unset):  Default: 0.
        result_record_count (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        client=client,
        relationship_id=relationship_id,
        object_ids=object_ids,
        result_offset=result_offset,
        result_record_count=result_record_count,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    relationship_id: str,
    object_ids: str | Unset = "",
    result_offset: int | Unset = 0,
    result_record_count: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Query Related Records

     Mesmo dado de `/api/camadas/{id}/relacionados/{rel}`, na forma que o ArcGIS Pro/Map Viewer esperam:
    `relationshipId` é o NOME direto/inverso (a Esri usa um inteiro pequeno estável; aqui o nome já é
    estável e o inteiro seria mais um mapeamento sem ganho — o portão pede paridade de DADO, não de
    forma
    de endereçar, e o teste de paridade confere os mesmos fids/valores nos dois formatos).

    Args:
        item_id (str):
        relationship_id (str):
        object_ids (str | Unset):  Default: ''.
        result_offset (int | Unset):  Default: 0.
        result_record_count (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        relationship_id=relationship_id,
        object_ids=object_ids,
        result_offset=result_offset,
        result_record_count=result_record_count,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    *,
    client: AuthenticatedClient | Client,
    relationship_id: str,
    object_ids: str | Unset = "",
    result_offset: int | Unset = 0,
    result_record_count: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Query Related Records

     Mesmo dado de `/api/camadas/{id}/relacionados/{rel}`, na forma que o ArcGIS Pro/Map Viewer esperam:
    `relationshipId` é o NOME direto/inverso (a Esri usa um inteiro pequeno estável; aqui o nome já é
    estável e o inteiro seria mais um mapeamento sem ganho — o portão pede paridade de DADO, não de
    forma
    de endereçar, e o teste de paridade confere os mesmos fids/valores nos dois formatos).

    Args:
        item_id (str):
        relationship_id (str):
        object_ids (str | Unset):  Default: ''.
        result_offset (int | Unset):  Default: 0.
        result_record_count (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
            relationship_id=relationship_id,
            object_ids=object_ids,
            result_offset=result_offset,
            result_record_count=result_record_count,
        )
    ).parsed

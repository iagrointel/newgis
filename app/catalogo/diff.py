"""Diferença entre dois documentos JSON no formato JSON Patch (RFC 6902): operações add/remove/replace, recursiva
sobre dicionários e listas (ADR 0004 seção 4.2). Sem dependência; o cliente só mostra."""

from typing import Any


def _escapar(parte: Any) -> str:
    return str(parte).replace("~", "~0").replace("/", "~1")


def _caminho(partes: list) -> str:
    return "/" + "/".join(_escapar(p) for p in partes) if partes else ""


def patch(antes: Any, depois: Any, _partes: list | None = None) -> list[dict]:
    partes = _partes or []
    if isinstance(antes, dict) and isinstance(depois, dict):
        ops: list[dict] = []
        for chave in sorted(set(antes) | set(depois)):
            if chave not in antes:
                ops.append({"op": "add", "path": _caminho(partes + [chave]), "value": depois[chave]})
            elif chave not in depois:
                ops.append({"op": "remove", "path": _caminho(partes + [chave])})
            else:
                ops.extend(patch(antes[chave], depois[chave], partes + [chave]))
        return ops
    if isinstance(antes, list) and isinstance(depois, list):
        ops = []
        comum = min(len(antes), len(depois))
        for i in range(comum):
            ops.extend(patch(antes[i], depois[i], partes + [i]))
        for i in range(comum, len(depois)):
            ops.append({"op": "add", "path": _caminho(partes + [i]), "value": depois[i]})
        # remoções do fim para o início, para os índices continuarem válidos ao aplicar
        for i in range(len(antes) - 1, comum - 1, -1):
            ops.append({"op": "remove", "path": _caminho(partes + [i])})
        return ops
    if antes == depois and type(antes) is type(depois):
        return []
    return [{"op": "replace", "path": _caminho(partes), "value": depois}]


def aplicar(documento: Any, operacoes: list[dict]) -> Any:
    """Aplica um patch (só para o teste de ida e volta); devolve o documento novo."""
    import copy

    doc = copy.deepcopy(documento)
    for op in operacoes:
        partes = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].split("/")[1:]] if op["path"] else []
        if not partes:
            doc = copy.deepcopy(op.get("value"))
            continue
        alvo = doc
        for p in partes[:-1]:
            alvo = alvo[int(p)] if isinstance(alvo, list) else alvo[p]
        ultimo = partes[-1]
        if isinstance(alvo, list):
            i = int(ultimo)
            if op["op"] == "add":
                alvo.insert(i, op["value"])
            elif op["op"] == "remove":
                del alvo[i]
            else:
                alvo[i] = op["value"]
        elif op["op"] == "remove":
            del alvo[ultimo]
        else:
            alvo[ultimo] = op["value"]
    return doc

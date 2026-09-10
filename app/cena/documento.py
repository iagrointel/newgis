"""Conferência do documento de cena (item L2-09-b-cena-extrusao-slides).

O esquema JSON do tipo `cena` (db/migracoes/20260908T0601_cena_esquema.sql) já cuida de formato: tipo de
cada campo, faixa dos ângulos, padrão do ULID/uuid/cor. Aqui entra só o que precisa olhar o documento
INTEIRO — exatamente o mesmo desenho de `app/catalogo/documento.validar_grafo`, que faz isso para o
grafo dos construtores do L5:

1. duas camadas (ou dois slides) com o mesmo `id`;
2. slide que cita, em `camadas_visiveis`, uma camada que não está em `corpo.camadas` — o slide não
   restauraria a cena que promete;
3. camada desenhada como extrusão sem altura nenhuma (nem `campo_altura`, nem `altura_fixa`): o
   MapLibre desenharia um chão de altura zero em silêncio, e a cena pareceria vazia sem erro;
4. base acima do topo quando as duas alturas são fixas (a caixa seria negativa).

Erro vira 422 `cena_invalida`, no mesmo contrato de lista de campos das outras validações
(app/erros.py), para o editor apontar o campo errado.
"""

from __future__ import annotations

from app.erros import ErroAPI

TIPO = "cena"


def _corpo(tipo: str, dados) -> dict | None:
    if tipo != TIPO or not isinstance(dados, dict):
        return None
    corpo = dados.get("corpo")
    return corpo if isinstance(corpo, dict) else None


def _lista(corpo: dict, chave: str) -> list:
    valor = corpo.get(chave, [])
    return valor if isinstance(valor, list) else []


def erros_de(tipo: str, dados) -> list[dict]:
    corpo = _corpo(tipo, dados)
    if corpo is None:
        return []
    erros: list[dict] = []

    ids_camada: set[str] = set()
    for i, camada in enumerate(_lista(corpo, "camadas")):
        if not isinstance(camada, dict):
            continue
        cid = camada.get("id")
        if isinstance(cid, str):
            if cid in ids_camada:
                erros.append({"campo": f"corpo.camadas.{i}.id", "erro": f"id de camada repetido: {cid}",
                              "regra": "id_duplicado"})
            ids_camada.add(cid)
        if camada.get("desenho", "extrusao") != "extrusao":
            continue
        ext = camada.get("extrusao") if isinstance(camada.get("extrusao"), dict) else {}
        campo_altura = ext.get("campo_altura")
        altura_fixa = ext.get("altura_fixa")
        if not campo_altura and altura_fixa is None:
            erros.append({
                "campo": f"corpo.camadas.{i}.extrusao",
                "erro": "extrusão sem altura: declare campo_altura (atributo) ou altura_fixa (metros)",
                "regra": "extrusao_sem_altura",
            })
            continue
        base_fixa = ext.get("base_fixa")
        if altura_fixa is not None and base_fixa is not None and base_fixa > altura_fixa:
            erros.append({
                "campo": f"corpo.camadas.{i}.extrusao.base_fixa",
                "erro": "a base fixa está acima do topo fixo",
                "regra": "base_acima_do_topo",
            })

    ids_slide: set[str] = set()
    for i, slide in enumerate(_lista(corpo, "slides")):
        if not isinstance(slide, dict):
            continue
        sid = slide.get("id")
        if isinstance(sid, str):
            if sid in ids_slide:
                erros.append({"campo": f"corpo.slides.{i}.id", "erro": f"id de slide repetido: {sid}",
                              "regra": "id_duplicado"})
            ids_slide.add(sid)
        visiveis = slide.get("camadas_visiveis")
        if not isinstance(visiveis, list):
            continue
        for j, alvo in enumerate(visiveis):
            if isinstance(alvo, str) and alvo not in ids_camada:
                erros.append({
                    "campo": f"corpo.slides.{i}.camadas_visiveis.{j}",
                    "erro": f"o slide cita uma camada que não está na cena: {alvo}",
                    "regra": "camada_inexistente",
                })
    return erros


def validar(tipo: str, dados) -> None:
    erros = erros_de(tipo, dados)
    if erros:
        raise ErroAPI(422, "cena_invalida", "documento de cena inconsistente", erros)


__all__ = ["TIPO", "erros_de", "validar"]

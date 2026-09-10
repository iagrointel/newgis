"""Metadado do fator do motor multicritério (item L3-15-metadado-fator, decisão A11 do
`laco/decomposicao/L3L6_CONCEITO.md`).

Cada fator do modelo (`docs/esquemas/amc_modelo.v1.json`) carrega, além da camada e da conta:

- `fonte` e `versao_fonte`: quem publica o dado e em que edição ele foi lido;
- `unidade` e `direcao`: a grandeza do valor bruto e para que lado ela é boa;
- `base`: por que o fator pesa — norma, engenharia ou preferência;
- `proxy`: declaração de que a camada mede uma grandeza DIFERENTE do gatilho, com teto de peso;
- `classe_peso`: de onde o peso vem — custo medido em R$, apetite de risco ou consequência normativa;
- `ancora_peso`: se o peso foi medido ou escolhido;
- `nao_sustenta`: o que aquele fator não permite concluir.

Os cinco últimos campos vêm do motor de linha de transmissão da casa (`rs-coop/tracado-lt/motor/pesos.py`
e `motor/camadas.py`). O teto de proxy é a regra que ali se chama `TETO_PROXY = 0.60`: uma camada que mede
presença declarada de vegetação, e não supressão de árvore, não pode pesar como se medisse o gatilho legal,
porque subir o peso de quem mede a coisa errada amplifica o erro em vez de corrigi-lo.

O que muda aqui em relação ao motor de LT: lá os pesos vivem numa escala fixa `[w_min, w_max]` e o teto é
`w_min + TETO_PROXY * (w_max - w_min)`. No motor da plataforma o peso é um multiplicador livre (≥ 0), então
"fração da escala" não tem sentido absoluto: o que existe é a FATIA que o fator toma do modelo,
`peso_i / Σ pesos`, que é exatamente o que a soma ponderada normalizada usa e é invariante a multiplicar
todos os pesos pelo mesmo número. É essa fatia que o teto limita. Consequência declarada: um modelo cujo
único fator é um proxy sempre reprova, porque a nota da unidade fica 100 % determinada por um dado que mede
outra grandeza.

O teto vale nos dois lugares onde um peso entra: no documento do modelo (`app.amc.esquema.validar`) e nos
pesos de uma execução, que podem sobrescrever os do modelo (`app.amc.esquema.validar_pesos`). Barrar só no
primeiro deixaria a porta dos fundos aberta.
"""

from __future__ import annotations

TETO_PROXY_PADRAO = 0.60
# folga numérica: peso exatamente no teto passa; ela cobre o erro de arredondamento de 0,6*10 = 6,000000000000001
FOLGA = 1e-9

CLASSES_PESO = {
    "custo_medido": "custo medido em R$ (preço publicado)",
    "apetite_de_risco": "apetite de risco do cliente (probabilidade de encrenca, não custo)",
    "consequencia_normativa": "consequência normativa (a norma muda o rito por causa deste fator)",
}
ANCORAS_PESO = {
    "medida": "peso ancorado em medida externa",
    "escolhida": "peso escolhido pelo usuário, sem âncora externa",
}
BASES = {
    "norma": "a norma obriga",
    "engenharia": "critério de engenharia",
    "preferencia": "preferência declarada de quem decide",
}
NAO_DECLARADO = "não declarado"

AVISO_ANCORA = ("peso sem âncora é escolha de quem decide, nunca medida: o relatório nomeia cada fator cuja "
                "âncora não foi declarada para que a escolha não passe por medição.")


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def teto_de(fator: dict) -> float | None:
    """Teto de fatia do fator, ou None quando ele não foi declarado proxy."""
    proxy = fator.get("proxy") if isinstance(fator, dict) else None
    if not isinstance(proxy, dict):
        return None
    teto = proxy.get("teto_peso", TETO_PROXY_PADRAO)
    return float(teto) if _numero(teto) else TETO_PROXY_PADRAO


def _pesos_efetivos(fatores: list, pesos_por_id: dict | None = None) -> dict:
    """`{id_fator: peso}` já resolvido: o peso da execução quando houver, senão o do modelo; não numérico ou
    negativo vira 0 (o peso negativo tem violação própria em `app.amc.esquema`)."""
    pesos: dict[str, float] = {}
    for f in fatores:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str):
            continue
        p = pesos_por_id[f["id"]] if pesos_por_id is not None and f["id"] in pesos_por_id else f.get("peso")
        pesos[f["id"]] = float(p) if _numero(p) and float(p) > 0 else 0.0
    return pesos


def fatias(fatores: list, pesos_por_id: dict | None = None) -> dict:
    """`{id_fator: peso_i / Σ pesos}`. Soma zero devolve {} — esse caso já tem violação própria ("soma dos
    pesos é zero") e não é papel deste módulo repeti-la."""
    pesos = _pesos_efetivos(fatores, pesos_por_id)
    soma = sum(pesos.values())
    if soma <= 0:
        return {}
    return {k: v / soma for k, v in pesos.items()}


def violacoes_teto_proxy(fatores: list, pesos_por_id: dict | None = None,
                         prefixo_caminho: str = "$.fatores") -> list[dict]:
    """Uma violação por fator declarado proxy cuja fatia do modelo passa do teto declarado.

    A mensagem diz o número medido, o teto, o que a camada mede de fato e qual peso caberia — recusar sem
    explicar devolveria o usuário ao mesmo lugar."""
    v: list[dict] = []
    if not isinstance(fatores, list):
        return v
    pesos = _pesos_efetivos(fatores, pesos_por_id)
    soma = sum(pesos.values())
    if soma <= 0:
        return v
    for i, f in enumerate(fatores):
        if not isinstance(f, dict):
            continue
        teto = teto_de(f)
        if teto is None:
            continue
        fid = f.get("id")
        if fid not in pesos:
            continue
        fatia = pesos[fid] / soma
        if fatia <= teto + FOLGA:
            continue
        descricao = (f.get("proxy") or {}).get("descricao") or NAO_DECLARADO
        soma_outros = soma - pesos[fid]
        if teto < 1.0:
            peso_max = teto * soma_outros / (1.0 - teto)
            conserto = (f"reduza o peso de \'{fid}\' para no máximo {peso_max:.4g} (mantidos os demais pesos, que "
                        f"somam {soma_outros:.4g}), aumente o peso dos outros fatores, ou retire a marca de proxy "
                        f"se a camada passar a medir o próprio gatilho")
        else:
            conserto = f"reduza o peso de \'{fid}\' ou aumente o dos outros fatores"
        v.append({
            "clausula": "fatores[].proxy: fatia do peso <= proxy.teto_peso",
            "caminho": f"{prefixo_caminho}[{i}].peso",
            "mensagem": (f"o fator \'{fid}\' está declarado como proxy ({descricao}) e ficaria com "
                         f"{fatia * 100:.1f}% do peso do modelo, acima do teto declarado de {teto * 100:.1f}%. "
                         f"Camada que mede grandeza diferente do gatilho não pode pesar como se medisse o "
                         f"gatilho: subir o peso amplifica o erro em vez de corrigi-lo. {conserto}."),
        })
    return v


# ---------------------------------------------------------------- ficha para a tela e para o relatório
def ficha(fator: dict, peso: float | None = None, fatia: float | None = None) -> dict:
    """Ficha de metadado de um fator — o conteúdo do '?' ao lado do fator na tela e a linha do relatório.
    Campo não declarado sai como `None` e com o texto "não declarado" no `resumo`, nunca como um valor
    inventado."""
    proxy = fator.get("proxy") if isinstance(fator.get("proxy"), dict) else None
    base = fator.get("base")
    classe = fator.get("classe_peso")
    ancora = fator.get("ancora_peso")
    teto = teto_de(fator)
    return {
        "fator_id": fator.get("id"),
        "nome": fator.get("nome"),
        "criterio": fator.get("criterio"),
        "fonte": fator.get("fonte"),
        "versao_fonte": fator.get("versao_fonte"),
        "unidade": fator.get("unidade"),
        "direcao": fator.get("direcao"),
        "base": base,
        "base_descricao": BASES.get(base, NAO_DECLARADO),
        "proxy": bool(proxy),
        "proxy_descricao": (proxy or {}).get("descricao"),
        "proxy_teto_peso": teto,
        "classe_peso": classe,
        "classe_peso_descricao": CLASSES_PESO.get(classe, NAO_DECLARADO),
        "ancora_peso": ancora,
        "ancora_peso_descricao": ANCORAS_PESO.get(ancora, NAO_DECLARADO),
        "nao_sustenta": fator.get("nao_sustenta"),
        "peso": float(peso) if _numero(peso) else (float(fator["peso"]) if _numero(fator.get("peso")) else None),
        "fatia_do_peso": fatia,
        "resumo": _resumo(fator, teto, fatia),
    }


def _resumo(fator: dict, teto: float | None, fatia: float | None) -> str:
    """Uma frase por linha, na ordem: o que se mede → de onde vem → por que pesa → o que não sustenta.
    Regra de escrita de 03/09/2026: sem metáfora, número sempre com a base de comparação."""
    partes = [f"mede {fator.get('unidade') or NAO_DECLARADO} "
              f"({'maior é melhor' if fator.get('direcao') == 'maior_melhor' else 'menor é melhor'})."]
    versao = fator.get("versao_fonte")
    partes.append(f"Fonte: {fator.get('fonte') or NAO_DECLARADO}"
                  + (f", versão {versao}." if versao else ", versão não declarada."))
    partes.append(f"Base do fator: {BASES.get(fator.get('base'), NAO_DECLARADO)}.")
    classe = fator.get("classe_peso")
    ancora = fator.get("ancora_peso")
    partes.append(f"Classe do peso: {CLASSES_PESO.get(classe, NAO_DECLARADO)}; "
                  f"âncora: {ANCORAS_PESO.get(ancora, NAO_DECLARADO)}.")
    if teto is not None:
        proxy_desc = (fator.get("proxy") or {}).get("descricao") or NAO_DECLARADO
        fatia_txt = f"{fatia * 100:.1f}% do peso do modelo" if fatia is not None else "fatia não calculada"
        partes.append(f"Proxy: {proxy_desc}. Teto de peso {teto * 100:.1f}%; hoje {fatia_txt}.")
    if fator.get("nao_sustenta"):
        partes.append(f"Não sustenta: {fator['nao_sustenta']}.")
    return " ".join(partes)


def fichas(definicao: dict, pesos_por_id: dict | None = None) -> dict:
    """Bloco de metadado do relatório: uma ficha por fator, a lista dos proxies (com teto e fatia) e a lista
    das âncoras (medida / escolhida / não declarada). É o que a cláusula "relatório lista proxies e âncoras"
    pede."""
    fatores = definicao.get("fatores") or []
    frac = fatias(fatores, pesos_por_id)
    lista = []
    for f in fatores:
        if not isinstance(f, dict):
            continue
        fid = f.get("id")
        peso = (pesos_por_id or {}).get(fid, f.get("peso"))
        lista.append(ficha(f, peso=peso, fatia=frac.get(fid)))
    proxies = [{"fator_id": x["fator_id"], "nome": x["nome"], "descricao": x["proxy_descricao"],
                "teto_peso": x["proxy_teto_peso"], "fatia_do_peso": x["fatia_do_peso"]}
               for x in lista if x["proxy"]]
    ancoras = {
        "medida": [x["fator_id"] for x in lista if x["ancora_peso"] == "medida"],
        "escolhida": [x["fator_id"] for x in lista if x["ancora_peso"] == "escolhida"],
        "nao_declarada": [x["fator_id"] for x in lista if x["ancora_peso"] not in ANCORAS_PESO],
    }
    sem_versao = [x["fator_id"] for x in lista if not x["versao_fonte"]]
    if proxies:
        aviso_proxy = (f"{len(proxies)} de {len(lista)} fator(es) medem grandeza diferente do gatilho e estão "
                       f"declarados como proxy: " + ", ".join(p["fator_id"] for p in proxies)
                       + ". O peso de cada um para no teto declarado.")
    else:
        aviso_proxy = f"nenhum dos {len(lista)} fatores está declarado como proxy"
    return {
        "fatores": lista,
        "proxies": proxies,
        "ancoras": ancoras,
        "fatores_sem_versao_de_fonte": sem_versao,
        "aviso_proxy": aviso_proxy,
        "aviso_ancora": AVISO_ANCORA,
    }

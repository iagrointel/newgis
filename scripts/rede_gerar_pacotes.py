#!/usr/bin/env python3
"""Gera os pacotes instalados em versão de esquema 2 (item L4-03-a-regras-de-conectividade).

Lê o pacote em versão 1, converte as regras pela MESMA conversão do `pacote.ler` (junção vai para o lado
`de` na junção-aresta), aplica o acréscimo declarado abaixo e regrava o arquivo na forma canônica
(`pacote.canonizar` — a única serialização aceita: `instalados.catalogo` confere byte a byte na subida).

Regra nova SUPERSEDE a convertida com o mesmo (tipo, de, para): é assim que as regras sem terminal da
versão 1 viram regras com terminal na 2 (ex.: o par transformador/trecho de média tensão sem terminal sai e
entra o mesmo par exigindo o terminal 'alta'). A regra `ramal_de_ligacao/1 -> trecho_de_baixa_tensao/1` da
versão 1 não tem lado junção (os dois grupos são linha) e por isso não converte; ela é substituída pela
aresta-junção-aresta RAMAL via POSTE -> TRECHO BT, declarada abaixo.

Uso: venv/bin/python scripts/rede_gerar_pacotes.py
Recusas: arquivo já em versão 2 (o gerador parte sempre da versão 1). Rodar uma vez por mudança de versão
de esquema; o resultado é determinístico (sha256 estável)."""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.rede_utilidades import pacote as pacote_mod  # noqa: E402

PACOTES = RAIZ / "app" / "rede_utilidades" / "pacotes"

TMT = {"grupo": "trecho_de_media_tensao", "tipo": 1}
TBT = {"grupo": "trecho_de_baixa_tensao", "tipo": 1}
RAMAL = {"grupo": "ramal_de_ligacao", "tipo": 1}
POSTE = {"grupo": "ponto_notavel", "tipo": 1}
TORRE = {"grupo": "ponto_notavel", "tipo": 2}


def _ref(grupo: str, tipo: int, terminal: str | None = None) -> dict:
    ref = {"grupo": grupo, "tipo": tipo}
    if terminal is not None:
        ref["terminal"] = terminal
    return ref


def _regras_eletrica_v2() -> list[dict]:
    """O acréscimo da versão 1.1.0 do pacote elétrica-BR. Os quatro exemplos do portão do item estão aqui:
    trecho de MT só liga o transformador pelo terminal de AT ('alta'); a chave de MT liga trecho de MT a
    trecho de MT (aresta-junção-aresta); o ramal de BT liga a unidade consumidora e o trecho de BT (esta
    última via poste, porque a BDGD não tem feição de ponto de derivação); o poste contém transformador,
    chave e medidor (unidade consumidora)."""
    r = []

    def je(grupo, tipo, terminal, aresta, descricao):
        r.append({"tipo": "juncao_aresta", "de": _ref(grupo, tipo, terminal), "para": aresta,
                  "descricao": descricao})

    def eje(de, via, para, descricao):
        r.append({"tipo": "aresta_juncao_aresta", "de": de, "via": via, "para": para,
                  "descricao": descricao})

    def jj(a, b, descricao):
        r.append({"tipo": "juncao_juncao", "de": a, "para": b, "descricao": descricao})

    def cont(de, para, descricao):
        r.append({"tipo": "contencao", "de": de, "para": para, "descricao": descricao})

    chaves = {1: "chave faca", 2: "chave fusível", 3: "religador", 4: "disjuntor", 5: "seccionalizador"}
    for codigo, nome in chaves.items():
        for lado in ("lado_1", "lado_2"):
            je("chave_de_media_tensao", codigo, lado, TMT,
               f"{nome} ligada ao trecho de média tensão pelo terminal {lado}")
        eje(TMT, _ref("chave_de_media_tensao", codigo), TMT,
            f"{nome} liga trecho de média tensão a trecho de média tensão")

    for lado in ("lado_1", "lado_2"):
        je("regulador_de_tensao", 1, lado, TMT,
           f"regulador de tensão ligado ao trecho de média tensão pelo terminal {lado}")
    eje(TMT, _ref("regulador_de_tensao", 1), TMT,
        "regulador de tensão liga trecho de média tensão a trecho de média tensão")

    trafos = {1: "transformador de distribuição", 2: "banco de transformadores",
              3: "transformador não classificado"}
    for codigo, nome in trafos.items():
        je("transformador_de_distribuicao", codigo, "alta", TMT,
           f"primário (AT) do {nome} no trecho de média tensão — trecho de MT só liga pelo terminal de AT")
        je("transformador_de_distribuicao", codigo, "baixa", TBT,
           f"secundário (BT) do {nome} no trecho de baixa tensão")
        eje(TMT, _ref("transformador_de_distribuicao", codigo), TBT,
            f"{nome} liga o trecho de média tensão ao trecho de baixa tensão")

    je("banco_de_capacitores", 1, "conexao", TMT, "banco de capacitores derivado do trecho de média tensão")
    je("subestacao", 1, "conexao", TMT, "saída da subestação alimenta o trecho de média tensão")
    eje(TMT, _ref("subestacao", 1), TMT, "a subestação é a origem do trecho de média tensão")
    je("unidade_consumidora", 2, "conexao", TMT,
       "consumidor de média tensão ligado ao trecho de média tensão")
    je("unidade_consumidora", 1, "conexao", RAMAL,
       "consumidor de baixa tensão ligado pelo ramal de ligação")
    je("geracao_distribuida", 1, "conexao", TBT, "geração em baixa tensão ligada ao trecho de baixa tensão")
    je("geracao_distribuida", 2, "conexao", TMT, "geração em média tensão ligada ao trecho de média tensão")
    je("ponto_de_iluminacao_publica", 1, "conexao", TBT, "luminária ligada ao trecho de baixa tensão")

    eje(RAMAL, POSTE, TBT,
        "ramal de baixa tensão deriva do trecho de baixa tensão no poste (a BDGD não tem ponto de derivação)")
    eje(TBT, POSTE, TBT, "vãos de baixa tensão se encontram no poste")

    jj(_ref("subestacao", 1), _ref("chave_de_media_tensao", 4),
       "disjuntor de saída coincidente com a subestação")
    jj(_ref("chave_de_media_tensao", 2), _ref("transformador_de_distribuicao", 1),
       "chave fusível de proteção coincidente com o transformador")

    cont(_ref("subestacao", 1), _ref("transformador_de_distribuicao", 2),
         "banco de transformadores contido na subestação")
    for codigo, nome in ((1, "transformador de distribuição"), (3, "transformador não classificado")):
        cont(POSTE, _ref("transformador_de_distribuicao", codigo), f"{nome} contido no poste")
    for codigo, nome in ((1, "chave faca"), (2, "chave fusível"), (3, "religador"), (5, "seccionalizador")):
        cont(POSTE, _ref("chave_de_media_tensao", codigo), f"{nome} contida no poste")
    cont(POSTE, _ref("unidade_consumidora", 1), "medidor de baixa tensão contido no poste")
    cont(POSTE, _ref("unidade_consumidora", 2), "medidor de média tensão contido no poste")
    cont(POSTE, _ref("ponto_de_iluminacao_publica", 1), "luminária contida no poste")
    cont(POSTE, _ref("banco_de_capacitores", 1), "banco de capacitores contido no poste")
    cont(POSTE, _ref("regulador_de_tensao", 1), "regulador de tensão contido no poste")
    return r


def _chave_sem_terminal(regra: dict) -> tuple:
    def k(ref):
        return (ref["grupo"], ref["tipo"]) if ref else None
    return (regra["tipo"], k(regra["de"]), k(regra.get("via")), k(regra["para"]))


def _gerar(codigo: str, versao_nova: str, extras: list[dict], nota: str | None) -> None:
    arquivo = PACOTES / f"{codigo}.json"
    doc_v1 = json.loads(arquivo.read_text(encoding="utf-8"))
    # tira antes da conversão as regras sem lado junção (os dois grupos são linha): a conversão as recusa
    # com a linha apontada, e aqui elas são SUBSTITUÍDAS pelas aresta-junção-aresta declaradas no acréscimo
    geometrias = {g["codigo"]: g["geometria"] for g in doc_v1["grupos"]}
    regras_v1 = []
    for r in doc_v1["regras"]:
        de_g = str(r["de"]).partition("/")[0]
        pa_g = str(r["para"]).partition("/")[0]
        if r["tipo"] == "conectividade_no_trecho" and geometrias.get(de_g) == geometrias.get(pa_g) == "linha":
            print(f"  substituída na conversão: {r['de']} -> {r['para']} ({r.get('descricao', '')})")
            continue
        regras_v1.append(r)
    doc_v1["regras"] = regras_v1
    doc = pacote_mod.ler((json.dumps(doc_v1, ensure_ascii=False) + "\n").encode("utf-8"))
    if doc["esquema_versao"] != pacote_mod.ESQUEMA_VERSAO:
        raise SystemExit(f"{arquivo.name}: leitura não devolveu a versão {pacote_mod.ESQUEMA_VERSAO}")
    regras = list(doc["regras"])
    # supersede em duas passadas: primeiro saem as CONVERTIDAS (sempre sem terminal) cobertas por uma regra
    # nova com o mesmo (tipo, de, via, para); depois entram TODAS as novas — duas novas que só diferem no
    # terminal (lado_1 x lado_2 da mesma chave) não se apagam entre si
    chaves_novas = {_chave_sem_terminal(n) for n in extras}
    regras = [x for x in regras
              if not (_chave_sem_terminal(x) in chaves_novas and x["de"].get("terminal") is None)]
    regras.extend(extras)
    doc["regras"] = regras
    doc["pacote"]["versao"] = versao_nova
    if nota:
        doc["pacote"]["descricao"] = (doc["pacote"].get("descricao", "").rstrip() + " " + nota).strip()
    # valida de novo já na forma final (as regras novas passam pela mesma conferência de referência)
    bruto = pacote_mod.canonizar(doc)
    pacote_mod.ler(bruto)
    arquivo.write_bytes(bruto)
    print(f"{arquivo.name}: {len(regras)} regras, versão {versao_nova}, {len(bruto)} bytes")


def main() -> None:
    for nome in ("eletrica-br", "agua-epanet"):
        meta = json.loads((PACOTES / f"{nome}.json").read_text(encoding="utf-8"))["pacote"]
        if meta["versao"] != "1.0.0":
            raise SystemExit(f"{nome}: esperado versão 1.0.0 de origem, achei {meta['versao']}")
    _gerar(
        "eletrica-br", "1.1.0", _regras_eletrica_v2(),
        "Desde a versão 1.1.0 as regras seguem o esquema 2: junção-aresta com terminal no lado da junção, "
        "aresta-junção-aresta (chave, religador, regulador e transformador entre trechos; ramal derivando "
        "do trecho de baixa tensão no poste), junção-junção, contenção (poste e subestação) e estrutura.",
    )
    _gerar("agua-epanet", "1.0.1", [], None)


if __name__ == "__main__":
    main()

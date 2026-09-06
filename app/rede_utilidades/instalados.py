"""Pacotes que vêm com a instalação (`app/rede_utilidades/pacotes/*.json`). São DADO entregue com o produto, não
código: quem quiser outro pacote manda o seu pela rota de importação. Lidos uma vez e mantidos em memória; a
leitura já confere que cada arquivo está na forma canônica, para que um pacote quebrado apareça na subida do
processo e não no primeiro cliente que tentar importá-lo."""

import hashlib
from functools import lru_cache
from pathlib import Path

from app.rede_utilidades import pacote as pacote_mod

DIRETORIO = Path(__file__).resolve().parent / "pacotes"


@lru_cache(maxsize=1)
def catalogo() -> dict[str, dict]:
    saida: dict[str, dict] = {}
    for arquivo in sorted(DIRETORIO.glob("*.json")):
        bruto = arquivo.read_bytes()
        doc = pacote_mod.ler(bruto)
        if pacote_mod.canonizar(doc) != bruto:
            raise ValueError(f"pacote instalado fora da forma canônica: {arquivo.name}")
        meta = doc["pacote"]
        saida[meta["codigo"]] = {
            "codigo": meta["codigo"],
            "nome": meta["nome"],
            "versao": meta["versao"],
            "disciplina": meta["disciplina"],
            "descricao": meta.get("descricao"),
            "fonte": meta.get("fonte"),
            "bytes": len(bruto),
            "sha256": hashlib.sha256(bruto).hexdigest(),
            "contagens": {s: len(doc.get(s, [])) for s in pacote_mod.SECOES},
            "arquivo": arquivo,
        }
    return saida


def bruto(codigo: str) -> bytes | None:
    ficha = catalogo().get(codigo)
    return None if ficha is None else ficha["arquivo"].read_bytes()

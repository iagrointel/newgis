#!/usr/bin/env python3
"""Assinatura e verificação Ed25519 de pacote de atualização do `plat` (item L7-16-assinatura-pacote,
ADR 0007 seção 2-3). Usa `cryptography` (pacote dpkg `python3-cryptography`, já em `deploy/pacotes_apt.txt`
pelo item L7-14). Sem rede: gerar chave, assinar e verificar são só leitura/escrita de arquivo e conta.

Chamado pelos wrappers `scripts/assinar_pacote.sh` e `scripts/verificar_pacote.sh` — não é para rodar
direto em produção, mas nada nele depende de estar dentro do repositório (usável de um host de release
separado, contanto que `cryptography` esteja instalado).

Formato do `.sig` (JSON, ao lado do arquivo assinado):
    {"algoritmo": "ed25519", "chave_id": "k<16 hex>", "assinatura_b64": "...", "arquivo": "...", "tamanho_bytes": N}

`chave_id` é derivado da chave pública (sha256 dos 32 bytes crus, 16 hex prefixados de "k"), nunca de um
contador — duas instalações que gerem a mesma chave (impossível na prática) dariam o mesmo id; duas
chaves diferentes nunca colidem em id por acaso.

Confiança fica em `deploy/chaves_publicas_release.txt` (fixado e versionado no repositório — só ele
decide o que é aceito; a chave PRIVADA nunca é lida daqui nem gravada aqui). Rotação de chave: para o
pacote assinado com uma chave nova ser aceito, o id dela precisa já estar nesse arquivo — por isso a
chave nova é distribuída (linha nova no arquivo, dentro de uma versão assinada com a chave ANTIGA) antes
de qualquer pacote ser assinado com ela.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

ALGORITMO = "ed25519"


def chave_id_de(chave_publica_raw: bytes) -> str:
    return "k" + hashlib.sha256(chave_publica_raw).hexdigest()[:16]


def chave_publica_raw(chave_privada: Ed25519PrivateKey) -> bytes:
    return chave_privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def carregar_ou_gerar_privada(caminho: Path) -> tuple[Ed25519PrivateKey, bool]:
    """Carrega a chave privada de `caminho`; gera um par novo se o arquivo não existir. Nunca sobrescreve
    uma chave já existente. Devolve (chave, gerada_agora)."""
    if caminho.exists():
        return load_pem_private_key(caminho.read_bytes(), password=None), False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(caminho.parent, 0o700)
    except PermissionError:
        pass  # diretório de terceiro (ex.: /etc/plat já existe com outro dono); segue mesmo assim
    chave = Ed25519PrivateKey.generate()
    pem = chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    return chave, True


def ler_chaves_confiaveis(caminho: Path) -> dict[str, str]:
    chaves: dict[str, str] = {}
    if not caminho.exists():
        return chaves
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split()
        if len(partes) >= 2:
            chaves[partes[0]] = partes[1]
    return chaves


def registrar_chave_publica(caminho: Path, chave_id: str, publica_b64: str, nota: str = "") -> bool:
    """Acrescenta a chave pública ao arquivo de confiança (fixado no repositório). Não sobrescreve linha
    existente do mesmo id. Devolve True se uma linha nova foi escrita."""
    if chave_id in ler_chaves_confiaveis(caminho):
        return False
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with caminho.open("a", encoding="utf-8") as f:
        if novo:
            f.write(
                "# id-da-chave chave-publica-base64 nota — gerado por scripts/plat_assinatura.py; "
                "versionar no git (item L7-16, ADR 0007 seção 2)\n"
            )
        linha = f"{chave_id} {publica_b64}"
        if nota:
            linha += f" {nota}"
        f.write(linha + "\n")
    return True


def cmd_gerar_chave(args: argparse.Namespace) -> None:
    chave, gerada = carregar_ou_gerar_privada(Path(args.chave_privada))
    pub_raw = chave_publica_raw(chave)
    cid = chave_id_de(pub_raw)
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    registrada = registrar_chave_publica(Path(args.confiaveis), cid, pub_b64, args.nota)
    print(
        json.dumps(
            {
                "chave_id": cid,
                "gerada_agora": gerada,
                "publica_b64": pub_b64,
                "privada_em": str(Path(args.chave_privada)),
                "confiaveis_em": str(Path(args.confiaveis)),
                "registrada_agora": registrada,
            },
            ensure_ascii=False,
        )
    )


def cmd_assinar(args: argparse.Namespace) -> None:
    caminho_privada = Path(args.chave_privada)
    if not caminho_privada.exists():
        print(f"recusado: chave privada não existe em {caminho_privada} (rode 'gerar-chave' primeiro)", file=sys.stderr)
        sys.exit(1)
    chave = load_pem_private_key(caminho_privada.read_bytes(), password=None)
    cid = chave_id_de(chave_publica_raw(chave))
    dados = Path(args.arquivo).read_bytes()
    assinatura = chave.sign(dados)
    saida = {
        "algoritmo": ALGORITMO,
        "chave_id": cid,
        "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
        "arquivo": os.path.basename(args.arquivo),
        "tamanho_bytes": len(dados),
    }
    Path(args.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(saida, ensure_ascii=False))


def cmd_verificar(args: argparse.Namespace) -> None:
    caminho_sig = Path(args.assinatura)
    if not caminho_sig.exists():
        print(f"recusado: {caminho_sig} não existe (pacote não assinado)", file=sys.stderr)
        sys.exit(2)
    try:
        info = json.loads(caminho_sig.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"recusado: {caminho_sig} não é um .sig válido ({e})", file=sys.stderr)
        sys.exit(2)
    if info.get("algoritmo") != ALGORITMO:
        print(f"recusado: algoritmo desconhecido {info.get('algoritmo')!r}", file=sys.stderr)
        sys.exit(2)
    cid = info.get("chave_id")
    chaves = ler_chaves_confiaveis(Path(args.confiaveis))
    if cid not in chaves:
        print(
            f"recusado: a chave '{cid}' não é confiável nesta versão "
            f"(rotação pendente ou origem desconhecida; confira {args.confiaveis})",
            file=sys.stderr,
        )
        sys.exit(3)
    try:
        publica = Ed25519PublicKey.from_public_bytes(base64.b64decode(chaves[cid]))
        assinatura = base64.b64decode(info["assinatura_b64"])
    except Exception as e:  # noqa: BLE001 — qualquer .sig malformado é recusa, não exceção não tratada
        print(f"recusado: .sig malformado ({e})", file=sys.stderr)
        sys.exit(2)
    dados = Path(args.arquivo).read_bytes()
    try:
        publica.verify(assinatura, dados)
    except InvalidSignature:
        print(f"recusado: assinatura inválida para {args.arquivo} (o arquivo pode ter sido alterado)", file=sys.stderr)
        sys.exit(4)
    print(
        json.dumps(
            {"aceito": True, "chave_id": cid, "arquivo": os.path.basename(args.arquivo), "tamanho_bytes": len(dados)},
            ensure_ascii=False,
        )
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="plat_assinatura")
    sub = ap.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("gerar-chave", help="gera o par Ed25519 se a chave privada ainda não existir")
    g.add_argument("--chave-privada", required=True, help="caminho da chave privada (PEM, PKCS8, sem senha)")
    g.add_argument("--confiaveis", required=True, help="deploy/chaves_publicas_release.txt (fixado no git)")
    g.add_argument("--nota", default="")
    g.set_defaults(func=cmd_gerar_chave)

    a = sub.add_parser("assinar", help="assina um arquivo com a chave privada informada")
    a.add_argument("arquivo")
    a.add_argument("--chave-privada", required=True)
    a.add_argument("--saida", required=True, help="caminho do .sig de saída")
    a.set_defaults(func=cmd_assinar)

    v = sub.add_parser("verificar", help="verifica um arquivo contra o .sig e as chaves confiáveis")
    v.add_argument("arquivo")
    v.add_argument("--assinatura", required=True)
    v.add_argument("--confiaveis", required=True)
    v.set_defaults(func=cmd_verificar)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

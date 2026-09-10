#!/usr/bin/env python3
"""Assinatura e verificação Ed25519 de pacote de atualização do `plat` (item L7-16-assinatura-pacote,
ADR 0007 seções 2-3, endurecido em 06/09/2026 depois do ataque adversarial ao grupo G6). Usa
`cryptography` (pacote dpkg `python3-cryptography`, em `deploy/pacotes_apt.txt`). Sem rede: gerar chave,
assinar e verificar são só leitura/escrita de arquivo e conta.

Chamado pelos wrappers `scripts/assinar_pacote.sh` e `scripts/verificar_pacote.sh`.

## O que mudou depois do ataque (três buracos medidos pelo adversário, laudo em
`laco/handoffs/T3/ataque-g6-ADVERSARIO.md`)

1. **Quem assina não escreve mais na lista de confiança.** Antes, `gerar-chave` acrescentava a própria
   chave pública em `deploy/chaves_publicas_release.txt` — o MESMO arquivo que a verificação consulta —,
   então qualquer pessoa que rodasse a ferramenta de assinatura virava origem confiável. Agora só há uma
   exceção, estreita e barulhenta: quando a lista ainda não tem NENHUMA chave (instalação sem âncora de
   release), a primeira chave é registrada como ÂNCORA INICIAL, com aviso em stderr. Com uma chave já na
   lista, registrar outra exige o ato separado e explícito de `scripts/confiar_chave_release.sh --confirmo`
   (que só escreve o arquivo e manda commitar; não tem acesso a chave privada nenhuma). O repositório do
   produto ships com a âncora preenchida e `tests/unit/test_release_seguranca.py` reprova se ela sumir —
   ou seja, em produção o caminho de âncora inicial nunca está aberto.

2. **A variável de ambiente não substitui mais a lista.** `PLAT_CHAVES_CONFIAVEIS` só é considerada
   quando o ambiente é declaradamente de desenvolvimento (`PLAT_AMBIENTE` em {dev, teste, homolog}) e,
   mesmo aí, ela ACRESCENTA à lista do produto em vez de trocá-la, escrevendo uma linha de aviso em
   stderr. Ambiente não declarado = produção: a variável é ignorada, com aviso. A lista de confiança
   também não depende mais de `APP_DIR`: é sempre `../deploy/chaves_publicas_release.txt` a partir do
   arquivo de script que está rodando.

3. **A assinatura passou a cobrir a identidade do pacote, não só os bytes.** O que se assina é uma
   DECLARAÇÃO canônica (nome do arquivo, tamanho, sha256, versão, data), e a verificação recomputa esses
   campos a partir do arquivo real e compara. Antes, `arquivo` e `tamanho_bytes` ficavam fora da conta e
   podiam mentir; agora mentir neles é assinatura inválida (saída 4).

Formato do `.sig` (JSON, ao lado do arquivo assinado):

    {"formato": "plat-sig-2", "algoritmo": "ed25519", "chave_id": "k<16 hex>",
     "declaracao_b64": "<base64 dos bytes EXATOS que foram assinados>",
     "assinatura_b64": "...",
     "declaracao": {"arquivo": ..., "tamanho_bytes": ..., "sha256": ..., "versao": ..., "quando": ...}}

`declaracao` é cópia legível para humanos; a verificação usa exclusivamente `declaracao_b64` e depois
confere que a cópia legível bate com ela. `.sig` no formato antigo (`plat-sig-1`, sem declaração) é
recusado com saída 2: pacote antigo tem de ser reassinado, e é assim que a frota deixa de aceitar um
pacote cuja identidade ninguém amarrou.

`chave_id` é derivado da chave pública (sha256 dos 32 bytes crus, 16 hex prefixados de "k"), nunca de um
contador.

Códigos de saída de `verificar` (contrato usado por `scripts/publicar_release.sh` e pelos testes):
    0  aceito
    2  `.sig` ausente, malformado, de formato antigo ou com algoritmo desconhecido
    3  a chave que assinou não está na lista de confiança desta instalação
    4  assinatura inválida OU o arquivo não é o que a declaração assinada diz (nome, tamanho ou sha256)
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
FORMATO = "plat-sig-2"
# Separação de domínio: bytes assinados nunca colidem com os de outro uso da mesma chave (ex.: a
# exportação OpenSSH da mesma chave, usada para assinar a etiqueta git do release).
PREFIXO_DOMINIO = b"plat-pacote-v2\n"
# Ambientes em que PLAT_CHAVES_CONFIAVEIS pode ACRESCENTAR chaves (nunca substituir). Qualquer outro
# valor — inclusive variável ausente — é tratado como produção.
AMBIENTES_DE_DESENVOLVIMENTO = frozenset({"dev", "teste", "test", "homolog", "homologacao"})


def chave_id_de(chave_publica_raw: bytes) -> str:
    return "k" + hashlib.sha256(chave_publica_raw).hexdigest()[:16]


def chave_publica_raw(chave_privada: Ed25519PrivateKey) -> bytes:
    return chave_privada.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def sha256_do_arquivo(caminho: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    tamanho = 0
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
            tamanho += len(bloco)
    return h.hexdigest(), tamanho


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


def ambiente_declarado() -> str:
    return (os.environ.get("PLAT_AMBIENTE") or "").strip().lower()


def chaves_confiaveis_efetivas(caminho_do_produto: Path) -> dict[str, str]:
    """Lista de confiança que vale para ESTA verificação.

    Em produção (padrão, inclusive com `PLAT_AMBIENTE` ausente) é exatamente o arquivo versionado do
    produto: `PLAT_CHAVES_CONFIAVEIS` é ignorada, com aviso em stderr. Em ambiente declarado de
    desenvolvimento a variável ACRESCENTA chaves à lista do produto — nunca substitui —, e o aviso diz
    quantas chaves entraram por essa via, para que nenhum log de aceitação seja ambíguo."""
    chaves = ler_chaves_confiaveis(caminho_do_produto)
    extra = os.environ.get("PLAT_CHAVES_CONFIAVEIS")
    if not extra:
        return chaves
    ambiente = ambiente_declarado()
    if ambiente not in AMBIENTES_DE_DESENVOLVIMENTO:
        print(
            f"AVISO: PLAT_CHAVES_CONFIAVEIS={extra} IGNORADA (ambiente '{ambiente or 'nao-declarado'}' "
            f"vale como produção; a lista de confiança é {caminho_do_produto}, dado de instalação "
            "versionado no git)",
            file=sys.stderr,
        )
        return chaves
    acrescentadas = {
        cid: pub for cid, pub in ler_chaves_confiaveis(Path(extra)).items() if cid not in chaves
    }
    print(
        f"AVISO: ambiente declarado '{ambiente}' — acrescentando {len(acrescentadas)} chave(s) de "
        f"PLAT_CHAVES_CONFIAVEIS={extra} à lista do produto ({len(chaves)} chave(s)); "
        "em produção esta variável é ignorada",
        file=sys.stderr,
    )
    chaves.update(acrescentadas)
    return chaves


def registrar_chave_publica(caminho: Path, chave_id: str, publica_b64: str, nota: str = "") -> bool:
    """Acrescenta a chave pública ao arquivo de confiança. SÓ escreve quando a lista ainda não tem chave
    nenhuma (âncora inicial de uma instalação sem release) ou quando esse mesmo id já está lá (idempotente,
    devolve False). Com uma chave de outra origem já registrada, recusa: registrar chave nova é o ato
    explícito de `scripts/confiar_chave_release.sh`. Devolve True se uma linha nova foi escrita."""
    existentes = ler_chaves_confiaveis(caminho)
    if chave_id in existentes:
        return False
    if existentes:
        raise PermissionError(
            f"recusado: {caminho} já tem {len(existentes)} chave(s) confiável(is) e a ferramenta de "
            "assinatura nunca acrescenta a própria chave a uma lista que já tem âncora. Para confiar "
            f"nesta chave, rode: bash scripts/confiar_chave_release.sh {chave_id} <publica_b64> --confirmo"
        )
    escrever_linha_de_confianca(caminho, chave_id, publica_b64, nota)
    print(
        f"AVISO: {caminho} não tinha chave nenhuma — {chave_id} entra como ÂNCORA INICIAL desta "
        "instalação. Confie nela só se esta é a máquina que corta o release; a linha PRECISA ser "
        "commitada e distribuída antes de qualquer pacote de verdade.",
        file=sys.stderr,
    )
    return True


def escrever_linha_de_confianca(caminho: Path, chave_id: str, publica_b64: str, nota: str = "") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with caminho.open("a", encoding="utf-8") as f:
        if novo:
            f.write(
                "# id-da-chave chave-publica-base64 nota — lista de confiança do produto; versionar no "
                "git (item L7-16, ADR 0007 seção 2)\n"
            )
        linha = f"{chave_id} {publica_b64}"
        if nota:
            linha += f" {nota}"
        f.write(linha + "\n")


def declaracao_bytes(declaracao: dict) -> bytes:
    """Serialização canônica do que é assinado: chaves ordenadas, sem espaço supérfluo, UTF-8, com
    prefixo de domínio. Duas execuções com os mesmos campos produzem exatamente os mesmos bytes."""
    corpo = json.dumps(declaracao, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PREFIXO_DOMINIO + corpo.encode("utf-8")


def cmd_gerar_chave(args: argparse.Namespace) -> None:
    chave, gerada = carregar_ou_gerar_privada(Path(args.chave_privada))
    pub_raw = chave_publica_raw(chave)
    cid = chave_id_de(pub_raw)
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    try:
        registrada = registrar_chave_publica(Path(args.confiaveis), cid, pub_b64, args.nota)
    except PermissionError as e:
        registrada = False
        print(str(e), file=sys.stderr)
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
    arquivo = Path(args.arquivo)
    sha, tamanho = sha256_do_arquivo(arquivo)
    declaracao = {
        "algoritmo": ALGORITMO,
        "arquivo": arquivo.name,
        "quando": args.quando,
        "sha256": sha,
        "tamanho_bytes": tamanho,
        "versao": args.versao or "",
    }
    assinados = declaracao_bytes(declaracao)
    assinatura = chave.sign(assinados)
    saida = {
        "formato": FORMATO,
        "algoritmo": ALGORITMO,
        "chave_id": cid,
        "declaracao_b64": base64.b64encode(assinados).decode("ascii"),
        "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
        "declaracao": declaracao,
    }
    Path(args.saida).write_text(json.dumps(saida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in saida.items() if k != "declaracao_b64"}, ensure_ascii=False))


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
    campos_conhecidos = {"formato", "algoritmo", "chave_id", "declaracao_b64", "assinatura_b64", "declaracao"}
    intrusos = sorted(set(info) - campos_conhecidos)
    if intrusos:
        # Nada viaja no .sig fora do que a assinatura cobre: campo desconhecido (inclusive um "arquivo" ou
        # "tamanho_bytes" solto, como no .sig do formato antigo) é recusa, não é ignorado em silêncio.
        print(f"recusado: {caminho_sig} tem campo fora do formato assinado: {intrusos}", file=sys.stderr)
        sys.exit(2)
    if info.get("formato") != FORMATO:
        print(
            f"recusado: formato de assinatura {info.get('formato')!r} não é {FORMATO!r}. Assinatura antiga "
            "não amarrava nome nem tamanho do pacote: reassine com scripts/assinar_pacote.sh.",
            file=sys.stderr,
        )
        sys.exit(2)
    if info.get("algoritmo") != ALGORITMO:
        print(f"recusado: algoritmo desconhecido {info.get('algoritmo')!r}", file=sys.stderr)
        sys.exit(2)
    cid = info.get("chave_id")
    chaves = chaves_confiaveis_efetivas(Path(args.confiaveis))
    if cid not in chaves:
        print(
            f"recusado: a chave '{cid}' não é confiável nesta instalação "
            f"(rotação pendente ou origem desconhecida; confira {args.confiaveis})",
            file=sys.stderr,
        )
        sys.exit(3)
    try:
        publica = Ed25519PublicKey.from_public_bytes(base64.b64decode(chaves[cid]))
        assinatura = base64.b64decode(info["assinatura_b64"])
        assinados = base64.b64decode(info["declaracao_b64"])
    except Exception as e:  # noqa: BLE001 — qualquer .sig malformado é recusa, não exceção não tratada
        print(f"recusado: .sig malformado ({e})", file=sys.stderr)
        sys.exit(2)
    try:
        publica.verify(assinatura, assinados)
    except InvalidSignature:
        print(
            f"recusado: assinatura inválida para {args.arquivo} (o arquivo, o .sig ou a declaração podem "
            "ter sido alterados)",
            file=sys.stderr,
        )
        sys.exit(4)
    if not assinados.startswith(PREFIXO_DOMINIO):
        print("recusado: declaração assinada fora do domínio de pacote do plat", file=sys.stderr)
        sys.exit(4)
    try:
        declaracao = json.loads(assinados[len(PREFIXO_DOMINIO) :].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        print(f"recusado: declaração assinada ilegível ({e})", file=sys.stderr)
        sys.exit(4)
    if declaracao_bytes(declaracao) != assinados:
        print("recusado: declaração assinada não está na forma canônica", file=sys.stderr)
        sys.exit(4)
    if info.get("declaracao") not in (None, declaracao):
        print(
            "recusado: a cópia legível da declaração no .sig não bate com a declaração assinada",
            file=sys.stderr,
        )
        sys.exit(4)
    arquivo = Path(args.arquivo)
    sha, tamanho = sha256_do_arquivo(arquivo)
    divergencias = []
    if declaracao.get("arquivo") != arquivo.name:
        divergencias.append(f"nome (assinado {declaracao.get('arquivo')!r}, real {arquivo.name!r})")
    if declaracao.get("tamanho_bytes") != tamanho:
        divergencias.append(f"tamanho (assinado {declaracao.get('tamanho_bytes')}, real {tamanho})")
    if declaracao.get("sha256") != sha:
        divergencias.append(f"sha256 (assinado {declaracao.get('sha256')}, real {sha})")
    if divergencias:
        print(
            f"recusado: o arquivo não é o que a declaração assinada descreve — {'; '.join(divergencias)}",
            file=sys.stderr,
        )
        sys.exit(4)
    print(
        json.dumps(
            {
                "aceito": True,
                "chave_id": cid,
                "arquivo": arquivo.name,
                "tamanho_bytes": tamanho,
                "sha256": sha,
                "versao": declaracao.get("versao") or None,
                "quando": declaracao.get("quando") or None,
            },
            ensure_ascii=False,
        )
    )


def cmd_exportar_ssh(args: argparse.Namespace) -> None:
    """Exporta a MESMA chave Ed25519 do release no formato OpenSSH, para o git assinar a etiqueta
    `vX.Y.Z` (item L7-15). A âncora de confiança da etiqueta passa a ser a mesma lista de chaves do
    pacote — não uma segunda lista que ninguém audita."""
    chave = load_pem_private_key(Path(args.chave_privada).read_bytes(), password=None)
    priv = Path(args.saida)
    priv.parent.mkdir(parents=True, exist_ok=True)
    pem = chave.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
    if priv.exists():
        priv.unlink()
    fd = os.open(priv, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = chave.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode("ascii")
    cid = chave_id_de(chave_publica_raw(chave))
    Path(str(priv) + ".pub").write_text(f"{pub} plat-release-{cid}\n", encoding="utf-8")
    print(json.dumps({"chave_id": cid, "privada_openssh": str(priv), "publica_openssh": pub}, ensure_ascii=False))


def cmd_allowed_signers(args: argparse.Namespace) -> None:
    """Gera o arquivo `allowed_signers` do git a partir da lista de confiança do produto: uma linha por
    chave confiável, no formato OpenSSH. Sem isso `git tag -v` não tem contra o que conferir."""
    chaves = ler_chaves_confiaveis(Path(args.confiaveis))
    if not chaves:
        print(f"recusado: {args.confiaveis} não tem chave confiável nenhuma", file=sys.stderr)
        sys.exit(3)
    linhas = []
    for cid, pub_b64 in sorted(chaves.items()):
        raw = base64.b64decode(pub_b64)
        pub = Ed25519PublicKey.from_public_bytes(raw).public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        # principal '*': quem corta o release é identificado pela CHAVE, não pelo e-mail configurado no
        # git da máquina de release (que muda de máquina para máquina e não é segredo de ninguém).
        linhas.append(f'* namespaces="git" {pub.decode("ascii")} plat-release-{cid}')
    Path(args.saida).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(json.dumps({"chaves": len(linhas), "saida": args.saida}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="plat_assinatura")
    sub = ap.add_subparsers(dest="comando", required=True)

    g = sub.add_parser("gerar-chave", help="gera o par Ed25519 se a chave privada ainda não existir")
    g.add_argument("--chave-privada", required=True, help="caminho da chave privada (PEM, PKCS8, sem senha)")
    g.add_argument("--confiaveis", required=True, help="deploy/chaves_publicas_release.txt (fixado no git)")
    g.add_argument("--nota", default="")
    g.set_defaults(func=cmd_gerar_chave)

    a = sub.add_parser("assinar", help="assina a declaração canônica de um arquivo (nome, tamanho, sha256)")
    a.add_argument("arquivo")
    a.add_argument("--chave-privada", required=True)
    a.add_argument("--saida", required=True, help="caminho do .sig de saída")
    a.add_argument("--versao", default="", help="versão X.Y.Z do release, quando houver")
    a.add_argument("--quando", default="", help="carimbo ISO-8601 UTC da assinatura")
    a.set_defaults(func=cmd_assinar)

    v = sub.add_parser("verificar", help="verifica um arquivo contra o .sig e as chaves confiáveis")
    v.add_argument("arquivo")
    v.add_argument("--assinatura", required=True)
    v.add_argument("--confiaveis", required=True)
    v.set_defaults(func=cmd_verificar)

    e = sub.add_parser("exportar-ssh", help="exporta a chave do release em formato OpenSSH (etiqueta git)")
    e.add_argument("--chave-privada", required=True)
    e.add_argument("--saida", required=True)
    e.set_defaults(func=cmd_exportar_ssh)

    s = sub.add_parser("allowed-signers", help="gera o allowed_signers do git a partir da lista de confiança")
    s.add_argument("--confiaveis", required=True)
    s.add_argument("--saida", required=True)
    s.set_defaults(func=cmd_allowed_signers)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

"""Texto canônico da licença de uma camada do acervo (item L6-01-e-assinatura-e-uso).

Uma função só monta o texto que a API mostra, que o aceite grava em `plat.acervo_assinatura` e que vai no
LICENCA.txt do pacote de exportação — os três são o MESMO texto, byte a byte; o `licenca_sha256` que o
chamador ecoa no POST de assinatura prova que o que ele clicou é o que o servidor gravou.

O texto nasce de `plat.acervo_licenca` (item L6-01-g: licença curada e testada por HTTP, com o recorte
literal da página em `evidencia`) e nunca de digitação: sem linha curada para a fonte, não existe texto e a
assinatura é recusada (regra D17 da linha L6 — sem licença escrita, a camada não circula).

As frases de obrigação por tipo são um mapa FIXO deste módulo (não são dado): descrevem o que cada licença
exige de quem recebe o pacote. ODbL e CC-BY-SA carregam atribuição E compartilhamento pela mesma licença —
é o que a refutação do item procura no pacote exportado.
"""

import hashlib

OBRIGACOES = {
    "ODbL": (
        "exige atribuição e compartilhamento pela mesma licença (share-alike): quem redistribuir estes "
        "dados, ou uma base derivada deles, precisa manter esta licença e este aviso de atribuição"
    ),
    "CC-BY-SA": (
        "exige atribuição e compartilhamento pela mesma licença (share-alike): adaptações precisam ser "
        "distribuídas sob a mesma licença, com este aviso de atribuição"
    ),
    "CC-BY": "exige atribuição: quem redistribuir precisa manter este aviso",
    "CC0": "dedicação ao domínio público: atribuição recomendada, não exigida",
    "Copernicus": "atribuição conforme o Regulamento (UE) nº 1159/2013 e o aviso deste arquivo",
    "dado-aberto-com-termo-do-orgao": "vale o termo do órgão publicado no endereço verificado abaixo",
    "licenca-propria": "licença própria do órgão: vale o termo publicado no endereço verificado abaixo",
    "nao-declarada": "sem licença declarada na fonte: esta camada não deveria circular (regra D17)",
}


def obrigacao(tipo: str) -> str:
    """Frase de obrigação do tipo de licença; tipo desconhecido não inventa frase."""
    return OBRIGACOES.get(tipo, "vale o termo publicado no endereço verificado abaixo")


def atribuicao(fonte_id: str, nome: str | None, orgao: str | None, tipo: str) -> str:
    """Linha de atribuição que o pacote carrega e que quem redistribui precisa manter."""
    quem = nome or fonte_id
    if orgao:
        quem = f"{quem} ({orgao})"
    return f"Dados de {quem}, licença {tipo}."


def texto_licenca(lic: dict, fonte: dict | None) -> str:
    """Texto canônico da licença de uma fonte. `lic` é a linha de plat.acervo_licenca; `fonte` é a linha de
    plat.acervo_ficha quando ela existe (nome/órgão para a atribuição; None quando a fonte não aparece na
    ficha — o texto cai para o fonte_id, nunca inventa nome)."""
    tipo = lic["tipo"]
    nome = fonte.get("nome") if fonte else None
    orgao = fonte.get("orgao") if fonte else None
    partes = [
        "LICENÇA DESTA CAMADA DO ACERVO",
        "",
        f"Fonte: {nome or lic['fonte_id']}" + (f" ({orgao})" if orgao else ""),
        f"Identificador da fonte: {lic['fonte_id']}",
        f"Licença: {tipo}",
        f"Termo verificado em: {lic['url_licenca']} (HTTP {lic['http_status']}, verificado em "
        f"{lic['verificado_em'].isoformat()})",
        "",
        "Trecho literal da página do termo, lido na verificação:",
        f'"{lic["evidencia"]}"',
        "",
        f"Atribuição exigida: {atribuicao(lic['fonte_id'], nome, orgao, tipo)}",
        f"Obrigações desta licença: {obrigacao(tipo)}.",
    ]
    return "\n".join(partes) + "\n"


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def licenca_da_fonte(cur, fonte_id: str) -> tuple[dict, dict | None] | None:
    """(linha de plat.acervo_licenca, linha de plat.acervo_ficha ou None) para a fonte; None quando não há
    licença curada — o chamador recusa a operação (sem licença escrita, a camada não circula)."""
    cur.execute(
        "SELECT fonte_id, tipo, url_licenca, http_status, evidencia, verificado_em "
        "FROM plat.acervo_licenca WHERE fonte_id = %s",
        (fonte_id,),
    )
    lic = cur.fetchone()
    if lic is None:
        return None
    cur.execute("SELECT nome, orgao FROM plat.acervo_ficha WHERE fonte_id = %s", (fonte_id,))
    return lic, cur.fetchone()


def ficha_licenca(cur, fonte_id: str) -> dict | None:
    """O que a API expõe e o aceite grava: tipo, texto, url e sha256 da fonte; None sem licença curada."""
    par = licenca_da_fonte(cur, fonte_id)
    if par is None:
        return None
    lic, fonte = par
    texto = texto_licenca(lic, fonte)
    return {
        "licenca_tipo": lic["tipo"],
        "licenca_texto": texto,
        "licenca_url": lic["url_licenca"],
        "licenca_sha256": sha256_texto(texto),
    }

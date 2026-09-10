"""Documento de construtor (item L5-05-documento-versoes; ADR 0011; `laco/decomposicao/L5_CONCEITO.md` D2/D3):
o modelo genérico que qualquer construtor do L5 (app, painel, e depois formulário, fluxo) usa para gravar um
grafo JSON — nunca um mecanismo novo. Reaproveita por inteiro o que o item L0-03 já construiu:
`plat.item.dados` (envelope), `plat.tipo_item.esquema`/`esquema_versao` (JSON Schema por tipo, validado em
`app/catalogo/tipos.py`) e `plat.item_versao` (versão imutável com sha256, publicar = `versao_publicada`).

Este módulo acrescenta só o que é específico de documento de construtor e que JSON Schema puro não expressa:

1. **Grafo**: cada nó de `corpo.nos` tem `id` ULID (o próprio esquema do tipo já reprova o formato pelo
   `pattern`; aqui entra a regra que precisa OLHAR A LISTA INTEIRA — dois nós com o mesmo id, ou uma ligação
   apontando para um id que não existe em `corpo.nos` — nenhuma das duas é expressável em JSON Schema puro
   sem `$data`/extensão).
2. **Hash canônico verificável fora do banco**: `plat.item_versao.sha256` (trigger `plat.tg_item_versao`)
   vem de `digest(corpo::text, 'sha256')`, onde `corpo` é `jsonb_build_object(...)` — reproduzível DENTRO
   deste Postgres, mas a serialização de texto do jsonb (ordena chave por comprimento-depois-alfabeto, com
   espaço depois de `:`/`,`) não é o que um `sha256sum` de fora reproduz sem reimplementar o formato interno
   do jsonb. Por isso o portão deste item pede um hash À PARTE, sobre uma forma canônica que qualquer
   ferramenta padrão (Python `json.dumps(sort_keys=True, separators=(",", ":"))`, ou o `jq -cS` do adversário)
   reproduz byte a byte: `sha256_canonico(corpo)`, devolvido pela API ao lado do `sha256` de `item_versao`
   (que continua sendo o de item_retrato inteiro, sem mudar o mecanismo genérico de L0-03).
3. **Migração na leitura**: função `migrar_<tipo>_v<N>_v<N+1>`, nunca no navegador, nunca gravada de volta no
   banco (quem grava de novo grava a versão nova por si — a leitura só devolve o corpo já ajustado ao esquema
   vigente e registra o evento).

Vale hoje para as famílias `app` e `painel` (`FAMILIAS_GRAFO`); `formulario`/`fluxo` continuam com o envelope
trivial até o item que desenha a forma própria dos nós (L5-03/L5-02) decidir o formato deles — quando decidir,
é só acrescentar a família aqui, nada neste módulo é específico de app/painel.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

from app.catalogo import tipos
from app.cena import documento as cena_documento
from app.erros import ErroAPI

# Crockford base32, 26 caracteres, primeiro em 0-7 (timestamp de 48 bits nunca estoura o 7º bit do 1º caractere)
ULID_RE = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# famílias de plat.tipo_item cujo `corpo` segue o formato {"nos": [...], "ligacoes": [...]} validado aqui
FAMILIAS_GRAFO = {"app", "painel"}


def gerar_ulid() -> str:
    """ULID (timestamp de 48 bits em ms + 80 bits aleatórios, Crockford base32, 26 caracteres) para o id de um
    nó novo. Servidor e testes usam a mesma função — o editor (JS) gera o seu próprio id da mesma forma; os dois
    lados só precisam concordar no FORMATO (`ULID_RE`), não compartilhar implementação."""
    ts = int(time.time() * 1000) & ((1 << 48) - 1)
    valor = (ts << 80) | int.from_bytes(os.urandom(10), "big")
    caracteres = []
    for _ in range(26):
        caracteres.append(_CROCKFORD[valor & 0x1F])
        valor >>= 5
    return "".join(reversed(caracteres))


def corpo_canonico(corpo: dict) -> str:
    """Forma canônica: chaves ordenadas, sem espaço em branco, utf-8 literal (sem escape \\u de ida e volta).
    Reproduzível fora do banco com (note `sys.stdout.write`, não `print`: `print` acrescenta \\n e muda o hash):
      python3 -c "import json,sys; sys.stdout.write(json.dumps(json.load(sys.stdin),
          sort_keys=True, ensure_ascii=False, separators=(',',':')))" < corpo.json | sha256sum
    """
    return json.dumps(corpo, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_canonico(corpo: dict) -> str:
    return hashlib.sha256(corpo_canonico(corpo).encode("utf-8")).hexdigest()


def _corpo_do_documento(tipo: str, dados) -> dict | None:
    if tipos.familia_de(tipo) not in FAMILIAS_GRAFO:
        return None
    if not isinstance(dados, dict):
        return None
    corpo = dados.get("corpo")
    return corpo if isinstance(corpo, dict) else None


def validar_grafo(tipo: str, dados) -> None:
    """422 grafo_invalido (mesmo contrato de app/erros.py) quando: nó sem id ULID, dois nós com o mesmo id, ou
    ligação (`origem`/`alvo`) apontando para um id que não está em `corpo.nos`. O formato de cada campo (tipo do
    nó, tipos de `corpo`/`nos`/`ligacoes`) já é responsabilidade do JSON Schema do tipo (`tipos.validar`,
    chamado ANTES desta função nas duas rotas que escrevem `dados`); aqui só entra o que precisa da lista
    inteira para ser conferido."""
    # o tipo `cena` (L2-09-b) tem a mesma natureza — regras que precisam do documento inteiro e que o
    # JSON Schema não expressa — e entra pela MESMA porta, para não haver dois lugares onde um item é
    # conferido antes de gravar. Para qualquer outro tipo a chamada não faz nada.
    cena_documento.validar(tipo, dados)
    corpo = _corpo_do_documento(tipo, dados)
    if corpo is None:
        return
    nos = corpo.get("nos", [])
    if not isinstance(nos, list):
        return
    erros: list[dict] = []
    vistos: set[str] = set()
    validos: set[str] = set()
    for i, n in enumerate(nos):
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not ULID_RE.match(nid):
            erros.append({"campo": f"corpo.nos.{i}.id", "erro": "id de nó precisa ser um ULID", "regra": "ulid"})
            continue
        if nid in vistos:
            erros.append(
                {"campo": f"corpo.nos.{i}.id", "erro": f"id de nó repetido: {nid}", "regra": "id_duplicado"}
            )
            continue
        vistos.add(nid)
        validos.add(nid)
    ligacoes = corpo.get("ligacoes", [])
    if isinstance(ligacoes, list):
        for i, lig in enumerate(ligacoes):
            if not isinstance(lig, dict):
                continue
            for campo in ("origem", "alvo"):
                alvo = lig.get(campo)
                if alvo is not None and alvo not in validos:
                    erros.append(
                        {
                            "campo": f"corpo.ligacoes.{i}.{campo}",
                            "erro": f"ligação aponta para nó inexistente: {alvo}",
                            "regra": "referencia_pendente",
                        }
                    )
    if erros:
        raise ErroAPI(422, "grafo_invalido", f"grafo do documento ({tipo}) inválido", erros)


# ---------------------------------------------------------------------------------------------------------------
# migração de esquema na leitura (nunca escrita de volta; quem salvar de novo grava a versão vigente por si)


def _migrar_painel_v1_v2(dados: dict) -> dict:
    """v1→v2 (`docs/esquemas/painel-v1.json` → `painel-v2.json`): v1 não tinha grafo (`corpo` livre, os 1.571
    itens `painel` semeados em demo têm `corpo: {}`); v2 exige `corpo.nos`/`corpo.ligacoes`. Documento antigo
    ganha as duas listas vazias na LEITURA — nunca perde dado (não havia nó nenhum para perder) e o usuário
    passa a editar dentro do esquema novo na primeira gravação."""
    corpo = dict(dados.get("corpo") or {})
    corpo.setdefault("nos", [])
    corpo.setdefault("ligacoes", [])
    return {**dados, "corpo": corpo, "esquema_versao": 2}


def _migrar_app_v1_v2(dados: dict) -> dict:
    """Mesma migração de `_migrar_painel_v1_v2`, para o tipo `app` (1.573 itens semeados com `corpo: {}`)."""
    corpo = dict(dados.get("corpo") or {})
    corpo.setdefault("nos", [])
    corpo.setdefault("ligacoes", [])
    return {**dados, "corpo": corpo, "esquema_versao": 2}


# registro fechado: (tipo, versão de origem) -> função que devolve o documento na versão seguinte
_MIGRACOES = {
    ("painel", 1): _migrar_painel_v1_v2,
    ("app", 1): _migrar_app_v1_v2,
}

_TETO_PASSOS = 50  # mesma ordem de grandeza de outras cadeias da casa; documento real nunca chega perto disso


def migrar_para_leitura(tipo: str, dados) -> tuple[dict, bool, int | None, int | None]:
    """Aplica a cadeia de `migrar_<tipo>_v<N>_v<N+1>` até `plat.tipo_item.esquema_versao` vigente.
    Devolve (dados_possivelmente_migrados, mudou, versao_de_origem, versao_final). Nunca grava no banco:
    é a leitura (GET) que decide se mostra migrado; se não houver migração registrada para o próximo passo,
    para onde conseguiu chegar (documento não fica ilegível por causa de uma migração ausente)."""
    if not isinstance(dados, dict):
        return dados, False, None, None
    origem = dados.get("esquema_versao")
    if not isinstance(origem, int):
        return dados, False, None, None
    try:
        alvo = tipos.obter(tipo)["esquema_versao"]
    except ErroAPI:
        return dados, False, None, None
    if origem >= alvo:
        return dados, False, None, None
    atual = dados
    passos = 0
    while atual.get("esquema_versao", origem) < alvo and passos < _TETO_PASSOS:
        fn = _MIGRACOES.get((tipo, atual.get("esquema_versao", origem)))
        if fn is None:
            break
        atual = fn(atual)
        passos += 1
    final = atual.get("esquema_versao", origem)
    return atual, final != origem, origem, (final if final != origem else None)

#!/usr/bin/env python3
"""Gerador de prompt de agente do laço PLATAFORMA ENTERPRISE.

Monta, a partir do estado REAL (estado.json + git dos worktrees), o prompt pronto de um agente
construtor, de um adversário de um item, ou de um adversário de uma linha inteira.

Uso:
  prompt_item.py L0-06-backup-status
  prompt_item.py L0-06-backup-status --adversario
  prompt_item.py --linha L1
  prompt_item.py L0-06 --trilha stac --porta 8162      (forçar trilha/porta)
  prompt_item.py --lista L1                            (só lista os itens da linha)

Escreve em laco/vivo/prompts/ e imprime o caminho. NUNCA escreve no estado.json.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

BASE = "/home/dev/plataforma/laco"
REPO = "/home/dev/plataforma/enterprise"
WT = "/home/dev/plataforma/wt"
ESTADO = f"{BASE}/estado.json"
BRIEF = f"{BASE}/BRIEF_WORKTREES.md"
SAIDA = f"{BASE}/vivo/prompts"

# Trilhas em worktree e a porta de teste de cada uma. A porta é do uvicorn que o agente sobe a
# partir do próprio worktree (regra 3 do brief); 8150-8159 são do produto e do painel, não usar.
#
# 06/09, pedido do supervisor: o dicionário era FIXO com quatro nomes, então toda trilha criada
# depois por `trilha_ambiente.sh` ficava invisível para o gerador e o agente tinha de corrigir
# worktree e porta à mão (por sed) no prompt já gerado — passo manual que a fábrica devia matar.
# Agora a lista sai do disco: uma trilha existe quando existe `var/trilha/<nome>.env`, que é
# exatamente o que `trilha_ambiente.sh` escreve ao terminar. As quatro portas históricas ficam
# fixas para não mudar debaixo de quem já está rodando; as novas ganham a primeira porta livre da
# faixa 8165-8199 e essa escolha é GRAVADA em `var/trilha/portas.json`, porque porta que muda entre
# duas gerações do mesmo prompt manda dois agentes para a mesma porta.
DIR_TRILHA = f"{BASE}/var/trilha"
MAPA_PORTAS = f"{DIR_TRILHA}/portas.json"
PORTAS_HISTORICAS = {"garage": 8161, "stac": 8162, "valida": 8163, "amc": 8164}
FAIXA_PORTAS = range(8165, 8400)  # 06/09: 8165-8199 esgotou com 35 trilhas; ampliada


def _portas_gravadas():
    try:
        with open(MAPA_PORTAS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _grava_portas(mapa):
    os.makedirs(DIR_TRILHA, exist_ok=True)
    tmp = MAPA_PORTAS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, MAPA_PORTAS)


def _portas_ocupadas():
    """Portas que JÁ estão escutando agora. Sem isto o gerador entrega a um agente novo a porta em
    que outro agente já subiu o uvicorn dele, e os dois medem a aplicação errada (o `ab`/k6 com URL
    errada 'passa' medindo 404 é a mesma classe de erro)."""
    try:  # `sh()` só é definida mais abaixo no arquivo; aqui vai o subprocess direto
        r = subprocess.run("ss -ltnH 2>/dev/null || netstat -ltn 2>/dev/null", shell=True,
                           capture_output=True, text=True, timeout=10)
        saida = r.stdout
    except Exception:
        return set()
    return {int(m) for m in re.findall(r"[:.](\d{4,5})\s", saida)}


def descobre_trilhas():
    """Toda trilha com `var/trilha/<nome>.env` no disco, com porta estável e worktree conferido."""
    nomes = sorted(os.path.basename(a)[:-4] for a in glob.glob(f"{DIR_TRILHA}/*.env"))
    for n in PORTAS_HISTORICAS:                       # aparecem mesmo sem .env, como antes
        if n not in nomes:
            nomes.append(n)
    gravadas = _portas_gravadas()
    usadas = set(PORTAS_HISTORICAS.values()) | {int(v) for v in gravadas.values()} | _portas_ocupadas()
    mudou = False
    trilhas = {}
    for n in sorted(nomes):
        if n in PORTAS_HISTORICAS:
            porta = PORTAS_HISTORICAS[n]
        elif n in gravadas:
            porta = int(gravadas[n])
        else:
            livre = next((p for p in FAIXA_PORTAS if p not in usadas), None)
            if livre is None:
                sys.exit(f"sem porta livre na faixa {FAIXA_PORTAS.start}-{FAIXA_PORTAS.stop - 1}")
            porta = livre
            gravadas[n] = porta
            usadas.add(porta)
            mudou = True
        caminho = f"{WT}/{n}"
        trilhas[n] = {"porta": porta, "caminho": caminho, "ramo": f"wt/{n}",
                      "existe": os.path.isdir(caminho)}
    if mudou:
        _grava_portas(gravadas)
    return trilhas


TRILHAS = descobre_trilhas()


def registra_trilha(nome):
    """Trilha NOVA para um item que ainda não tem a sua. Um agente, uma árvore: dois agentes na mesma
    árvore compartilham o índice do git, e isso quase custou o trabalho de todos em 06/09."""
    if nome in TRILHAS:
        return TRILHAS[nome]
    gravadas = _portas_gravadas()
    usadas = set(PORTAS_HISTORICAS.values()) | {int(v) for v in gravadas.values()} | _portas_ocupadas()
    livre = next((p for p in FAIXA_PORTAS if p not in usadas), None)
    if livre is None:
        sys.exit(f"sem porta livre na faixa {FAIXA_PORTAS.start}-{FAIXA_PORTAS.stop - 1}")
    gravadas[nome] = livre
    _grava_portas(gravadas)
    caminho = f"{WT}/{nome}"
    TRILHAS[nome] = {"porta": livre, "caminho": caminho, "ramo": f"wt/{nome}",
                     "existe": os.path.isdir(caminho)}
    return TRILHAS[nome]
# Afinidade por assunto: o agente cai na trilha que já mexe naquele código, para reduzir conflito
# de merge. A ordem importa (primeira regra que casa vence).
AFINIDADE = [
    (r"garage|s3|balde|bucket|objeto|armazenamento|cota|upload|envio", "garage"),
    (r"stac|cog|catalogo|catálogo|item|colecao|coleção|tile|raster|mosaico|titiler", "stac"),
    (r"valida|validac|validaç|teste|refuta|seguranc|seguranç|isolament|auditoria|permiss", "valida"),
    (r"amc|multicrit|fator|peso|analise|análise|geoprocess|rede|utilidade|traçado|tracado", "amc"),
]


def sh(cmd, cwd=None, timeout=25):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def carrega():
    with open(ESTADO, encoding="utf-8") as f:
        return json.load(f)


def acha_item(backlog, chave):
    for x in backlog:
        if x["id"] == chave:
            return x
    cand = [x for x in backlog if x["id"].startswith(chave)]
    if len(cand) == 1:
        return cand[0]
    if not cand:
        sys.exit(f"item não encontrado: {chave}")
    sys.exit("ambíguo: " + ", ".join(x["id"] for x in cand[:12]))


def commit_do_item(iid):
    """Último commit que carrega o id do item no assunto ou no corpo, em qualquer ramo."""
    s = sh(f"git log --all -1 --format='%h|%ad|%s' --date=short --grep={json.dumps(iid)} -F", cwd=REPO)
    if s:
        return s.split("|", 2)
    return None


def commit_do_ledger(estado, iid):
    sha = None
    nota = None
    for l in estado.get("ledger", []):
        if l.get("item") == iid:
            sha = l.get("commit") or sha
            nota = l.get("nota") or l.get("evento") or nota
    return sha, nota


def arquivos_do_commit(sha):
    if not sha:
        return []
    s = sh(f"git show --name-only --format= {sha}", cwd=REPO)
    return [x for x in s.splitlines() if x.strip()]


def prefixo_familia(iid):
    """L0-02-g-perfil-usuario -> L0-02 ; L1-01-d-garage -> L1-01."""
    p = iid.split("-")
    return "-".join(p[:2]) if len(p) >= 2 else iid


def irmaos(backlog, item):
    pai = item.get("pai")
    pre = prefixo_familia(item["id"])
    saida = []
    for x in backlog:
        if x["id"] == item["id"]:
            continue
        if (pai and x.get("pai") == pai) or prefixo_familia(x["id"]) == pre:
            saida.append(x)
    return saida


CAMINHO_RE = re.compile(r"`([^`\n]+)`")
PARECE_CAMINHO = re.compile(r"^[\w./-]+\.(py|sql|sh|md|json|yml|yaml|html|js|css|ini|toml|regex)$|^(app|db|tests|docs|web|deploy|install\.d|changelog\.d)/")


def arquivos_do_texto(*textos):
    achados = []
    for t in textos:
        if not t:
            continue
        for m in CAMINHO_RE.findall(t):
            m = m.strip()
            if PARECE_CAMINHO.match(m):
                achados.append(m)
        for m in re.findall(r"\b(?:app|db|tests|docs|web|deploy)/[\w./-]+", t):
            achados.append(m)
    vistos, saida = set(), []
    for a in achados:
        if a not in vistos:
            vistos.add(a)
            saida.append(a)
    return saida


def arquivos_provaveis(backlog, item, estado):
    """Deriva de (a) caminhos citados no portão/hipótese e (b) arquivos tocados pelos irmãos já
    entregues. Não é promessa: é onde a família do item costuma morar."""
    do_texto = arquivos_do_texto(item.get("portao_de_pronto"), item.get("hipotese"), item.get("refutacao"))
    de_irmaos = {}
    for irm in irmaos(backlog, item):
        if irm["estado"] not in ("entregue", "parcial"):
            continue
        sha, _ = commit_do_ledger(estado, irm["id"])
        if not sha:
            c = commit_do_item(irm["id"])
            sha = c[0] if c else None
        for a in arquivos_do_commit(sha):
            de_irmaos.setdefault(a, []).append(irm["id"])
    ordenados = sorted(de_irmaos.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return do_texto, ordenados[:25]


def escolhe_trilha(item, forcada=None):
    if forcada:
        if forcada not in TRILHAS:
            sys.exit(f"trilha desconhecida: {forcada} (use {', '.join(TRILHAS)})")
        if not TRILHAS[forcada]["existe"]:
            print(f"aviso: o worktree {TRILHAS[forcada]['caminho']} ainda não existe no disco",
                  file=sys.stderr)
        return forcada
    # 06/09: a AFINIDADE por assunto foi DESLIGADA. Ela mandava vários itens para as mesmas quatro
    # trilhas históricas, e dois agentes na MESMA árvore compartilham o índice do git: um deles achou
    # 18 deleções falsas no índice e só não perdeu o trabalho de todo mundo porque conferiu antes de
    # um `commit -a`; outro teve de commitar por índice privado. Um agente, uma árvore.
    # Agora cada item recebe uma trilha PRÓPRIA, derivada do id, criada por trilha_ambiente.sh.
    nome = "i" + re.sub(r"[^a-z0-9]", "", item["id"].lower())[:10]
    registra_trilha(nome)
    return nome


def bloco_dependencias(backlog, estado, item):
    deps = item.get("dependencias") or []
    if not deps:
        return "Nenhuma dependência declarada.", []
    linhas, abertas = [], []
    porid = {x["id"]: x for x in backlog}
    for d in deps:
        x = porid.get(d)
        if not x:
            linhas.append(f"- `{d}` — NÃO EXISTE no backlog (dependência quebrada; avise no handoff)")
            abertas.append(d)
            continue
        sha, nota = commit_do_ledger(estado, d)
        c = commit_do_item(d)
        sha = sha or (c[0] if c else None)
        assunto = c[2] if c else ""
        if x["estado"] == "entregue":
            linhas.append(f"- `{d}` — ENTREGUE, commit `{sha or 'sem sha no ledger'}` {assunto}".rstrip())
        elif x["estado"] == "parcial":
            linhas.append(f"- `{d}` — PARCIAL, commit `{sha or '-'}`. Faltava: {(nota or '').strip()[:300]}")
            abertas.append(d)
        else:
            linhas.append(f"- `{d}` — **{x['estado'].upper()}, ainda não entregue**. {(x.get('bloqueio') or '').strip()[:200]}")
            abertas.append(d)
    return "\n".join(linhas), abertas


def cabecalho(item, trilha):
    t = TRILHAS[trilha]
    return f"""# Item `{item['id']}` — trilha `{trilha}`

| campo | valor |
|---|---|
| linha de produto | {item.get('linha')} |
| prioridade | {item.get('prioridade')} |
| estado atual | {item.get('estado')} · tentativas {item.get('tentativas', 0)} |
| worktree | `{t['caminho']}` (ramo `{t['ramo']}`) |
| porta de teste | **{t['porta']}** (uvicorn seu, a partir do worktree) |
| papéis | {', '.join(item.get('papeis') or [])} |
| bloqueio anotado | {item.get('bloqueio') or '—'} |
"""


def corpo_comum(estado, backlog, item, trilha):
    deps_txt, deps_abertas = bloco_dependencias(backlog, estado, item)
    do_texto, de_irmaos = arquivos_provaveis(backlog, item, estado)
    t = TRILHAS[trilha]
    p = []
    p.append(cabecalho(item, trilha))
    p.append("## Hipótese (o que se afirma)\n\n" + (item.get("hipotese") or "—"))
    p.append("## Portão de pronto — LITERAL, cláusula por cláusula\n\n> "
             + (item.get("portao_de_pronto") or "—").replace("\n", "\n> ")
             + "\n\nCada cláusula acima vira teste ou medida gravada em "
               f"`tests/medidas/{item['id']}.json`. Não marque nada que não tenha passado.")
    p.append("## Refutação exigida (o adversário vai fazer isto)\n\n> "
             + (item.get("refutacao") or "—").replace("\n", "\n> "))
    p.append("## Dependências\n\n" + deps_txt
             + ("\n\n**Dependência aberta: " + ", ".join(deps_abertas)
                + "** — se ela bloquear uma cláusula, entregue o resto e registre a cláusula pendente"
                  " no handoff em vez de fingir que passou." if deps_abertas else ""))
    if do_texto:
        p.append("## Arquivos citados no próprio portão\n\n"
                 + "\n".join(f"- `{a}`" for a in do_texto))
    if de_irmaos:
        p.append("## Arquivos prováveis (derivados dos irmãos já entregues desta família)\n\n"
                 + "\n".join(f"- `{a}`  ← {', '.join(ids[:3])}" for a, ids in de_irmaos)
                 + "\n\nIsto é onde a família deste item mora hoje; não é ordem de mexer em todos.")
    fontes = item.get("fontes") or []
    if fontes:
        p.append("## Fontes declaradas no item\n\n" + "\n".join(f"- {f}" for f in fontes))
    ativos = item.get("ativos_da_casa") or ([item["ativo_da_casa"]] if item.get("ativo_da_casa") else [])
    if ativos:
        p.append("## Ativo da casa a reusar (não refazer)\n\n" + "\n".join(f"- {a}" for a in ativos))
    p.append(f"""## Ambiente da trilha (rode antes de qualquer teste)

```bash
bash {BASE}/trilha_ambiente.sh {trilha}
set -a; source {BASE}/var/trilha/{trilha}.env; set +a
cd {t['caminho']}
venv/bin/pytest tests/unit tests/api -q          # base própria: SEM flock
# API sua, se o item precisar:
venv/bin/uvicorn app.main:app --port {t['porta']}
```

Ao terminar, marque o item (o script já trava e escreve atômico):

```bash
python3 {BASE}/marcar_item.py {item['id']} <entregue|parcial|refutado> "<nota honesta>" <sha>
```""")
    return "\n\n".join(p)


def brief():
    with open(BRIEF, encoding="utf-8") as f:
        return f.read()


def prompt_construtor(estado, backlog, item, trilha):
    papeis = ", ".join(item.get("papeis") or ["backend"])
    return f"""Você é um agente construtor do laço PLATAFORMA ENTERPRISE, nos papéis: {papeis}.
Construa o item abaixo até o portão de pronto passar de verdade. Não pergunte no meio: decida,
construa, meça e registre. Sem placeholder, sem mock, sem rota de dado fixo. Português no código,
nos testes e nos documentos. Sem emoji.

{corpo_comum(estado, backlog, item, trilha)}

---

# Brief comum das trilhas (leia inteiro antes de tocar em qualquer arquivo)

{brief()}
"""


def prompt_adversario(estado, backlog, item, trilha):
    sha, nota = commit_do_ledger(estado, item["id"])
    c = commit_do_item(item["id"])
    sha = sha or (c[0] if c else None)
    handoff = f"{BASE}/handoffs/T{estado.get('turno', 3)}/{item['id']}.md"
    tem = "existe" if os.path.exists(handoff) else "NÃO existe — cobre isso no laudo"
    return f"""Você é o ADVERSÁRIO do item `{item['id']}`. Seu trabalho é DERRUBAR a afirmação, não
elogiá-la. Você não construiu nada disto e não deve defender ninguém. Comece assumindo que o portão
foi declarado passado sem passar, e procure a cláusula mais cara de provar.

Regras do laudo:
1. Ataque cláusula por cláusula do portão. Para cada uma: reproduza o comando, cole a saída, e diga
   PASSA ou CAI. Cláusula sem comando reproduzível = CAI.
2. Todo achado seu vira teste no repositório marcado `@pytest.mark.xfail(strict=True)` com o motivo
   no `reason`, para que o conserto quebre o xfail e prove que consertou.
3. Procure especificamente: escrita concorrente, limite/cota que só existe no adaptador, segredo que
   vaza para processo filho, contagem que diverge da estimativa, caminho que sai do inquilino,
   número no documento que ninguém mediu, e "passou" que na verdade foi pulado (skip).
4. Escreva o laudo em `{BASE}/handoffs/T{estado.get('turno', 3)}/{item['id']}-laudo-adversario.md`:
   cláusula → veredito → prova → gravidade. Termine com um veredito único:
   ENTREGUE, PARCIAL (com a lista do que falta) ou REFUTADO (com o achado que derruba).
5. Marque o resultado: `python3 {BASE}/marcar_item.py {item['id']} <estado> "<achado>" <sha>`.
   Não conserte o código: você mede e derruba, quem constrói conserta.

Material sob ataque:
- commit reivindicado: `{sha or 'nenhum sha no ledger — pergunte-se por que'}`
- última nota do ledger: {(nota or '—').strip()[:500]}
- handoff do construtor: `{handoff}` ({tem})

{corpo_comum(estado, backlog, item, trilha)}

---

# Brief comum das trilhas (vale para você também)

{brief()}
"""


def prompt_linha(estado, backlog, linha):
    alvo = [x for x in backlog if x.get("linha", "").upper().startswith(linha.upper())
            or x["id"].upper().startswith(linha.upper() + "-")]
    if not alvo:
        sys.exit(f"nenhum item na linha {linha}")
    atacaveis = [x for x in alvo if x["estado"] in ("entregue", "parcial")]
    refutados = [x for x in alvo if x["estado"] == "refutado"]
    nome_linha = alvo[0].get("linha", linha)
    blocos = []
    for x in atacaveis:
        sha, nota = commit_do_ledger(estado, x["id"])
        c = commit_do_item(x["id"])
        sha = sha or (c[0] if c else None)
        blocos.append(
            f"""### `{x['id']}` — {x['estado'].upper()} · commit `{sha or 'sem sha'}`

- hipótese: {x.get('hipotese') or '—'}
- portão (LITERAL): {x.get('portao_de_pronto') or '—'}
- refutação exigida: {x.get('refutacao') or '—'}
- última nota do ledger: {(nota or '—').strip()[:300]}
""")
    lista_ref = "\n".join(f"- `{x['id']}` — {(x.get('bloqueio') or '')[:200]}" for x in refutados) or "nenhum"
    return f"""Você é o ADVERSÁRIO DE LINHA da **{nome_linha}**. Ataque de uma vez os {len(atacaveis)}
itens desta linha que estão declarados entregues ou parciais e ainda não foram derrubados. Seu ganho
está no que a linha TEM EM COMUM: a mesma suposição errada costuma valer para todos os irmãos.

Ordem de trabalho:
1. Leia os {len(atacaveis)} portões abaixo juntos e escreva PRIMEIRO as 3 a 5 suposições
   transversais que a linha inteira assume (isolamento por inquilino, cota, unidade de medida,
   projeção, ordem de escrita, quem valida a entrada). Ataque essas primeiro: uma delas cair derruba
   vários itens de uma vez.
2. Depois, item por item, cláusula por cláusula: comando, saída, PASSA ou CAI.
3. Todo achado vira teste `@pytest.mark.xfail(strict=True)` com o motivo no `reason`.
4. Laudo único em `{BASE}/handoffs/T{estado.get('turno', 3)}/linha-{linha}-laudo-adversario.md`, com
   uma seção por item e uma seção "o que é comum à linha". Marque cada item derrubado com
   `python3 {BASE}/marcar_item.py <id> refutado "<achado>" <sha>`.
5. Não conserte nada. Você mede e derruba.

Já refutados nesta linha (não repita o trabalho, mas confira se o conserto criou buraco novo):
{lista_ref}

## Itens sob ataque

{chr(10).join(blocos)}

---

# Brief comum das trilhas

{brief()}
"""


def main():
    ap = argparse.ArgumentParser(description="gera o prompt de um item do laço")
    ap.add_argument("item", nargs="?", help="id (ou prefixo único) do item")
    ap.add_argument("--adversario", action="store_true", help="prompt do adversário do item")
    ap.add_argument("--linha", help="prompt de adversário de uma linha inteira (ex.: L1)")
    ap.add_argument("--lista", help="só lista os itens de uma linha e sai")
    ap.add_argument("--trilha", help="forçar trilha (" + ", ".join(TRILHAS) + ")")
    ap.add_argument("--porta", type=int, help="forçar porta de teste")
    a = ap.parse_args()

    estado = carrega()
    backlog = estado["backlog"]

    if a.lista:
        for x in backlog:
            if x["id"].upper().startswith(a.lista.upper()):
                print(f"{x['estado']:9} {x['id']:38} {x.get('linha','')}")
        return

    os.makedirs(SAIDA, exist_ok=True)
    if a.linha:
        texto = prompt_linha(estado, backlog, a.linha)
        destino = f"{SAIDA}/linha-{a.linha}-adversario.md"
    else:
        if not a.item:
            ap.error("informe o id do item ou --linha")
        item = acha_item(backlog, a.item)
        trilha = escolhe_trilha(item, a.trilha)
        if a.porta:
            TRILHAS[trilha] = dict(TRILHAS[trilha], porta=a.porta)
        if a.adversario:
            texto = prompt_adversario(estado, backlog, item, trilha)
            destino = f"{SAIDA}/{item['id']}--adversario.md"
        else:
            texto = prompt_construtor(estado, backlog, item, trilha)
            destino = f"{SAIDA}/{item['id']}.md"

    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(tmp, destino)
    print(destino)


if __name__ == "__main__":
    main()

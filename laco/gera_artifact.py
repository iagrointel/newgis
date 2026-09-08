#!/usr/bin/env python3
"""Gera a página de progresso da corrida (artifact) a partir do dado VIVO:
agora.json (painel), estado.json (backlog), git (commits) e atividade dos worktrees.
Uso: python3 gera_artifact.py > /caminho/saida.html   (republicar = rodar de novo)"""
import json, os, subprocess, time, glob, html

B = "/home/dev/plataforma/laco"; R = "/home/dev/plataforma/enterprise"; WT = "/home/dev/plataforma/wt"
d = json.load(open(f"{B}/vivo/agora.json"))
e = json.load(open(f"{B}/estado.json"))
p = e["placar"]; tot = p["total"]
b = e["backlog"]
por_id = {x["id"]: x for x in b}

def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout
    except Exception: return ""

# --- atividade real por worktree (arquivos mexidos nos últimos 40 min = agente em voo)
agora = time.time(); em_voo = []
for w in sorted(glob.glob(f"{WT}/*/")):
    nome = os.path.basename(w.rstrip("/"))
    if nome in ("integra",): continue
    rec = 0; ult = 0
    for root, dirs, files in os.walk(w):
        dirs[:] = [x for x in dirs if x not in ("venv", ".git", "__pycache__", "node_modules")]
        for f in files:
            try: m = os.path.getmtime(os.path.join(root, f))
            except OSError: continue
            if agora - m < 2400: rec += 1; ult = max(ult, m)
    if rec:
        ramo = sh(f"git -C {w} log -1 --format=%s 2>/dev/null").strip()[:70]
        em_voo.append((nome, rec, int((agora - ult) / 60), ramo))
em_voo.sort(key=lambda t: t[2])

commits_1h = int(sh(f"git -C {R} log --all --since='1 hour ago' --oneline | wc -l").strip() or 0)
commits_24h = d.get("commits_24h") or int(sh(f"git -C {R} log --all --since='24 hours ago' --oneline | wc -l").strip() or 0)
cph = d.get("commits_por_hora") or []
laudos = len(glob.glob(f"{B}/handoffs/T3/*ADVERS*"))
consertos = len(glob.glob(f"{B}/handoffs/T3/*CONSERTO*"))
handoffs = len(glob.glob(f"{B}/handoffs/T3/*.md"))
testes = int(sh(f"git -C {R} log --all --since='24 hours ago' -p --diff-filter=AM -- 'tests/*' 2>/dev/null | grep -c '^+def test_'").strip() or 0)
rec = d.get("recursos", {})
con = rec.get("conexoes", {})
fila = sh(f"cd {B} && bash fila_merge.sh listar 2>&1").strip().splitlines()
fila = [l.split(". ", 1)[-1] for l in fila if l[:1].isdigit()]
refut = [x for x in b if x["estado"] == "refutado"]
conserto_ramos = {r for r in os.listdir(WT) if r.endswith("fix") or r in ("partilha", "secdef", "segur", "cred")}

def esc(s): return html.escape(str(s))
def n(v, t, w=100.0): return v * w / t if t else 0

linhas_html = []
for L in d["linhas"]:
    t = L["total"]; ent = L.get("entregue", 0); par = L.get("parcial", 0); ref = L.get("refutado", 0); ten = L.get("tentando", 0)
    pend = t - ent - par - ref - ten
    linhas_html.append(f"""
    <div class="linha">
      <div class="linha-nome">{esc(L['titulo'])}</div>
      <div class="barra" title="{ent} provados · {par} parciais · {ref} refutados · {pend} na fila">
        <span class="s-ent" style="width:{n(ent,t):.2f}%"></span><span class="s-par" style="width:{n(par,t):.2f}%"></span><span class="s-ref" style="width:{n(ref,t):.2f}%"></span><span class="s-ten" style="width:{n(ten,t):.2f}%"></span>
      </div>
      <div class="linha-num mono">{ent}<span class="dim">/{t}</span></div>
    </div>""")

voo_html = "".join(f"""<li><span class="mono">{esc(a)}</span><span class="dim">{c} arquivos · há {m} min</span><span class="ramo">{esc(r)}</span></li>""" for a, c, m, r in em_voo[:18]) or "<li class='dim'>nenhum worktree com atividade nos últimos 40 min</li>"
fila_html = "".join(f"<li class='mono'>{esc(x)}</li>" for x in fila) or "<li class='dim'>fila vazia — lote em verificação ou já juntado</li>"
ult = d.get("ultimos_commits") or []
ult_html = "".join(f"<li><span class='mono dim'>{esc(str(c.get('sha',''))[:7])}</span> {esc(str(c.get('assunto', c.get('msg','')))[:88])}</li>" for c in ult[:10])
if not ult_html:
    for l in sh(f"git -C {R} log --all --since='3 hours ago' --format='%h|%s' | head -10").splitlines():
        s, _, m = l.partition("|"); ult_html += f"<li><span class='mono dim'>{esc(s)}</span> {esc(m[:88])}</li>"

mx = max([c.get("n", c) if isinstance(c, dict) else c for c in cph] or [1])
spark = "".join(f"<i style='height:{max(4, n((c.get('n',c) if isinstance(c,dict) else c), mx, 100)):.0f}%' title='{esc(c.get('hora','') if isinstance(c,dict) else '')}'></i>" for c in cph[-24:])

ref_por_linha = {}
for x in refut: ref_por_linha.setdefault(x["id"].split("-")[0], []).append(x["id"])
ref_html = "".join(f"<div class='ref-linha'><b class='eyebrow'>{esc(k)}</b> <span class='mono'>{esc(', '.join(i.replace(k+'-','') for i in sorted(v)))}</span></div>" for k, v in sorted(ref_por_linha.items()))

mem = rec.get("mem_disponivel_mb", 0); conn = con.get("total", 0)
sem_mem = "crit" if mem < 2000 else ("aviso" if mem < 4000 else "ok")
sem_con = "crit" if conn > 85 else ("aviso" if conn > 70 else "ok")
quando = time.strftime("%d/%m/%Y %H:%M UTC", time.gmtime())

print(f"""<title>Corrida plat</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@500;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#0d0f11;--sup:#14171c;--sup2:#1a1e24;--tx:#e8e4dc;--dim:#8d8a82;--lin:#2a2f37;--amb:#e8a33d;
--ent:#5fb36a;--par:#d9b44a;--ref:#d9534f;--ten:#4fb3bf;--fila:#2e333b;
--disp:"Big Shoulders Display",Impact,"Arial Narrow",sans-serif;--body:"IBM Plex Sans",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font-family:var(--body);font-size:14px;line-height:1.45;-webkit-font-smoothing:antialiased}}
a{{color:var(--amb)}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 22px 60px}}
.mono{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
.dim{{color:var(--dim)}}
.eyebrow{{font-family:var(--disp);font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:12px;color:var(--amb)}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;border-bottom:1px solid var(--lin);padding-bottom:14px;margin-bottom:22px}}
h1{{font-family:var(--disp);font-weight:800;font-size:44px;line-height:.95;margin:0;letter-spacing:.01em;text-wrap:balance}}
h1 small{{display:block;font-family:var(--body);font-weight:400;font-size:13px;color:var(--dim);letter-spacing:0;margin-top:8px;text-transform:none}}
.quando{{font-family:var(--mono);color:var(--dim);font-size:12px;text-align:right}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}}
.tile{{background:var(--sup);border:1px solid var(--lin);padding:14px 16px 12px;position:relative}}
.tile::before,.tile::after{{content:"";position:absolute;width:10px;height:10px;border-color:var(--amb);border-style:solid}}
.tile::before{{top:-1px;left:-1px;border-width:2px 0 0 2px}}.tile::after{{bottom:-1px;right:-1px;border-width:0 2px 2px 0}}
.tile .n{{font-family:var(--disp);font-weight:800;font-size:46px;line-height:1;margin:6px 0 2px;font-variant-numeric:tabular-nums}}
.tile .l{{color:var(--dim);font-size:12px}}
.c-ent{{color:var(--ent)}}.c-par{{color:var(--par)}}.c-ref{{color:var(--ref)}}.c-ten{{color:var(--ten)}}
section{{margin-bottom:26px}}
h2{{font-family:var(--disp);font-weight:700;font-size:20px;letter-spacing:.04em;text-transform:uppercase;margin:0 0 10px;color:var(--tx)}}
h2 span{{color:var(--dim);font-family:var(--body);font-weight:400;font-size:12px;letter-spacing:0;text-transform:none;margin-left:10px}}
.linha{{display:grid;grid-template-columns:150px 1fr 76px;gap:12px;align-items:center;padding:6px 0}}
.linha-nome{{font-weight:500}}
.barra{{display:flex;height:18px;background:var(--fila);overflow:hidden}}
.barra span{{display:block;height:100%}}
.s-ent{{background:var(--ent)}}.s-par{{background:var(--par)}}.s-ref{{background:var(--ref)}}.s-ten{{background:var(--ten)}}
.linha-num{{text-align:right;font-size:15px}}
.legenda{{display:flex;gap:18px;flex-wrap:wrap;color:var(--dim);font-size:12px;margin-top:8px}}
.legenda i{{display:inline-block;width:12px;height:12px;vertical-align:-2px;margin-right:6px}}
.duas{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
.painel{{background:var(--sup);border:1px solid var(--lin);padding:14px 16px}}
ul{{list-style:none;margin:0;padding:0}}
li{{padding:5px 0;border-bottom:1px solid var(--lin);display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:baseline;font-size:13px}}
li .ramo{{grid-column:1/-1;color:var(--dim);font-size:12px;padding-left:2px}}
li:last-child{{border-bottom:0}}
.fluxo{{font-family:var(--mono);font-size:12.5px;line-height:1.55;white-space:pre;overflow-x:auto;color:var(--tx);background:var(--sup2);padding:14px 16px;border-left:3px solid var(--amb)}}
.fluxo b{{color:var(--amb);font-weight:500}}
.spark{{display:flex;align-items:flex-end;gap:3px;height:54px;margin-top:6px}}
.spark i{{flex:1;background:var(--amb);opacity:.85;min-width:6px}}
.rec{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.rec div{{padding:10px 12px;border:1px solid var(--lin)}}
.rec .v{{font-family:var(--disp);font-size:26px;font-weight:700}}
.ok .v{{color:var(--ent)}}.aviso .v{{color:var(--par)}}.crit .v{{color:var(--ref)}}
.ref-linha{{padding:6px 0;border-bottom:1px solid var(--lin);font-size:13px;line-height:1.6}}
.ref-linha:last-child{{border-bottom:0}}
.nota{{color:var(--dim);font-size:12.5px;max-width:70ch;margin-top:10px}}
@media(max-width:820px){{.grid{{grid-template-columns:1fr 1fr}}.duas{{grid-template-columns:1fr}}.rec{{grid-template-columns:1fr 1fr}}.linha{{grid-template-columns:110px 1fr 60px}}h1{{font-size:34px}}}}
</style>
<div class="wrap">
<header>
  <h1>Corrida <span style="color:var(--amb)">plat</span><small>Plataforma SIG própria · {tot} itens com portão de pronto e adversário independente · sessão única, Fable dirige</small></h1>
  <div class="quando">retrato de<br>{quando}</div>
</header>

<div class="grid">
  <div class="tile"><div class="eyebrow">provados</div><div class="n c-ent">{p['entregues']}</div><div class="l">portão passou e adversário não refutou</div></div>
  <div class="tile"><div class="eyebrow">parciais</div><div class="n c-par">{p['parciais']}</div><div class="l">mecanismo provado, cláusula pendente nomeada</div></div>
  <div class="tile"><div class="eyebrow">refutados</div><div class="n c-ref">{p['refutados']}</div><div class="l">derrubados pelo adversário, conserto em curso</div></div>
  <div class="tile"><div class="eyebrow">na fila</div><div class="n dim">{tot - p['entregues'] - p['parciais'] - p['refutados']}</div><div class="l">não iniciados</div></div>
</div>

<section>
  <h2>Por linha de produto <span>barra = 100 % dos itens da linha</span></h2>
  {''.join(linhas_html)}
  <div class="legenda"><span><i style="background:var(--ent)"></i>provado</span><span><i style="background:var(--par)"></i>parcial</span><span><i style="background:var(--ref)"></i>refutado, conserto a caminho</span><span><i style="background:var(--ten)"></i>agente no item</span><span><i style="background:var(--fila)"></i>fila</span></div>
  <p class="nota">O vermelho não é trabalho perdido: são itens que estavam marcados como prontos e caíram quando um adversário independente os verificou. Cada conserto entra com o teste do ataque junto, então o vermelho vira verde com prova, não com declaração.</p>
</section>

<section>
  <h2>O ciclo <span>como um item vira "provado"</span></h2>
<div class="fluxo"><b>FABLE</b> dirige · elege itens · JUNTA os ramos · arbitra
   │
   ├──▶ <b>SONNET</b> constrói ou conserta em worktree próprio, base de banco própria
   │            │  commit no ramo wt/&lt;item&gt;
   ▼            ▼
<b>FILA DE JUNÇÃO</b>  lote de 6–11 ramos · suíte inteira uma vez por lote
   │            bisseção acha o ramo culpado se quebrar
   ▼
<b>ADVERSÁRIO</b>  agente separado que NÃO viu a construção · ataca as suposições
   │          transversais da linha primeiro · achado vira teste xfail(strict)
   └──▶ achou? volta para <b>SONNET</b> consertar ──▶ fila ──▶ até o adversário não achar nada</div>
</section>

<div class="duas">
  <div class="painel">
    <h2>Em voo agora <span>worktrees com arquivo mexido nos últimos 40 min</span></h2>
    <ul>{voo_html}</ul>
  </div>
  <div class="painel">
    <h2>Fila de junção <span>{len(fila)} ramos esperando</span></h2>
    <ul>{fila_html}</ul>
    <h2 style="margin-top:18px">Últimos commits</h2>
    <ul>{ult_html}</ul>
  </div>
</div>

<section style="margin-top:22px">
  <div class="duas">
    <div class="painel">
      <h2>Ritmo <span>{commits_1h} commits na última hora · {commits_24h} em 24 h</span></h2>
      <div class="spark">{spark}</div>
      <div class="rec" style="margin-top:14px">
        <div><div class="eyebrow">testes novos 24 h</div><div class="v mono">{testes}</div></div>
        <div><div class="eyebrow">laudos de adversário</div><div class="v mono">{laudos}</div></div>
        <div><div class="eyebrow">consertos</div><div class="v mono">{consertos}</div></div>
        <div><div class="eyebrow">repasses</div><div class="v mono">{handoffs}</div></div>
      </div>
    </div>
    <div class="painel">
      <h2>Máquina <span>o limite é cota do modelo, não a máquina</span></h2>
      <div class="rec">
        <div class="{sem_mem}"><div class="eyebrow">memória livre</div><div class="v mono">{mem/1024:.1f}<small style="font-size:13px"> GB</small></div></div>
        <div class="{sem_con}"><div class="eyebrow">conexões</div><div class="v mono">{conn}<small style="font-size:13px">/100</small></div></div>
        <div class="ok"><div class="eyebrow">disco /</div><div class="v mono">{rec.get('disco_raiz_livre_gb',0):.0f}<small style="font-size:13px"> GB</small></div></div>
        <div class="ok"><div class="eyebrow">carga</div><div class="v mono">{(rec.get('carga') or [0])[0]:.1f}</div></div>
      </div>
      <p class="nota">Medido hoje: os agentes usam 1,1 % do tempo em processador. O que derrubou agentes duas vezes foi o limite de cota da interface do modelo, por isso a corrida reparte papéis entre três modelos.</p>
    </div>
  </div>
</section>

<section>
  <h2>Refutados por linha <span>{len(refut)} itens · conserto em {len(conserto_ramos)} ramos</span></h2>
  <div class="painel">{ref_html}</div>
</section>

<p class="nota">Retrato gerado de <span class="mono">estado.json</span>, do painel vivo e do git. Republicado a pedido; a página não consulta o servidor.</p>
</div>""")

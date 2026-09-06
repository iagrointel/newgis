#!/usr/bin/env python3
"""Integra laco/decomposicao/*.json ao estado.json: valida ids, dependências (com externas propostas), ciclos, placeholder,
nome de cliente; itens existentes ficam; filhos ganham 'pai'; L7-05-producao-final depende de tudo."""
import json, re, glob, sys, datetime, shutil
B='/home/dev/plataforma/laco'; E=f'{B}/estado.json'
e=json.load(open(E)); ex={x['id'] for x in e['backlog']}
def itens(d):
    if isinstance(d,list): return d
    for k in ('itens','items','backlog'):
        if k in d: return d[k]
    raise SystemExit('formato desconhecido')
novos={}; ext_prop={}; dec_prop=[]
for f in sorted(glob.glob(f'{B}/decomposicao/L*.json')):
    d=json.load(open(f))
    for it in itens(d):
        if it['id'] in ex: continue
        if it['id'] in novos: print('DUPLICADO entre linhas:',it['id'],f); continue
        it.setdefault('estado','pendente'); it.setdefault('tentativas',0); it.setdefault('turno',None); it.setdefault('bloqueio',None)
        it.setdefault('dependencias',[]); it.setdefault('papeis',[]); it['origem_arquivo']=f.split('/')[-1]
        novos[it['id']]=it
    if isinstance(d,dict):
        for x in d.get('dependencias_externas_propostas',[]) or []:
            xid=x['id'] if isinstance(x,dict) else str(x); ext_prop[xid]=x
        for x in d.get('decisoes_do_dono_propostas',[]) or []: dec_prop.append(x)
todos=ex|set(novos)
# dependências externas propostas que ninguém criou viram itens-esboço pendentes (portão = "definir com o item que a pediu")
criados=0
for xid,x in ext_prop.items():
    if xid in todos: continue
    d=x if isinstance(x,dict) else {}
    novos[xid]={"id":xid,"linha":{"L0":"L0 fundação","L1":"L1 imagens","L2":"L2 plataforma","L3":"L3 motor AMC","L4":"L4 rede de utilidades","L5":"L5 builder","L6":"L6 conectores","L7":"L7 operação"}.get(xid[:2],"L7 operação"),
        "prioridade":d.get('prioridade',3),"estado":"pendente","dependencias":d.get('dependencias',[]),
        "hipotese":d.get('hipotese') or d.get('descricao') or d.get('motivo') or f"dependência pedida por outra linha ({d.get('pedido_por','')})",
        "portao_de_pronto":d.get('portao_de_pronto') or "portão a fixar pelo arquiteto no turno em que o item que a pediu entrar (registrar aqui antes de construir)",
        "refutacao":d.get('refutacao') or "adversário confere que o item que pediu esta dependência funciona com ela",
        "papeis":d.get('papeis',["arquiteto","backend","adversario"]),"tamanho":d.get('tamanho','M'),"tentativas":0,"turno":None,"bloqueio":None,"pai":None,"origem":"externa_proposta"}
    criados+=1; todos.add(xid)
falt=[(i,d) for i,it in novos.items() for d in it['dependencias'] if d not in todos]
for i,d in falt: novos[i]['dependencias'].remove(d); novos[i].setdefault('deps_nao_resolvidas',[]).append(d)
# ciclo
g={**{x['id']:x['dependencias'] for x in e['backlog']},**{i:it['dependencias'] for i,it in novos.items()}}
vis={}
def dfs(n,st):
    if n in st: raise SystemExit(f'CICLO em {n}')
    if vis.get(n): return
    st.add(n); [dfs(m,st) for m in g.get(n,[])]; st.discard(n); vis[n]=True
for n in g: dfs(n,set())
rx=re.compile(r'TODO|FIXME|lorem|placeholder|em breve',re.I); cli=re.compile(r'\bfgr\b|\bcbre\b|novaterra|paracan|sigcorp|certaja|certel|\bedp\b',re.I)
ph=[i for i,it in novos.items() if rx.search(json.dumps(it,ensure_ascii=False))]
cl=[i for i,it in novos.items() if cli.search(json.dumps(it,ensure_ascii=False))]
shutil.copy(E,f'{E}.bak-{datetime.datetime.now():%Y%m%d%H%M}')
e['backlog']+=list(novos.values())
fin=[x for x in e['backlog'] if x['id']=='L7-05-producao-final'][0]
fin['dependencias']=sorted({x['id'] for x in e['backlog'] if x['id']!='L7-05-producao-final'})
for x in dec_prop:
    if isinstance(x,dict) and x.get('id') and x['id'] not in {d['id'] for d in e['decisoes_do_dono']}:
        e['decisoes_do_dono'].append({"id":x['id'],"data":"2026-09-05","pergunta":x.get('pergunta') or x.get('decisao') or json.dumps(x,ensure_ascii=False)[:300],"estado":"aberta"})
e['placar']['total']=len(e['backlog'])
e['notas'].append(f"2026-09-05 T2: decomposição integrada — {len(novos)} itens novos ({criados} esboços de dependência externa), total {len(e['backlog'])}; conceitos em laco/decomposicao/*_CONCEITO.md (L0 20 · L1 20 · L2 20 · L3L6 27 · L4 17 · L5 25 · L7 18 decisões). L7-05 depende de todos.")
json.dump(e,open(E,'w'),ensure_ascii=False,indent=1)
from collections import Counter
print('novos',len(novos),'| esboços externos',criados,'| total',len(e['backlog']))
print('por linha',dict(Counter(x['linha'] for x in e['backlog'])))
print('deps não resolvidas',len(falt),falt[:8]); print('placeholder',ph); print('nome de cliente',cl); print('decisões novas',[x.get('id') for x in dec_prop if isinstance(x,dict)])

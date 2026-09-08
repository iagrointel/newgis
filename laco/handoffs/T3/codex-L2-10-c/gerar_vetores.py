"""Adiciona casos por contrato, sem importar nenhum avaliador."""
import json
from pathlib import Path
p=Path('/home/dev/plataforma/enterprise/tests/expressoes/vetores.json')
v=json.loads(p.read_text())[:41]
def add(label, text, expected, **context):
 v.append(dict(descricao=label,entrada=text,contexto=context,saida=expected))
for name,s in [('vazio',''),('ascii','abc def'),('acentos','ação'),('unicode','a🌍ç'),('aspas',"d'água")]:
 for n in [0,1,2,20]:
  add(f'Left {name} {n}','Left($s,$n)',s[:n],s=s,n=n)
  add(f'Right {name} {n}','Right($s,$n)',s[-n:] if n else '',s=s,n=n)
 for start,n in [(0,0),(0,2),(1,2),(3,1),(20,3)]:
  add(f'Mid {name} {start}/{n}','Mid($s,$start,$n)',s[start:start+n],s=s,start=start,n=n)
 add(f'Mid até fim {name}','Mid($s,1)',s[1:],s=s)
 add(f'Contagem texto {name}','Contagem($s)',len(s),s=s)
for s in ['', '  abc  ','\tá\r\n', '\u00a0abc\u00a0', ' \v\f ', ' a b ']:
 add(f'Trim {s!r}','Trim($s)',s.strip(' \t\r\n\f\v'),s=s)
for needle,s,start,expected in [('a','banana',0,1),('a','banana',2,3),('x','banana',0,-1),('🌍','a🌍b',0,1),('b','a🌍b',0,2),('','abc',3,3),('','abc',4,-1),('','',0,0)]:
 add(f'Find {needle!r}/{s!r}/{start}','Find($needle,$s,$start)',expected,needle=needle,s=s,start=start)
for s,sep in [('a,b,c',','),('a,,b,',','),('','/'),('abc',''),('a🌍b',''),('',''),('a::b::c','::'),('abc','x')]:
 add(f'Split {s!r}/{sep!r}','Split($s,$sep)',s.split(sep) if sep else list(s),s=s,sep=sep)
for s,old,new in [('aaa','a','bb'),('abc','','x'),('🌍a🌍','🌍','ç'),('aaaa','aa','b'),('abc','x',''),('abc','b','')]:
 add(f'Replace {s!r}/{old!r}/{new!r}','Replace($s,$old,$new)',s.replace(old,new) if old else s,s=s,old=old,new=new)
for x,lo,hi in [(-2.5,-3,-2),(-1,-1,-1),(-0.5,-1,0),(0,0,0),(0.5,0,1),(2.5,2,3),(1234.125,1234,1235)]:
 add(f'Floor {x}','Floor($x)',lo,x=x);add(f'Ceil {x}','Ceil($x)',hi,x=x)
for x,y in [(0,0),(1,1),(4,2),(9,3),(0.25,0.5),(144,12)]: add(f'Sqrt {x}','Sqrt($x)',y,x=x)
for day in range(-8,9): add(f'Weekday dia {day}','Weekday($ms)',(day+4)%7,ms=day*86400000)
collections=[[],[1],[1,2,3],[None,True,'x'],[1,True,1,False,0],[{'a':1},{'a':1},{'a':2}],[[1],[2],[1]]]
for i,x in enumerate(collections):
 add(f'Contagem lista {i}','Contagem($x)',len(x),x=x)
 add(f'Primeiro {i}','Primeiro($x)',x[0] if x else None,x=x)
 add(f'Ultimo {i}','Ultimo($x)',x[-1] if x else None,x=x)
 add(f'Reverter {i}','Reverter($x)',list(reversed(x)),x=x)
 add(f'Obter índice zero {i}','Obter($x,0)',x[0] if x else None,x=x)
 add(f'Obter ausente {i}',"Obter($x,99,'ausente')",'ausente',x=x)
for i,x in enumerate([[],[1,2,3],[-2,2],[0.25,0.75],[None,1],[True,1]]):
 if i==5: continue
 add(f'Soma {i}','Soma($x)',None if None in x else sum(x),x=x)
 add(f'Media {i}','Media($x)',None if not x or None in x else sum(x)/len(x),x=x)
for text,value in [('Lista()',[]),('Lista(1,nulo,verdadeiro)',[1,None,True]),('Lista(Lista(1),Lista(2))',[[1],[2]]),('Unicos(Lista(1,verdadeiro,1,falso,0))',[1,True,False,0]),("Juntar(Lista('a',nulo,3),'/')",'a//3'),('Juntar(Lista(1,2,3))','123'),("Decode(2,1,'a',2,'b','c')",'b'),("Decode(9,1,'a',2,'b','c')",'c'),("Decode(nulo,nulo,'sim','não')",'sim'),("Decode(verdadeiro,1,'número','booleano')",'booleano'),('Decode(1,1,7,1/0)',7),('Decode(1,1,7,$negado,0,1/0)',7)]: add(text,text,value)
for expr,value,ctx in [("Obter($x,'a')",1,{'x':{'a':1}}),("Obter($x,'z',4)",4,{'x':{'a':1}}),("Obter($x,'a',4)",None,{'x':{'a':None}}),("Contagem($x)",2,{'x':{'a':1,'b':None}}),("Contem($x,verdadeiro)",False,{'x':[1]}),("Contem($x,nulo)",True,{'x':[None]}),("Contem($x,$y)",True,{'x':[{'a':1,'b':[2]}],'y':{'b':[2],'a':1}}),("Unicos($x)",[{'a':1,'b':2}],{'x':[{'a':1,'b':2},{'b':2,'a':1}]}),("Obter(Obter($x,'a'),0)",7,{'x':{'a':[7]}})]: add(expr,expr,value,**ctx)
for name in ['Trim','Floor','Ceil','Sqrt','Weekday','Contagem','Primeiro','Ultimo','Soma','Media','Reverter','Unicos','Juntar']:
 add(f'{name} propaga nulo',f'{name}(nulo)',None)
assert len(v)>=200
assert len({x['descricao'] for x in v})==len(v)
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
print(len(v),'vetores')

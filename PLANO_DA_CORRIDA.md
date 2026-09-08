# O TIRO ÚNICO: corrida autônoma até esgotar o backlog, com o máximo de subagentes que os recursos permitem

## Contexto

O pedido é entregar tudo numa corrida só, sem parar, com o máximo de agentes. A fase de construir
ferramentas ACABOU — hoje foram construídos e provados o gerador de prompt por item, a base de banco
por trilha, a fila de junção com bisseção, o vigia de recursos, o painel ao vivo e o supervisor. O
que falta é LIGAR tudo isso em modo contínuo e deixar rodando, com esta sessão como único
supervisor e a sessão executora (plataforma-d7) como segundo braço.

Estado no início da corrida (17:34 UTC):
- 22 entregues com prova · 16 parciais · **39 refutados a consertar** · 429 não iniciados
- 22 itens livres para construção; cada conserto de refutado libera os dependentes em cascata
- Recursos folgados: 9,7 GB de RAM, 27 conexões de 100, carga 6,7 — vigia diz SOBE
- 19 ramos com trabalho pronto esperando junção; 3 resgates de trabalho interrompido por cota
- Teto de subagentes por sessão: 40 (já elevado)

## A restrição que desenha tudo: a cota, não a máquina

Onze agentes morreram às 17:30 no limite da cota da sessão (segunda queda em massa do dia). A cota
de Opus volta às **20:20 UTC**. A sessão agora roda em Fable, cuja cota é SEPARADA. Isso permite a
jogada central do plano: **repartir a corrida entre três bolsos de cota** em vez de esgotar um só.

| papel | modelo | por quê |
|---|---|---|
| supervisão, junção, arbitragem (eu) | Fable (sessão) | poucas chamadas, alto critério |
| construtores de item M e P | **sonnet** | trabalho mecânico com portão literal; decisão do dono já autoriza |
| adversários, consertos de segurança, itens G | **opus** (a partir de 20:20) | onde o critério paga |
| retomadas de resgate | sonnet primeiro; opus se travar | o trabalho já está 80% feito em disco |

Regra de sobrevivência já provada: cota é falha correlacionada. O supervisor detecta a queda
(saída <3 min + registro casando o erro de limite), pausa TUDO, espera 5-10-20-40-60 min e volta
com um canário antes de reabrir. Nunca marca tentativa nem refuta item por queda de cota.

## Fase A — religar e escoar (agora, ~40 min, sonnet)

1. **Retomar os 3 resgates** (wt/partilha, wt/g4fix, wt/secdef) e os 8 interrompidos sem resgate
   (g1fix, g3fix, destrava, L0-13, L0-04-h, L0-04-e, L2-11-a, cred já entregue). Prompt de retomada
   padrão: `git log -1` + `git status` + handoff, continuar, nunca recomeçar. É o maior retorno por
   chamada da corrida inteira: trabalho quase pronto.
2. **Processar a fila de junção** com os ramos limpos (adv1-6, cred, g2fix, t602h, segur, t601b) em
   lotes de 6-8, bisseção ligada. Juntar À MÃO os 3 protegidos (stac, amc, valida — refutação
   aberta): conferir portão, rebasear, `make openapi` uma vez ao fim do conjunto.
3. **Atualizar o estado**: cada refutado cujo conserto entrou vira `parcial` ou `entregue` conforme
   o portão, com o sha. Isso reabre a cascata de dependentes — hoje 22 livres, estimados 60+ depois
   das junções (o documento de mapa sozinho destrava a frente do mapa web).

## Fase B — ligar o supervisor em modo contínuo (assim que a Fase A escoar)

`laco/supervisor.py` já existe e foi testado em seco (adoção por pid+starttime, detecção de cota,
regra do veneno, arrendamento de arquivo quente). Falta ligá-lo de verdade:

1. Rodar `--seco` uma vez, conferir a decisão, então ligar com `--teto 10` e subir por degraus
   (10 → 16 → 24 → 32) medindo entrega por agente em janelas de 90 min; parar de subir quando a
   taxa parar de crescer. Teto duro = min(RAM/250MB, conexões<70, 40 da sessão).
2. O supervisor lança com o prompt de `laco/prompt_item.py` (trilha própria por item, porta
   reservada, base própria via `trilha_ambiente.sh` — que agora dá GRANT nos schemas de dado e
   grava pool 1/2). Eleição: itens livres por prioridade, sem sobreposição de arquivo quente.
3. **Modelo por tamanho**: o lançamento passa `--model sonnet` para itens P/M e `--model opus` para
   G e todo papel de adversário/conserto (a partir de 20:20; antes disso, tudo em sonnet).
4. **Veneno**: 3 falhas reais = pendência declarada, sai da fila com os dependentes marcados. A
   trava de cancelamento em massa já existe (acima de 25 dependentes, só as raízes gravam).
5. Junção contínua: a cada 5 ramos prontos na fila, eu processo um lote. Merge é serial e meu.

## Fase C — o ciclo que se sustenta (contínuo, horas)

Cada onda repete: construir (sonnet) → adversário por linha (opus) → consertar (opus) → juntar →
o estado reabre dependentes → construir. A cobertura de adversário é POR LINHA (um agente ataca os
irmãos de uma vez, suposições transversais primeiro) — foi o que cobriu 52 itens em 6 agentes hoje.
Nenhum item vira `entregue` sem laudo; a taxa de refutação de hoje (7 de 8 nos verificados) é o
motivo de o portão ficar.

A sessão executora (plataforma-d7) mantém 4-6 agentes na faixa dela (coordenada por mensagem, sem
interseção; ela não junta ramo). O painel (`http://127.0.0.1:8159`) e o `checklist.py` mostram tudo;
o `vigia.sh` decide sobe/segura/desce e agora detecta porta duplicada.

## O que o tiro único NÃO resolve sozinho (fica visível, não trava)

- **36 itens dependem de decisão sua** (credencial do parceiro = 20; disco/licenças/janela de banco
  = o resto). Ficam em quarentena declarada no painel.
- **5 passos de produção do conserto de segurança G6** (tirar segredos do `.env`, rotacionar token,
  etiqueta assinada) — preparados, com comando exato em `docs/AMBIENTES.md` §5; eu executo os
  seguros e deixo o que mexe no banco compartilhado para janela combinada.
- A conta honesta continua a de sempre: ~555 horas-agente de trabalho restante. Com 30-40 agentes
  efetivos entre as duas sessões e as três cotas, o teto físico é o caminho crítico (~13 rodadas).
  **O tiro único leva a corrida até onde a cota do dia deixar, sem parar por decisão minha** — e
  quando uma cota cair, o supervisor espera e retoma sozinho, com resgate e retomada já provados.

## Verificação

- Fase A: placar sobe de 22 entregues sem nenhum item marcado sem prova; `git log` de master mostra
  os lotes; nenhum ramo protegido juntado sem conferência de portão.
- Fase B: supervisor vivo sobrevivendo a `kill` (readota), registro de queda de cota com recuo
  automático visível no log; entrega por agente medida em cada degrau de teto.
- Fase C: o painel mostra ondas sucessivas sem intervenção; cobertura de adversário = 100% dos
  itens novos; relatório final com entregue/refutado/consertado/pendência-do-dono.

# 20260908T1105 — Série temporal da rede: uma rede por safra, e a linhagem entre elas

Item `L4-15-serie-temporal-da-rede`. Estado: aceito.

## Contexto

A rede de utilidades chega em safras: a BDGD da ANEEL publica uma base por distribuidora por ano. O
planejamento pergunta coisas que uma safra sozinha não responde — que transformador está carregando
mais a cada ano, onde a rede cresceu, quantas unidades consumidoras entraram. Para responder, é preciso
antes decidir uma coisa difícil: **quando dois COD_ID de anos diferentes são o mesmo ativo**.

O modelo de elementos (ADR 20260906T2126) guarda uma rede com a restrição `UNIQUE (rede_id, papel,
codigo_externo)`. O mesmo COD_ID não pode aparecer duas vezes na mesma rede.

## Decisão

### 1. Cada safra é uma `plat.rede`; a série é o que as amarra

Em vez de acrescentar uma coluna de ano em `rede_no`/`rede_aresta` (o que quebraria a restrição de
unicidade, os índices e todo o traçado da linha L4), uma safra é uma rede inteira, e `plat.rede_serie` +
`plat.rede_serie_safra` amarram várias redes do mesmo inquilino em ordem de ano.

Consequências aceitas: o dado da rede ocupa espaço por safra (não há compartilhamento entre anos), e uma
rede participa de uma série só. Em troca, tudo o que a linha L4 já sabe fazer sobre uma rede — traçado,
topologia, feições, controladores — continua valendo para CADA safra sem nenhuma mudança.

### 2. A identidade entre safras é o COD_ID da fonte, não o `codigo_externo`

Achado deste item, medido no recorte real da cooperativa de teste: para `UCBT_tab`/`UCMT_tab` o
importador (item L4-01-c) grava em `codigo_externo` o OBJECTID da linha do arquivo, sob a premissa de que
essas tabelas não têm `COD_ID`. Elas têm: o esquema V11 traz um `COD_ID` de 64 hexadecimais, e é ele que a
casa mediu como estável entre safras. Um número de linha de arquivo não é identidade — usá-lo faria
TODA unidade consumidora aparecer como extinta e nascida a cada ano.

A série lê a identidade de `atributos->>'COD_ID'`, com `codigo_externo` como reserva
(`serie.SQL_IDENTIDADE`). Para o transformador os dois coincidem. Isso resolve o problema sem mexer no
importador, que é de outro item e está na fila de junção; a correção lá continua desejável e está
registrada no repasse.

### 3. Quatro classes, e a régua medida da casa

`plat.rede_linhagem` classifica cada COD_ID por par de safras consecutivas em persistente, recodificado,
novo ou extinto. A régua do `recodificado` é a do relatório de linhagem da casa (série pública de seis
anos de uma distribuidora do Sudeste): Jaccard das unidades consumidoras identificadas ≥ 0,6; ou
coordenada a ≤ 10 m com Jaccard ≥ 0,3; ou coordenada a ≤ 10 m quando os dois lados têm menos de cinco
unidades consumidoras. Cada COD_ID é usado uma vez só de cada lado.

O que ficou de FORA de propósito: o casamento de unidade consumidora por perfil de consumo. A casa o
mediu e ele não sustenta número agregado (precisão do melhor par cai a 0,30 em bloco grande; 1.061 elos
em cinco pares de anos). Unidade consumidora tem, aqui, só persistente, novo e extinto — o que sai do
arquivo é, na maioria esmagadora, cliente desligado. Também ficaram de fora as classes de
*reconfiguração* do relatório (desmembrado, fundido, recebeu de quem sumiu): elas descrevem a carteira,
não a identidade, e entram quando houver item que as peça.

### 4. Carregamento é proxy declarado, e a placa pode não valer

O carregamento por transformador usa a fórmula do ativo `bdgd_temporal` da casa, com fator de carga 0,45
e fator de potência 0,92 fixos sobre a energia declarada na fonte. É triagem, não medição, e os dois
fatores viajam com o resultado em `plat.rede_serie.metodo` e na resposta da rota de tendência.

A regra da placa: quando mais de 10 % dos transformadores persistentes de um par de safras mudam de
potência nominal, a safra mais antiga do par é marcada `pot_nom_confiavel = false`, com o motivo escrito.
Placa de transformador não muda em massa em um ano. A medida que originou o limiar: 23,4 % num par
contra ~1 % nos pares seguintes, na série pública de seis anos. A ressalva viaja na tabela de tendência e
na exportação em CSV, coluna a coluna — o número nunca sai sozinho.

### 5. Prefixo de rota próprio

As rotas ficam em `/api/rede-serie`, não em `/api/rede/series`: `/api/rede/{rede_id}` já captura qualquer
segmento depois de `/api/rede/`, e uma coleção nova ali dentro passaria a depender da ordem de registro
dos roteadores para não ser engolida.

## Alternativas descartadas

- **Coluna `ano` nas tabelas de elemento.** Quebra a unicidade por COD_ID, obriga todo traçado e toda
  topologia da linha L4 a filtrar por ano, e o primeiro esquecimento mistura safras em silêncio.
- **Casar por geometria sozinha.** Dois transformadores no mesmo poste em anos diferentes não são o
  mesmo ativo; o teste `test_trafo_grande_nao_casa_so_pela_coordenada` trava essa porta.
- **Inferir recodificação sempre que algo some e algo nasce.** Inventaria linhagem. Sem evidência, o que
  some é extinto e o que nasce é novo.

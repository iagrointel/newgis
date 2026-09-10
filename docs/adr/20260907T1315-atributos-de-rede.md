# ADR — Atributos de rede (item L4-01-d-atributos-de-rede)

Data: 2026-09-07. Migração: `db/migracoes/20260907T1239_rede_atributos_de_rede.sql`. Código:
`app/rede_utilidades/atributos.py`, `app/rede_utilidades/rotas_atributos.py`.

## Contexto

`plat.rede_atributo` (item L4-01-a) já é o catálogo de onde cada atributo importado do pacote vem — nome,
tipo, unidade, coluna de origem por tipo de ativo. "Atributo de rede", no vocabulário da Esri (*network
attribute*), é mais estreito: a coluna da TOPOLOGIA DERIVADA que o traçado lê sem ir à camada de origem nem
ao `atributos` jsonb cru — fase (bitmask, propagável), tensão, capacidade, estado do dispositivo (com
traversabilidade), comprimento geodésico, `is_connected` e `subrede`.

## Decisões

1. **Sem tabela nova para o catálogo.** As flags `propagavel`/`apoia_traversabilidade` são duas colunas a
   mais em `plat.rede_atributo` (já existente), não uma tabela paralela — o catálogo continua sendo UM
   lugar só. As linhas SINTÉTICAS dos 3 atributos calculados (sem coluna de origem na BDGD) entram no MESMO
   catálogo, com `origem = {"calculado": true}` em vez de câmera/coluna, para nunca inventar proveniência.

2. **Flags marcadas pelo SUFIXO real do código, não por um nome genérico "fase".** O catálogo importado do
   pacote `eletrica-br` nomeia cada atributo com o prefixo da tabela BDGD de origem (`ssdmt_fas_con`,
   `unsemt_p_n_ope`) — não existe uma linha `fase` solta. `declarar_flags_padrao` marca `propagavel = true`
   em todo código terminado em `_fas_con` e `apoia_traversabilidade = true` em todo terminado em `_p_n_ope`,
   chamada uma vez ao fim de `deposito.importar`. Único propagável/único traversável hoje, como o enunciado
   declara — a função generaliza para o dia em que houver um segundo.

3. **Aresta interna do dispositivo é tabela nova (`rede_topo_dispositivo_aresta`), fora de
   `rede_topo_aresta`.** Uma aresta de TRECHO representa um trecho físico com comprimento; uma aresta de
   DISPOSITIVO representa a condução por DENTRO de um dispositivo de 2+ terminais (chave, religador),
   comprimento zero, e o único atributo que importa é `traversavel`. Misturar as duas na mesma tabela exigia
   nulos demais (comprimento, geometria) para o caso do dispositivo. Transformador NUNCA ganha esta aresta —
   ele separa duas subredes (alta×baixa), nunca conduz por dentro; decisão da função Python
   (`sincronizar_topologia_lote`), não da migração, porque depende de categoria (`rede_tipo_categoria`).

4. **Sincronização em DOIS caminhos, nunca um só.** Um TRIGGER (`tg_rede_atributo_sincronizar_linha/_ponto`)
   cobre a edição de UMA feição já refletida na topologia — copia o valor, não reconstrói estrutura. Uma
   função Python (`sincronizar_topologia_lote`) cobre o LOTE — reconstrói `rede_topo_dispositivo_aresta` do
   zero para a rede inteira, porque essa reconstrução depende da CONTAGEM de terminais por dispositivo, que
   não cabe num trigger de linha única. O enunciado do item pede os dois; nenhum substitui o outro.

5. **Propagação por caminho, nunca por grafo inteiro.** `propagar_fase` faz um BFS a partir de cada raiz e
   guarda a fase corrente NO CAMINHO (dicionário por nó visitado nesta passada), não uma variável global —
   é o que garante a refutação do enunciado ("mudar a montante muda a jusante, não o irmão"): dois ramos que
   nascem do mesmo tronco mas nunca se re-encontram carregam fases independentes se um deles atravessar uma
   substituição.

6. **Substituição indexada por PONTO, não por aresta de dispositivo.** `rede_atributo_substituicao` guarda
   `tipo_id`; a consulta que a aplica junta pelo TIPO do ponto que originou a aresta de dispositivo
   (`rede_feicao_ponto.tipo_id`), nunca por um id de aresta de dispositivo direto — a regra é sobre o TIPO de
   ativo (toda chave-fusível se comporta assim), não sobre uma instância.

## Fronteira achada (registrada, não escondida)

`topologia.habilitar` (L4-01-b) funde diretamente as duas pontas de trecho que se tocam sempre que são do
MESMO grupo — pensado para um trecho partido em vários pedaços sem dispositivo no meio. Quando um
dispositivo de 2 terminais do MESMO tier (o caso normal — chave em série na média tensão, tronco e jusante
ambos `trecho_de_media_tensao`) senta exatamente sobre esse encontro, a fusão trecho-trecho funde as duas
pontas ENTRE SI antes de o dispositivo entrar no jogo, e os dois terminais da chave caem no mesmo grupo de
união — vira um nó só, não dois. `sincronizar_topologia_lote` detecta isto honestamente (conta em
`ignorados_sem_dois_nos`, nunca cria a aresta interna com um nó só). Isto NÃO é bug deste item: é uma
ambiguidade de construção de L4-01-b que este item herda. Consequência medida em escala real: o extrato BDGD
da cooperativa de teste não tem NENHUMA chave/subestação do pacote `eletrica-br` (só trechos, transformador,
poste) — logo `sincronizar_topologia_lote` mede 0 aresta de dispositivo nessa base (5.481 transformadores
todos ignorados por categoria, corretamente), e a cláusula de concordância de fase ≥95% usa a raiz ASSUMIDA
por alimentador (extremidade de grau 1), nunca uma subestação real. Os testes de mecânica pura
(`tests/api/test_rede_atributos.py`) contornam a fronteira construindo a topologia manualmente (2 nós de
terminal reais para a chave) — provam a lógica de `atributos.py` isolada da ambiguidade, cláusula por
cláusula, com refutação incluída. Recomendação para um item futuro de L4: reservar terminal próprio para
dispositivo de 2+ terminais mesmo quando os vizinhos são do mesmo grupo/tier (hoje só funciona quando os
tiers diferem).

## Alternativas descartadas

- **Corrigir `topologia._resolver_uniao` para nunca fundir trecho-trecho na presença de um dispositivo
  coincidente**: mudaria o resultado medido e assinado do item L4-01-b (73.512 arestas, componentes por
  CTMT) sem re-medir aquele item inteiro — fora do escopo deste turno, registrado como recomendação acima.
- **Fase como atributo genérico único no catálogo (`codigo = 'fase'`)**: o catálogo real do pacote não tem
  essa linha (cada camada BDGD nomeia o próprio campo); criar uma sintética a mais confundiria com o que
  vem do arquivo. A via escolhida (marcar por sufixo) respeita o vocabulário real.

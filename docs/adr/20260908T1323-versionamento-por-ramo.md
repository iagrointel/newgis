# ADR 20260908T1323 — versionamento por ramo: onde moram as linhas do ramo

Item `L2-13-a-versoes-ramo-reconciliar`. Estado: aceito.

## Contexto

O item pede o equivalente ao *branch versioning* do ArcGIS Enterprise: uma camada marcada como
versionada aceita ramos de trabalho paralelos; ler dentro de um ramo mostra as edições dele mais o
padrão como estava no momento em que o ramo nasceu; reconciliar compara os dois lados desde esse
momento e lista os conflitos; publicar (post) leva as edições do ramo para o padrão.

A hipótese escrita no `estado.json` dizia: "toda linha da camada versionada ganha colunas `versao_id`,
`momento_inicio`, `momento_fim`". Este documento registra por que a implementação NÃO fez isso, e o que
fez no lugar.

## Decisão

1. **A versão padrão continua sendo a tabela da camada, sem coluna nova.** `d_<slug>.c_<uuid16>` é
   exatamente o que era antes: uma linha por feição, o estado de agora.
2. **As linhas de ramo vivem numa tabela companheira** `d_<slug>.c_<uuid16>__ramo`, criada por
   `plat.camada_versionar` com `LIKE` da tabela da camada mais `versao_id`, `momento_inicio`,
   `momento_fim`, `apagada` e uma chave própria `ramo_pk`.
3. **O momento histórico do padrão é reconstruído de `plat.feicao_historico`** (item L2-03-d), que já
   grava, por gatilho, atributos e geometria de antes e de depois de toda escrita — inclusive a que não
   passa pela API.
4. **Ler num ramo é um `UNION ALL` de três pernas**, montado em `app/versionamento/leitura.py`: as
   linhas vigentes do ramo; o padrão de agora, sem as feições alteradas depois do momento base e sem as
   que o ramo tocou; e as feições alteradas depois do momento base, remontadas do "antes" do histórico.
5. **A relação entra no motor de consulta como origem**, no lugar da tabela física. `gdbVersion` e
   `historicMoment` do protocolo Esri são, os dois, a mesma troca de origem.

## Por que não pôr as colunas na tabela da camada

Porque o não-vazamento passaria a depender de memória. Hoje leem a tabela da camada, sem filtro de
versão: o motor de consulta do FeatureServer, o OGC API Features, o WFS, os tiles do Martin, a
exportação, a união e a divisão de feição, os anexos, e a bancada de teste. Com `versao_id` na própria
tabela, cada um desses caminhos passaria a ver as linhas de ramo até ser corrigido, um a um, e a
cláusula do portão "leitura no ramo antes do post não vaza para o padrão, e vice-versa" viraria uma
promessa sobre uma lista de lugares que ninguém consegue jurar estar completa.

Com a tabela companheira, o isolamento é **estrutural**: quem não sabe que ramo existe lê a tabela da
camada e vê exatamente o padrão. Quem sabe, monta a relação. O preço é o `UNION ALL` na leitura
versionada — que só corre quando o pedido pede ramo ou momento — e uma tabela a mais por camada
versionada. A troca é boa: o custo é de desempenho num caminho opcional, e o que se compra é
correção num caminho obrigatório.

Custo secundário, escrito para não virar surpresa: coluna acrescentada à camada DEPOIS de ela ser
versionada não aparece sozinha na tabela de ramo. `plat.camada_versionar` é idempotente e pode ser
chamada de novo, mas hoje ela não sincroniza colunas — quem alterar o esquema de uma camada versionada
tem de reversionar. Está registrado como limitação, não como pendência escondida.

## Invariante do ramo

Para cada par (ramo, feição) existe **no máximo uma linha com `momento_fim` nulo** — a linha vigente.
Toda alteração fecha a vigente e insere outra; apagar no ramo insere uma linha vigente com
`apagada = true`, que é ao mesmo tempo a marca de "esta feição saiu no ramo" e o registro de que o ramo
TOCOU a feição. Tocar é o que tira a feição da perna do padrão na leitura: sem isso, uma feição apagada
no ramo reapareceria pelo padrão.

## Conflito, decisão e reabertura

Conflito é a mesma feição alterada dos dois lados desde o momento base, comparada **atributo a atributo
e geometria** (é a detecção "por objeto" da Esri; a "por atributo" não é oferecida). A decisão —
`ramo`, `padrao` ou `manual` — é gravada em `plat.versao_conflito` junto com `momento_padrao`, o
instante da última alteração do padrão naquela feição quando a decisão foi tomada. Se o padrão andar de
novo depois disso, a reconciliação seguinte vê um `momento_padrao` diferente e **reabre** o conflito. É
essa comparação, e não uma marca de "resolvido", que impede publicar sobre um padrão que mudou.

Publicar sempre reconcilia antes e recusa com 409 se sobrar conflito sem decisão. A recusa desfaz a
transação inteira, inclusive as linhas de conflito que a detecção acabou de gravar — por isso a lista
vai dentro do erro, e quem quer a lista persistida chama `reconciliar`, que é o passo obrigatório do
fluxo da Esri de qualquer modo.

## O que fica de fora, com o motivo

- **Ramo de ramo.** A Esri permite; reconciliar em cadeia multiplica os estados a comparar e o item não
  pede. A coluna `pai` existe e hoje é sempre nula (o padrão).
- **Detecção de conflito por atributo** (`conflictDetection=byAttribute`). O parâmetro é aceito e
  ignorado; a detecção é por objeto.
- **`historicMoment` dentro de um ramo.** Recusado com 422: o momento histórico é do padrão, e dentro
  de um ramo a leitura é sempre a do ramo agora.
- **Sessão de leitura/edição do protocolo** (`startReading`, `startEditing` e pares). As rotas existem,
  conferem existência do ramo e permissão, e devolvem o momento do servidor; não guardam sessão, porque
  a leitura consistente e a escrita atômica vêm da transação do Postgres.
- **ArcGIS Pro de verdade.** Não há licença nem máquina Windows nesta casa (decisão D20 do dono). O que
  se provou é o protocolo, com a sequência de chamadas do cliente Python `arcgis` reproduzida em
  `tests/esri/cliente_arcgis_versoes.py`; o pacote `arcgis` em si não está instalado (dependência
  grande, disco a 96 %) e o script diz isso em vez de fingir.

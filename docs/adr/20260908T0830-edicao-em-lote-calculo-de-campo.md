# ADR 20260908T0830 — edição em lote e cálculo de campo (item L2-03-f)

## Contexto
O L2-03-a fixou UMA porta de escrita de feição (`POST /api/camadas/{id}/edicoes`, feição a feição, com validação,
versão otimista e gatilhos de versão/histórico na tabela). Faltava o equivalente ao "Calculate" do FeatureServer:
uma operação sobre N feições escolhidas por seleção ou por expressão, com o mesmo custo de validação e o mesmo
rastro, sem o cliente ter de baixar e reenviar cada feição. A linguagem de expressão (L2-10-c) já existe nos dois
lados (Python e JavaScript), mas ainda sem tipo geometria e sem tradução para SQL.

## Decisões
1. **Uma rota, seis operações, dois tempos.** `POST /api/camadas/{id}/lote` com `operacao` ∈ calcular, atribuir,
   apagar, corrigir_geometria, copiar, mover; `previa=true` devolve as 10 primeiras linhas antes/depois sem gravar;
   até `LOTE_SINCRONO_MAX` (5.000) feições roda no pedido, acima vira o job `camadas.lote` (202 + `job_id`). O
   corpo e a função de execução são os mesmos nos dois tempos — a diferença é só quem segura a transação.
2. **Tradução para SQL quando o subconjunto permite, linha a linha quando não.** `app/expressao/compilador_sql.py`
   traduz literais, `$campo`, aritmética, comparação, lógica, `Se`/`SeNulo`/`EhNulo`, texto simples, arredondamento
   e mínimo/máximo para SQL parametrizado (cada fragmento carrega os seus `%s`; um fragmento repetido repete os
   parâmetros). Fora disso (`Texto` de número, datas, coleções, formatação pt-BR) o lote lê as linhas em blocos e
   avalia com o MESMO avaliador do L2-10-c, com o orçamento por linha de 500 ms. A resposta diz qual caminho foi
   usado (`traducao`, `traducao_motivo`) e o teste grava o mesmo campo pelos dois caminhos e exige igualdade.
3. **Geometria entra como campo derivado, não como tipo da linguagem.** `$area_m2`, `$comprimento_m`,
   `$perimetro_m` (geography, geodésicos) e `$x`/`$y` (centroide) são calculados pelo PostGIS e oferecidos à
   expressão nos dois caminhos. "Área geográfica / 10.000" é `$area_m2 / 10000`. Quando o L2-10-c ganhar tipo
   geometria, os derivados continuam válidos como atalho.
4. **Uma transação por lote, sub-lotes de 1.000 só para progresso.** Erro nomeado no modo `transacao` (domínio,
   tipo, divisão por zero, campo não permitido) ou cancelamento do job desfaz TUDO: a camada volta ao estado
   anterior e o histórico do que foi desfeito some junto (é a mesma transação). O modo `parcial` (só calcular e
   atribuir) avalia linha a linha e devolve as falhas por feição.
5. **Validação e rastro do L2-03-a, sem cópia.** `validar_atributos` (linha a linha) e a mesma regra escrita em SQL
   (`_conferir_dominio_sql`, depois do UPDATE do sub-lote) para o caminho SQL; `somente_proprias` restringe a
   seleção às feições do ator (com aviso do que ficou de fora); os gatilhos da tabela geram versão e uma linha de
   `plat.feicao_historico` por feição tocada, também no job; `tiles_versao` sobe e um evento `camadas/lote` é
   gravado por lote (no job, com o `job_id`).
6. **Sem acesso a outra camada dentro da expressão.** A linguagem só enxerga a lista branca de campos da camada
   (`campo_nao_permitido` para o resto) — isolamento entre inquilinos é o da RLS de `plat.item`, 404 nunca 403.

## Consequências
- `reprojetar` (hipótese do item) NÃO foi construído: mudar o SRID da coluna é `ALTER TABLE ... USING ST_Transform`
  (não dispara gatilho de histórico) e afeta tiles/extensão/metadado da camada inteira — é operação de camada, não
  de lote; fica para o dono de L2-13/L0-04.
- Seleção por filtro do L2-06-e (`compilar_filtro`) não foi ligada: a seleção é por ids, por expressão `onde` da
  própria linguagem ou todas. Quando a fila juntar cx201i, `onde` pode aceitar o mesmo JSON de filtro.
- O modelo `Minimo/Maximo` com nulo devolve nulo no SQL (o avaliador recusa nulo): a diferença só aparece com
  nulo, e a linha nula é reprovada pela mesma validação nos dois caminhos.

# ADR 0016 — Motor multicritério: forma do modelo, proveniência da execução e unidade de análise

Data: setembro de 2026. Itens L3-01-a-modelo-dado e L3-01-b-unidades. Decisões de conceito já tomadas em
`laco/decomposicao/L3L6_CONCEITO.md`, parte A (A1, A3, A5, A6, A7, A10, A14) — esta ADR registra só o que a
implementação fixou e o que ela obriga em quem vier depois.

## Contexto

O motor precisa de três coisas ao mesmo tempo: (a) um modelo que o usuário edite e que o produto saiba explicar
fator a fator; (b) um resultado que alguém possa auditar meses depois, sabendo exatamente o que rodou; (c) uma
unidade de análise cuja área não dependa de em que parte do país ela está.

## Decisão

**1. O modelo é um documento JSON, e a versão dele é o sha256 do JSON canônico.** Canônico =
`json.dumps(definicao, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` em UTF-8. O documento é validado
contra `docs/esquemas/amc_modelo.v1.json` (JSON Schema Draft 2020-12) mais três regras que o esquema não expressa:
id de fator único, soma dos pesos maior que zero e, no combinador `percentual`, pesos que fecham 100. Toda violação
sai junta, com a cláusula, o caminho e a frase em português (422 `modelo_invalido`).

`plat.amc_modelo` é a cabeça editável; `plat.amc_modelo_versao` guarda toda versão que já existiu e é imutável para
a aplicação (gatilho no banco: só um superusuário passa). Editar cria versão e move a cabeça. Uma execução aponta
para o par (modelo, versão), com chave estrangeira composta — por isso editar um modelo já executado não muda a
execução nem o resultado.

**2. A execução congela a proveniência.** `plat.amc_execucao` grava, no instante em que nasce: versão do modelo,
pesos usados, versão do motor (`amc/<versão> + versão da aplicação + sha do commit`), semente e a ficha de cada
camada de entrada — identificador, título, sha256 e contagem de linhas quando o registro tem. O que não existe
entra como `"nao_registrado"`, nunca como zero. Contagem de tabela hospedada usa `COUNT(*)` com tempo limite de
25 s dentro de um SAVEPOINT; estourado o tempo, o campo diz `contagem_nao_concluida_em_25s` e a execução continua.
Camada citada que não existe (ou está bloqueada no acervo) recusa a execução inteira com 422: execução sem entrada
resolvida não é auditável e não deve nascer.

**3. Fator bruto e resultado são LINHAS, nunca coluna por fator.** `plat.amc_fator_bruto(execucao, unidade, fator)`
e `plat.amc_resultado(execucao, unidade)`. A favorabilidade é `double precision` de 0 a 100, e `NULL` significa sem
dado. Unidade vetada carrega `vetado = true` e um motivo obrigatório, e nunca um número na escala — a restrição
`CHECK` do banco garante isso.

**4. A unidade de análise vive num CRS métrico declarado.** Grade hexagonal (`ST_HexagonGrid`) ou quadrada
(`ST_SquareGrid`) gerada em UTM SIRGAS 2000 da zona do centróide da área de estudo, recortada à área, guardada em
4326 com a área geodésica (`ST_Area(geography)`, GRS80) de cada célula. A ficha do conjunto declara sempre o CRS, a
zona, o meridiano central e a distorção de área mínima e máxima medida ponto a ponto com
`pyproj.Proj.get_factors(...).areal_scale`. Área que cruza mais de uma zona UTM é aceita — com as zonas listadas,
`cruza_zonas_utm = true` e um aviso escrito. Nada disso fica implícito.

Alternativa a `feições do usuário`: o id vem de `feature.id` ou de uma propriedade escolhida, e é preservado como
`unidade_id`. Id duplicado ou ausente recusa o conjunto inteiro, com a lista das posições.

**5. RLS por inquilino nas sete tabelas** (`amc_modelo`, `amc_modelo_versao`, `amc_conjunto_unidade`, `amc_unidade`,
`amc_execucao`, `amc_fator_bruto`, `amc_resultado`), mesmo padrão de `002_identidade.sql`.

## O que foi descartado

- **H3 como grade.** `h3-pg` não está instalado nesta máquina e o brief proíbe instalar. H3 fica como índice
  opcional por biblioteca Python, fora do caminho crítico.
- **Uma tabela relacional de fatores** (como no motor logístico da casa). O que doeu naquele motor foi ter a mesma
  regra em dois lugares (banco e front). Um documento e um hash resolvem isso.
- **Guardar tudo na cabeça do modelo com um campo `imutavel`.** Sem a tabela de versões, uma execução antiga
  perderia o sentido assim que alguém editasse o modelo.
- **Contar linha de camada externa por estimativa (`reltuples`).** O registro do acervo já mostrou duas tabelas
  fantasma com estimativa positiva e `COUNT(*)` zero; o número que vai para a proveniência é contado ou é declarado
  como não contado.

## Consequências

- O adversário recomputa o hash com `scripts/amc_hash_independente.py`, que não importa o módulo da aplicação: se
  a regra do hash mudar de um lado só, o teste falha.
- A extração de fator (L3-01-c), a biblioteca de transformações (L3-01-d) e a combinação (L3-01-e) escrevem em
  tabelas que já existem; nenhuma delas precisa de migração nova para o caminho básico.
- L2-01 pode recolorir a camada no cliente a partir de um vetor de `(unidade_id, favorabilidade)`, porque o id da
  unidade é estável e a geometria já está em 4326.
- L3-07 (agregação) tem de reprojetar para `srid_trabalho` antes de medir área ou distância — nunca medir em 4326.
- Teto declarado em `app/limites.py`: 1.000.000 de unidades por conjunto. Medido nesta máquina: 250 mil células de
  100 m levam 8,6 s e ocupam ~186 MB de tabela e índices; 1 milhão não foi gerado porque `/mnt/pgdata` está a 99 %
  (13 GB livres) — a extrapolação está gravada como extrapolação em `tests/medidas/L3-01-b.json`.

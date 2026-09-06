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
`json.dumps(normalizar_numeros(definicao), sort_keys=True, separators=(",", ":"), ensure_ascii=False)` em UTF-8. O
documento é validado contra `docs/esquemas/amc_modelo.v1.json` (JSON Schema Draft 2020-12) mais as regras que o
esquema não expressa: id de fator único, soma dos pesos maior que zero, no combinador `percentual` pesos que fecham
100, e a coerência INTERNA de cada transformação (ver decisão 1.b). Toda violação sai junta, com a cláusula, o
caminho e a frase em português (422 `modelo_invalido`).

**1.a. Normalização numérica do JSON canônico** (acrescentada em 06/09/2026, depois da refutação do item). Em JSON
`3` e `3.0` são o MESMO número; sem normalizar, reenviar o mesmo modelo com o peso escrito como inteiro criava uma
versão nova que não mudara nada. A regra é uma só, e é esta: **todo número de ponto flutuante com parte fracionária
zero e magnitude menor que 2^53 vira inteiro; nada mais muda.** `0,5` continua `0,5`, `1e30` continua `1e30`,
booleano nunca é número (em Python `True == 1`, e a regra testa `isinstance(v, bool)` primeiro), e `-0.0` vira `0`.
A implementação é iterativa, não recursiva, porque `extrator.parametros` é objeto livre no esquema e um documento
com milhares de níveis de aninhamento é aceito.

A normalização é aplicada **também ao documento que vai ao banco**, não só ao texto que entra no sha256. É essa
escolha que mantém a auditoria por fora possível: quem ler `plat.amc_modelo_versao.definicao` e recomputar o hash
com a regra simples (`json.dumps` com `sort_keys`/`separators`, sem normalizar nada) chega ao mesmo valor gravado.
Custo declarado: o hash de um documento com float integral MUDA em relação à regra anterior. Medido em 06/09/2026
antes de decidir: os 53 modelos existentes em `plat` são todos resíduo de teste (`zt-*` e "modelo de teste
interno"), então nenhum histórico real foi invalidado.

**1.b. Coerência interna da transformação.** O `allOf` do esquema descreve os campos obrigatórios de 4 dos 16 tipos
de transformação, então faixa invertida (`minimo` ≥ `maximo`), faixa degenerada, número de notas incompatível com o
de quebras (`len(notas)` tem de ser `len(quebras) + 1`), quebras e bandas fora de ordem crescente e função contínua
sem nenhum parâmetro entravam no modelo, ganhavam hash e só quebrariam — ou dariam nota errada em silêncio — quando
o motor do item L3-01-d fosse executá-las. Passaram a ser violação com cláusula própria. A regra da função contínua
é deliberadamente fraca (**pelo menos um parâmetro numérico além de `tipo`, `abaixo`, `acima` e `metodo`**) porque a
lista de parâmetros de cada curva do Rescale by Function só fica fechada no L3-01-d: apertar mais agora seria
inventar contrato.

**1.c. Corpo JSON ambíguo é recusado.** Chave repetida no mesmo objeto (`{"nome": "A", "nome": "B"}`) é legal para
`json.loads`, que fica em silêncio com a última ocorrência. Num documento cuja VERSÃO é o hash dele mesmo, aceitar
texto ambíguo sem avisar é buraco de auditoria: as três rotas de modelo releem o corpo cru com `object_pairs_hook` e
devolvem 422 `json_ambiguo` com a chave. Corpo malformado continua sendo assunto do parser do FastAPI.

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
- Teto declarado em `app/limites.py`: 1.000.000 de unidades por conjunto. Ele vale para a CONTAGEM REAL, não para
  a estimativa área/área-da-célula: a célula de borda entra recortada e o conjunto pode passar do teto (medido:
  1.000.175 unidades com o teto em 1.000.000). Quando passa, `gerar_grade` apaga as unidades, marca o conjunto como
  `falhou` com o motivo, e a tarefa `amc.gerar_unidades` levanta `FalhaDefinitiva` — o operador não pode ver
  "concluído" sobre um conjunto recusado. A guarda da estimativa continua na entrada, para recusar barato o que já
  se sabe grande demais.
- Medido nesta máquina: 250 mil células de 100 m levam 8,6 s e ocupam ~186 MB de tabela e índices. A escala de
  1 milhão de células, que no fecho do item não tinha sido gerada, foi gerada depois (adversário do item, com 43 GB
  livres em `/mnt/pgdata`): **1.000.175 células em 30,97 s**, desvio de contagem +0,201 %; a re-medição depois do
  conserto do teto deu 989.334 células em 33,55 s. A projeção linear de 34,3 s que estava no lugar era conservadora
  — errou cerca de 10 % para mais. A única linha ainda marcada `EXTRAPOLADO` em `tests/medidas/L3-01-b.json` é a de
  bytes para 1 milhão, que ninguém mediu.
- A reescrita de schema de `app/schema_ambiente.py` é infraestrutura de que este item depende, e o item abriu a
  primeira exceção a ela ao usar `psycopg2.extras.execute_values` (que entrega `bytes` ao cursor). A exceção foi
  fechada como classe, não como remendo: ver `app/schema_ambiente.MixinReescritaSchema`, que declara em
  `METODOS_COM_CONSULTA` o que cobre (`execute`, `executemany`, `callproc`, `mogrify`, `copy_expert`, em texto e em
  bytes) e em `METODOS_FORA_DE_COBERTURA` o que não cobre e por quê (`copy_from` e `copy_to` recebem NOME de tabela
  e a casa não os usa — varrido em `app/`, `scripts/` e `db/`; `psycopg2.sql.Composed` passa cru, e a casa também
  não o usa). `tests/unit/test_schema_ambiente.py` reprova se um ponto de entrada novo aparecer sem decisão escrita
  e se alguém passar a usar um dos excluídos.

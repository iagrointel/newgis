# ADR 20260906T1640 — Grades aninhadas do motor multicritério (L3-19-multiescala)

Estado: aceito (dados+backend+adversário, turno T3, setembro de 2026). Nome de arquivo por carimbo de
tempo (regra nascida do incidente de colisão de ADR 0018 em 06/09) em vez de número sequencial, porque
outras trilhas escrevem ADR no mesmo minuto sem se falar.

## Contexto

Hipótese do item: triagem regional numa grade MACRO grosseira (ex. 1 km), estudo fino numa grade MICRO
(ex. 100 m) gerada só dentro das regiões aprovadas no macro; camada de escala quilométrica não custa por
célula de 100 m (regra herdada do motor de LT); o resultado macro vira a máscara de estudo do micro.
`L3-01-b-unidades` (dependência declarada) está PARCIAL num ramo (`wt/amc`) ainda não juntado a este —
este item não importa `app/amc/*`: reimplementa a resolução de CRS própria (`app/multiescala/crs.py`) em
vez de depender de um módulo que não existe nesta árvore. Quando os dois ramos juntarem, a duplicação de
`crs.py` é candidata a unificação, registrada aqui para não se perder.

## Decisão A — aninhamento é ARITMÉTICO, não um filtro aplicado depois

As duas grades de um conjunto compartilham origem (`origem_x_m`/`origem_y_m`, canto inferior-esquerdo do
bbox da área de estudo) e CRS de trabalho. A resolução macro é múltiplo inteiro `k >= 2` da micro
(`gerar_grade_micro` recusa razão não inteira, `aninhamento_nao_inteiro`). A célula macro `(col, lin)`
contém exatamente as micro `(col*k+dx, lin*k+dy)`, `0 <= dx,dy < k` — a query de geração da micro faz
`JOIN plat.escala_resultado ... WHERE aprovada` ANTES do `CROSS JOIN generate_series(0,k-1)`: célula fora
de região aprovada nunca é gerada (não existe linha em `escala_celula` para ela), não é uma célula gerada
e depois descartada. É a cláusula central do portão e a que torna a economia de custo mensurável
(`celulas` vs `grade.celulas_possiveis`, ver medidas).

## Decisão B — custo por BLOCO na escala NATIVA do fator, não por célula

`plat.escala_bloco` agrega a amostra bruta do fator (`escala_amostra`) num bloco de resolução
`res_bloco = max(resolucao_fonte_declarada, resolucao_da_grade)` — nunca mais fino que a fonte declarada.
Blocos são cacheados por `(tenant_id, fator_id, srid, resolucao_m, bloco_x, bloco_y)`, `ON CONFLICT DO
NOTHING`: uma execução nova na MESMA grade reaproveita blocos já calculados por uma execução anterior;
`escala_execucao_fator.blocos_calculados` conta só os que esta rodada teve de agregar, contra
`blocos_usados` (o total). É a mecânica que faz um fator de 1 km custar uma agregação por km², nunca uma
por célula de 100 m, mesmo numa grade micro de milhares de células.

**Achado rodando de verdade (medido, não hipotético)**: o bloco usa a coordenada ABSOLUTA no CRS de
trabalho (`floor(x/r)`), não a posição relativa à origem do conjunto — então o bloco que uma CÉLULA
consulta (pelo `floor(centro_x_m/r)` do seu próprio centro) só bate com o bloco que uma AMOSTRA populou se
a amostra cair dentro do MESMO bloco absoluto, não só "dentro da área de estudo". Um retângulo de estudo
cujo segundo eixo mal passa de `k` vezes a resolução (ex. 1,35-1,47 km sobre grade de 1 km) produz uma
célula-fatia cujo CENTRO nominal cai fora da extensão real de dado — nenhuma amostra a alcança e a célula
fica sem nota, não por defeito do motor, por a área de estudo ser fina demais para o próprio grid nominal
que ela pediu. Documentado em `tests/api/multiescala/test_multiescala.py` (comentário da constante
`ALVO_LARGURA_M`/`ALVO_ALTURA_M`, 1.900 m escolhido de propósito) para o próximo teste não tropeçar na
mesma coisa achando que é bug do motor.

## Decisão C — `escala_grosseira` é CALCULADO, nunca recebido do cliente

`resolucao_fonte_m` é campo obrigatório do fator (a escala nativa DECLARADA, sem padrão) e nunca é
comparado pelo cliente: o motor calcula `escala_grosseira = resolucao_fonte_m > resolucao_grade_m` em
`executar()` e grava em `escala_execucao_fator`, junto com `razao_escala` (fonte/grade). Isto é a
refutação do item: um fator de 1 km usado sozinho, sem qualquer flag do chamador, sai marcado `grosseira`
quando a grade é mais fina que 1 km, e `propria` quando não é — o MESMO fator, a MESMA chamada de API,
muda de veredito só porque a grade mudou. Medido em `test_relatorio_declara_escala_grosseira_do_fator`:
um fator de resolução 1.000 m sai `propria` numa grade de 1.000 m e `grosseira` na grade de 100 m gerada
pela MESMA execução macro, sem o cliente declarar nada de diferente entre as duas chamadas.

## Decisão D — combinação: `Σ(peso × favorabilidade) / Σ(peso)` sobre os fatores COM dado

Célula sem dado de um fator não entra na soma (nem no numerador nem no denominador) — nunca
`COALESCE(favorabilidade, 0)`, que penalizaria silenciosamente uma célula por ausência de cobertura em vez
de declarar a ausência. `cobertura` (fração do peso total que tinha dado) é gravada por célula ao lado da
nota. `favorabilidade` satura em 50,0 quando `min = max` do fator inteiro (sem variação, não há o que
normalizar) — decisão herdada de `laco/decomposicao/L3L6_CONCEITO.md` A3/A5, não uma escolha nova deste
item; reconferida aqui porque o teste deste item depende dela (amostra de valor constante para exercitar
a mecânica de escala sem se preocupar com a distribuição do dado).

## Achado de framework, fora do escopo deste item mas bloqueando-o: `CursorSchemaAmbiente.executemany`

`app/schema_ambiente.py::CursorSchemaAmbiente` reescreve `plat.` → `plat_t<trilha>.` dentro de `execute` e
`callproc`, mas não tinha essa reescrita em `executemany` (psycopg2 implementa `executemany` em C e nunca
chama `execute` de volta). `POST /api/multiescala/fatores/{id}/amostras` usa `executemany` para o lote de
pontos e falhava com `permission denied for schema plat` em QUALQUER trilha. Reproduzido também numa rota
que NADA tem a ver com este item — `POST /api/papeis` (`app/auth/rotas_usuarios.py`, grava
`plat.papel_privilegio` por `executemany`) — e confirmado como a causa real de uma falha de
`tests/api/test_cruzado.py` que parecia RLS cruzada (`erro_do_banco` converte `InsufficientPrivilege` em
403 "operação fora do inquilino da sessão") e não era. Corrigido acrescentando o método faltante à classe
(mesmo corpo de `execute`); a correção é da CLASSE, então vale para as duas rotas, não só para esta.

## Portas ainda fechadas (fora do portão deste item, registradas para o próximo)

- `DELETE /api/multiescala/conjuntos/{id}` e `.../fatores/{id}` foram acrescentados NESTE turno (não
  estavam na hipótese original) só porque a varredura cruzada A→B (`tests/api/cruzado_casos.py`) precisa
  de um jeito de limpar o que cria em A — sem eles a suíte acumularia lixo no inquilino de teste a cada
  rodada, o mesmo problema que toda rota de criação da casa já resolve com sua própria DELETE.
- Sem endpoint de "listar fatores por execução com valor bruto por célula" (`escala_fator_celula`) — o
  relatório por fator (`escala_execucao_fator`) é agregado; ver célula a célula fica para quem for
  desenhar o mapa de resultado (fora do portão: "relatório declara a escala de cada fator", não "mostra o
  mapa").
- `docs/openapi.json` comitado não inclui as rotas `/api/multiescala/*` (regeneração é pendência do
  gerente após os merges, ADR 0014/RETOMADA_20260906.md item 3) — `tests/api/cruzado_casos.py` já tem os
  11 casos prontos; `tests/api/test_cruzado.py::test_cobertura_100_por_cento` só vai exercitá-los depois
  de `make openapi` rodar contra a árvore juntada.

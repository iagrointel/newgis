# Execução do motor AMC sobre camadas do acervo, sem cópia (item L6-04-acervo-no-motor)

## Contexto

O item pede: "camada do acervo assinada é usável como fator ou restrição no motor L3 sem cópia (o extrator lê a
view); o resultado guarda fonte_id, sha256 e contagem da camada na proveniência." Duas dependências, as duas
`parcial`: L6-01-b-view-so-leitura entregou a view só-leitura de `plat_acervo` com o porteiro
`plat.acervo_pode_ler`; L3-01-c-extracao-fator entregou os extratores puros de raster (`app/amc/zonal.py`) e
vetor (`app/amc/vetorial.py`), que recebem listas Python em memória, não uma consulta ao banco. Nenhum dos dois
itens ligou a extração a uma EXECUÇÃO (`plat.amc_execucao`) de verdade — não existia job que lesse uma camada e
gravasse `amc_fator_bruto`/`amc_resultado`. As três peças moravam em três worktrees diferentes
(`wt/amc`, `wt/extrat`, `wt/t601b`), nenhum mesclado em `master`.

## Decisão

1. **Merge dos três worktrees neste ramo** (`wt/amc` → `wt/extrat` → `wt/t601b`), na ordem de dependência.
   Conflitos textuais resolvidos preservando as duas metades (import de rotas em `app/main.py`, bytes/mixin em
   `app/schema_ambiente.py`). O merge automático de `tests/api/cruzado_casos.py` não gerou marcador de conflito
   mas produziu Python inválido (função partida por uma `def`, `)` de fechamento perdido) — corrigido à mão,
   registrado no CHANGELOG.
2. **Novo módulo `app/amc/executor.py`** com a função `executar(ctx, execucao_id)`, corpo do job `amc.executar`
   (`app/amc/tarefas.py`), no mesmo padrão de `ContextoJob`/`ContextoDeTeste` que `amc.gerar_unidades` já usa.
3. **Tradutor de vocabulário**: o esquema do modelo (`docs/esquemas/amc_modelo.v1.json`, do item L3-01-a) usa
   nomes de extrator (`poligono_fracao_area`, `linha_distancia_mais_proxima`, ...) diferentes dos nomes que
   `app/amc/vetorial.py` (item L3-01-c) implementa (`vetor_fracao_area`, `vetor_distancia_mais_proxima`, ...) —
   os dois vocabulários nasceram em ramos que não se falaram. `executor.MAPA_EXTRATOR_VETOR` faz a tradução;
   um extrator sem correspondente (todo `raster_*`, `valor_pronto`) recusa com mensagem clara, não finge.
4. **Assinatura como porteiro em DOIS lugares, não um**: `app/amc/camadas.py::_acervo` já checava
   `estado = 'exposta'` na CRIAÇÃO da execução; agora também chama `plat.acervo_pode_ler` (a MESMA função que
   `app.acervo.publicacao` usa na API de mapa, nunca um segundo critério que pudesse divergir). Sem assinatura,
   422 `sem_assinatura` — a execução nem nasce. Isso cobre "revogar impede nova execução". Para a refutação
   ("revoga durante um job"), o `executor.executar` confere a assinatura de NOVO, uma vez antes de extrair cada
   fator e uma segunda vez depois do último, antes de gravar qualquer coisa.
5. **Gravação atômica no fim, nunca incremental**: `amc_fator_bruto` e `amc_resultado` só são inseridos num
   único bloco, depois que TODAS as checagens de assinatura (a segunda rodada incluída) passaram. Se a
   assinatura for revogada em qualquer ponto antes disso, `FalhaDefinitiva` é levantada e o bloco de gravação
   nunca roda — a execução vai a `falhou` com mensagem, nunca fica com resultado parcial nem com zeros. É esta
   decisão, mais que a checagem em si, que sustenta "nunca completa com zeros".
6. **Transformação mínima**: só o tipo `linear` do esquema é implementado (`executor._transformar`); os outros
   sete tipos (`categoria`, `faixas`, `degraus`, as seis funções contínuas) recusam com `FalhaDefinitiva`
   explícita. O combinador é sempre `soma_ponderada_normalizada` sobre os fatores do acervo com dado
   (política `excluir_fator`). Isto não é o motor completo do item L3-01-d/e (que decide transformação e
   combinador em geral) — é o suficiente para o portão deste item: rodar um modelo real com 3 fatores do
   acervo e gravar proveniência.
7. **Camada lida só na caixa envolvente das unidades + 0,05°** (`executor._envelope_4326`), não na tabela
   inteira. Necessário na prática: `public.hidro_nacional_bc250` tem 1,6 mi de linhas; ler a tabela inteira a
   cada execução não escala. Efeito colateral honesto: "distância ao mais próximo" é a mais próxima DENTRO
   dessa caixa, não a distância nacional — documentado no módulo e no handoff, não escondido.

## Prova (camadas REAIS, não sintéticas)

`public.icmbio_unidades_conservacao` (UC, 346 polígonos), `public.funai_terras_indigenas` (TI, 655 polígonos) e
`public.hidro_nacional_bc250` (hidrografia, 1.599.240 linhas, com índice GiST — por isso essa tabela e não
`public.car_hidrografia`, 3,86 mi de linhas SEM índice espacial, que estourou o relógio do teste em consultas de
bbox). Bbox medido com 2 UC + 1 TI + 1.101 feições de hidrografia sobre Santa Catarina
(-49.5,-27.4,-48.9,-26.9). Ver `tests/api/amc/test_acervo_no_motor.py` e
`tests/medidas/L6-04-acervo-no-motor.json`.

## O que fica de fora, deliberadamente

Fator `camada.tipo == 'item'` (catálogo do inquilino) não é extraído por este job — a proveniência já o resolve
(`app/amc/camadas.py::_item`, do L3-01-a), falta só ligar a extração de verdade, item futuro. Extração de
raster do acervo (o esquema já prevê `camada.banda`) também fica fora: nenhuma camada raster do acervo estava
publicada nesta base para testar de verdade, e "testar sem provar" é pior que declarar fora do escopo.

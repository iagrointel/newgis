# Regras de atributo de rede (item L4-29-regras-de-atributo-de-rede)

Data: 08/09/2026. Estado: aceito. Par: `docs/PARIDADE_REGRAS_ATRIBUTO.md` (paridade com os perfis de
attribute rule do ArcGIS Pro / Utility Network, com fontes e data de acesso); `docs/EXPRESSAO.md` §5 (as
seis funções de rede na linguagem).

## Contexto

A linguagem de expressão da plataforma ganhou, neste item, seis funções de rede (`Subrede`, `Alimentador`,
`TensaoAlimentador`, `ContarJusante`, `NivelRede`, `AtributoRede`) que leem topologia. Faltava o consumidor
dessas funções: quem escreve a regra, quem a guarda, quem a avalia e o que acontece quando a regra erra ou
custa demais. O portão do item tem uma refutação explícita: o adversário escreve uma regra com laço
infinito ("jusante de jusante") e confere limite de tempo e de profundidade. Qualquer desenho que deixe o
motor iterar até estabilizar perde essa refutação por construção.

## Decisão

1. **Três perfis com o vocabulário do produto de referência, não a sua mecânica de gatilho.** `calculo`,
   `restricao` e `validacao` em `plat.rede_regra` (CHECKs: perfil fechado; `atributo_alvo` não nulo se e só
   se `perfil = 'calculo'`; nome e tipo alvo não vazios). Avaliar é SEMPRE uma ação explícita —
   `aplicar_calculo`, `checar_restricao`, `rodar_validacao` — e não um gancho em toda escrita de
   `rede_objeto`. Ganchos de edição (insert/update/delete + campos gatilho do modelo Esri) ficam fora do
   item; a paridade marca a lacuna com cobertor.
2. **Uma rodada = cada regra UMA vez por objeto. NÃO existe ponto fixo.** É a decisão central e é o que
   mata a refutação: a regra `AtributoRede('x') + 1` avança exatamente 1 por rodada
   (`test_laco_autorreferente_avanca_uma_vez_por_rodada`); "rodar de novo" é ação nova de quem opera, como
   a segunda passada da ferramenta de avaliação em lote. O adversário não consegue escrever jusante de
   jusante porque a linguagem não alcança o vizinho — `ContarJusante()` lê o valor JÁ calculado pelo motor
   (atributo `clientes_jusante`), e `TensaoAlimentador()` é um salto só, alimentador → atributo (memo de
   rodada, uma consulta por código distinto). Profundidade demais corta NA CRIAÇÃO (70 `Se` aninhados →
   422 `profundidade_excedida`); o que escapa corta em orçamento EXPOSTO: `limite_passos`/`limite_ms`
   nomeados nas três funções, erro NOMEADO (`limite_passos`, `tempo_excedido`) contado em `erros_total` — a
   rodada sobrevive (`test_laco_corta_no_orcamento_de_passos_com_erro_nomeado`).
3. **Restrição é falha FECHADA e recusa no lado verdadeiro da expressão.** A expressão de `restricao`
   afirma o impedimento (verdadeiro = recusa) — com lógica de três valores isso deixa o nulo do lado
   seguro sem negação de mão (a direção da Esri é a oposta; `docs/PARIDADE_REGRAS_ATRIBUTO.md` §3
   documenta a inversão e o motivo). Nulo NUNCA recusa. Erro de avaliação RECUSA com o código nomeado na
   resposta (`recusas[i].erro`) — regra que não consegue avaliar nunca autoriza
   (`test_regra_que_erra_recusa_com_erro_nomeado`).
4. **Ausência é dado.** Objeto fora de subrede, alimentador sem linha, atributo que o objeto não tem: NULO.
   `aplicar_calculo` não sobrescreve atributo existente com nulo. `rodar_validacao` lista só o verdadeiro;
   erro vira item nomeado e a rodada CONTINUA (validação lista, não trava). Teto de itens
   (`REDE_REGRAS_ITENS_MAX`) sai `truncado: true` — declarado, não escondido.
5. **Contexto fechado, chave `rede` reservada.** `montar_contexto` achata os atributos no topo
   (equivalente do `$feature`) e grava `rede` POR ÚLTIMO — um atributo chamado `rede` nunca substitui a
   reservada. NÃO existe `$datastore`: a linguagem não abre tabela, não lê arquivo, não roda SQL
   (`docs/EXPRESSAO.md` §6); o que vem de fora entra pelo contexto. Vizinho arbitrário pela topologia não é
   alcançável pela linguagem — é a segunda metade da refutação.
6. **Tetos de rodada em `app/limites.py`, documentados em `docs/LIMITES.md`**: `REDE_REGRA_MAX` (1.000
   regras ativas por perfil — criadas acima disso dão 422 `regras_demais`, sem poda automática),
   `REDE_REGRAS_OBJETOS_MAX` (50.000 objetos por tipo numa rodada), `REDE_REGRAS_ITENS_MAX` (10.000 itens
   de validação), `REDE_REGRAS_ERROS_MAX` (100 erros guardados, total contado em `erros_total`). O teto
   freia o tamanho da rodada, não a profundidade da iteração — porque não existe iteração.
7. **Sem rota nova de API neste item.** O motor é biblioteca (`app/rede/regras.py`) com testes de API
   contra o banco real (mesmo padrão de `tests/api/test_rls.py`: inquilinos semeados `demo`/`demo2` via
   `plat.auth_login`, GUC por transação, rollback no fixture). Isolamento de inquilino testado
   (`test_inquilino_b_nao_ve_regra_nem_objeto_de_a`); rotas e telas consomem depois.

## Consequências

- Quem quiser "recalcular tudo até estabilizar" chama `aplicar_calculo` em laço NO CHAMADOR, com critério
  de parada próprio — o motor nunca decide quando parar.
- Um erro de regra em produção aparece nomeado nos três perfis (recusa, `erros`, item de validação); não
  existe caminho silencioso.
- Error layer persistente com Error Inspector, ganchos de edição e `$originalFeature` ficam marcados como
  lacuna em `docs/PARIDADE_REGRAS_ATRIBUTO.md` §7, cada um com o item que o cobre ou sem cobertor
  declarado.

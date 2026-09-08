# L2-04-a-leitor-rls-martin — handoff

Ramo `wt/stac` (worktree `/home/dev/plataforma/wt/stac`). Base de teste PRÓPRIA `plat_tt204a`
(`bash laco/trilha_ambiente.sh t204a`), nunca o schema `plat` de produção.

## O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T1546_leitor_tiles.sql` | migração nova (nome conferido com `ls db/migracoes` na hora; não havia carimbo `20260906T1546`) |
| `db/leitor_instalar.sh` | papel de leitura: LOGIN, senha em credential, linha do `pg_hba.conf`. Idempotente (`mudancas: N` na última linha) |
| `install.sh` | passa a chamar `db/leitor_instalar.sh` logo depois da seção `e. pg_hba` |
| `app/ingestao/carregar.py` | 1 linha: `plat.camada_tile_garantir` logo depois de `plat.camada_preparar` |
| `app/catalogo/destruidores.py` | 3 linhas: `plat.camada_tile_apagar` antes do DROP da tabela da camada |
| `tests/api/test_leitor_tiles.py` | 16 testes, um por cláusula do portão + refutação + varredura cruzada + restrição de Referer/IP |
| `tests/medidas/L2-04-a-leitor-rls-martin.json` | 11 medidas |
| `docs/adr/0020-papel-de-leitura-e-tile-por-token.md` | a decisão (por que a prova, e não a GUC crua) |
| `CHANGELOG.md` | entrada do item |

Objetos de banco novos: papel `plat_leitor` (LOGIN, sem BYPASSRLS, sem ser dona), `plat.papel_leitor()`,
`plat.escopo_cobre()`, `plat.origem_permitida()`, `plat.ip_permitido()`, `plat.segredo_leitor`,
`plat.prova_leitor()`, `plat.tenant_leitor()`, `plat.contexto_por_token()`, `plat.camada_tile_garantir()`,
`plat.camada_tile_apagar()`, e uma função de tile `d_<slug>.t_<16 hex>(z,x,y,query_params json)` por camada.

## Cláusula do portão → prova

Tudo abaixo saiu de `venv/bin/pytest tests/api/test_leitor_tiles.py -q` (16 passed, 3 execuções seguidas) com o
ambiente da trilha:

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t204a
set -a; source /home/dev/plataforma/laco/var/trilha/t204a.env; set +a
cd /home/dev/plataforma/wt/stac && venv/bin/pytest tests/api/test_leitor_tiles.py -q -p no:warnings
```

| cláusula literal | teste | resultado |
|---|---|---|
| psql como plat_leitor sem token: SELECT em `c_*` devolve 0 linhas | `test_sem_token_le_zero_linhas_e_o_tile_levanta_excecao_nomeada` | 0 linhas |
| ... e a função de tile sem token lança exceção nomeada | mesmo teste | `token_ausente` |
| com token de demo: só linhas de demo | `test_com_token_ve_so_o_proprio_inquilino` | 3 linhas em demo, 0 em demo2 na MESMA transação; tile de 353 bytes |
| token revogado: 0 linhas em ≤ 1 s | `test_token_revogado_para_de_valer_em_menos_de_um_segundo` | recusa `token_revogado` e 0 linhas em **0,002 s** |
| log_acesso ganha 1 linha por chamada de contexto | `test_uma_linha_de_log_por_chamada_de_contexto` | 5 chamadas → 5 linhas (`linhas_log_por_chamada_de_contexto: 1.0`), última com `resultado=ok`, `status=200`, `rota=/tiles` |
| install.sh idempotente cria role e pg_hba (2ª execução = 0 mudanças) | `test_instalador_do_papel_e_idempotente` | `mudancas: 0` — **com ressalva, ver abaixo** |
| teste cruzado A→B nas funções de tile de todas as camadas da demo | `test_toda_camada_do_catalogo_tem_funcao_de_tile` + `test_varredura_cruzada_nas_funcoes_de_tile` | 2 camadas do catálogo, todas com função de tile; **6 chamadas cruzadas, 0 tile com dado** |

Refutação exigida:

| ataque | teste | resultado |
|---|---|---|
| token de A e depois tile de camada de B na mesma conexão | `test_token_de_a_e_tile_de_b_na_mesma_conexao_falha` | exceção `tile_de_outro_inquilino` |
| `set_config` direto como papel de leitura | `test_set_config_direto_como_leitor_nao_tem_efeito` | 0 linhas; `SELECT * FROM plat.segredo_leitor` e `plat.prova_leitor()` negados por privilégio; com token de A na mão, forjar a GUC de B continua dando 0 |
| o log cresce sem limite? | `test_log_nao_cresce_sem_limite` | 1 linha/chamada, **113 bytes × 1000 chamadas = 113 kB**, 4 partições mensais e `plat.log_expurgar(meses)` já existente (003) |

Medida extra: `test_contexto_nao_vaza_para_a_transacao_seguinte` — o contexto é `set_config(..., true)`, some no
fim da transação; a mesma conexão volta a ver 0 linhas (importante para pool e para o Martin, que reusa conexão).

## Decisão de projeto que o adversário precisa conhecer

`plat.tenant_id` é GUC: **qualquer** papel conectado escreve nela. O papel de leitura é o MESMO para todos os
inquilinos e conecta de fora, então uma política `tenant_id = plat.tenant_atual()` para ele seria furada por um
`SET plat.tenant_id`. Por isso a política do papel de leitura é `tenant_id = (SELECT plat.tenant_leitor())`, e
`tenant_leitor()` exige a GUC `plat.prova` = `sha256(segredo || inquilino || pg_backend_pid())`, com o segredo
em `plat.segredo_leitor` (sem SELECT para papel comum) e a prova emitida só por `contexto_por_token`.
Consequência: `plat.camada_tile_garantir` REESCREVE a política `p_c_<curto>` criada pela 029 tirando
`plat_leitor` dela e criando `p_c_<curto>_leitor` com a prova.

## O que ficou de fora, e por quê

1. **O Martin não está instalado nem configurado.** Este item entrega o CONTRATO de banco que ele consome
   (papel, contexto por token, função de tile por camada com a assinatura de "function source" do Martin:
   `(z integer, x integer, y integer, query_params json)`). Subir o serviço, o `config.yaml` e o proxy é dos
   itens irmãos do L2-04. Nenhuma linha deste item afirma que o Martin foi testado.
2. **`install.sh` inteiro não roda dentro da suíte** — reescreveria o `.env`, as senhas e as migrações da
   INSTALAÇÃO desta máquina, não da base de teste. O que o teste roda duas vezes é o passo do papel
   (`db/leitor_instalar.sh`), que é o que o item pede (role + pg_hba) e que o `install.sh` chama. A cláusula
   está provada para esse passo, não para o script inteiro: fronteira honesta.
3. **Recusa não fica em `plat.log_acesso`.** A linha é escrita e desfeita com a transação abortada (PostgreSQL
   não tem transação autônoma). Medido: `linhas_log_de_recusa_persistidas: 0`. O rastro da recusa fica no log
   do servidor (exceção nomeada) e, quando o pedido passa pela API, no log de acesso dela (L0-02-d).
4. **Restrição de Referer/IP**: implementada, aplicada dentro de `contexto_por_token` (espelho de
   `app/auth/sessao.py`) e testada — `test_restricao_de_ip_do_token_vale_na_funcao_de_contexto` e
   `test_restricao_de_referer_do_token_vale_na_funcao_de_contexto` (subdomínio casa, ápice não casa,
   `mapa.exemplo.gov.br.invasor.com` não casa, esquema diferente não casa, sem valor = falha fechada). O que
   NÃO existe é a ponta: o Martin não repassa cabeçalho HTTP, então `ip` e `origem` têm de ser injetados em
   `query_params` pelo proxy na frente. Sem esse proxy, um token COM restrição simplesmente não passa.
5. **`L0-04-c-tabela-camada` está PARCIAL**: nenhuma cláusula deste item dependeu do que falta lá (a tabela de
   camada, a RLS e `plat.camada_preparar` já existem desde a 029 e foram usadas de verdade).
6. **Camada preparada e nunca passada por `camada_tile_garantir`** mantém a política antiga (com `plat_leitor`
   dentro). O retroativo da migração varre o CATÁLOGO — não o `pg_class`, porque o schema `d_<slug>` é
   COMPARTILHADO entre produção, homologação e as bases por trilha desta máquina, e mexer em política de
   tabela de outro ambiente seria estragar a casa alheia.

## Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t204a
cd /home/dev/plataforma/wt/stac
# a migração deste item não está na árvore principal: aplique-a na base da trilha
TRILHA=t204a /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/20260906T1546_leitor_tiles.sql \
  | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -
# a suíte precisa que plat_tt204a_app possa criar a tabela de camada no schema compartilhado:
sudo -u postgres psql -d iagro_sat -c "GRANT USAGE, CREATE ON SCHEMA d_demo, d_demo2 TO plat_tt204a_app"
set -a; source /home/dev/plataforma/laco/var/trilha/t204a.env; set +a
venv/bin/pytest tests/api/test_leitor_tiles.py -q -p no:warnings      # 16 passed
```

Ataques que valem a pena tentar além dos que já estão no arquivo: reusar a GUC `plat.prova` de uma conexão em
outra (o `pg_backend_pid()` entra no hash); pedir tile de uma camada de B com um token de A que tenha
`admin:inquilino`; pôr `ip`/`origem` mentidos em `query_params` quando o token tem restrição; chamar
`plat.camada_tile_garantir` como papel de leitura (sem GRANT) e como `plat_app` apontando para o schema de
outro inquilino (deve dar `schema_sem_inquilino`/`nome_de_tabela_invalido`).

## Achado de percurso (vale para as outras trilhas)

A primeira versão fazia `GRANT USAGE ON SCHEMA d_<slug>` e `GRANT SELECT` sem conferir antes. Repetir um GRANT
reescreve a linha do catálogo (`pg_namespace`), e com outro agente fazendo DDL no MESMO schema — `d_demo` é
COMPARTILHADO por produção, homologação e todas as bases por trilha desta máquina — a suíte quebrava de forma
intermitente com `tuple concurrently updated`. Agora só concede o que falta (`has_schema_privilege` /
`has_table_privilege` antes). Três execuções seguidas verdes depois do conserto.

## O que NÃO deu para rodar nesta base

`tests/api/ingestao` (que é onde a linha nova do `carregar.py` seria exercitada de ponta a ponta) **não roda
nesta trilha**: os jobs `ingestao.inspecionar` ficam `pendente`, `worker: null` — não há worker atendendo o
canal `plat_tt204a_job`. Nada a ver com este item (nenhum job chegou a começar). O caminho
`plat.camada_preparar` → `plat.camada_tile_garantir`, que é exatamente o que a linha nova faz, está exercitado
no fixture `camadas` de `tests/api/test_leitor_tiles.py`. Quem tiver worker rodando deve repetir
`pytest tests/api/ingestao` antes do merge.

## Riscos de merge

- `app/ingestao/carregar.py` e `CHANGELOG.md` estão sendo editados por OUTRO agente neste mesmo worktree. O
  commit deste item foi montado com um índice privado (`GIT_INDEX_FILE`) a partir do HEAD, então carrega
  **apenas** a linha do `camada_tile_garantir` (carregar.py) e **apenas** a entrada deste item (CHANGELOG.md);
  o trabalho do outro agente continua intacto na árvore de trabalho, sem commit.
- `install.sh` e `app/catalogo/destruidores.py` só tinham mudança minha.
- ADR numerado 0020 (o maior existente era 0019); se outra trilha reservar o mesmo número, renumerar é seguro.

## Commits do ramo `wt/stac`

- `441569f` papel de leitura, contexto por token e função de tile por camada (9 arquivos)
- `89e1eb9` restrição de Referer/IP provada + GRANT sem reescrita (3 arquivos)
- `b0b34ce` ALTER ROLE e GRANT em `plat` só quando falta (1 arquivo)

Os três foram montados com índice privado (`GIT_INDEX_FILE`) a partir do HEAD do momento, para não carregar
o trabalho não commitado dos outros agentes que dividem este worktree; o gancho `[guarda]` confirmou a lista
declarada em cada um.

## Estado do ambiente ao fim do turno

Schema de teste `plat_tt204a` e `plat_trabalho_tt204a` DERRUBADOS, papel `plat_tt204a_leitor` e as tabelas de
teste em `d_demo`/`d_demo2` apagadas, linha do `pg_hba.conf` do papel de trilha removida. Para reproduzir,
refazer com `bash laco/trilha_ambiente.sh t204a` (o passo a passo está na seção "Como o adversário reproduz").

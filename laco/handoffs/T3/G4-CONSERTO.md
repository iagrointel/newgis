# G4 — conserto de dono/privilégio de objeto, teto de cota, expurgo de rastro e contrato comitado (turno 3, ramo `wt/g4fix`)

Resposta ao laudo `laco/handoffs/T3/ataque-g4-ADVERSARIO.md` (ramo `wt/adv4`, commit `e1ff144`), que refutou 6
dos 6 itens do grupo com 24 achados. Este turno conserta os **8 achados delegados a esta trilha** (G4-01,
G4-04, G4-05, G4-06, G4-07, G4-08, G4-09, G4-10). Os outros 16 (G4-02/03/11/12/13/14/15/16/17/18/19/20/21/22/23/24)
pertencem a outros itens ou são transversais a outra trilha e **não foram tocados aqui**; `app/schema_ambiente.py`
e permissão de função de outros itens também não foram tocados, por instrução explícita de escopo.

Worktree `/home/dev/plataforma/wt/g4fix`, base própria `plat_tg4fix`/`plat_trabalho_tg4fix`
(`bash laco/trilha_ambiente.sh g4fix`). Nada rodou contra o schema `plat` de produção; a migração deste ramo
NÃO foi aplicada em produção (a migração ainda não está em master — como no caso do `wt/g3fix`, a checagem de
`trilha_ambiente.sh` compara o SHA da versão REESCRITA para o schema da trilha, que já batia com o que estava
aplicado; nenhuma reaplicação manual foi necessária desta vez).

Estado ao retomar: o agente anterior morreu escrevendo este handoff, com todo o código, a migração e os dois
arquivos de teste já commitados no commit de RESGATE `f81a920`. Este turno não reescreveu nada do que estava
lá — conferiu cláusula por cláusula, limpou debris de uma base de teste persistente (ver §4), e fechou o que
faltava: este handoff, o ADR e a entrada de CHANGELOG.

## 1. O que já estava construído (herdado do RESGATE, conferido nesta sessão)

| arquivo | o que faz |
|---|---|
| `app/rotas_arquivos.py` | `GET`/`DELETE /api/arquivos/{sha256}` exigem ser DONO (`plat.arquivo.criado_por`) ou ter `conteudo.ver_tudo`/`conteudo.apagar_tudo`; grava `arquivos/enviar` e `arquivos/apagar` |
| `app/objetos.py` | `apagar()` chama `plat.arquivo_apagado_marcar(tenant_id, chave)` em vez de `UPDATE` direto; `parte_concluir` recebe `usuario_id` para popular `criado_por` |
| `app/auth/rotas_org.py` | `org_gravar` lê o teto do inquilino e recusa `422 cota_acima_do_teto` acima dele; `_org_json` expõe `cota_bytes_teto`/`cota_teto` |
| `app/auth/rotas_plataforma.py` | `GET`/`PUT /api/plataforma/inquilinos/{id}/cotas` (superadmin) — só a plataforma move o teto |
| `app/auth/modelos.py` | `InquilinoCotasEntrada`, `InquilinoCotas` |
| `app/limites.py` | `ORG_COTA_BYTES_TETO_MAX` (1 TiB), `ORG_COTA_USUARIOS_TETO_MAX` (100.000) — teto ABSOLUTO da instalação |
| `db/migracoes/20260906T1601_g4_conserto_seguranca.sql` | teto de cota + gatilho `tg_tenant_cota_guarda`; `plat.tenant_cotas_teto_definir`/`tenant_cotas`; `plat.arquivo_apagado_marcar`; `evento_expurgar`/`log_expurgar` validados e sem `EXECUTE` para `plat_app`/`plat_worker`; `*_expurgar_inquilino` com filtro; 6 tipos de evento novos |
| `docs/openapi.json` | regerado (`make openapi`), 28 rotas que faltavam agora presentes |
| `tests/api/test_openapi_contrato.py` | novo: compara o CONJUNTO de rotas do arquivo comitado com `app.openapi()` vivo a cada rodada |
| `tests/api/test_g4_conserto.py` | novo: ciclo completo do apagar (linha+objeto+evento+varredura), permissão de banco pós-conserto, caminho legítimo do teto (inquilino não passa, plataforma move) |
| `tests/api/test_g4_adversario.py` | cópia do arquivo do adversário (`wt/adv4`) com as marcas `xfail(strict=True)` dos 8 achados desta trilha trocadas por teste comum |
| `tests/api/test_org.py`, `tests/api/eventos_esperados.py`, `tests/api/test_eventos.py` | ajustados ao novo corpo de `/api/org` e ao vocabulário de evento novo |
| `docs/LIMITES.md` | regerado com as duas constantes de teto |

Esta sessão acrescentou: `docs/adr/20260906T1747-g4-conserto-seguranca.md` (6 decisões, D1-D6) e a entrada de
CHANGELOG do turno.

## 2. Cláusula por cláusula — prova

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh g4fix
cd /home/dev/plataforma/wt/g4fix
set -a; source /home/dev/plataforma/laco/var/trilha/g4fix.env; set +a

venv/bin/pytest tests/api/test_g4_adversario.py -p no:randomly -q -rA
  # 15 passed, 15 xfailed — os 15 passed são exatamente G4-01/04/05/06/07/08/09/10 (8 achados,
  # 2 deles com 2 testes cada: cota_bytes e cota_usuarios; leitura e apagar) + os 6 que já aguentavam
  # sem marca. Nenhum xpass: nenhum achado fora de escopo foi tocado sem querer.

venv/bin/pytest tests/api/test_g4_conserto.py -q -rA
  # 6 passed

venv/bin/pytest tests/api/test_openapi_contrato.py -q -rA
  # 1 passed
```

| achado | cláusula | prova |
|---|---|---|
| G4-06 | `GET/DELETE /api/arquivos/{sha}` exige dono ou privilégio | `test_visualizador_nao_apaga_objeto_do_inquilino`, `test_visualizador_nao_le_nem_apaga_e_o_dono_continua_podendo` — visualizador 403, dono 200/204 |
| G4-07 | idem para leitura de objeto de outro membro | `test_visualizador_nao_le_objeto_de_outro_usuario` |
| G4-08 | apagar objeto grava evento | `test_apagar_arquivo_grava_evento`, `test_ciclo_completo_do_apagar_linha_objeto_e_evento` |
| G4-09 | apagar objeto marca a linha, não deixa órfão | `test_apagar_objeto_marca_a_linha_como_apagada`; varredura de órfãos não acusa a exclusão legítima |
| G4-04 | admin do inquilino não eleva cota de armazenamento acima do teto | `test_admin_do_inquilino_nao_eleva_a_propria_cota_de_armazenamento`; `test_inquilino_nao_passa_do_teto_e_a_plataforma_e_quem_move` (422 + teto no corpo; 9e18 nem passa da validação de esquema) |
| G4-05 | idem para cota de usuários | `test_admin_do_inquilino_nao_eleva_a_propria_cota_de_usuarios` |
| G4-10 | `evento_expurgar`/`log_expurgar` validam argumento, sem `EXECUTE` para `plat_app`/`plat_worker`; partição corrente nunca cai | `test_plat_app_nao_pode_apagar_particao_de_evento`; `test_expurgo_de_rastro_valida_argumento_e_filtra_inquilino` (-1/0/NULL levantam `meses_invalido`, partição do mês corrente de pé); `test_expurgo_por_inquilino_nao_alcanca_o_vizinho` |
| G4-01 | `docs/openapi.json` comitado == `app.openapi()` vivo, conferido em toda rodada | `test_openapi_comitado_igual_ao_app_vivo`, `test_openapi_comitado_tem_as_mesmas_rotas_do_app_vivo` |

Defesa em profundidade extra (não exigida por nenhuma cláusula, medida porque o achado original era "chega
ao SQL direto"): `test_gatilho_do_banco_recusa_cota_acima_do_teto` — mesmo um `UPDATE` direto via `psql` como
`postgres` é recusado pelo gatilho `tg_tenant_cota_guarda`.

Suíte mais ampla, para checar que nada regrediu (mesmo comando do laudo adversarial, seção (a) de
`L0-10-eventos-historico`):

```
venv/bin/pytest tests/api/test_org.py tests/api/test_arquivos.py tests/api/test_eventos.py \
    tests/api/test_limite_corpo.py tests/api/test_versionamento.py \
    tests/api/catalogo/test_metadado_ogc.py tests/unit/test_limites_doc.py -p no:randomly -q
  # 54 passed (o laudo original tinha "1 failed, 48 passed" — o falho era
  # test_toda_rota_de_escrita_tem_evento_declarado, que caiu com o openapi.json regerado)
```

`make lint` e `make sem-marcador` têm achados pré-existentes em `master` (import não ordenado em
`tests/api/catalogo/conftest.py`/`tests/api/test_conexoes.py`; duas linhas com a palavra "placeholder"/"TODOS"
em `app/settings.py`/`app/geocodificador/motor.py`) — conferidos contra `/home/dev/plataforma/enterprise` e
confirmados que **já existiam antes desta trilha**; nenhum arquivo novo desta sessão (ADR, CHANGELOG) bate no
regex de marcador. `docs/gerar_limites.py --check` passa.

## 3. Estado dos 6 itens do grupo — veredito honesto

Nenhum dos 6 itens volta a `entregue`: os 8 achados desta trilha não são todos os achados de cada item.

| item | achados desta trilha | ainda refutado por (fora de escopo) |
|---|---|---|
| `L0-07-a-configuracoes-org` | G4-04, G4-05 consertados | G4-17 (blocos de página inicial não existem), G4-18 (banner/contato administrativo não existem) |
| `L0-09-metadado-catalogo` | nenhum (G4-20 é o único achado do item, fora de escopo) | G4-20 (CSW, ISO 19115-3, editor de metadado) |
| `L0-10-eventos-historico` | G4-08, G4-10 consertados | G4-02 (cobertura real 75,7 % contra o app vivo), G4-03 (lista vazia conta como declarado), G4-11 (sem periódico de partição/retenção), G4-12 (sem exportação CSV), G4-13 (sem tela Auditoria) |
| `L0-11-arquivos-objetos` | G4-06, G4-07, G4-08, G4-09 consertados (todos os do item, exceto G4-19) | G4-19 (`/saude` não marca Garage como obrigatório) |
| `L0-12-contrato-api-e-limites` | G4-01 consertado | G4-14 (sem rate limit), G4-15 (sem teste de contrato/lint), G4-16 (sem `Retry-After`), G4-23 (42501 disfarçado de 403 de inquilino) |
| `L0-14-identidade-visual` | nenhum (G4-21/22 fora de escopo) | G4-21 (literais de cor fora dos tokens), G4-22 (telas sem tokens, sem `/estilo`) |

Recomendação ao gerente: mover `L0-07-a-configuracoes-org`, `L0-10-eventos-historico`,
`L0-11-arquivos-objetos` e `L0-12-contrato-api-e-limites` de `refutado` para `parcial` com nota apontando os
achados que restam (marcado nesta sessão via `marcar_item.py`, ver rodapé). `L0-09-metadado-catalogo` e
`L0-14-identidade-visual` ficam como estavam — esta trilha não tocou nenhum achado deles.

## 4. O que ficou de fora, e por quê

1. Os 16 achados não delegados a esta trilha (lista no topo) — de outros itens/trilhas por decisão do gerente.
2. **Limpeza de debris de teste**: a base `plat_tg4fix` tinha 9 linhas órfãs em `upload` (referenciando itens
   `zt-cem-mb.csv`/`zt-fora-de-ordem.csv`/`zt-corrida.csv` do item de upload retomável, criadas entre 16:26 e
   16:41 por rodadas anteriores da mesma trilha antes do RESGATE) que quebravam o teardown de
   `tests/api/catalogo/conftest.py::_expurgar_zt` com `ForeignKeyViolation` quando a suíte de arquivos rodava
   antes da suíte de catálogo. Removidas por SQL direto na base da TRILHA (nunca produção); não é código, é
   higiene de uma base de teste persistente reusada por sessões que caíram no meio.
3. **G4-19 não foi tratado** mesmo estando em `L0-11-arquivos-objetos` (o mesmo item de G4-06/07/08/09) porque
   não está na lista de achados desta tarefa; fica para quem fechar o item por completo.

## 5. Riscos de junção

- `app/rotas_arquivos.py`, `app/objetos.py`, `app/auth/rotas_org.py`, `app/auth/rotas_plataforma.py`,
  `app/auth/modelos.py`, `app/limites.py`: mudanças localizadas (assinatura de função ganhou parâmetro
  default, rota nova, campo novo no corpo de saída) — baixo risco de colisão textual, mas **qualquer outra
  trilha que também mexa em `PUT /api/org` ou no console de plataforma precisa reconferir** as duas novas
  checagens de teto.
- `db/migracoes/20260906T1601_g4_conserto_seguranca.sql`: idempotente (`ADD COLUMN IF NOT EXISTS`,
  `CREATE OR REPLACE`, `ON CONFLICT DO NOTHING`), mas **redefine** `plat.evento_expurgar`/`log_expurgar` e faz
  `REVOKE EXECUTE ... FROM PUBLIC, plat_app, plat_worker` — se outra trilha também concedeu `EXECUTE` nessas
  funções a `plat_app`/`plat_worker` por outro caminho (não encontrado nesta varredura), o merge precisa
  decidir qual regra vale.
- `docs/openapi.json`: arquivo grande, gerado; **qualquer outra trilha que também tenha rodado `make openapi`
  no meio tempo vai colidir literalmente aqui** — na integração, o certo é regerar de novo depois do merge de
  código, nunca escolher um lado do diff.
- `tests/api/test_g4_adversario.py`: é uma CÓPIA do arquivo de `wt/adv4`. Se o gerente juntar `wt/adv4`
  também, há dois arquivos com o mesmo nome e propósito — o desta trilha é o que reflete o conserto; o de
  `wt/adv4` é o retrato do ataque original (não deve ser sobrescrito por cima deste na hora de decidir qual
  fica).

## 6. Como reproduzir do zero

```
bash /home/dev/plataforma/laco/trilha_ambiente.sh g4fix
cd /home/dev/plataforma/wt/g4fix
set -a; source /home/dev/plataforma/laco/var/trilha/g4fix.env; set +a
venv/bin/pytest tests/api/test_g4_adversario.py tests/api/test_g4_conserto.py tests/api/test_openapi_contrato.py -p no:randomly -q -rA
```

Apagar a base ao fim (nunca necessário para o merge, só para liberar espaço):
`sudo -u postgres psql -d iagro_sat -c 'DROP SCHEMA plat_tg4fix CASCADE; DROP SCHEMA plat_trabalho_tg4fix CASCADE'`

Commits do ramo `wt/g4fix`: `f81a920` (RESGATE — todo o código, migração e testes) + o commit desta sessão que
fecha o handoff/ADR/CHANGELOG (sha no rodapé do relato ao gerente).

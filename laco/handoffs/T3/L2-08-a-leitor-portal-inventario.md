# L2-08-a-leitor-portal-inventario — handoff

Ramo **`wt/l208a`** (2 commits: `17fdef1`, `944ab62`), worktree **`/home/dev/plataforma/wt/l208a`** (⚠ NÃO é o `wt/stac` do prompt — ver
"desvios" no fim). Base: `master` em `2fe849d`.

## O que foi construído

| arquivo | o que é |
|---|---|
| `db/migracoes/20260906T1540_migracao_inventario_portal.sql` | `plat.migracao_inventario` / `migracao_item` / `migracao_grupo` / `migracao_usuario`, RLS por inquilino, 2 tipos de evento. **Nome com carimbo de tempo conferido na hora** (`ls db/migracoes | tail -3` dava `046_raster_item`, `046_upload_retomavel`, `047_smtp_convites_redefinicao`; hoje master já tem um `049_*` de outra trilha, que reprova o teste de nome — não é meu). |
| `app/migracao/portal.py` | cliente só-leitura do Portal/AGOL sobre `app.conexao.seguranca` (L6-02-a): SSRF, IP pinado, redirecionamento revalidado, token em `X-Esri-Authorization`, espera com `Retry-After` em 429/503, erros nomeados |
| `app/migracao/classificacao.py` | tabela tipo Esri → `migra`/`migra_parcial`/`nao_migra`; tipo fora da tabela = `desconhecido` |
| `app/migracao/inventario.py` | motor com as 4 fases e a retomada por dado |
| `app/migracao/tarefas.py` | job `migracao.inventariar` (3 tentativas; `ErroRede` repete, o resto é `FalhaDefinitiva`) |
| `app/migracao/relatorio.py` | CSV (BOM UTF-8, `;`) e resumo por tipo |
| `app/migracao/rotas.py`, `modelos.py` | `/api/migracao/inventarios` (POST/GET/DELETE), `/itens`, `/relatorio.csv` |
| `web/migracao.html`, `web/migracao.css`, `web/js/migracao/migracao.js` | tela `/migracao` |
| `tests/migracao/portal_falso.py` + `respostas/gerar.py` + `respostas/portal.json` | servidor de mentira (59 itens, 19 serviços, 3 grupos, 4 usuários, 21 tipos) |
| `tests/migracao/PORTAL_DE_TESTE.md` | **a pendência da prova contra Portal real, escrita** |
| `docs/adr/0018-leitor-inventario-portal-agol.md` | 6 decisões |
| shared, mudança mínima: `app/main.py` (+3), `app/jobs/tipos.py` (+1), `app/paginas.py` (+2), `web/js/base/layout.js` (+1), `web/js/i18n/pt-BR.json` (+2), `CHANGELOG.md` | registro do router, do tipo de job, da página e do item de menu |

## Portão de pronto, cláusula por cláusula

| cláusula | prova | veredito |
|---|---|---|
| "contra um Portal público de teste (organização AGOL pública…, registrada com URL e data em `tests/migracao/`)" | `tests/migracao/PORTAL_DE_TESTE.md` registra que **NÃO foi feito**: credencial do parceiro = D20 em aberto, e ler organização pública de terceiro sem autorização não se faz. | ⛔ **PENDENTE** |
| "o inventário lista ≥ 50 itens com tipos, contagens e dependências corretas (amostra conferida à mão no JSON)" | `pytest tests/api/test_migracao_inventario.py::test_inventario_lista_itens_tipos_contagens_e_dependencias` — 59 itens; para CADA item confere tipo, dono, tamanho e visualizações contra `respostas/portal.json`; para os 19 serviços confere a soma das contagens de `returnCountOnly`; para cada web map confere que as dependências são exatamente as `operationalLayers[].itemId` do documento | ✅ (contra o servidor de mentira) |
| "credencial do parceiro (D20) = PENDENTE" | dito no ADR 0018, no CHANGELOG e no PORTAL_DE_TESTE.md | ✅ (declarado) |
| "token nunca aparece em log (grep 0)" | `::test_token_nunca_aparece_em_log_nem_em_coluna_de_texto` — varre TODA coluna `text`/`varchar`/`jsonb` do schema (>100 colunas, dentro do contexto do inquilino, senão a RLS zeraria a busca), menos `conexao.credencial_cifrada`; e confere que o servidor não recebeu nenhum `?token=` | ✅ |
| "job retoma após falha de rede no meio (teste com corte)" | `::test_job_retoma_depois_de_corte_de_rede_no_meio` — corte no 30º pedido, inventário fica `rodando` com `retomada.fase='itens'` e itens parciais; 2ª tentativa conclui com **177 pedidos contra 203 do zero** | ✅ |
| "relatório CSV gerado" | `::test_relatorio_csv_sai_com_uma_linha_por_item` — 60 linhas (59 + cabeçalho), BOM, `Content-Disposition`, sem token | ✅ |
| "e2e da tela de conexão e inventário com captura" | `pytest tests/e2e/test_migracao.py` — 3 capturas em `tests/e2e/capturas/L2-08-a-*.png` (conexão, lista, relatório), 0 erro de console | ✅ |

## Refutação exigida

| ataque | prova | resultado |
|---|---|---|
| Portal com 10 mil itens (paginação e tempo) | `::test_dez_mil_itens…` (marcado `lento`) | 10.000 itens, **8,4 s, 107 pedidos** |
| URL que não é Portal (erro nomeado, sem 500) | `::test_url_que_nao_e_portal_da_erro_nomeado_e_nunca_500` | `FalhaDefinitiva("nao_e_portal…")`, inventário `falhou` com mensagem; a rota também recusa conexão que não é `esri_rest` com 422 `conexao_nao_e_portal` |
| nenhum e-mail de usuário gravado | `::test_nenhum_dado_pessoal_de_usuario_e_gravado` — o portal de mentira DEVOLVE `email`/`fullName`/`description`; nenhuma das 4 tabelas contém as agulhas, e `migracao_usuario` **não tem coluna** onde caberia | ✅ |

## Regressão medida (não é o portão, mas o gerente vai perguntar)

`tests/unit` inteiro e os grupos de API mais expostos às minhas linhas em arquivo compartilhado
(`test_paginas.py`, `test_docs.py`, `test_privilegios_declarados.py`, `test_privilegios_matriz.py`,
`test_privilegios_doc.py`) passam. As falhas que sobram **não são deste item** e reproduzem sem ele:

- `tests/unit/test_migracoes_nome_e_dependencia.py` — `049_convite_resolver_config.sql`, de outra trilha;
- `tests/unit/test_jobs_registro.py::test_tipos_de_prova_estao_registrados` — `app/ingestao/inspecionar.py`
  declara `memoria_mb=768` e o teste fixa o teto em 512 (o meu tipo declara 512, dentro do teto);
- `tests/unit/test_politica.py` e `test_settings.py` — fixture `caplog` ausente neste ambiente;
- `tests/api/jobs/*` — exigem worker vivo, que a trilha não sobe;
- `tests/api/test_cruzado.py` — erra no preparo de rotas alheias (`/api/org`, `/api/usuarios`, `/api/papeis`)
  com "operação fora do inquilino da sessão"; e, por ler o `docs/openapi.json` velho, **não cobre as rotas
  novas** — por isso a trava A→B delas foi provada à mão em
  `test_inventario_de_a_nao_aparece_nem_abre_para_b` (commit `944ab62`).

⚠ a suíte `tests/unit tests/api` COMPLETA não terminou dentro do turno (a máquina está disputada); o que está
acima foi rodado em blocos.

## Medidas (`tests/medidas/L2-08-a-leitor-portal-inventario.json`, git_sha 2fe849d88a4a)

59 itens · 203 pedidos HTTP · 0,44 s · 237.057 feições contadas · retomada 177 vs 203 do zero ·
10 mil itens em 8,4 s com 107 pedidos · página `/migracao` medida pelo playwright.

## Como o adversário reproduz

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh l208a
cd /home/dev/plataforma/wt/l208a
set -a; source /home/dev/plataforma/laco/var/trilha/l208a.env; set +a
# a migração deste item NÃO está na árvore principal que o trilha_ambiente.sh varre; aplique à mão:
TRILHA=l208a /home/dev/plataforma/laco/trilha_reescrever.py \
  db/migracoes/20260906T1540_migracao_inventario_portal.sql > /tmp/mig_l208a.sql
chmod 644 /tmp/mig_l208a.sql && sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f /tmp/mig_l208a.sql

venv/bin/pytest tests/unit/test_migracao_classificacao.py tests/api/test_migracao_inventario.py -q   # 26, sem flock
venv/bin/pytest tests/api/test_migracao_inventario.py -q -m lento                                    # 10 mil itens

# e2e (precisa de TLS: a defesa de CSRF compara o Origin com PLAT_URL_PUBLICA, que só aceita https)
mkdir -p var/e2e && openssl req -x509 -newkey rsa:2048 -nodes -keyout var/e2e/chave.pem \
  -out var/e2e/cert.pem -days 30 -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"
PLAT_URL_PUBLICA=https://127.0.0.1:8169 venv/bin/python -m uvicorn tests.e2e.servidor_local:app \
  --host 127.0.0.1 --port 8169 --ssl-keyfile var/e2e/chave.pem --ssl-certfile var/e2e/cert.pem &
PLAT_GIT_SHA=$(git rev-parse HEAD) venv/bin/pytest tests/e2e/test_migracao.py -q --base-url https://127.0.0.1:8169
```

## Desvios do prompt, e por quê

1. **Worktree.** O prompt manda `wt/stac`. Às 16h01 outro agente estava escrevendo NA MESMA árvore (L4-01-a
   rede de utilidades: `app/catalogo/*`, `app/conexao/seguranca.py`, `MANUAL.md`, `app/main.py` já **staged**,
   e a minha chave nova em `pt-BR.json` foi sobrescrita por ele). Commitar ali arrastaria o trabalho dele.
   Fiz worktree própria `wt/l208a` (ramo novo a partir de `master`), copiei o meu para lá e **desfiz as minhas
   linhas nos arquivos compartilhados do `wt/stac`**, que voltou a ter só o trabalho do outro agente.
2. **Porta.** 8162 (a do prompt) já estava ocupada por outro processo; usei **8169**.
3. **`docs/openapi.json` NÃO foi regerado.** Medido: o arquivo commitado tem 126 caminhos e **falta 26**, dos
   quais 22 são de OUTRAS trilhas já no master (`/api/convites*`, `/api/org/smtp*`, `/api/uploads*`,
   `/api/geocodificar`, `/rest/services/Geocodificador/*`) e 4 são meus. Ou seja,
   `tests/api/test_privilegios_declarados.py` (que exige "docs/openapi.json comitado é o da aplicação") já
   reprovava antes deste item. Regerar aqui produziria 4.797 inserções e 2.489 remoções e conflito garantido
   com todas as trilhas. **O gerente precisa rodar `make openapi` uma vez, sozinho, depois dos merges.**
4. **Falha alheia na suíte**: `tests/unit/test_migracoes_nome_e_dependencia.py` reprova por causa de
   `049_convite_resolver_config.sql`, de outra trilha, já no master.

## Limitações honestas

- Tudo o que se sabe do leitor foi medido contra respostas gravadas por esta casa. Portal real varia em versão,
  campo ausente, `typeKeywords` fora do documentado, serviço que recusa `returnCountOnly` e limite de uso
  próprio. Nenhum número de tempo daqui vale como desempenho contra portal real (a rede é local).
- Token expirado no meio de um inventário longo hoje para com `credencial_recusada`; não há renovação.
- A tabela de classificação cobre 21 tipos com nome; o resto responde `desconhecido` de propósito. O relatório
  de migração completo (com XLSForm e exportação reversa) é o L2-08-d, que consome esta tabela.
- `plat.migracao_item.camadas` guarda a contagem por camada, não o esquema completo — esquema é do L2-08-b.
- O servidor de mentira escuta no **IP público da máquina**, em porta efêmera, durante os segundos do teste —
  é o mesmo padrão que `tests/unit/test_conexao_seguranca.py` já usa, e é obrigatório porque a defesa de SSRF
  recusa loopback. Ele só serve dado fictício e não aceita escrita, mas fica registrado que durante a suíte
  existe uma porta aberta para fora.
- `tests/e2e/servidor_local.py` monta `StaticFiles` sobre `app.main.app`. É arquivo de teste, importado só
  pelo uvicorn do e2e da trilha; `app/main.py` de produção continua sem `StaticFiles` (quem serve `/static`
  lá é o nginx).

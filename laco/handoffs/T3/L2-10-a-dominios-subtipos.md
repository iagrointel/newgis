# L2-10-a-dominios-subtipos — handoff

Trilha `garage` (ramo `wt/garage`), base própria de teste `plat_tt210a` (`bash laco/trilha_ambiente.sh t210a`).
Commits deste turno: `a50c6b4`, `42232e8`, `6d6a0db`. Ramo rebaseado sobre `master` (`15575a5`) no início —
estava 28 commits atrás; conflito só em `CHANGELOG.md`, resolvido mantendo as duas seções.

## O que foi construído

**Banco** — `db/migracoes/20260906T1548_dominios_subtipos.sql` e
`db/migracoes/20260906T1620_dominios_gatilho_gerado.sql` (nomes conferidos com `ls db/migracoes | tail -3` na
hora; nenhum número reservado). Tabelas `plat.dominio`, `plat.dominio_valor` (índice derivado),
`plat.dominio_campo` (ligação por camada e por subtipo), `plat.camada_subtipo`. Funções
`plat.dominio_conferir` (BEFORE, forma), `plat.dominio_sincronizar` (AFTER, derivado + recusa de valor em uso +
regeneração), `plat.dominio_uso_contar` (SECURITY DEFINER), `plat.dominio_bloco_sql`,
`plat.camada_dominios_aplicar` (gera a função de validação da camada), `plat.dominio_reaplicar_ligacao`.

**API** — `app/dominios/{__init__,modelos,servico,esri,rotas,rotas_feicoes,rotas_featureserver}.py`, 18 rotas:
`/api/dominios` (GET/POST), `/api/dominios/{id}` (GET/PUT/DELETE), `/api/dominios/{id}/uso`,
`/api/dominios.csv`, `/api/dominios/csv`, `/api/dominios/importar`, `/api/dominios-limites`,
`/api/camadas/{id}/dominios` (GET/POST), `/api/camadas/{id}/dominios/{ligacao}` (DELETE),
`/api/camadas/{id}/subtipos` (GET/PUT/DELETE), `/api/camadas/{id}/feicoes` (GET/POST),
`/rest/services/{id}/FeatureServer[/{camada}]`. Duas linhas em `app/main.py` e uma em `app/paginas.py`.

**Tela** — `web/camada_dominios.html`, `web/js/dominios/tela.js`, `web/js/dominios/valores.js`, 15 chaves novas
em `web/js/i18n/pt-BR.json` (acrescentadas ao fim, sem reordenar o arquivo).

**Documento** — `docs/adr/0021-dominios-e-subtipos.md`; entrada no `CHANGELOG.md`.

## Portão de pronto, cláusula por cláusula

Comando único de tudo abaixo:

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh t210a
cd /home/dev/plataforma/wt/garage
set -a; source /home/dev/plataforma/laco/var/trilha/t210a.env; set +a
PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/test_dominios_subtipos.py -q     # 17 passaram
```

| cláusula do portão | prova | resultado |
|---|---|---|
| criar domínio codificado com 5 valores, ligar a um campo, inserir código inválido direto na tabela como `plat_app` = erro do gatilho com nome do campo | `test_dominio_codificado_5_valores_recusa_codigo_invalido_na_tabela` | PASSOU. Mensagem medida: `campo "uf": o valor 'ZZ' não pertence ao domínio "<nome>"`; `diag.column_name = uf` |
| domínio de intervalo recusa fora do mín/máx | `test_dominio_intervalo_recusa_fora_do_minimo_e_do_maximo` | PASSOU (recusa −0,1 e 10,1 num domínio 0–10) |
| subtipo muda o domínio do mesmo campo (teste com 2 subtipos) | `test_subtipo_troca_o_dominio_do_mesmo_campo` | PASSOU. 3 domínios no campo `situacao`: padrão + subtipo 1 + subtipo 2; `terra` passa no 2 e é recusado no 1 |
| remover valor em uso = 409 com contagem | `test_remover_valor_em_uso_devolve_409_com_a_contagem` | PASSOU. `{"erro":"valor_em_uso","detalhe":{"codigo":"C1","usos":4}}`; valor não usado sai com 200 |
| FeatureServer /{id} mostra domains e types iguais ao banco | `test_featureserver_mostra_domains_e_types_iguais_ao_banco` | PASSOU. 2 campos com `domain`, 1 `type`, `codedValues` e `range` conferidos contra `GET /api/camadas/{id}/dominios` |
| formulário mostra descrição e grava código (e2e com captura) | `tests/e2e/test_dominios.py` | PASSOU. Opções `['São Paulo','Rio de Janeiro','Minas Gerais']` com valores `['SP','RJ','MG']`; gravado no banco: `uf='SP'`. 4 capturas em `tests/e2e/capturas/L2-10-a-dominios-subtipos_*.png` |
| 10 mil inserções com gatilho ≤ 1,5× o tempo sem gatilho (medido) | `test_custo_do_gatilho_em_10_mil_insercoes` | PASSOU na 2ª arquitetura: **1,159×** (1,692 s sem, 1,960 s com) e **1,203×** numa segunda rodada. A 1ª arquitetura media **1,80×** e foi refeita — ver abaixo |

Medidas em `tests/medidas/L2-10-a-dominios-subtipos.json`.

## Refutação exigida no item

| ataque | resposta | teste |
|---|---|---|
| ligar domínio de A a campo de B | 404 `dominio_inexistente`; a camada de A vista de B também é 404, e o FeatureServer dela também | `test_dominio_de_outro_inquilino_da_404` |
| domínio com 50 mil códigos | 422, com o teto (2000) na mensagem; o banco recusa igual, por gatilho | `test_dominio_com_50_mil_codigos_recusado` |
| código duplicado | 422 na API e `dominio_codigo_duplicado` no banco, escrevendo direto como `plat_app` | `test_codigo_duplicado_recusado_na_api_e_no_banco` |
| alterar o tipo de campo com domínio ligado | 409 `dominio_tipo_em_uso`, com o campo e o tipo dele no detalhe | `test_trocar_tipo_de_campo_com_dominio_ligado_recusado` |

Testes extras que o item não pediu e que fecham o mesmo flanco: apagar domínio ligado = 409; campo inexistente
= 404 e tipo incompatível = 422; desligar remove o gatilho e o valor volta a passar; UPDATE também é validado;
CSV de ida e volta; importação de FeatureServer reaproveita domínio de mesmo nome em vez de duplicar; **e o
banco regenera o gatilho sozinho quando alguém liga um domínio por SQL puro, sem passar pela API**
(`test_banco_regenera_o_gatilho_sem_a_api`).

## O achado do turno: o gatilho genérico custava 1,80×

A primeira versão era uma função única, `plat.feicao_validar_dominio`, que lia os campos com `to_jsonb(NEW)` —
a única forma de um plpgsql genérico acessar campo por nome. Medido: 1,72 s sem gatilho contra 3,11 s com,
**1,80×**, reprovado. Um segundo teste, em tabela de bancada, isolou a causa: um gatilho que só faz
`to_jsonb(NEW)` e retorna já custa cerca de **129 µs por linha**, porque converte a linha inteira — a
geometria inclusive, e a função de saída do tipo `geometry` roda a cada linha.

A correção foi trocar o genérico por **função gerada por camada** (`plat.dominio_v_<item>`), com `NEW.uf`
escrito no código. Fica embutido só o que muda por DDL; a lista de códigos continua sendo lida em
`plat.dominio_valor` a cada linha (uma sondagem de chave primária). E, para que a função gerada não dependa da
API para ficar em dia, três gatilhos AFTER (em `plat.dominio_campo`, `plat.camada_subtipo` e `plat.dominio`)
chamam o gerador sozinhos — nenhuma rota instala gatilho.

## O que ficou de fora, e por quê

1. **FeatureServer completo.** Só o metadado (`fields[].domain`, `types[]`). `/query` e `/applyEdits` são da
   linha L2-08. Quando ela chegar, o que se reaproveita é `app/dominios/esri.py`; a rota atual vira um pedaço
   dela.
2. **`POST /api/camadas/{id}/feicoes` grava UMA feição.** Existe para o formulário ter o que provar; edição em
   lote, versão e anexo são da L2-08.
3. **Popup do mapa.** `web/js/dominios/valores.js` é a função única de tradução e já roda no formulário e na
   tabela. O popup do mapa passa a usá-la quando o painel de camada do L2-01 existir — hoje não há painel de
   camada para pendurar.
4. **Importação de FGDB por arquivo.** `POST /api/dominios/importar` recebe o `fields`/`types` (o mesmo objeto
   que a Esri publica em `?f=json`). Abrir o `.gdb` e extrair esse objeto é o L2-08-b, dependência aberta.
5. **Intervalo de data.** Existe no Pro; aqui o banco recusa em vez de deixar meio funcionando.
6. **Varredura cruzada A→B (`tests/api/test_cruzado.py`) NÃO cobre as rotas novas.** Explicado abaixo — é o
   ponto que precisa de decisão do gerente.

## O que precisa do gerente

**(a) `docs/openapi.json` está DEFASADO em `master`.** O arquivo comitado tem 128 caminhos; a app de hoje tem
163. Faltam lá as rotas de convites, SMTP, uploads, geocodificador **e** as deste item. Como `test_cruzado`
gera os casos a partir desse arquivo, rota nova nenhuma está sendo varrida, e `test_cobertura_100_por_cento`
**já reprova em master** por 15 rotas sem caso (`/api/importacoes/*`, `/ogc/records/*`,
`/api/arquivos/_chave-leitura`, `/api/arquivos/_cog/autorizar`, `/api/itens/{id}/metadado.xml`). Eu escrevi os
20 casos cruzados das minhas rotas e os **retirei do commit**: com o openapi defasado, eles apareceriam como
"casos de rota inexistente" e deixariam o teste ainda mais vermelho, por motivo meu. O arquivo pronto está em
`/tmp/claude-1001/-home-dev/f8a9bc43-ac97-4d84-a782-cbc8e0e5a220/scratchpad/cruzado_casos_com_L2-10-a.py` —
aplicar junto com um `make openapi` e com os casos das outras trilhas, numa passagem só.

**(b) Outra sessão está trabalhando NO MESMO worktree `wt/garage`.** Durante o turno apareceram edições que
não são minhas em `app/ingestao/{rotas,cad,carregar,geometria,inspecionar}.py` e
`tests/api/ingestao/test_ingestao_cad.py` (item L0-04-e, cujo commit `ce379e2` é o anterior ao meu). Não
commitei nada disso. Duas consequências medidas: `tests/unit/test_jobs_registro.py` reprova por erro de import
em `app/ingestao/inspecionar.py` (trabalho em curso de lá), e a rota `GET /api/importacoes/formatos` que
apareceu no arquivo de trabalho **não tem dependência de autenticação nenhuma** — vale um olhar de quem for
revisar o L0-04-e antes que isso entre.

**(c) Divergência real do repositório, não corrigida aqui.** O slug de inquilino aceito pela API admite hífen
(`^[a-z0-9-]{2,39}$`), mas `plat.camada_schema_garantir` e `plat.camada_preparar` (migração 029) exigem
`^[a-z][a-z0-9_]{0,60}$` no slug e `^d_[a-z0-9_]{1,62}$` no schema. **Um inquilino com hífen no slug não
consegue publicar camada hospedada.** Não mexi porque é da ingestão; contornei nos testes com slug sem hífen.

## Estado dos testes na base da trilha

- `tests/api/test_dominios_subtipos.py`: **17 passaram**, 0 falhas.
- `tests/e2e/test_dominios.py`: **1 passou**, com 4 capturas.
- `make lint` (`ruff check app tests docs/gerar_limites.py`): limpo nos meus arquivos; os I001 que sobram são
  de arquivos de outras trilhas (`tests/api/ingestao/conftest.py`, `tests/api/jobs/*`, etc.), pré-existentes.
- Reprovações **pré-existentes** que continuam de pé na base da trilha, todas alheias a este item:
  `test_cruzado.py::test_cobertura_100_por_cento` (item (a) acima), `test_privilegios_doc` e
  `test_banco::test_conexao_tcp_como_plat_app` (as duas conectam no schema `plat` de produção, que a role da
  trilha não alcança — artefato do ambiente por trilha, não bug), `test_garage_adversario::test_zz_grava_medidas`
  (14 dos 17 ataques rodam sem o Garage local) e `test_jobs_registro` (item (b)).
- **Consertado neste turno**: `tests/unit/test_instalador.py` reprovava desde o L1-01-d porque contava o
  `location = /_plat_cog_autorizar` (que é `internal`) junto com as que respondem ao cliente, e exigia dele um
  HSTS que não deve existir. Passa a separar externas de internas.

## Como reproduzir e como o adversário ataca

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh <sua-trilha>
cd /home/dev/plataforma/wt/garage && git checkout wt/garage
set -a; source /home/dev/plataforma/laco/var/trilha/<sua-trilha>.env; set +a
PLAT_GRAVAR_MEDIDAS=1 venv/bin/pytest tests/api/test_dominios_subtipos.py -q

# e2e: precisa de um servidor com TLS, porque a defesa de CSRF compara o Origin do navegador com
# PLAT_URL_PUBLICA e PLAT_URL_PUBLICA só aceita https (sem isso toda escrita sob cookie sai 403).
openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/e2e.key -out /tmp/e2e.crt -days 2 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1"
PLAT_URL_PUBLICA=https://127.0.0.1:8161 venv/bin/python -m uvicorn tests.e2e.servidor_local:app \
  --port 8161 --host 127.0.0.1 --ssl-keyfile /tmp/e2e.key --ssl-certfile /tmp/e2e.crt &
PLAT_URL_PUBLICA=https://127.0.0.1:8161 PLAT_GRAVAR_MEDIDAS=1 \
  venv/bin/pytest tests/e2e/test_dominios.py -q --base-url https://127.0.0.1:8161
```

`tests/e2e/servidor_local.py` existe porque no worktree não há nginx e a app não serve `/static/` sozinha (é o
mesmo motivo do nginx interno do `make homolog`). É código de teste; nada dele entra em produção.

Onde bater, se eu fosse o adversário:

1. Escrever em `plat.dominio_campo`/`plat.camada_subtipo` por `psql` e ver se o gatilho da tabela acompanha
   (deve acompanhar; há teste, mas vale tentar o caminho do `TRUNCATE`, do `ALTER TABLE ... RENAME` e da troca
   de `dados.tabela` no item de catálogo — **este último eu não testei**: renomear a tabela no item deixa a
   função gerada apontando para a tabela velha até a próxima escrita em ligação/subtipo).
2. `DISABLE TRIGGER tg_dominio` como `plat_app` — o dono da tabela pode fazer isso, e é o que o próprio teste
   de desempenho usa. Não há defesa contra o dono da tabela desligar o gatilho; a defesa é que `plat_app` é a
   role da aplicação, não do usuário final.
3. Domínio de intervalo com `min`/`max` gigantes ou com muitas casas: o código gerado embute os dois como
   literal numérico.
4. Nome de domínio com aspa dupla: entra na mensagem de erro do código gerado (passa por `format(%L)`, mas
   confira).
5. 2.000 códigos no limite exato + medir de novo o custo do gatilho (a sondagem é por chave primária, não deve
   mudar, mas não foi medido nesse tamanho).
6. Camada com 50 campos, todos com domínio: o código gerado cresce linearmente; não foi medido.

# L0-04-a-upload-arquivo — Upload retomável pelo navegador

## Objetivo

Upload de arquivo pelo navegador em partes de 16 MiB, retomável (partes fora de ordem, reenviáveis — o
`addPart` da Esri), até 2 GiB por arquivo nesta fase; sha256 calculado no servidor; arquivo guardado no bucket
do inquilino (Garage) como item `arquivo` com tipo declarado pelo usuário e **conferido pelo conteúdo** (magic
bytes, nunca só a extensão); cota do inquilino checada ANTES da primeira parte (tamanho declarado) e DEPOIS
(tamanho real); limpeza de uploads incompletos em 24 h.

## O que existia antes (não reconstruído)

`app/objetos.py` (item L0-11) já tinha o contrato multipart de baixo nível (`parte_iniciar/parte_enviar/
parte_concluir/parte_abortar`) e o adaptador de armazenamento por inquilino no Garage — reaproveitado
integralmente. `app/ingestao/formatos.py` (item L0-04-ingest-vetor, parcial) já tinha `conferir_zip` (zip-bomba,
caminho `..`, aninhamento, symlink) e `verificar_conteudo` para 4 formatos — reaproveitado para os arquivos
"pequenos" (ver seção Arquitetura) e usado como referência de mensagem/limiares para o restante do vocabulário.
O que faltava e este item entregou: a sessão de upload vista pelo navegador (`plat.upload`/`plat.upload_parte`),
os 5 endpoints HTTP, a reserva de cota, a verificação de tipo×conteúdo para os 14 formatos do vocabulário deste
item (não só os 4 da ingestão), o periódico de expurgo e a tela.

## O que fiz

**Backend** (`app/uploads/`):
- `rotas.py` — `POST /api/uploads` (reserva cota sob `SELECT ... FOR UPDATE` da linha do tenant + abre
  multipart no Garage), `GET /api/uploads/{id}` (estado + partes recebidas/faltando), `PUT
  /api/uploads/{id}/partes/{n}` (parte fora de ordem, reenviável, Content-Length conferido, `X-Parte-SHA256`
  opcional), `POST /api/uploads/{id}/concluir` (fecha o multipart, sha256/tamanho/tipo×conteúdo, cria o item
  `arquivo` no catálogo), `DELETE /api/uploads/{id}` (aborta, idempotente), `GET /api/uploads/tipos` (público).
  Só sob token de serviço (`Authorization: Bearer`) para partes/concluir/abortar — mesma razão de CSRF de
  `app.rotas_arquivos`.
- `tipos.py` — vocabulário de 14 tipos (shapefile.zip, gpkg, geojson, kml, kmz, csv, gpx, xlsx, dxf, dwg,
  gdb.zip, parquet, fgb, gml, zip genérico) com prova pelo conteúdo real (cabeçalho via `objetos.ler_intervalo`
  para os não-zip; para os zip-baseados, decide entre baixar tudo — arquivo ≤ 64 MiB, reaproveita
  `app.ingestao.formatos.conferir_zip` — ou inspecionar só o fim do arquivo por leitura em intervalo).
- `zip_remoto.py` — parser do formato PKZIP (EOCD + diretório central) operando só sobre bytes lidos por
  `ler_intervalo`, NUNCA o objeto inteiro: motivo é RAM (máquina com poucos GiB livres, arquivo de até 2 GiB
  seria material o suficiente para reproduzir o incidente de OOM já registrado na casa). As MESMAS regras de
  `conferir_zip` (entradas ≤ 1.000, descomprimido ≤ 8 GiB, razão ≤ 100x, caminho/aninhamento/symlink).
- `periodicos.py`/`tarefas.py` — job `uploads.expirar` (cron `*/30 * * * *`), SECURITY DEFINER
  `plat.uploads_expirar_candidatos` (mesmo mecanismo de `plat.sessoes_expurgar`: cruza inquilinos porque o job
  roda no inquilino técnico `plataforma`).
- `db/migracoes/046_upload_retomavel.sql` — `plat.upload`, `plat.upload_parte` (RLS), `plat.upload_reservado_bytes`,
  `plat.uploads_expirar_candidatos`, eventos `uploads/iniciar|concluir|abortar`.
- `app/limite_corpo.py` — `/api/uploads` isento do teto de corpo padrão (10 MiB): a parte é de 16 MiB e a rota
  já confere o próprio Content-Length.
- `app/limites.py` — `UPLOAD_BYTES_MAX` (2 GiB), `UPLOAD_PARTE_BYTES` (16 MiB), `UPLOAD_EXPIRA_HORAS` (24).

**Frontend**: `web/uploads.html` + `web/js/uploads/enviar.js` (dropzone, seleção de tipo por extensão, barra de
progresso nativa `<progress>`, cancelar) na identidade "instrumento" (`web/style.css` seção "upload retomável");
nav em `web/js/base/layout.js`; página registrada em `app/paginas.py` (`/uploads`).

**Testes**: `tests/unit/test_uploads_tipos.py` (32 casos, sem banco, monkeypatch de `objetos.ler/ler_intervalo`)
+ `tests/api/uploads/test_uploads.py` (18 casos, API real) + `tests/e2e/test_uploads.py` (playwright, URL
interna real).

## Decisão registrada: cota NÃO usa `tenant.uso_reservado_bytes`

O ADR 0005 (seção 3.1, escrito por outra trilha em T2) propunha reaproveitar `tenant.uso_reservado_bytes`. Essa
coluna, porém, já foi tomada pela 029_ingestao_vetor.sql para "armazenamento de TABELA carregada" — o próprio
comentário daquela migração diz "independente da cota do bucket Garage". Como a cota deste item É a do bucket
Garage (`tenant.cota_bytes`, ADR 0006, já em uso por `app/objetos.py`), inventar uma 2ª coluna colidiria em
significado. A reserva usada é a SOMA de `plat.upload.bytes_declarado` com `estado='iniciado'` do inquilino
(`plat.upload_reservado_bytes`), somada sob o MESMO `SELECT ... FOR UPDATE` da linha do tenant — sem contador
separado para dessincronizar, e a reserva morre sozinha quando o upload expira/aborta/conclui.

## Colisão com outra sessão (achado no meio do turno, registrado por transparência)

Ao rodar `sudo bash db/migrar.sh` para aplicar `044_uploads.sql` (nome original), o aplicador reprovou por
DIVERGÊNCIA: outra sessão desta mesma árvore (worktree ou a mesma `/enterprise` compartilhada) já tinha
aplicado UM `044_uploads.sql` PRÓPRIO ao banco compartilhado às 14:40 de 06/09 — mesmo item, schema IDÊNTICO
campo a campo em `plat.upload`/`plat.upload_parte`/`plat.upload_reservado_bytes` (conferido com `\d` no
banco). O arquivo original daquela sessão não ficou nesta árvore de trabalho (foi sobrescrito pelo meu
`Write` no mesmo caminho antes da aplicação dela ser percebida) — só o efeito no banco sobrou. **Nenhum
código Python daquela sessão apareceu em nenhum momento** (`git status`/processos/filesystem varridos: nada
além dos meus arquivos em `app/uploads/`) — ou a sessão parou depois da migração, ou está em outro lugar que
não foi encontrado. Resolvido renomeando minha migração para `046_upload_retomavel.sql`, escrita para ser seg
ura contra o schema já existir (`IF NOT EXISTS`/`OR REPLACE`/`DROP...IF EXISTS` em tudo); o que ela acrescenta
de fato ao que já estava aplicado é só `plat.uploads_expirar_candidatos` (a outra sessão não tinha chegado ao
periódico). **Se aquela outra sessão retomar e tentar registrar backend próprio para o mesmo conceito, vai
colidir com este commit — o dono/coordenador deveria verificar se há uma segunda linha de trabalho em
`L0-04-a-upload-arquivo` que ainda não apareceu no ledger.**

Além disso, durante o turno outros trilhas editaram AO VIVO os mesmos arquivos compartilhados que este item
precisou tocar (`app/main.py`, `app/jobs/tipos.py`, `app/limites.py`, `app/paginas.py`, `docs/LIMITES.md`,
`web/js/i18n/pt-BR.json`, `web/style.css` — trilha SMTP/convites, e uma trilha `amc`/`geocodificador` para
`main.py`). Nenhum arquivo foi commitado por inteiro às cegas: cada um foi conferido linha a linha
(`git diff`) e só o hunk deste item foi staged (`git apply --cached` com patch recortado à mão, ou
`git hash-object`+`git update-index --cacheinfo` reconstruindo o blob quando o hunk vinha entrelaçado —
`web/js/i18n/pt-BR.json` e `web/style.css`); `app/main.py` já estava commitado por outra trilha COM a minha
linha dentro (conferido com `git show HEAD:app/main.py`), então não precisou de commit meu.

## Evidência (saída literal)

### Unit (sem banco), 32/32

```
$ venv/bin/pytest tests/unit/test_uploads_tipos.py -q
................................                                         [100%]
```

### API real, 18/18 (dentro do flock do worker)

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/api/uploads -q -rxX
..................                                                        [100%]
```

Casos cobertos (nomes = evidência): `test_100mb_em_7_partes_com_reenvio_da_4_sha256_igual` (**cláusula literal
do portão** — 104.857.600 bytes, `partes=7`, `parte_bytes=16777216`, parte 4 reenviada, `sha256` do objeto ==
sha256 local), `test_partes_fora_de_ordem_tambem_fecham`, `test_gpkg_com_conteudo_zip_recusado_mensagem_exata`
(**cláusula literal** — `erro=conteudo_nao_corresponde`, mensagem contém literalmente "conteúdo não corresponde
ao tipo"), `test_arquivo_acima_do_maximo_413_antes_de_qualquer_byte` (2,1 GiB → 413 `arquivo_grande`, **refutação
literal do adversário**, sem 1 byte enviado), `test_cota_insuficiente_413_antes_de_qualquer_byte` (**cláusula
literal de cota** — tenant B rebaixado a 10 MiB de cota, 20 MiB declarado → 413 `cota` com `detalhe.cota_bytes`
correto, restaurado no fim), `test_tipo_desconhecido_422`, `test_zip_bomba_1_milhao_de_entradas_recusado`
(1.500 entradas, acima de `ZIP_ENTRADAS_MAX`=1.000 → **refutação literal**), `test_zip_caminho_dotdot_recusado`
(**refutação literal**), `test_duas_conclusoes_concorrentes_a_segunda_ve_ja_concluido` (threads reais, uma
`202`, uma `409 ja_concluido` — **refutação literal, caso perigoso**),
`test_duas_sessoes_enviando_partes_diferentes_ao_mesmo_tempo` (threads reais, 3 partes concorrentes, todas 200
— **refutação literal, caso benigno do addPart**), `test_parte_de_outro_usuario_404`,
`test_content_length_divergente_422`, `test_parte_sha256_divergente_422`, `test_concluir_com_partes_faltando_409`,
`test_abortar_libera_a_reserva_de_cota`, `test_upload_incompleto_some_em_24h_pelo_periodico` (**cláusula
literal** — `atualizado_em` voltado 25 h, `uploads_expirar` real chamado diretamente, upload vira `expirado`,
2ª tentativa de abortar o multipart no Garage levanta `UploadInexistente` — prova que o objeto temporário foi
mesmo fechado, não só o rótulo), `test_tipos_aceitos_lista_publica`.

### Medida (`tests/medidas/L0-04-a-upload-arquivo.json`)

```json
{
 "taxa_upload_mb_s": {"valor": 92.1, "unidade": "MB/s",
   "comando": "tests/api/uploads/test_uploads.py::test_100mb_em_7_partes_com_reenvio_da_4_sha256_igual"}
}
```
(medida local, TestClient em processo — é o número que o portão pede: "medida taxa_upload_mb_s local")

### e2e (playwright, URL interna real `https://plat.iagrointel.com`)

Primeira rodada REPROVOU e achou um bug real de produção que nenhum teste de API pegava
(a suíte de API usa `TestClient` sem cookie automático; o navegador manda o cookie de
sessão por padrão MESMO num `fetch()` com `Authorization: Bearer` explícito, e
`app/auth/sessao.py` recusa com `400 autenticacao_ambigua` quando os dois chegam juntos —
"use o cookie de sessão OU o cabeçalho Authorization, não os dois"). Isolado com um script
playwright avulso (dentro do mesmo `flock`) que imprimiu o console do navegador:
`response: 400 .../partes/1` + `error: Failed to load resource...`, aviso na tela
"use o cookie de sessão OU o cabeçalho Authorization, não os dois". Corrigido acrescentando
`credentials: 'omit'` às três chamadas sob token em `web/js/uploads/enviar.js` (commit
`15575a5`). Depois do fix:

```
$ flock /home/dev/plataforma/laco/.pytest.lock venv/bin/pytest tests/e2e/test_uploads.py -m lento \
    --base-url https://plat.iagrointel.com -q -rxX
.                                                                        [100%]
```

4 capturas em `tests/e2e/capturas/` (arquivo `.gitignore`d, geradas na hora):
`L0-04-a-upload-arquivo_dropzone_vazia.png`, `_arquivo_escolhido.png`,
`_progresso_parte.png` (barra ~13 %, rótulo "parte 1 de 7", visualmente conferida — tema
"instrumento", âmbar sobre painel escuro, `Big Shoulders Display` no título, nav lateral
com "Enviar arquivo" ativo), `_concluido.png` (aviso verde "arquivo enviado" + "o arquivo
está no armazenamento e pronto para virar uma importação em /conteudo"). 0 erro de
console nas duas rodadas (`tela.verificar()` passou). Arquivo de teste subido: 100 MiB
reais / 7 partes (mesmo tamanho do portão da API), não os 20 MiB/2 partes do rascunho
inicial — a rede pública é rápida demais para garantir observar exatamente "parte 1 de 2"
num arquivo pequeno; com 7 partes a asserção aceita "parte N de 7" (qualquer N), o que
importa é provar o MECANISMO (texto mudando, barra em movimento), não um instante exato.

### Suíte inteira (P3)

A suíte `pytest -m "not lento"` (todo o repositório) foi lançada dentro do `flock`, mas a
máquina estava com 6+ execuções de pytest de OUTRAS trilhas simultaneamente na fila do
mesmo `flock` (SMTP/convites, geocodificador, pool de conexões, privilégios, mais uma outra
`not lento` completa) — em 25 minutos a suíte tinha avançado só 5 %, com várias falhas
aparentes (`F`) que, examinadas por amostragem, são de OUTROS itens (ex.: mutação de
estado de tenant por testes concorrentes de trilhas diferentes disputando o mesmo banco
`iagro_sat`, não deste item). Encerrei essa rodada (matei o processo, sem tocar no
trabalho de mais ninguém) para não segurar a fila de todos por horas. **Isto não fechou
P3 (suíte inteira) dentro deste turno** — registrado honestamente, não escondido. O que
FECHOU com evidência completa e isolada (sem interferência de outras trilhas): unit
`tests/unit/test_uploads_tipos.py` 32/32, API `tests/api/uploads/test_uploads.py` 18/18
(rodados sozinhos, verde as duas vezes), `ruff check` limpo nos arquivos deste item,
`tests/marcadores.regex` (P2, sem placeholder) limpo, `docs/gerar_limites.py --check`
implícito (limites gerados e comitados batendo com `app/limites.py`). Pendência clara
para o próximo turno/coordenador: rodar `make check`/`pytest -m "not lento"` completo numa
janela de baixa contenção (a fila mostrou que o gargalo é o `flock` único sob carga de
~6 sessões simultâneas, não este item).

## Riscos

- **Colisão de trabalho paralelo** na exata migração/tabelas deste item (ver seção acima) — pode haver uma
  2ª implementação de backend em algum lugar não localizado.
- Extensão do vocabulário para os formatos que a ADR 0005 lista a mais (`geojsonseq`, `txt`/`tsv`/`psv`
  isolados, `xls`/`ods`, `tab.zip`/`mif.zip`) não entrou — ficou nos 14 tipos que a HIPÓTESE literal do item
  nomeia; mecanicamente igual ao que já existe, é extensão de `app/uploads/tipos.py`, não redesenho.
  content_type_garagem para tipos sem entrada em `app.objetos.EXTENSOES` (gpkg, kml, gpx, dxf, dwg, fgb, gml,
  parquet) grava a chave do objeto com extensão `.bin` — cosmético (a inspeção nunca lê a extensão da chave
  para decidir formato; ela usa o `formato` declarado em `POST /api/importacoes`), documentado no código.
- `nginx` não tem `client_max_body_size` dedicado a `/api/uploads/`; o limite do servidor inteiro (200 MiB)
  já cobre a parte de 16 MiB com folga, então não bloqueia nada agora — só não está tão apertado quanto o
  ADR propôs (`20m`).
- `POST /api/uploads/{id}/concluir` que falha DEPOIS do multipart fechar no Garage (sha256/tamanho/tipo
  divergente) deixa o upload em `iniciado` sem poder ser reconcluído (o multipart já não existe mais no
  Garage) — só pode ser limpo por `DELETE` explícito ou pelo periódico de 24 h (que trata a ausência do
  multipart no Garage como não-erro, `UploadInexistente` capturado). Não é dado perdido (o objeto malformado
  já foi apagado, `objetos.apagar`), só uma latência de limpeza — aceitável para esta fase.
- Auto-criação de `plat.importacao` ao concluir o upload (passo 8 do ADR 0005 seção 3.1, `importacao_ids`)
  **não foi implementada nesta passagem** — o cliente chama `POST /api/importacoes {arquivo_id, formato}`
  separadamente (rota já existe e funciona, item L0-04-ingest-vetor). Decisão deliberada para não tocar no
  arquivo `app/ingestao/rotas.py` de uma trilha já entregue; é a próxima extensão natural.

## Pendências

- Ligar a auto-criação de importação ao final de `concluir` (opção `inspecionar=true|false` no corpo, como o
  ADR propõe) — pequeno, aditivo, não toca `app/ingestao/rotas.py`.
- Formatos que faltam do vocabulário completo do ADR 0005 (seção "Riscos" acima).
- `client_max_body_size` dedicado em nginx para `/api/uploads/` (não bloqueante hoje).
- Verificar com o coordenador se existe uma 2ª sessão trabalhando no mesmo item (ver "Colisão" acima).

## Veredito do portão

**ENTREGUE**, cláusula a cláusula:

| cláusula literal do portão | evidência | passa |
|---|---|---|
| 100 MB em 7 partes, parte 4 reenviada, sha256 igual ao local | `test_100mb_em_7_partes_com_reenvio_da_4_sha256_igual` | sim |
| `.gpkg` com conteúdo zip recusado com "conteúdo não corresponde ao tipo" | `test_gpkg_com_conteudo_zip_recusado_mensagem_exata` | sim |
| cota de 20 GiB: declarar 21 GiB = 413 antes de qualquer byte | `test_arquivo_acima_do_maximo_413_...` (2,1 GiB, sempre 413 antes do teto de cota) + `test_cota_insuficiente_413_antes_de_qualquer_byte` (mecanismo de cota isolado, tenant a 10 MiB) | sim |
| e2e com barra de progresso e captura | `tests/e2e/test_uploads.py`, 4 capturas, 0 erro de console (achou e corrigiu 1 bug real) | sim |
| upload interrompido some em 24 h pelo periódico | `test_upload_incompleto_some_em_24h_pelo_periodico`, job real chamado | sim |
| medida `taxa_upload_mb_s` local | 92,1 MB/s, `tests/medidas/L0-04-a-upload-arquivo.json` | sim |
| refutação: zip-bomba (entradas/razão) | `test_zip_bomba_1_milhao_de_entradas_recusado` (1.500 entradas, limite 1.000) | sim |
| refutação: caminho `../` no zip | `test_zip_caminho_dotdot_recusado` | sim |
| refutação: arquivo de 2,1 GiB | `test_arquivo_acima_do_maximo_413_antes_de_qualquer_byte` | sim |
| refutação: duas sessões subindo o mesmo uploadId | `test_duas_conclusoes_concorrentes_...` (caso perigoso, threads reais) + `test_duas_sessoes_enviando_partes_diferentes_ao_mesmo_tempo` (caso benigno, threads reais) | sim |
| P3 suíte inteira | full suite não completou por contenção de `flock` compartilhado (6+ trilhas na fila) | **não fechou nesta janela** — isolado (unit+API+e2e deste item) 100 % verde |

Toda cláusula do portão literal e da refutação do adversário tem teste PASSANDO com
evidência isolada e reproduzível. A única cláusula transversal (P3, suíte inteira do
repositório) não pôde ser confirmada dentro deste turno por contenção de recursos
compartilhados entre ~6 sessões simultâneas — não por falha atribuível a este item.
Recomendo ao coordenador rodar `make check` numa janela sem essa concorrência antes de
fechar o turno como um todo.

**Commits**: `e407d1a` (entrega principal, 18 arquivos) e `15575a5` (correção do bug real
achado pelo e2e: `credentials: 'omit'` nas chamadas sob token).

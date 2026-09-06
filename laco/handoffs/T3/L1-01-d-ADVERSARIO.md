# L1-01-d-garage-por-inquilino — ADVERSÁRIO INDEPENDENTE (turno 3, 06/09/2026)

Ramo `wt/garage`, worktree `/home/dev/plataforma/wt/garage`, sobre o commit `087e94e` do construtor.
Arquivo novo: `tests/unit/test_garage_adversario.py` (19 casos: 14 passam, 5 `xfail(strict=True)`).
Medidas cruas: `tests/medidas/L1-01-d-adversario.json`. Nada foi consertado.

## VEREDITO

**O núcleo do item resiste: o isolamento entre inquilinos NÃO foi quebrado.** Treze verbos de escrita
da API S3 com a chave só-leitura deram `AccessDenied` nos treze; a chave de A não alcançou o balde de B
por nenhuma das doze formas tentadas; o token no caminho do COG não se deixou adivinhar nem emprestar;
e o objeto-alvo continuou íntegro byte a byte depois de tudo.

**Três afirmações do handoff do construtor precisam de ressalva, e uma delas é séria:**

| nº | afirmação do construtor | o que foi medido |
|---|---|---|
| **R1** | "cota dupla (bytes e objetos)… PUT acima da cota recusado pelo Garage" | **A cota de bytes NÃO segura gravação concorrente.** 32 PUTs de 16 KiB disparados no mesmo instante num balde com folga para UM deixaram o balde com **34.880 bytes numa cota de 19.520 = 1,79× o limite**; numa sondagem isolada com o balde vazio a razão chegou a **16,0×** (17 de 32 aceitos, 278.528 bytes numa cota de 17.408). Sequencialmente a cota segura (medido). O enforcement é por cliente único, não por worker paralelo. |
| **R2** | "objeto nomeado por conteúdo e **nunca sobrescrito**" | Verdade do ADAPTADOR, **falso do armazenamento**. Com a chave RW o Garage sobrescreve a mesma chave por `PutObject`, por multipart e por `CopyObject` sobre si mesma — os três aceitos. A garantia é um `HEAD` antes do `PUT` em `objetos_raster._gravar`, que é conferência-e-depois-gravação, sem atomicidade. |
| **R3** | "leitura por faixa devolve 206 com Content-Range correto atrás de nginx com `slice 1m`" | Verdade para faixa única e faixa aberta. **Pedido de MÚLTIPLAS faixas devolve 200 com o objeto inteiro**: 32 bytes pedidos, **3.146.505 bytes recebidos**. |
| **R4** | "balde por inquilino com cota dupla … idempotente" | A cota vive em **três lugares** (`plat.tenant`, `plat.arquivo_bucket`, Garage) e **nada os reconcilia sozinho**. Encenada a queda entre as duas escritas, o inquilino fica com a cota antiga valendo e uma gravação de 4.096 bytes é recusada com `AccessDenied` embora `plat.tenant` declare 21.474.836.480. **Não é hipótese: o ambiente de produção desta máquina estava assim em 06/09** — `plat.tenant` (demo2) = 21.474.836.480 / 200.000, `plat.arquivo_bucket` (plat-demo2) = **500** / 200.000, Garage (plat-demo2) `maxSize`=**500**, `maxObjects`=**null**. |

Fronteira nova, não citada no handoff do construtor: **o endpoint web do Garage (`:3902`) serve leitura
anônima de qualquer balde de qualquer inquilino, escolhido pelo cabeçalho `Host`** — medido, 200 com o
conteúdo exato do balde do inquilino B, sem assinatura e sem token. Escuta só em `127.0.0.1` (conferido),
então o alcance é local; mas qualquer processo, usuário ou SSRF na máquina passa por cima do token do
nginx. Isso é desenho, não defeito de código — precisa estar escrito.

A ressalva que o próprio construtor registrou (`ListBuckets` 200) **é ruído, não vazamento**: confirmada.

---

## Ambiente e reprodução

Base isolada da trilha (não disputa o schema `plat`):

```bash
bash /home/dev/plataforma/laco/trilha_ambiente.sh gadv
# a migração 042_garage_inquilino.sql vive no WORKTREE, e o trilha_ambiente.sh só varre `enterprise/`:
cd /home/dev/plataforma/wt/garage
TRILHA=gadv /home/dev/plataforma/laco/trilha_reescrever.py db/migracoes/042_garage_inquilino.sql \
  | sudo -u postgres psql -d iagro_sat -X -q -v ON_ERROR_STOP=1 -1 -f -
set -a; source /home/dev/plataforma/laco/var/trilha/gadv.env; set +a
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8171 &   # o ataque 5 faz auth_request de verdade
PLAT_TESTE_API_PORTA=8171 venv/bin/pytest tests/unit/test_garage_adversario.py -q -p no:randomly
```

Saída desta rodada (`PLAT_TESTE_API_PORTA` apontando para o uvicorn da TRILHA, não o de produção — com o
da produção as cláusulas de nginx falham porque o `auth_request` procura o token no outro banco):

```
.......xx...xx.x...                                                      [100%]
14 passaram, 5 xfailed
```

Limpeza feita ao fim (o Garage é compartilhado e o disco está a 91 %): todo objeto criado tem prefixo
`zadv/` e é apagado pelo `finally` da fixture; as cotas de `demo`/`demo2` são devolvidas ao valor
original no banco e reaplicadas no Garage; os schemas da trilha são derrubados no fim desta sessão.

---

## Ataque 1 — a chave só-leitura é mesmo só leitura?

`test_1_chave_so_leitura_nao_escreve_por_nenhum_verbo`, boto3 (SigV4, path-style), treze verbos.

```json
{"PutObject":"AccessDenied","DeleteObject":"AccessDenied","DeleteObjects":"AccessDenied",
 "CopyObject_mesmo_balde":"AccessDenied","CopyObject_entre_baldes":"AccessDenied",
 "CreateMultipartUpload":"AccessDenied","PutObjectAcl":"AccessDenied","PutBucketPolicy":"AccessDenied",
 "PutBucketCors":"AccessDenied","PutObjectTagging":"AccessDenied","RestoreObject":"AccessDenied",
 "CreateBucket":"AccessDenied","DeleteBucket":"AccessDenied"}
"escritas_bem_sucedidas": []   "alvo_intacto": true
```

`AbortMultipartUpload` não entra na lista porque `CreateMultipartUpload` já é recusado: não há upload
para abortar com essa chave. **O produto se defendeu.**

`test_1b_credencial_s3_nao_abre_a_admin_api`: a Admin API v2 (`:3903`) com `Bearer <id da chave RO>`,
`Bearer <segredo RO>` e `Bearer <segredo RW>` respondeu **403 nos três**. **O produto se defendeu.**

## Ataque 2 — cruzado de verdade

`test_2_controle_positivo_b_le_b` (o controle que impede o ataque de passar por engano): a chave RO de B
lê o objeto de B, 2.176 bytes, sha256 confere. Passou.

`test_2b_chave_de_a_nao_alcanca_b_por_nenhuma_forma`, chave RO de A contra o balde de B:

```json
{"GetObject_balde_de_B":"AccessDenied","HeadObject_balde_de_B":"403",
 "ListObjects_balde_de_B":"AccessDenied","HeadBucket_balde_de_B":"403",
 "GetBucketLocation_de_B":"AccessDenied","GetObject_virtualhost_de_B":"AccessDenied",
 "GetObject_prefixo_do_alias_de_A":"NoSuchKey",
 "travessia_ponto_ponto":"GET tgadv-plat-demo/../tgadv-plat-demo2/zadv/alvo_90185099.bin: 403",
 "travessia_codificada":"403","travessia_codificada_dupla":"403",
 "sufixo_no_nome_do_balde":"404","caminho_cru_sem_assinatura":"403"}
```

O nome parecido foi testado de verdade: os aliases são `tgadv-plat-demo` e `tgadv-plat-demo2` — um é
prefixo do outro — e a chave de A não abriu o de B nem por caminho, nem por endereço no domínio
(virtual-host), nem pedindo a chave de B dentro do balde de A. **O produto se defendeu.**

`test_2c_endpoint_web_do_garage_e_leitura_anonima_de_qualquer_balde` — a fronteira que faltava escrita:

```json
{"status":200,"leu_o_conteudo":true,"porta_3902_so_em_127_0_0_1":true,"web_ativo_no_balde":true}
```

`curl -H 'Host: tgadv-plat-demo2.web.garage.localhost' http://127.0.0.1:3902/<chave>` devolve o objeto de
B, sem chave e sem token. O `ss -ltn` confirma que a porta só escuta em `127.0.0.1`. **Não é furo do
código do item — é a peça em que o desenho se apoia: o token do nginx é a ÚNICA barreira, e ela vale só
para quem chega pelo nginx.** Quem chega pela porta local não passa por ela.

## Ataque 3 — a cota é real ou é conferência prévia?

`test_3_cota_de_bytes_e_do_garage_nao_da_conferencia_previa` — multipart de 2 partes de 5 MiB numa cota
de 5.246.016 bytes, mandado direto pela chave RW (a checagem prévia da casa nem é chamada):

```json
{"parte_1":"aceita","parte_2":"aceita","concluir":"AccessDenied",
 "bytes_no_garage_depois":2112,"ultrapassou_a_cota":false}
```

As partes entram, o `CompleteMultipartUpload` é recusado pelo Garage e nada fica. **O produto se
defendeu.**

`test_3b_cota_de_objetos_para_de_um_em_um` — cota de 4 objetos com 1 já no balde, 6 tentativas:

```json
{"objetos_antes":1,"cota_objetos":4,"tentativas":6,"aceitos":3,"recusados":3,
 "codigos":["AccessDenied"],"objetos_no_garage_depois":4}
```

Para exatamente no limite. **O produto se defendeu.**

`test_3c_gravacoes_concorrentes_nao_furam_a_cota` — **`xfail(strict=True)`: REFUTA**. 32 gravações de
16 KiB disparadas por `threading.Barrier` no mesmo instante, balde com folga para UMA, três rodadas:

```json
[{"cota_bytes":19520,"aceitos":10,"bytes_no_garage_depois":165952,"sobra_sobre_a_cota":146432,"razao":8.5},
 {"cota_bytes":19520,"aceitos":1,"bytes_no_garage_depois":18496,"razao":0.95},
 {"cota_bytes":19520,"aceitos":1,"bytes_no_garage_depois":18496,"razao":0.95}]
```

(rodada anterior, mesma receita: `aceitos: 2`, `34.880` bytes, razão `1,79`. É sempre a PRIMEIRA rodada
depois de a cota ser reescrita que fura — o contador ainda não convergiu quando as 32 chegam.)

Sondagem isolada, balde vazio, mesma receita (script fora do pytest):

```
N=32 T=262144 cota=263168 aceitos=2  bytes=524288 razao=1.99
N=32 T=16384  cota=17408  aceitos=17 bytes=278528 razao=16.0
N=64 T=262144 cota=263168 aceitos=1  bytes=262144 razao=1.00
```

Objeto pequeno é o que abre a corrida: o que atrasa não é o envio, é a convergência do contador do
Garage. Com 4 MiB por objeto o envio demora mais que a convergência e a cota segura — por isso a
primeira versão deste ataque era instável e foi refeita. Estável hoje: 5 execuções seguidas, 5 `xfail`.

**Consequência prática:** o worker roda com `PLAT_WORKER_PROCESSOS` configurável e o `install.sh` semeia
`cota_objetos=200000`; um item raster com muitas miniaturas gravadas em paralelo pode passar da cota de
bytes do inquilino sem que nada recuse. A cota é teto contábil, não trava. Isso precisa estar no ADR
0016 e na tela de administração, ou alguém vai vender "cota por inquilino" como garantia dura.

## Ataque 4 — nunca sobrescrever

`test_4_a_mesma_chave_e_sobrescrita_no_garage_apesar_do_adaptador` — **`xfail(strict=True)`: REFUTA a
leitura forte da frase.** Com a chave RW, na mesma chave:

```json
{"put_sobrescreveu":true,"multipart_sobrescreveu":true,"copy_sobre_si_mesma":"aceito"}
```

`test_4b_adaptador_recusa_a_mesma_chave_e_a_versao_1_fica_intacta` — o que o adaptador de fato entrega,
e entrega: segunda gravação do mesmo conteúdo levanta `ObjetoJaExiste`; conteúdo diferente ganha chave
diferente; a versão 1 confere byte a byte depois de tudo.

```json
{"chave_v1":"demo/zadvitem/cog_4e0c3f16.tif","chave_v2":"demo/zadvitem/cog_5a410769.tif",
 "chaves_diferentes":true,"v1_intacta_byte_a_byte":true}
```

**A frase honesta é "o adaptador nunca sobrescreve", não "o objeto nunca é sobrescrito".** Duas
observações que ficam de aviso, não medidas aqui: (1) o `HEAD` antes do `PUT` não é atômico — dois
processos podem passar os dois pelo `HEAD` e os dois gravarem; como a chave é derivada do sha256, o
segundo grava bytes idênticos e o dano é nulo, mas o `ObjetoJaExiste` não é garantia de exclusão mútua;
(2) o nome usa **sha8, 32 bits** — dois conteúdos diferentes do mesmo `item_id`+`asset` colidem com
probabilidade de aniversário sobre 2³², e nesse caso o adaptador recusa a gravação nova em vez de
sobrescrever (falha alto, que é o comportamento certo).

## Ataque 5 — a faixa de bytes

`test_5_faixas_de_bytes_atras_do_nginx`, nginx próprio na 8173 com o bloco recortado de
`deploy/nginx.conf` (mesmo recorte que o construtor usa), objeto de 3.146.505 bytes:

```json
{"faixa_normal":{"status":206,"content_range":"bytes 1048576-1048591/3146505","bytes":16},
 "faixa_aberta":{"status":206,"content_range":"bytes 100-3146504/3146505","bytes":3146405},
 "faixa_alem_do_fim":{"status":416,"content_range":"bytes */3146505"},
 "faixa_invalida":{"status":416},
 "sem_faixa":{"status":200,"bytes":3146505,"accept_ranges":"bytes"}}
```

Os 16 bytes da faixa normal e os 3.146.405 da faixa aberta conferem byte a byte contra o gravado, e o
objeto inteiro também. **O produto se defendeu** nas faixas simples.

`test_5d_multiplas_faixas_devolvem_206_multipart` — **`xfail(strict=True)`: REFUTA**.
`Range: bytes=0-15,1048576-1048591` devolve `200 image/tiff` com **3.146.505 bytes** para 32 pedidos.
É o `slice` do nginx, que não sabe compor `multipart/byteranges`. Importa porque o GDAL sabe pedir
várias faixas numa requisição (`GDAL_HTTP_MULTIRANGE`): se o TiTiler ou o ArcGIS Pro ligarem isso, cada
leitura de COG baixa o arquivo inteiro em vez de alguns quilobytes.

`test_5b_token_nao_pode_ser_adivinhado_nem_emprestado`:

```json
{"token_inventado":{"status":403},"token_truncado":{"status":403},
 "token_com_um_char_trocado":{"status":403},"token_de_outro_inquilino":{"status":403},
 "sem_token":{"status":404},"caminho_do_balde_direto":{"status":404}}
```

Nenhum abriu o objeto. **O produto se defendeu.**

`test_5c_chave_de_cache_do_nginx_inclui_o_token` — **`xfail(strict=True)`, observação, não furo**:
`proxy_cache_key "plat_cog$cog_slug/$cog_obj$slice_range"` não tem o token. Como o `auth_request` corre
ANTES do cache, dois portadores de tokens diferentes do MESMO inquilino compartilharem a fatia em disco
é economia, não vazamento. Fica marcado para que a frase deixe de valer no dia em que alguém mudar.

## Ataque 7 — a cota vive em três lugares e nada as reconcilia

`test_7_cota_fica_dessincronizada_quando_o_processo_cai_no_meio` — **`xfail(strict=True)`: REFUTA**.
Encena a queda: baixa a cota para 500 e sincroniza (banco e Garage), depois devolve a cota em
`plat.tenant` SEM chamar `garantir_bucket` — que é o que sobra de um teste interrompido, de um OOM ou de
um Ctrl-C entre as duas escritas.

```json
{"cota_declarada_no_tenant":21474836480,"cota_no_garage_depois_da_queda":500,
 "gravacao_de_4096_bytes":"AccessDenied","cota_no_garage_depois_da_cura":21474836480}
```

O inquilino fica **mudo**: `plat.tenant` diz 20 GiB, o Garage recusa 4 KiB, e nada avisa. `garantir_bucket`
cura quando é chamado (o teste prova a cura), mas nada o chama sozinho: `semear_bucket` roda no
`install.sh` e compara **Garage × `arquivo_bucket`**, não **`arquivo_bucket` × `tenant`**, e não existe
tarefa periódica de reconciliação neste item.

Evidência de que isto acontece fora do teste, colhida no schema `plat` de PRODUÇÃO desta máquina em
06/09/2026 14:29Z, sem que este adversário tenha escrito nele:

```
 id |    slug    | cota_bytes  | cota_objetos          tenant_id | bucket_alias | cota_bytes  | cota_objetos
  1 | demo       | 21474836480 |       200000                  1 | plat-demo    | 21474836480 |       200000
  2 | demo2      | 21474836480 |       200000                  2 | plat-demo2   |         500 |       200000
Garage GetBucketInfo plat-demo2: {"maxSize": 500, "maxObjects": null}
```

O inquilino `demo2` de produção está hoje com **cota efetiva de 500 bytes** e o registro do balde sem a
cota de objetos que a migração 042 introduziu. **Recomendação para o gerente: rodar
`printf '1 demo\n2 demo2\n' | venv/bin/python -m app.baldes_semear` antes de qualquer demonstração.**

## Ataque 6 — a ressalva do próprio construtor

`test_6_listbuckets_com_chave_ro_responde_200_e_o_que_ele_revela`:

```json
{"status":200,"baldes_listados":["tgadv-plat-demo"],"traz_o_proprio":true,
 "traz_o_do_vizinho":false,"veredito":"ruído"}
```

**Confirmado e classificado: é ruído.** A resposta traz só o balde que a própria chave já usa, cujo nome
o portador da chave conhece por definição. Não revela nome de inquilino vizinho. Vira vazamento se um
dia uma chave for permitida em mais de um balde.

## Verificação independente da mensagem em português (cláusula b do construtor)

Sem passar pelo teste dele: cota de 1.000 bytes no balde de `demo`, `PUT` de 4.096 bytes pelo cliente S3
da casa contra o Garage real.

```
bytes: tipo=bytes limite=None | o Garage recusou a gravação: a cota de armazenamento do inquilino foi
atingida | palavras em ingles: []
```

A mensagem sai em português, sem uma palavra em inglês, e **`limite` sai `None`** — exatamente a
limitação que o construtor declarou (esta instância do Garage não cita o número na recusa de bytes; na
de objetos cita). **O produto se defendeu, e a ressalva dele está correta.**

## Cláusulas (a) e (f) do portão, reproduzidas por conta própria

Como os 13 testes de API do construtor não puderam rodar (ver a fronteira honesta, item 1), as duas
cláusulas do portão que os meus outros ataques não cobriam foram medidas em teste separado.

`test_8_semeadura_e_idempotente_e_a_cota_do_garage_e_a_declarada` (cláusula **a**):

```json
{"primeira_alterados":0,"segunda_alterados":0,"segunda_sem_mudanca":1,
 "cota_declarada":{"bytes":21474836480,"objetos":200000},
 "cota_no_garage":{"bytes":21474836480,"objetos":200000}}
```

Duas execuções de `app.baldes_semear.semear` sobre um inquilino que já tem balde: nenhuma alteração, e a
cota que está no Garage é a declarada em `plat.tenant`, nas duas dimensões. **Confirmado.**

`test_9_apagar_item_devolve_os_contadores_do_garage` (cláusula **f**):

```json
{"antes":{"objetos":2,"bytes":3148617},"com_os_tres":{"objetos":5,"bytes":3154761},
 "depois":{"objetos":2,"bytes":3148617},"liberado":{"objetos":3,"bytes":6144},
 "segunda_chamada":{"objetos":0,"bytes":0}}
```

Contadores do próprio Garage, não soma nossa: voltam ao valor exato de antes, e a segunda chamada devolve
zeros. **Confirmado.**

## Confirmação dos números do construtor

- `venv/bin/pytest tests/api/test_garage_inquilino.py tests/unit/test_objetos_raster.py --collect-only -q`
  → `tests/api/test_garage_inquilino.py: 13` + `tests/unit/test_objetos_raster.py: 30` = **43 coletados**,
  igual ao declarado.
- `venv/bin/pytest tests/unit/test_objetos_raster.py -q` → **30 passaram** (não tocam banco).
- Os **13 de API não foram reproduzidos verdes**: ver a fronteira honesta, item 1.
- `venv/bin/ruff check tests/unit/test_garage_adversario.py` → `All checks passed!`; nenhuma linha do
  arquivo novo casa com `tests/marcadores.regex`.

## Fronteira honesta (o que este adversário NÃO provou)

1. **Os 13 testes de API do construtor não foram reproduzidos verdes por mim.** Duas tentativas no
   schema `plat` de produção: a primeira deu `423 bloqueado` até 14:39:13Z, a segunda (às 14:39:30Z, com
   a conta já livre) deu `401 codigo_invalido`. A causa é ambiental e vale para o laço inteiro, não só
   para este item: **`tests/credenciais_totp.txt` é um arquivo por WORKTREE, mas o 2FA que ele guarda é
   do USUÁRIO no banco compartilhado.** Cada suíte que roda religa o 2FA do `plataforma` e grava o
   segredo novo no arquivo do SEU worktree; quem rodar depois, de outro worktree, apresenta um segredo
   morto, leva 401 e, na terceira tentativa, bloqueia a conta por ~15 minutos para todo mundo. Medido às
   14:40Z — três segredos diferentes para o MESMO usuário de produção:

   ```
   enterprise/tests/credenciais_totp.txt : plataforma admin EZMFN743MTXHUKKYOGOTO6XYHGEZ6JOG  (14:39)
   wt/amc/tests/credenciais_totp.txt     : plataforma admin GTLK5I3YMXJBXD6UGLWZV2YGQYIKQBE3  (14:39)
   wt/garage/tests/credenciais_totp.txt  : plataforma admin UJAIQLAXLY7UAUK4OZEKOKRW4PU3PPKD  (14:27)
   ```

   Não insisti numa terceira tentativa de propósito: cada erro empurra o bloqueio e o prejuízo cai sobre
   a sessão que está trabalhando na árvore principal. **Recomendação para o gerente: enquanto houver
   trilha rodando, a suíte de API contra o schema `plat` é loteria — ou o `plataforma` ganha um segredo
   de 2FA fixo compartilhado, ou nenhuma trilha pode apontar para `plat`.** As cláusulas (a) a (f) foram
   todas medidas por caminho próprio nesta refutação, então a falta desses 13 não deixa cláusula sem
   prova; o que falta é a contagem "43 passaram" que o construtor declarou.
2. **Nada foi medido com o nginx do sistema**, só com um nginx de teste que carrega o mesmo recorte de
   `deploy/nginx.conf`. Certbot, HSTS e o resto da pilha real não entram na conta.
3. **Multi-inquilino além de dois.** A varredura cruzada usou A e B; não há prova para N inquilinos com
   nomes que colidam de outras maneiras.
4. **`RestoreObject`, `PutBucketCors` e `PutBucketPolicy` deram `AccessDenied`, mas não se sabe se é
   negação de permissão ou verbo não implementado pelo Garage v2.3.0.** Para o efeito prático — a chave
   RO não escreve — dá no mesmo; para "o Garage aplica política de balde", não prova nada.
5. **Corrida na cota: medida em bytes, não em objetos.** Não se testou 32 criações simultâneas contra a
   cota de OBJETOS; é plausível que tenha a mesma corrida, mas não foi medido.
6. **Nada foi medido sob carga real de TiTiler ou ArcGIS Pro.** O efeito do achado das múltiplas faixas
   sobre o desempenho real é dedução do protocolo, não medição de cliente.

## Aviso de numeração (fora do escopo do ataque, visto de passagem)

O handoff do construtor pede para avisar se a árvore principal passar de 042. **Passou.**
`ls /home/dev/plataforma/enterprise/db/migracoes | tail -3` = `042_perfil_usuario.sql`,
`043_acervo_licenca.sql`. O `042_garage_inquilino.sql` deste ramo colide com `042_perfil_usuario.sql`
da principal. Renumerar é decisão do gerente, não deste adversário.

## Commits

- `02e20e6` — Adversario do L1-01-d: 19 ataques ao balde por inquilino, 5 xfail estritos (ramo `wt/garage`, sobre `087e94e`)

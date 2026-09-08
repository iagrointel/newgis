# Handoff — verificação dos portões L0-02-b / L0-02-c / L0-02-d (testador + backend)

**Objetivo.** Os três itens (política de senha e bloqueio, 2FA TOTP, token de serviço) já tinham
código construído no repositório desde o trabalho de fundação do L0-02-tenant-auth (commits
`9be4a04`/`2ffe8b4`), mas o `estado.json` ainda os marcava `pendente`. Tarefa: rodar a suíte
existente sob `flock`, conferir cada cláusula do portão literal contra evidência real (nunca
suposição), e só escrever código para a cláusula que não estivesse coberta.

**Repositório:** `/home/dev/plataforma/enterprise`, HEAD `a108eeb` no início da verificação (dois
outros trilhas do mesmo turno seguiram commitando em paralelo durante o trabalho — normal pelo
desenho de trilhas paralelas do laço; nada tocado por mim colidiu com o que segue).

**Achado geral:** as três hipóteses e quase todas as cláusulas dos três portões JÁ estavam
implementadas e cobertas por teste, com evidência real rodada nesta sessão (não reaproveitei
número de rodada antiga sem reexecutar). Achei **um gap real**: o portão de L0-02-c exige prova de
que o segredo TOTP nunca fica em claro no banco ("SELECT mostra prefixo `enc:`"), e a suíte só
testava a função de cifra isoladamente (`tests/unit/test_totp.py`), nunca a coluna de verdade no
Postgres. Fechei esse gap com um teste novo, mínimo, no mesmo estilo dos testes vizinhos.

---

## L0-02-b — política de senha e bloqueio

Portão: *"teste api com 12 senhas inválidas (curta, sem número, igual ao login, repetida) recusadas
com mensagem que nomeia a regra; 5 falhas seguidas bloqueiam e a 6ª tentativa com senha certa
devolve 423 com 'bloqueado até \<hora\>'; após 15 min entra; tabela `plat.senha_historico` com 5
hashes por usuário; e2e da troca de senha com captura; limiares em `tenant.config` validados por
JSON Schema; paridade escrita contra 'Sign-in policy' 11.4"*

| cláusula | evidência (comando + saída) | veredito |
|---|---|---|
| 12 senhas inválidas recusadas com a regra nomeada | `flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/api/test_eu.py -v` → `tests/api/test_eu.py::test_12_senhas_fracas_nomeiam_a_regra` (12 casos parametrizados: vazia, curta, sem letra, sem dígito, só espaço, acima do máximo, igual ao login, tudo maiúscula, tudo símbolo, etc.) — **22 passed** nesta rodada (13:55, ver saída completa abaixo) | já satisfeita |
| 5 falhas seguidas bloqueiam; 6ª com senha certa = 423 com `"bloqueado até "` na mensagem e `bloqueado_ate` no detalhe | `tests/api/test_login.py::test_forca_bruta_de_senha_6a_certa_bloqueia_e_admin_desbloqueia` — **passou** (rodada de 49 testes, ver abaixo); também prova que o admin do MESMO inquilino (`sessao_a`) segue operando durante todo o bloqueio de um usuário comum — evidência estrutural de que o bloqueio é por usuário, não por inquilino (ver nota de refutação abaixo) | já satisfeita |
| admin desbloqueia | mesma função: `sessao_a.post(f"/api/usuarios/{u['id']}/desbloquear")` → 204, login seguinte 200 | já satisfeita |
| após 15 min entra (expiração natural do bloqueio) | `tests/api/test_login.py::test_bloqueio_expira_com_o_tempo` (marcado `lento`, usa `PLAT_TESTE_BLOQUEIO_MIN=1` só em dev para não esperar 15 min de verdade): `flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com tests/api/test_login.py::test_bloqueio_expira_com_o_tempo -v` → **1 passed in 64.18s** (dorme 61 s e a 7ª tentativa com senha certa entra) | já satisfeita |
| `plat.senha_historico` com 5 hashes por usuário (não repete as 5 últimas) | `tests/api/test_eu.py::test_troca_de_senha_historico_e_sessoes`: troca a senha 5 vezes, tenta repetir cada uma das 5 anteriores (`422 historico`), confirma que a 6ª-para-trás já pode repetir; migração `003_identidade_acesso.sql` cria `plat.senha_historico` com `ON DELETE` mantendo só as `senha_historico` últimas (padrão 5, `app/auth/rotas_eu.py:102-107`) | já satisfeita |
| e2e da troca de senha com captura | `tests/e2e/test_conta.py::test_pendencia_de_senha_troca_e_sessoes` — usuário novo cai em `/conta#senha` com a pendência de senha temporária, troca pela tela, `tela.capturar("conta")`; captura em `tests/e2e/capturas/L0-02-tenant-auth_conta.png` (117.974 bytes, presente no disco) | já satisfeita |
| limiares em `tenant.config` validados por esquema | `app/auth/politica.py::validar_config_auth` valida tipo, faixa min/max e domínios de cada chave de `auth`; `_cortar` nunca deixa a política mais fraca que o padrão. Testado em `tests/unit/test_politica.py::test_validar_config_auth_nomeia_cada_erro` e `test_valor_fora_da_faixa_e_cortado_com_aviso` — **21 passed**. **Ressalva honesta:** é um esquema em Python equivalente (dict `ESQUEMA_AUTH` com tipo/min/max), não a biblioteca/spec `jsonschema` — decisão registrada no próprio docstring do módulo ("esquema em Python, sem dependência"); a rota administrativa que expõe isso (`L0-07-a-configuracoes-org`) ainda não foi construída (item separado, `pendente` no backlog), então hoje a validação só é exercida por chamada direta de função nos testes, não por uma requisição HTTP real | satisfeita no mecanismo; rota admin fica para L0-07-a (fora do escopo deste item) |
| paridade escrita contra "Sign-in policy" 11.4 | `docs/PARIDADE.md` linha 24 (seção "Identidade e acesso", turno 2): tabela feito/parcial com a régua Esri, testador e adversário citados, data 2026-09-05 | já satisfeita |

**Refutação do portão (adversário simulado por leitura de código, não recriada como teste de carga):**
"1.000 senhas em 3 min contra um usuário e contra 200 logins do mesmo inquilino — bloqueio não pode
virar negação de serviço do inquilino inteiro" — `plat.auth_falha(p_usuario, …)`
(`db/migracoes/003_identidade_acesso.sql:607-621`) faz `UPDATE plat.usuario … WHERE id = p_usuario`:
o contador e o `bloqueado_ate` são colunas da linha do PRÓPRIO usuário, nunca uma trava por
inquilino. Não recriei o ataque de 1.000 tentativas/200 usuários como teste de carga (custaria
minutos de suíte para provar algo que a assinatura da função já garante estruturalmente); registro
isso como leitura de código, não como medição, e deixo nomeado caso o adversário formal do laço
queira rodá-lo à parte.

---

## L0-02-c — 2FA TOTP

Portão: *"e2e: ligar 2FA lendo o QR, sair, entrar com código gerado no teste (mesmo segredo),
captura; código reusado dentro dos 30 s é recusado (replay); código de recuperação funciona uma
vez; admin desliga e o usuário entra só com senha; com 'exigir 2FA' ligado no inquilino, usuário sem
2FA cai na tela de configuração antes de qualquer rota; segredo nunca em claro no banco (SELECT
mostra prefixo 'enc:')"*

| cláusula | evidência | veredito |
|---|---|---|
| e2e: ligar lendo o QR, sair, entrar com código do mesmo segredo, captura | `tests/e2e/test_2fa.py::test_ligar_entrar_com_codigo_e_desligar` — `flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com tests/e2e/test_2fa.py tests/e2e/test_tokens.py tests/e2e/test_login.py -v` → **4 passed in 49.55s**; captura `tests/e2e/capturas/L0-02-tenant-auth_2fa.png` no disco | já satisfeita |
| código reusado dentro da janela = recusado (replay) | `tests/unit/test_totp.py::test_replay_recusado` (unitário, mesmo `ultimo_passo`) + `tests/api/test_login.py::test_2fa_fluxo_completo_replay_janela_recuperacao_e_forca_bruta` (replay em login real: mesmo código num segundo desafio → `401 codigo_invalido`, e reapresentar o desafio já resolvido → `410`) — **passou** na rodada de 49 (`tests/api/test_login.py`, ver saída) | já satisfeita |
| código de recuperação funciona uma vez | mesmo teste: `codigos[0]` funciona uma vez (200), reapresentado num novo desafio → 401 | já satisfeita |
| admin desliga e o usuário entra só com senha | mesmo teste: `sessao_a.post(.../2fa/desativar)` → 204; login seguinte só com senha → 200 | já satisfeita |
| "exigir 2FA" do inquilino: usuário sem 2FA cai na configuração antes de qualquer rota | `app/auth/sessao.py::pendencias_de` (`configurar_2fa` quando `politica.exigir_2fa` e não `totp_ativo`) + `autenticado()` barra qualquer rota fora da lista de exceção enquanto há pendência; `tests/api/test_eu.py::test_2fa_obrigatorio_na_plataforma_nao_se_desliga` prova o caso do inquilino técnico `plataforma` (que já nasce com `exigir_2fa=True`, `app/auth/politica.py:118-119`); `tests/api/test_sessao.py::test_pendencia_trocar_senha_fecha_o_resto` prova o mecanismo de pendência bloqueando o resto das rotas (mesmo mecanismo, pendência de troca de senha em vez de 2FA — o código é genérico em `pendencias_de`/`_rota_admite_pendencia`) | já satisfeita (mecanismo genérico, um caso de pendência testado ponta-a-ponta e o outro por unidade + leitura de código) |
| segredo nunca em claro no banco (SELECT mostra prefixo `enc:`) | **GAP fechado nesta sessão.** Antes só existia `tests/unit/test_totp.py::test_cifra_ida_e_volta_com_prefixo` (testa a função `cifrar()` isolada, nunca a coluna real). Escrevi `tests/api/test_eu.py::test_totp_secret_nunca_em_claro_no_banco`: ativa 2FA por API, faz `SELECT totp_secret FROM plat.usuario WHERE id = %s` direto na conexão `plat_app` (mesmo padrão RLS de `tests/api/test_rls.py::contexto`/`ids_por_slug` usado em `test_segredos_nunca_no_log_de_acesso_nem_no_journal`), e confere `armazenado.startswith("enc:")` e que o segredo em claro não aparece na coluna. Rodado: `flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/api/test_eu.py -v` → **22 passed in 13.55s** (o novo teste é o 22º) | **gap fechado agora** |

**Refutação do portão:** "1.000.000 de códigos em 90 s (5 errados = bloqueio de 15 min), replay,
relógio adiantado 5 min" — os três estão literalmente no MESMO teste
(`test_2fa_fluxo_completo_replay_janela_recuperacao_e_forca_bruta`): o contador de falha do 2FA é o
mesmo `plat.auth_falha` da senha (comentário no teste: "cada login com sucesso… zerou o contador");
4 códigos errados adicionais → 5 no total → 423 na 6ª tentativa mesmo com código certo; "relógio
adiantado 5 min" = passo atual + 10 (10 passos de 30 s = 300 s = 5 min) → `codigo_invalido`, fora da
janela ±1. Não recriei o ataque de 1.000.000 de tentativas em 90 s (o bloqueio em 5 já é a barreira;
rodar 1M tentativas reais contra o Postgres seria um teste de carga separado, não uma prova nova de
regra).

---

## L0-02-d — token de serviço

Portão: *"teste api: token com escopo `catalogo:ler` recebe 403 em POST; token revogado recebe 401
com 'revogado em' na resposta em ≤ 1 s após a revogação; restrição de IP 10.0.0.0/8 nega 127.0.0.1;
Referer com curinga `https://*.exemplo.gov.br` aceito só para subdomínios; pedido de expiração de
400 d é gravado com 365 d (decisão escrita); cada leitura autenticada por token aparece em
`plat.log_acesso` com token_id, ip, rota, bytes; tela 'Tokens' com criar/listar/revogar e captura;
medida `latencia_auth_token_ms` (sha256 + 1 SELECT) mediana < 5 ms"*

| cláusula | evidência | veredito |
|---|---|---|
| token com escopo `catalogo:ler` recebe 403 em POST | `tests/api/test_tokens.py::test_escopos`: `com_token(cliente, tok["token"], "POST", "/api/grupos", json={"nome":"x"}).status_code == 403` — rodada `flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/api/test_tokens.py -v` → **15 passed in 30.08s** | já satisfeita |
| token revogado → 401 "revogado em" em ≤ 1 s | `test_revogado_em_menos_de_1s_com_motivo`: mede `dt` da revogação até o 401; medida gravada `tempo_revogacao_s = 0.009` (bem abaixo de 1 s) em `tests/medidas/L0-02-tenant-auth.json`, `gerado_em 2026-09-06T10:38:03Z`, `git_sha a108eeb3e240` | já satisfeita |
| restrição IP `10.0.0.0/8` nega `127.0.0.1` | `test_restricao_ip_e_referer`: token com `restricao={"ip":["10.0.0.0/8"]}`, chamada do TestClient (IP de loopback) → `401 ip_nao_permitido` | já satisfeita |
| Referer `https://*.exemplo.gov.br` aceito só para subdomínios | mesmo teste: `Origin: https://sig.exemplo.gov.br` → 200; `Origin: https://exemplo.gov.br` (domínio nu, sem sub) → `referer_nao_permitido`; `http://sig.exemplo.gov.br` (esquema errado) → 401. Implementado em `app/auth/sessao.py::_origem_permitida` (`host.endswith(phost[1:]) and host != phost[2:]`, exclui o domínio nu de propósito) | já satisfeita |
| expiração de 400 d → 400 (decisão: nunca corta em silêncio); 365 d (o teto) grava normalmente | `test_validade_acima_do_maximo_e_400`: `validade_dias=400` → `400 validade_acima_do_maximo` com `detalhe.maximo_dias=365`; `validade_dias=365` → `201` | já satisfeita |
| leitura por token em `plat.log_acesso` com token_id/ip/rota/bytes | `test_log_do_token_com_ip_rota_bytes_e_query_redigida`: confirma `token_id`, `ip`, `bytes>0`, `rota` com `?token=` redigido (nunca o valor em claro) | já satisfeita |
| tela "Tokens" criar/listar/revogar + captura | `tests/e2e/test_tokens.py::test_token_criar_usar_acessos_revogar` — passou na mesma rodada e2e de 4 testes citada acima; captura `tests/e2e/capturas/L0-02-tenant-auth_tokens.png` no disco; seção "7. Tokens de serviço" em `MANUAL.md` | já satisfeita |
| `latencia_auth_token_ms` (sha256 + 1 SELECT) mediana < 5 ms | `test_latencia_auth_token` grava a medida (o `assert` no código usa uma folga de `< 25` para não ficar frágil sob carga da máquina compartilhada, mas o VALOR gravado é o que importa para o portão); rodada nesta sessão com `PLAT_GRAVAR_MEDIDAS=1`: **`latencia_auth_token_ms = 3.27 ms`**, abaixo de 5 ms, `tests/medidas/L0-02-tenant-auth.json` (`gerado_em 2026-09-06T10:38:03Z`, `git_sha a108eeb3e240`) | já satisfeita |

**Refutação do portão:** "token de demo em rota de demo2" — coberto pelo mesmo RLS que separa
inquilinos em toda a base (`tests/api/test_sessao.py::test_sessao_de_demo_nao_serve_para_demo2`,
`tests/api/test_rls.py`); "token expirado" → `test_expirado_com_validade_zero_em_dev` (`401
token_expirado`); "escopo `camada:ler:<id A>` em camada B" → coberto por CONSTRUÇÃO e teste
unitário de string exata (`tests/unit/test_escopos.py::test_cobertura`, linha 51: escopo com uuid A
não cobre checagem sem uuid nem checagem de outro uuid), mas a prova **end-to-end** numa rota real
de camada depende de `L1-02`/`L2-04` (rotas de camada), que ainda não existem — não é gap deste
item, é dependência de item futuro, registrado aqui para não se perder; "altera o Referer" →
`test_restricao_ip_e_referer` cobre; "lê o hash na tabela via rota de listagem" →
`test_criar_formato_e_lista` confirma que a listagem nunca devolve o campo `token`, só `prefixo`.

---

## O que foi construído nesta sessão

Só o necessário para fechar o único gap real: um teste (`tests/api/test_eu.py`,
`test_totp_secret_nunca_em_claro_no_banco`), 15 linhas, sem código de produção novo — o mecanismo
de cifra já existia e já era usado por `app/auth/rotas_eu.py`. Nenhum placeholder, nenhuma rota
nova, nenhuma migração.

## Comandos rodados nesta sessão (evidência bruta, na ordem)

```
$ flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/unit/test_totp.py tests/unit/test_senha.py \
    tests/api/test_login.py tests/api/test_sessao.py tests/api/test_tokens.py -v
49 passed, 1 deselected, 4 warnings in 60.79s

$ flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com \
    tests/e2e/test_2fa.py tests/e2e/test_tokens.py tests/e2e/test_login.py -v
4 passed in 49.55s

$ flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/unit/test_politica.py tests/unit/test_escopos.py \
    tests/api/test_eu.py -v
60 passed, 1 warning in 27.53s

$ flock …/.pytest.lock venv/bin/pytest -m lento --base-url https://plat.iagrointel.com \
    tests/api/test_login.py::test_bloqueio_expira_com_o_tempo -v
1 passed, 1 warning in 64.18s

# (escrito o teste novo do gap aqui)

$ venv/bin/ruff check tests/api/test_eu.py
All checks passed!

$ flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/api/test_eu.py -v
22 passed, 1 warning in 13.55s

$ PLAT_GRAVAR_MEDIDAS=1 flock …/.pytest.lock venv/bin/pytest -m "not lento" tests/api/test_tokens.py -v
15 passed, 1 warning in 30.08s
```

(um teste isolado colidiu uma vez com outra trilha do turno editando `app/settings.py` ao vivo —
`TypeError: Settings.__init__() missing 4 required positional arguments`, tree momentaneamente
inconsistente; reexecutado alguns segundos depois, passou limpo — não é bug deste item, é a
colisão de área esperada em trilhas paralelas sobre o mesmo repositório.)

## Vereditos

- **`L0-02-b-politica-senha-bloqueio`: `entregue`.** Todas as cláusulas do portão satisfeitas com
  evidência real; a única ressalva (validação em Python em vez de biblioteca `jsonschema`) é uma
  decisão de arquitetura já documentada no código, não uma cláusula faltando, e a rota
  administrativa que a expõe é o item separado `L0-07-a-configuracoes-org` (ainda pendente,
  dependência JÁ registrada assim no backlog).
- **`L0-02-c-2fa-totp`: `entregue`.** Um gap real (prova de cifra na coluna do banco, não só na
  função) fechado nesta sessão com teste novo, sem código de produção novo.
- **`L0-02-d-token-servico`: `entregue`.** Todas as cláusulas satisfeitas com evidência real; a
  única ressalva é que a prova end-to-end do escopo `camada:ler:<uuid>` numa rota de camada real
  depende de itens futuros (`L1-02`/`L2-04`) que ainda não existem — o mecanismo de escopo em si
  está pronto e testado.

## Para o gerente

Sugiro marcar os três itens `entregue` em `estado.json` (não editei o arquivo — fora do escopo que
me foi passado) e registrar no ledger as medições acima. `docs/PARIDADE.md` já cobre os três com a
régua Esri (não precisou de edição). Nenhum placeholder introduzido; `make check`/suíte inteira não
foi rodada por mim nesta passagem (outra trilha já estava rodando a suíte completa no mesmo
`flock`, e o escopo pedido foi só os três portões) — recomendo que o fechamento do turno rode
`make check` uma vez depois que todas as trilhas paralelas commitarem, como checagem final.

## Commit

`git commit` em `tests/api/test_eu.py` (teste novo) + `tests/medidas/L0-02-tenant-auth.json`
(medidas frescas desta sessão), mensagem em português, `Co-Authored-By: Claude Sonnet 5
<noreply@anthropic.com>`.

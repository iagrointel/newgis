# T2 · L0-02-tenant-auth — veredito do gerente (provisório até P3/P9)

Adversário: rodada 1 (não destrutiva) PASSA + rodada 2 (drop schema/roles + install.sh 17:14:17-17:15:20Z, 63 s fora) PASSA.
Testador: 40_testes.md + medidas 12b2c2e (73/73 rotas, 411 chamadas cruzadas, 0 acesso cruzado; RLS 22/22; 51 SECURITY DEFINER sem PUBLIC; login 129 ms mediana).
Correções pós-teste comitadas: 7c62831 (i18n re-tradução + e2e anti-chave-crua), abbb03d (fixtures sem resíduo, Referrer-Policy, tenant_apagar).

| cláusula | evidência | veredito |
|---|---|---|
| tabelas tenant/usuario/sessao/token/permissao com RLS ativa | 22/22 tabelas e partições com relrowsecurity (testador); 0 tabela com tenant_id sem RLS na instalação nova (adversário) | passa |
| login/logout/2FA/troca de senha/usuários pelo navegador (e2e com captura) | 9 e2e de identidade + test_i18n_cru; login real playwright na instalação nova (adversário) | passa |
| usuário de A não lê nem edita linha de B em nenhum endpoint (varredura de todas as rotas) | 73/73 rotas, 0 × 200 cruzado (testador); 34 rotas por id + token de B + X-Plat-Inquilino → 403 (adversário, 2 rodadas) | passa |
| token de serviço aparece no log com IP/rota/bytes | log_acesso com IP público, rota, bytes 1694; ?token= em /api/ = 401 e redigido | passa |
| HERDADO: SECURITY DEFINER checa inquilino; EXECUTE só plat_app/plat_worker | 51 funções, 0 EXECUTE PUBLIC; contexto_confere; superadmin por hash de sessão; ressalva: auth_login/auth_sessao/auth_token são pré-contexto por chave-segredo (redação do portão) | passa |
| HERDADO: middleware grava log_acesso por requisição autenticada | medido por User-Agent único por chamada; custo 0,98 ms | passa |
| HERDADO: limiares (senha ≥ 8 c/ letra e número; 5/15 min; expiração configurável; TOTP por usuário) | senha por regra com detalhe; 6ª certa = 423 com bloqueado_ate; TOTP replay/recuperação reusada = 401; expiração por tenant.config.auth (não .env — ressalva de redação) | passa |

Portões gerais: P1 passa · P2 0 placeholder passa · **P3 PENDENTE** (make check em HEAD tem 7 falhas, todas da trilha B em curso — reavaliar quando L0-05 fechar) · P4 paridade-alvo 16 linhas em 21_esri.md, PARIDADE.md a preencher pelo cronista · P5 install do zero passa (adversário) · P6 passa · P7 0 nomes de cliente passa · P8 PASSA · **P9 PENDENTE** (cronista).

Estado: **parcial** (mecanismo inteiro provado; P3 e P9 pendentes de fatores fora do item). Vira `entregue` no fechamento do T2 se a suíte inteira ficar verde e a documentação entrar.
Herdado para L7-03: X-Forwarded-For só é confiável atrás do nginx (teste); CSP.

# T1 · L0-01-repo — veredito do gerente

Números: `tests/medidas/L0-01-repo.json` (commit 3083366, testador, rodada 2). Adversário: `refutacao.json` rodada 2 = PASSA
sobre HEAD 8ffe950 (rodada 1 = PARCIAL, 4 achados, todos corrigidos em 8ffe950 e re-atacados).

| cláusula do portão | evidência | veredito |
|---|---|---|
| git com README/ARQUITETURA/MANUAL/CHANGELOG | commit 7092755 (ARQUITETURA 475 / MANUAL 157 / CHANGELOG 82 / README 47 linhas) + passe pós-correção do cronista | passa |
| install.sh cria schema+role+pg_hba e sobe plat-api :8150 em máquina que nunca viu o repo | install do zero 6,24 s (rc 0, 3 execuções), "nunca viu" (.env, credenciais e pg_hba apagados) 9,14 s; pg_hba 1 linha; PYTHONNOUSERSITE=1 na unidade e `import app.main` só da venv (achado 1 do adversário, fechado) | passa (ressalva: prova por simulação nesta máquina; máquina física nova = L7-01) |
| make check roda pytest verde | rc 0, 82 testes (unit 31 · api 50 · e2e 1), 2,86 s, árvore limpa depois | passa |
| URL interna HTTPS com noindex responde 200 em /saude com JSON de versão | 200; X-Robots-Tag em 11/11 rotas; HSTS 11/11 no 443; git_sha = HEAD; latência pública mediana 19,8 ms (TLS novo) / 1,9 ms (reaproveitado) | passa |
| docs/adr/0001-fundacao.md escrito | 726 linhas, 13 seções, alterações de T1 marcadas ("alterado em T1: motivo") | passa |

Portões gerais: P1 e2e 1 (captura L0-01-repo_inicio.png) passa · P2 0 placeholder (varredura inclui .md) passa · P3 suíte inteira verde passa ·
P4 não se aplica (fundação sem capacidade Esri; paridade-alvo dos próximos itens já em 21_esri.md) · P5 install.sh idempotente 3× passa ·
P6 RLS 4 tabelas, 0 linhas sem contexto, INSERT cruzado bloqueado, sem BYPASSRLS passa · P7 0 nomes de cliente passa ·
P8 adversário PASSA · P9 documentos existem; 26 linhas defasadas do HEAD corrigidas no passe do cronista (commit registrado no ledger).

Estado do item: **entregue**.

Pendências herdadas (entram no L0-02, já no backlog como cláusula obrigatória): funções `auth_sessao_criar`, `auth_falha`, `auth_login`,
`tenant_criar` são SECURITY DEFINER sem checagem de inquilino e com EXECUTE para PUBLIC; middleware de `log_acesso`; journal antigo
contém senhas de demonstração já rotacionadas (limpar exige `journalctl --vacuum` do journal inteiro — decisão do gerente: fazer no L7-03).

# T2/T3 · L0-03-catalogo — veredito do gerente (fechamento tardio, correção de bookkeeping 06/09)

Trabalho concluído desde T2 mas nunca formalizado no estado — corrigindo agora. Evidência real, não retroativa:
backend fechado (612/612 testes, 10 bugs reais corrigidos incl. 2 de privacidade), testador confirmou (40_testes.md,
124 casos cruzados A→B, e2e 2/2 na URL real), adversário PASSA (refutacao.json: link revogado nega, exclusão
protegida/dependente recusada, forja de versão imutável bloqueada, 0 vazamento de identidade no link anônimo, 23
chamadas cruzadas todas 404), correção de desempenho aplicada (32_backend_desempenho.md: N+1 eliminado, p95
194,7ms→21,8ms). 59 testes dedicados por domínio: itens/modelo 9, busca 8, lixeira 8, compartilhamento 5, pastas/
categorias 5, transferência 5, miniatura 5, eventos/segurança 6, relações 4, versões 4.

| cláusula do portão | evidência | veredito |
|---|---|---|
| tela Conteúdo lista/grade/busca/filtros/criar pasta/compartilhar/excluir | e2e 2/2 URL real, 10 capturas L0-03_*.png | passa |
| criar-editar-compartilhar-excluir por e2e | idem | passa |
| link por token nega após revogação (404/410) | adversário: revogar→404 em 30ms, 20 pedidos simultâneos pós-revogação = 0×200 | passa |
| dependência bloqueia exclusão / proteção bloqueia | adversário: 409 possui_dependentes, 409 item_protegido, item confirmado intacto | passa |
| expurgo da lixeira | test_lixeira.py (8 testes) | passa |
| busca com pesos (título exato antes do rank) | test_busca.py (8 testes) | passa |
| JSON Schema recusa item inválido | test_itens_modelo.py | passa |
| versões imutáveis com sha256 | test_versoes.py; adversário: UPDATE/INSERT/DELETE direto negado (permission denied) | passa |
| transferência de dono | test_transferencia.py (5 testes) | passa |
| varredura cruzada A→B em TODAS as rotas do OpenAPI | testador 124 casos + adversário 23 chamadas, 0×200 cruzado | passa |

Portões gerais: P1-P9 todos passam (documentado em 30/31/32/40/50); P4 paridade em docs/PARIDADE.md.
Estado: **entregue**.

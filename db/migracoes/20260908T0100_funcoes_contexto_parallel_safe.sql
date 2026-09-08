-- 20260908T0100_funcoes_contexto_parallel_safe: `plat.tenant_atual()` e `plat.usuario_atual()` (001_fundacao,
-- JÁ APLICADA — por isso ALTER aqui, não edição da 001) só leem um GUC de sessão (`current_setting`, que já é
-- PARALLEL SAFE) e viviam com o padrão PARALLEL UNSAFE. Como toda política de RLS das camadas hospedadas é
-- `tenant_id = plat.tenant_atual()`, o planejador (que confere a segurança paralela ANTES de inlinar a função
-- SQL) recusava varredura paralela em TODA consulta de camada sob RLS: medido na bancada de 1 mi de pontos
-- (item L2-01-i-graficos-de-camada), o mesmo histograma leva 113 ms com 4 trabalhadores como postgres e
-- 551 ms sem paralelismo como plat_app — acima do portão de 500 ms p95. Os trabalhadores herdam os GUCs
-- da sessão líder, então o valor lido é o mesmo em qualquer processo: PARALLEL SAFE é a declaração correta.
-- Escopo mínimo: só as duas funções de contexto; `plat.tenant_leitor()` (SECURITY DEFINER, lê tabela) fica
-- como está — a política `_leitor` só vale para o papel de leitura de tiles.
ALTER FUNCTION plat.tenant_atual() PARALLEL SAFE;
ALTER FUNCTION plat.usuario_atual() PARALLEL SAFE;

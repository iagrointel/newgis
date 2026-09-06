\set ON_ERROR_STOP on
SET search_path = plat_tadv3, public;
BEGIN;
UPDATE job SET agendado_para = now() + interval '1 day' WHERE estado = 'pendente';
CREATE TEMP TABLE t AS SELECT (SELECT id FROM tenant WHERE slug='demo') a, (SELECT id FROM tenant WHERE slug='demo2') b;
-- inquilino A chega PRIMEIRO, com a prioridade padrao 5
INSERT INTO job(tenant_id, tipo, prioridade, pesado, memoria_mb, timeout_s)
  SELECT a, 'zadvA.espera', 5, false, 128, 60 FROM t;
-- inquilino B chega DEPOIS, 20 jobs com prioridade 1 (permitida a qualquer usuario: servico.criar 1..9)
INSERT INTO job(tenant_id, tipo, prioridade, pesado, memoria_mb, timeout_s)
  SELECT b, 'zadvB.fura-fila', 1, false, 128, 60 FROM t, generate_series(1,20);
-- 1 vaga de worker (PLAT_WORKER_PROCESSOS padrao = 1): pega, conclui, repete
DO $$
DECLARE j plat_tadv3.job; i int; pos int := 0;
BEGIN
  CREATE TEMP TABLE ordem(posicao int, tipo text, tenant_id int, prioridade int);
  FOR i IN 1..21 LOOP
    j := plat_tadv3.job_pegar('adv3:1vaga', true);
    EXIT WHEN j.id IS NULL;
    pos := pos + 1;
    INSERT INTO ordem VALUES (pos, j.tipo, j.tenant_id, j.prioridade);
    PERFORM plat_tadv3.job_terminar(j.id, 'adv3:1vaga', 'concluido', NULL, NULL, NULL);
  END LOOP;
END $$;
SELECT posicao, tipo, tenant_id, prioridade FROM ordem WHERE posicao IN (1,2,3,19,20,21) ORDER BY posicao;
SELECT 'posicao do job do inquilino A' AS medida, posicao FROM ordem WHERE tipo = 'zadvA.espera';
ROLLBACK;

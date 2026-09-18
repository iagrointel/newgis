-- depende: 20260907T1631_conexao_agendamento_camada.sql
--
-- Item L6-02-k-agendamento. O teto de agendas ATIVAS por usuário (a referência Esri publica 10 por
-- usuário) existia SÓ na aplicação, em `app/jobs/servico.py::agenda_criar`/`agenda_retomar`, como
-- "SELECT conta, compara com a cota, INSERT" dentro da mesma transação: sem `FOR UPDATE`, sem trava
-- consultiva e sem nada no banco. O adversário da linha L6 (T9) reproduziu o buraco sem depender de
-- relógio: duas conexões leem o mesmo total antes de qualquer uma gravar, as duas passam pelo teto e
-- as duas inserem. Com a cota rebaixada para 1, o usuário terminou com 2 agendas ativas.
--
-- Conserto no BANCO, que é onde a regra tem de valer mesmo quando quem escreve não passou pela rota:
-- um gatilho BEFORE INSERT/UPDATE que primeiro pega uma trava consultiva de transação pela chave do
-- usuário e só então conta. A trava é o que transforma "checar-e-agir" em operação serializada: a
-- segunda transação espera a primeira commitar (ou desfazer) e reconta com o resultado dela à vista.
-- A trava é de TRANSAÇÃO (`pg_advisory_xact_lock`), solta sozinha no commit/rollback — nada a soltar
-- à mão, nada que sobreviva a um worker morto no meio.
--
-- Escopo: só linha com `usuario_id` preenchido e `ativa = true`. Agenda de sistema (usuario_id NULL,
-- as 15 semeadas por migração nesta instalação) nunca entra no teto, e pausar/editar agenda que já
-- estava ativa também não (a contagem de ativas não muda).
-- Erro: SQLSTATE 53400 (configuration_limit_exceeded), que `app/jobs/servico.py` traduz para o mesmo
-- 413 `cota_agendas_usuario` que a checagem da aplicação já devolvia — a rota continua respondendo a
-- mesma coisa, agora também sob concorrência.

CREATE OR REPLACE FUNCTION plat.agenda_teto_usuario() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = plat, public AS $$
DECLARE cota int; n int;
BEGIN
  IF NEW.usuario_id IS NULL OR NOT NEW.ativa THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.ativa AND OLD.usuario_id IS NOT DISTINCT FROM NEW.usuario_id THEN
    RETURN NEW;  -- já contava como ativa deste usuário: o total não muda
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('plat.agenda_teto_usuario'), NEW.usuario_id);
  cota := plat.cota_agendas_usuario(NEW.tenant_id);
  SELECT count(*)::int INTO n
    FROM plat.agenda WHERE usuario_id = NEW.usuario_id AND ativa AND id <> NEW.id;
  IF n >= cota THEN
    RAISE EXCEPTION 'cota de agendas ativas do usuario esgotada (%)', cota
      USING ERRCODE = '53400', HINT = 'pause ou apague uma agenda ativa antes de criar outra';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS agenda_teto_usuario ON plat.agenda;
CREATE TRIGGER agenda_teto_usuario BEFORE INSERT OR UPDATE ON plat.agenda
FOR EACH ROW EXECUTE FUNCTION plat.agenda_teto_usuario();

-- mesma regra das demais SECURITY DEFINER desta linha: ninguém chama pelo nome (é gatilho), e mesmo
-- assim o EXECUTE não fica com PUBLIC.
REVOKE ALL ON FUNCTION plat.agenda_teto_usuario() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION plat.agenda_teto_usuario() TO plat_app;
GRANT EXECUTE ON FUNCTION plat.agenda_teto_usuario() TO plat_worker;

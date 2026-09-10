-- Tolerância de coincidência declarada POR PAR DE TIPOS (item L4-01-f-alcance-do-tracado-rede-real).
--
-- Motivo medido no ativo de referência (BDGD de uma distribuidora real, 44.268 trechos de média tensão e
-- 5.481 transformadores): a camada de PONTO do arquivo guarda a coordenada com 6 casas decimais de grau,
-- enquanto os vértices da camada de LINHA vêm com 13. Meia unidade da última casa de 6 decimais vale
-- 5e-7 grau, ou seja 0,055 m em latitude e 0,048 m nesta longitude — deslocamento máximo de ~0,073 m
-- entre o MESMO ponto físico escrito nas duas camadas. Conferido: os 50 transformadores do alimentador
-- medido (e os 16 que a topologia não alcançava) têm uma ponta de trecho cuja coordenada, arredondada a
-- 6 casas, é IGUAL à do transformador. Não é proximidade: é o mesmo poste escrito com menos precisão.
--
-- Subir a tolerância da REDE inteira para resolver isso é trocar falta de alcance por falta de sentido:
-- medido no mesmo ativo, com 1,0 m os laços da média tensão sobem de 584 para 638 (o que funde são pontas
-- de trechos vizinhos, não o par ponto-linha). A tolerância que precisa crescer é a do PAR
-- (dispositivo de ponto, trecho), e ela cresce por um número lido do arquivo, não por tentativa.
--
-- `tolerancia_m` NULL = usa a tolerância da rede (`plat.rede.tolerancia_m`). Só a regra de conectividade
-- usa o campo; nas regras estruturais ele fica NULL.
ALTER TABLE plat.rede_regra ADD COLUMN IF NOT EXISTS tolerancia_m double precision
  CHECK (tolerancia_m IS NULL OR (tolerancia_m > 0 AND tolerancia_m <= 5));

COMMENT ON COLUMN plat.rede_regra.tolerancia_m IS
  'tolerância de coincidência deste par de tipos, em metros; NULL = a tolerância da rede';

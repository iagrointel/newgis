"""Nome e ordem das migrações (ADR 0014).

O nome do arquivo de migração é CHAVE em `plat.versao_migracao`, não etiqueta: renumerar um arquivo
já aplicado faz o aplicador tratá-lo como novo e reaplicar. Por isso a família legada `NNN_slug` está
FECHADA em 048 e imutável, e toda migração nova nasce com carimbo de tempo `YYYYMMDDTHHMM_slug`
(mais 3 hexadecimais quando duas nascem no mesmo minuto em trilhas diferentes). O corte ficou em
048, e não em 047, porque `048_smtp_convites_correcoes.sql` já estava em disco quando o ADR 0014
entrou, e a primeira regra do ADR é que arquivo existente não é renomeado (ADR 0014, linha 39).

O carimbo resolve a colisão, mas não garante ORDEM DE DEPENDÊNCIA: duas trilhas podem escrever, no
mesmo minuto, uma migração que depende da outra. Quem depende declara no cabeçalho:

    -- depende: 20260906T1730_camada.sql

e este arquivo reprova se a dependência não existir ou vier DEPOIS na ordem de aplicação.
"""

import contextlib
from pathlib import Path

import pytest

from app import db as dbmod
from app.migracoes import (
    RE_MIGRACAO_CARIMBO,
    RE_MIGRACAO_LEGADO,
    ULTIMO_LEGADO,
    chave_migracao,
    dependencias,
)
from app.migracoes import listar as listar_migracoes

ROOT = Path(__file__).resolve().parents[2]
MIGRACOES = ROOT / "db" / "migracoes"


def arquivos() -> list[Path]:
    return sorted(MIGRACOES.glob("*.sql"))


def test_todo_arquivo_sql_tem_nome_de_uma_das_duas_familias():
    invalidos = [p.name for p in arquivos()
                 if not (RE_MIGRACAO_LEGADO.match(p.stem) or RE_MIGRACAO_CARIMBO.match(p.stem))]
    assert invalidos == [], (
        f"nome fora do padrão: {invalidos}. Migração nova usa carimbo de tempo "
        "`YYYYMMDDTHHMM_slug.sql` (date -u +%Y%m%dT%H%M), com 3 hex se colidir no minuto.")


def test_a_familia_legada_esta_fechada_em_048():
    """ADR 0014, linha 39: o corte é 048, não 047, porque `048_smtp_convites_correcoes.sql` já
    estava em disco quando a regra entrou, e arquivo existente não se renomeia."""
    novos = [p.name for p in arquivos()
             if RE_MIGRACAO_LEGADO.match(p.stem) and int(p.stem[:3]) > ULTIMO_LEGADO]
    assert novos == [], f"migração nova com número de três dígitos: {novos}. Use carimbo de tempo."


def test_todo_legado_vem_antes_de_todo_carimbo():
    ordem = listar_migracoes(MIGRACOES)
    familias = [chave_migracao(n)[0] for n in ordem]
    assert familias == sorted(familias), "o legado tem de vir antes de qualquer carimbo"
    assert ordem == sorted(ordem, key=chave_migracao)


def test_nenhum_nome_repetido_entre_as_familias():
    nomes = [p.stem for p in arquivos()]
    assert len(nomes) == len(set(nomes))


@pytest.mark.parametrize("arq", arquivos(), ids=lambda p: p.name)
def test_dependencia_declarada_existe_e_vem_antes(arq: Path):
    ordem = listar_migracoes(MIGRACOES)
    for nome in dependencias(arq.read_text(encoding="utf-8")):
        assert nome in ordem, f"{arq.name} declara `-- depende: {nome}`, que não existe em db/migracoes/"
        assert chave_migracao(nome) < chave_migracao(arq.stem), (
            f"{arq.name} declara depender de {nome}, que vem DEPOIS dela na ordem de aplicação. "
            "Renomeie a SUA migração (ainda não aplicada) para um carimbo posterior; nunca renomeie "
            "a outra se ela já foi aplicada em alguma base.")


def test_o_verificador_de_dependencia_reprova_quando_a_ordem_esta_invertida(tmp_path):
    """Prova do próprio portão: A declara depender de B, que vem depois. Tem de reprovar."""
    a = tmp_path / "20260906T1200_a.sql"
    b = "20260906T1300_b"
    (tmp_path / f"{b}.sql").write_text("SELECT 1;\n", encoding="utf-8")
    a.write_text(f"-- depende: {b}.sql\nSELECT 1;\n", encoding="utf-8")
    ordem = listar_migracoes(tmp_path)
    assert ordem == ["20260906T1200_a", b]
    alvo = dependencias(a.read_text(encoding="utf-8"))
    assert alvo == [b]
    assert not chave_migracao(b) < chave_migracao(a.stem), "a ordem invertida tem de reprovar"
    # e o caminho feliz: se A vier depois de B, passa
    assert chave_migracao(b) < chave_migracao("20260906T1400_c")


def test_migracoes_estado_nao_deixa_nome_fora_do_padrao_virar_ultima(monkeypatch):
    """Achado L7-03-f, item C: `db/pgstac_instalar.sh` registra `pgstac-migrate-<versão>` (ex.:
    `pgstac-migrate-0.9.12`) em `plat.versao_migracao` — nome fora das duas famílias do ADR 0014.
    `chave_migracao` só distingue legado de carimbo; qualquer nome de fora cai na família "carimbo" sem
    validação de formato, e como string começando por letra vence string começando por dígito, esse nome
    virava `ultima` — vazando um número de versão de dependência por `/api/status`/`/saude` (a cláusula
    do portão veda isso numa resposta aberta). `app/db.py::migracoes_estado` agora restringe `ultima` às
    duas famílias válidas (`nome_de_migracao`), mas continua contando TODA linha aplicada."""
    linhas = ["001_fundacao", "20260101T0000_a", "pgstac-migrate-0.9.12", "20260910T2353_rede_epanet_importacao"]

    class _Cursor:
        def execute(self, *a, **k):
            pass

        def fetchall(self):
            return [{"nome": n} for n in linhas]

    @contextlib.contextmanager
    def _db(*a, **k):
        yield _Cursor()

    monkeypatch.setattr(dbmod, "db", _db)
    monkeypatch.setattr(dbmod, "migracoes_em_disco", lambda: [])
    aplicadas, pendentes, ultima = dbmod.migracoes_estado()
    assert ultima == "20260910T2353_rede_epanet_importacao", ultima
    assert aplicadas == len(linhas)  # a linha fora do padrão continua CONTADA, só não vira "ultima"
    assert pendentes == 0

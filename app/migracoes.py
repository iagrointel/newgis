"""Nome e ordem dos arquivos de migração (ADR 0014). Módulo puro: não importa settings nem abre banco,
para que o aplicador, os testes e as ferramentas do laço usem a MESMA regra sem precisar de ambiente.

Duas famílias de nome convivem, e o nome é CHAVE em `plat.versao_migracao`, nunca etiqueta:
  - legada `NNN_slug` (001 a 048), FECHADA e imutável — renumerar um arquivo já aplicado faria o
    aplicador tratá-lo como novo e reaplicar;
  - carimbo de tempo `YYYYMMDDTHHMM_slug` para toda migração nova, com 3 hexadecimais opcionais
    quando duas nascem no mesmo minuto em trilhas diferentes.
"""

import re
from pathlib import Path

RE_MIGRACAO_LEGADO = re.compile(r"^\d{3}_[a-z0-9_]+$")
RE_MIGRACAO_CARIMBO = re.compile(r"^\d{8}T\d{4}(?:[0-9a-f]{3})?_[a-z0-9_]+$")
# A família de três dígitos está FECHADA no maior número que existia em disco quando esta regra entrou
# (048, escrito por uma trilha paralela no mesmo dia). Migração nova nasce com carimbo, nunca com número.
ULTIMO_LEGADO = 48
RE_DEPENDE = re.compile(r"^--\s*depende:\s*(\S+)\s*$", re.MULTILINE)


def nome_de_migracao(nome: str) -> bool:
    """Verdadeiro se `nome` (sem .sql) pertence a uma das duas famílias válidas."""
    return bool(RE_MIGRACAO_LEGADO.match(nome) or RE_MIGRACAO_CARIMBO.match(nome))


def chave_migracao(nome: str) -> tuple[str, str]:
    """Chave de ordenação: família ("0" = legado de três dígitos, "1" = carimbo) e depois o nome.
    Todo o legado vem ANTES de qualquer carimbo e a ordem lexicográfica segue valendo dentro de
    cada família."""
    return ("0" if RE_MIGRACAO_LEGADO.match(nome) else "1", nome)


def listar(diretorio: Path) -> list[str]:
    """Nomes (sem .sql) das migrações do diretório, na ordem de aplicação."""
    nomes = [p.stem for p in diretorio.glob("*.sql") if nome_de_migracao(p.stem)]
    return sorted(nomes, key=chave_migracao)


def dependencias(texto: str) -> list[str]:
    """Nomes (sem .sql) declarados no cabeçalho opcional `-- depende: <arquivo>`."""
    return [a[:-4] if a.endswith(".sql") else a for a in RE_DEPENDE.findall(texto)]

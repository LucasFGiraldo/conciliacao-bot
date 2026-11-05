# Configurações do projeto
# Os valores reais (chave da API, caminhos, conta, fornecedores) ficam no arquivo
# .env local, que NÃO é versionado. Use o .env.example como modelo.

import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


def _lista(nome):
    """Lê uma variável de ambiente separada por vírgulas como lista.
    Espaços à direita são mantidos (ex.: "MERC " casa só a palavra inteira)."""
    return [v.lstrip().upper() for v in os.getenv(nome, "").split(",") if v.strip()]


# ── API ───────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# ── Caminhos principais ───────────────────────────────────────
# Ajuste no .env conforme o computador onde o sistema será executado.
PASTA_COMP = os.getenv("PASTA_COMP", os.path.join("dados", "comprovantes"))
PASTA_EXTRATOS = os.getenv("PASTA_EXTRATOS", os.path.join("dados", "extratos"))
PLANILHA = os.getenv("PLANILHA", os.path.join("dados", "fluxo_de_caixa.xlsx"))
PASTA_SAIDA = os.getenv("PASTA_SAIDA", os.path.join("dados", "saida"))

# ── Conta bancária ────────────────────────────────────────────
BANCO = os.getenv("BANCO", "Bradesco")
CONTA = os.getenv("CONTA", "")

# ── Regras específicas da empresa ─────────────────────────────
# Nome da empresa que aparece no cabeçalho das páginas do extrato (linha ignorada)
EMPRESA_CABECALHO_PDF = os.getenv("EMPRESA_CABECALHO_PDF", "").strip().upper()

# Fornecedor que paga 1 PIX no extrato correspondente a N linhas na planilha
FORNECEDOR_AGRUPADO = os.getenv("FORNECEDOR_AGRUPADO", "").strip().upper()

# Nomes de fornecedores PJ conhecidos (não confundir com PIX de funcionário CLT)
FORNECEDORES_PJ = _lista("FORNECEDORES_PJ")

# Conciliação Bancária Automática

Pipeline em Python para conciliação bancária diária. Ele cruza comprovantes de pagamento (.txt), extratos bancários (PDF, layout Bradesco) e a planilha de fluxo de caixa (.xlsx). A classificação comprovante × extrato usa a API do Claude (Anthropic).

## O que faz

1. Lê os comprovantes (`leitor_txt.py`), o extrato em PDF (`leitor_pdf.py`) e a planilha de fluxo de caixa (`leitor_excel.py`).
2. Classifica cada comprovante contra o extrato com IA, em lotes (`claude_service.py`). Os status possíveis são: `CONCILIADO`, `PROVAVEL_CONCILIADO`, `PENDENTE`, `DIVERGENTE` e `DUPLICIDADE`.
3. Casa cada item com a planilha de fluxo de caixa usando regras em Python (`conciliador_planilha.py`). Isso inclui dois casos especiais: o fornecedor agrupado (1 PIX equivale a N linhas) e a folha CLT (N PIX equivalem a 1 linha).
4. Gera uma planilha incremental com saldo anterior e saldo final (`gerador_saida.py`) e um relatório em texto (`relatorio_saida.py`). O saldo diário fica salvo em `saldos.json` (`saldo_diario.py`).

## Como usar

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env          # preencha chave da API, caminhos e regras
python main.py
```

Todas as configurações sensíveis ficam no `.env`, que não é versionado. Isso inclui a chave da API, os caminhos das pastas, a conta bancária e os nomes de fornecedores.

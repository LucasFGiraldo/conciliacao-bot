import os
import json
import requests

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL as MODEL


def chamar_claude(prompt, max_tokens=8000):
    if not ANTHROPIC_API_KEY:
        raise ValueError("Chave da API não definida. Defina ANTHROPIC_API_KEY no arquivo .env.")
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    resposta = requests.post(url, headers=headers, data=json.dumps(payload))
    try:
        dados = resposta.json()
    except Exception:
        raise ValueError(f"API retornou nao-JSON ({resposta.status_code}): {resposta.text[:300]}")
    if resposta.status_code != 200:
        raise ValueError(f"Erro na API ({resposta.status_code}): {dados.get('error', dados)}")
    stop_reason = dados.get("stop_reason")
    if stop_reason and stop_reason != "end_turn":
        print(f"    [API] stop_reason={stop_reason}")
    content = dados.get("content", [])
    if not content:
        raise ValueError(f"API retornou content vazio: {dados}")
    texto_blocks = [b for b in content if b.get("type") == "text"]
    if not texto_blocks:
        raise ValueError(f"Sem bloco de texto na resposta: {content}")
    return texto_blocks[0]["text"]


def extrair_json_da_resposta(resposta):
    resposta = resposta.strip()
    for marcador in ["```json", "```"]:
        resposta = resposta.replace(marcador, "")
    inicio = resposta.find("{")
    fim = resposta.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError("Nenhum JSON encontrado na resposta da IA.")
    return resposta[inicio:fim + 1]


def preparar_registros_planilha(registros_planilha, lote_comprovantes, extratos_lote=None):
    """
    Filtra registros da planilha pela coluna PAGAMENTO usando EXATAMENTE
    as datas dos comprovantes e extratos do lote (+-1 dia de margem).
    Evita enviar milhares de registros para a API.
    """
    from datetime import timedelta, date, datetime

    def norm(d):
        if d is None:
            return None
        return d.date() if hasattr(d, "date") else d

    # Coleta datas dos comprovantes
    datas = set()
    for c in lote_comprovantes:
        d = norm(c.get("data_pagamento"))
        if d:
            datas.add(d)

    # Coleta datas dos extratos
    for e in (extratos_lote or []):
        d = norm(e.get("data"))
        if d:
            datas.add(d)

    if not datas:
        print("    [planilha] Nenhuma data identificada — enviando sem registros.")
        return []

    # Margem estrita de 3 dias para cada lado do periodo analisado
    MARGEM_DIAS = 3
    data_min = min(datas) - timedelta(days=MARGEM_DIAS)
    data_max = max(datas) + timedelta(days=MARGEM_DIAS)
    print(f"    [planilha] Filtrando coluna PAGAMENTO: {data_min} a {data_max} "
          f"(margem ±{MARGEM_DIAS} dias)")

    def data_no_periodo(d):
        """Retorna True se a data esta dentro do periodo analisado."""
        if d is None:
            return False
        return data_min <= d <= data_max

    resultado = []
    for r in registros_planilha:
        if not isinstance(r, dict):
            continue
        conta = str(r.get("CONTA", "")).upper().strip()
        conta_norm = conta.replace("Í","I").replace("Ú","U").replace("Á","A")
        if "SAIDA" not in conta_norm:
            continue
        valor = r.get("valor_padrao")
        if not valor:
            continue
        # Fonte primaria: data_pagamento_padrao
        data_pag = norm(r.get("data_pagamento_padrao"))
        # Fallback: vencimento SO se estiver dentro do periodo
        # (evita puxar lancamentos de meses anteriores)
        if not data_no_periodo(data_pag):
            data_venc = norm(r.get("data_vencimento_padrao"))
            if data_no_periodo(data_venc):
                data_pag = data_venc
            else:
                continue

        resultado.append({
            "linha_excel":    r.get("linha_excel"),
            "empresa":        r.get("EMPRESA"),
            "favorecido":     r.get("DESPESAS") or r.get("REFERENTE"),
            "valor":          valor,
            "data_pagamento": str(data_pag),
            "plano_contas":   r.get("plano_contas_padrao") or r.get("PLANO DE CONTAS"),
            "situacao":       r.get("SITUACAO PAGTO") or r.get("SITUAÇÃO PAGTO"),
            "banco":          r.get("BANCO"),
        })

    print(f"    [planilha] {len(resultado)} registro(s) selecionado(s) para o prompt.")
    return resultado


def filtrar_extratos_por_comprovantes(extratos, comprovantes, dias_margem=2):
    """
    Filtra extratos para incluir apenas os relevantes ao lote de comprovantes.
    Usa as datas dos comprovantes como referencia +- dias_margem.
    """
    from datetime import timedelta, datetime, date
    datas = set()
    for c in comprovantes:
        d = c.get("data_pagamento")
        if d:
            if hasattr(d, "date"):
                d = d.date()
            datas.add(d)
    if not datas:
        return extratos
    data_min = min(datas) - timedelta(days=dias_margem)
    data_max = max(datas) + timedelta(days=dias_margem)
    filtrados = []
    for e in extratos:
        de = e.get("data")
        if de:
            if hasattr(de, "date"):
                de = de.date()
            if data_min <= de <= data_max:
                filtrados.append(e)
    return filtrados


def conciliar_com_claude(comprovantes, extratos, saldo_anterior=None):
    # Planilha processada em Python — nao enviada para a IA

    secao_saldo = ""
    if saldo_anterior:
        secao_saldo = f"""
SALDO ANTERIOR REGISTRADO:
  Banco: {saldo_anterior.get('banco')}
  Conta: {saldo_anterior.get('conta')}
  Saldo final do dia anterior: R$ {saldo_anterior.get('saldo_final'):,.2f}
  Use esse valor como referência para validar se os lançamentos do extrato
  são consistentes com a continuidade do saldo esperado.
"""


    # Filtra extratos para o periodo dos comprovantes do lote
    extratos = filtrar_extratos_por_comprovantes(extratos, comprovantes)
    print(f"    [IA] Extratos filtrados: {len(extratos)} lancamentos")

    prompt = f"""
Você é um especialista em conciliação financeira bancária.
Sua tarefa é comparar cada comprovante com os lançamentos do extrato bancário.

{secao_saldo}

═══════════════════════════════════════════════════
REGRAS DE CLASSIFICAÇÃO — EXTRATO
═══════════════════════════════════════════════════

CONCILIADO
  Valor idêntico E favorecido compatível (mesmo nome ou abreviação reconhecível).

PROVÁVEL CONCILIADO
  Valor idêntico E favorecido compatível E data com diferença de até 2 dias úteis.

PENDENTE
  Nenhum lançamento do extrato corresponde a este comprovante.

DIVERGENTE
  Existe lançamento para o mesmo favorecido, mas o valor é diferente.

DUPLICIDADE — critério OBRIGATÓRIO (todos simultaneamente):
  1. Mesmo valor numérico
  2. Mesmo favorecido (mesma pessoa/empresa)
  3. Mesma data (até 1 dia de diferença)
  IMPORTANTE: funcionários diferentes com mesmo salário NÃO são duplicidade.
  IMPORTANTE: fornecedores diferentes com mesmo valor NÃO são duplicidade.
  Em caso de dúvida, prefira CONCILIADO.



═══════════════════════════════════════════════════
REGRAS OBRIGATÓRIAS
═══════════════════════════════════════════════════
1. Retorne EXATAMENTE um item por comprovante, na mesma ordem.
2. Não crie itens para lançamentos sem comprovante correspondente.
3. Não invente valores, datas ou totais.
4. Baseie datas da planilha sempre em "data_pagamento", nunca em "data_vencimento".
5. Responda SOMENTE com JSON — sem Markdown, sem texto fora do JSON.

═══════════════════════════════════════════════════
FORMATO DE RESPOSTA
═══════════════════════════════════════════════════
{{
  "resumo": {{
    "total_comprovantes": <int>,
    "total_extratos": <int>,
    "total_planilha": <int>,
    "conciliados": <int>,
    "provaveis": <int>,
    "pendentes": <int>,
    "divergentes": <int>,
    "duplicidades": <int>,
    "extratos_sem_comprovante": <int>,
    "motivos_sem_comprovante": ["<tipo>"]
  }},
  "itens": [
    {{
      "favorecido": "<nome>",
      "valor": <número>,
      "data_comprovante": "<data>",
      "data_extrato": "<data ou vazio>",
      "status": "<CONCILIADO | PROVÁVEL CONCILIADO | PENDENTE | DIVERGENTE | DUPLICIDADE>",
      "justificativa": "<explicação>",
    }}
  ]
}}

═══════════════════════════════════════════════════
DADOS DE ENTRADA
═══════════════════════════════════════════════════

COMPROVANTES ({len(comprovantes)} registros):
{json.dumps(comprovantes, ensure_ascii=False, default=str)}

EXTRATOS ({len(extratos)} lancamentos — filtrados pelo periodo do lote):
{json.dumps(extratos, ensure_ascii=False, default=str)}

"""

    resposta = chamar_claude(prompt)
    try:
        return json.loads(extrair_json_da_resposta(resposta))
    except Exception:
        print("Erro ao converter resposta da IA:")
        print(resposta)
        raise


def gerar_relatorio_com_claude(resultado_conciliacao):
    resumo = resultado_conciliacao.get("resumo", {})
    escopo = resultado_conciliacao.get("escopo", {})
    itens = resultado_conciliacao.get("itens", [])

    pendentes    = [i for i in itens if "PENDENTE"   in i.get("status", "").upper()]
    divergentes  = [i for i in itens if "DIVERGENTE" in i.get("status", "").upper()]
    provaveis    = [i for i in itens if "PROV"       in i.get("status", "").upper()]
    conciliados  = [i for i in itens if i.get("status", "").upper() == "CONCILIADO"]
    duplicidades = [i for i in itens if "DUPLIC"     in i.get("status", "").upper()]
    nao_plan     = [i for i in itens if i.get("status_planilha") == "NAO_ENCONTRADO_PLANILHA"]

    total_comp = resumo.get("total_comprovantes", 0)
    total_ext  = resumo.get("total_extratos", 0)
    total_plan = resumo.get("total_planilha", 0)
    sem_comp   = resumo.get("extratos_sem_comprovante", max(0, total_ext - total_comp))
    motivos    = resumo.get("motivos_sem_comprovante", [])
    diferenca  = total_ext - total_comp

    contexto_diferenca = ""
    if diferenca != 0:
        contexto_diferenca = f"""
DIFERENÇA DE VOLUMES:
  Comprovantes: {total_comp} | Extratos: {total_ext} | Planilha: {total_plan}
  Diferença extrato vs comprovantes: {diferenca}
  Lançamentos sem comprovante: {sem_comp}
  Tipos: {motivos or 'ver análise'}
"""

    dados = {
        "escopo": escopo,
        "resumo": resumo,
        "resumo_planilha": resultado_conciliacao.get("resumo_planilha", {}),
        "contexto_diferenca": contexto_diferenca,
        "amostra_conciliados": [{"fav": i.get("favorecido"), "val": i.get("valor")} for i in conciliados[:3]],
        "pendentes": [{"fav": i.get("favorecido"), "val": i.get("valor"), "just": str(i.get("justificativa",""))[:80]} for i in pendentes[:10]],
        "provaveis": [{"fav": i.get("favorecido"), "val": i.get("valor")} for i in provaveis[:10]],
        "divergentes": [{"fav": i.get("favorecido"), "val": i.get("valor")} for i in divergentes[:10]],
        "duplicidades": [{"fav": i.get("favorecido"), "val": i.get("valor")} for i in duplicidades[:5]],
        "nao_encontrados_planilha": [{"fav": i.get("favorecido"), "val": i.get("valor")} for i in nao_plan[:10]],
    }

    prompt = f"""
Você é um analista financeiro sênior. Redija um relatório formal de conciliação bancária
com base EXCLUSIVAMENTE nos dados abaixo. Não invente totais ou percentuais.

ESTRUTURA OBRIGATÓRIA:
1. Objetivo
2. Escopo (data, tipo: diária ou parcial)
3. Fontes analisadas
4. Resumo quantitativo — extrato bancário
5. Resumo quantitativo — planilha de fluxo de caixa
6. Análise de Diferença de Volumes (omitir se não houver diferença)
7. Ocorrências relevantes
8. Pendências (favorecido + valor, até o limite do resumo)
9. Itens não encontrados na planilha de fluxo
10. Divergências
11. Duplicidades detectadas
12. Conclusão executiva
13. Recomendações

DADOS:
{json.dumps(dados, ensure_ascii=False, default=str)}
"""
    return chamar_claude(prompt, max_tokens=6000)

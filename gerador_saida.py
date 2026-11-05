"""
gerador_saida.py — Planilha de conciliacao unica e incremental.

Estrutura de cada execucao na planilha:
  [linha azul claro  — SALDO ANTERIOR]  <- saldo mais recente do saldos.json
  [lancamentos da execucao]
  [linha verde claro — SALDO FINAL]     <- saldo capturado no extrato desta execucao
"""
import os
import json
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

NOME_PLANILHA = "planilha_conciliacao.xlsx"
NOME_ABA      = "Conciliacao"   # sem acento para evitar erros de encoding no Windows

COLUNAS = [
    "data_execucao", "favorecido", "valor", "data_comprovante",
    "data_extrato", "status", "justificativa",
    "status_planilha", "linha_excel_planilha", "favorecido_planilha",
    "data_planilha", "plano_contas_planilha", "justificativa_planilha",
    "descricao_planilha", "observacao_planilha",
]

IDX_DATA       = COLUNAS.index("data_execucao")
IDX_FAVORECIDO = COLUNAS.index("favorecido")
IDX_VALOR      = COLUNAS.index("valor")
IDX_STATUS     = COLUNAS.index("status")
IDX_JUST       = COLUNAS.index("justificativa")

COR_STATUS = {
    "CONCILIADO":          "C6EFCE",
    "PROVAVEL_CONCILIADO": "FFEB9C",
    "PENDENTE":            "FCE4D6",
    "DIVERGENTE":          "FFC7CE",
    "DUPLICIDADE":         "D9D9D9",
    "SEM_COMPROVANTE":     "E2EFDA",
}
COR_STATUS_PLANILHA = {
    "ENCONTRADO_PLANILHA":     "00B050",
    "PROVAVEL_PLANILHA":       "FFA500",
    "NAO_ENCONTRADO_PLANILHA": "FF0000",
}
COR_SALDO_ANTERIOR = "D6E4F0"
COR_SALDO_FINAL    = "D5E8D4"
COR_SEP_FONTE      = "1F4E78"

THIN      = Side(style="thin",   color="CCCCCC")
THICK     = Side(style="medium", color="1F4E78")
BORDER    = Border(left=THIN,  right=THIN,  top=THIN,  bottom=THIN)
BORDER_SEP= Border(left=THICK, right=THICK, top=THICK, bottom=THICK)


def _fill(cor):
    return PatternFill(start_color=cor, end_color=cor, fill_type="solid")


def _caminho_planilha(pasta_saida):
    return os.path.join(pasta_saida, NOME_PLANILHA)


def _aplicar_cabecalho(ws):
    for cell in ws[1]:
        cell.fill      = _fill("1F4E78")
        cell.font      = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = BORDER
    ws.row_dimensions[1].height = 30


def _ajustar_colunas(ws):
    larguras = {
        "data_execucao": 16, "favorecido": 35, "valor": 16,
        "data_comprovante": 16, "data_extrato": 14, "status": 22,
        "justificativa": 50, "status_planilha": 26,
        "linha_excel_planilha": 10, "favorecido_planilha": 35,
        "data_planilha": 14, "plano_contas_planilha": 30,
        "justificativa_planilha": 50, "descricao_planilha": 40,
        "observacao_planilha": 40,
    }
    for i, col in enumerate(COLUNAS, 1):
        ws.column_dimensions[get_column_letter(i)].width = larguras.get(col, 18)


def _estilizar_linha_normal(ws, row_idx, item):
    status      = str(item.get("status", "")).upper().strip()
    status_plan = str(item.get("status_planilha", "")).upper().strip()
    cor_linha   = COR_STATUS.get(status)

    for col_idx, col in enumerate(COLUNAS, 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.border    = BORDER
        cell.alignment = Alignment(
            wrap_text=True, vertical="top",
            horizontal="center" if col in (
                "valor", "data_comprovante", "data_extrato",
                "data_planilha", "linha_excel_planilha"
            ) else "left"
        )
        if cor_linha:
            cell.fill = _fill(cor_linha)
        if col == "status_planilha" and status_plan in COR_STATUS_PLANILHA:
            cell.fill = _fill(COR_STATUS_PLANILHA[status_plan])
            cell.font = Font(color="FFFFFF", bold=True)

    linhas_texto = max(
        str(item.get(c, "") or "").count("\n") + 1
        for c in ("justificativa", "justificativa_planilha", "descricao_planilha")
    )
    ws.row_dimensions[row_idx].height = max(linhas_texto * 15, 18)


def _inserir_linha_saldo(ws, row_idx, tipo, banco, conta, saldo, data_ref, execucao):
    cor = COR_SALDO_ANTERIOR if "ANTERIOR" in tipo else COR_SALDO_FINAL
    valores = [""] * len(COLUNAS)
    valores[IDX_DATA]       = execucao
    valores[IDX_FAVORECIDO] = f">>> {tipo} — {banco} | Conta {conta}"
    valores[IDX_VALOR]      = saldo if saldo is not None else "N/D"
    valores[IDX_STATUS]     = tipo
    valores[IDX_JUST]       = f"Data referencia: {data_ref} | Registrado em: {execucao}"
    ws.append(valores)

    for col_idx in range(1, len(COLUNAS) + 1):
        cell           = ws.cell(row=row_idx, column=col_idx)
        cell.fill      = _fill(cor)
        cell.border    = BORDER_SEP
        cell.font      = Font(bold=True, color=COR_SEP_FONTE)
        cell.alignment = Alignment(
            horizontal="center" if col_idx == IDX_VALOR + 1 else "left",
            vertical="center",
        )
        if col_idx == IDX_VALOR + 1 and isinstance(saldo, float):
            cell.number_format = '#,##0.00'

    ws.row_dimensions[row_idx].height = 22


def _criar_ou_atualizar_aba_resumo(wb, resultado, execucao, saldo_anterior_val, saldo_final_val):
    if "Resumo" in wb.sheetnames:
        del wb["Resumo"]
    ws = wb.create_sheet("Resumo")
    resumo      = resultado.get("resumo", {})
    resumo_plan = resultado.get("resumo_planilha", {})

    ws.append(["Metrica", "Valor"])
    _aplicar_cabecalho(ws)

    def fmt(v):
        return f"R$ {v:,.2f}" if v is not None else "N/D"

    var = fmt(saldo_final_val - saldo_anterior_val) \
        if saldo_anterior_val is not None and saldo_final_val is not None else "N/D"

    linhas = [
        ("Data de execucao",                  execucao),
        ("--- SALDOS ---",                    ""),
        ("Saldo anterior",                    fmt(saldo_anterior_val)),
        ("Saldo final (esta execucao)",        fmt(saldo_final_val)),
        ("Variacao",                          var),
        ("--- EXTRATO ---",                   ""),
        ("Comprovantes processados",          resumo.get("total_comprovantes_processados")),
        ("Conciliados",                       resumo.get("conciliados")),
        ("Provaveis",                         resumo.get("provaveis")),
        ("Pendentes",                         resumo.get("pendentes")),
        ("Divergentes",                       resumo.get("divergentes")),
        ("Duplicidades",                      resumo.get("duplicidades")),
        ("--- FLUXO DE CAIXA ---",            ""),
        ("Encontrados na planilha",           resumo_plan.get("encontrados")),
        ("Provaveis na planilha",             resumo_plan.get("provaveis")),
        ("Nao encontrados na planilha",       resumo_plan.get("nao_encontrados")),
    ]
    for linha in linhas:
        ws.append(linha)

    ws.column_dimensions["A"].width = 45
    ws.column_dimensions["B"].width = 22


def _gerar_linhas_via_ia(itens, execucao, chamar_claude_fn):
    # Envia apenas os campos essenciais para economizar tokens
    itens_compactos = [
        {
            "favorecido": item.get("favorecido", ""),
            "valor": item.get("valor", 0),
            "data_comprovante": item.get("data_comprovante", ""),
            "data_extrato": item.get("data_extrato", ""),
            "status": item.get("status", ""),
            "justificativa": item.get("justificativa", ""),
            "status_planilha": item.get("status_planilha", ""),
            "linha_excel_planilha": item.get("linha_excel_planilha") or item.get("linha_excel"),
            "favorecido_planilha": item.get("favorecido_planilha", ""),
            "data_planilha": item.get("data_planilha") or item.get("data_pagamento_planilha", ""),
            "plano_contas_planilha": item.get("plano_contas_planilha") or item.get("plano_contas", ""),
            "justificativa_planilha": item.get("justificativa_planilha", ""),
            "descricao_planilha": item.get("descricao_planilha", ""),
            "observacao_planilha": (item.get("observacao_planilha") or item.get("observacao_planilha", ""))[:200],
        }
        for item in itens
    ]
    prompt = (
        f"Formate {len(itens_compactos)} itens de conciliacao como linhas de planilha.\n"
        f"data_execucao de todos = '{execucao}'\n"
        "Retorne JSON: {\"linhas\":[{campos}]} com EXATAMENTE um objeto por item.\n"
        "Campos: data_execucao,favorecido,valor,data_comprovante,data_extrato,status,"
        "justificativa,status_planilha,linha_excel_planilha,favorecido_planilha,"
        "data_planilha,plano_contas_planilha,justificativa_planilha,descricao_planilha,observacao_planilha\n"
        "Datas em DD/MM/YYYY. Valores numericos. Status exatamente como recebido.\n"
        "Responda SOMENTE JSON valido sem Markdown.\n\n"
        f"ITENS:\n" + json.dumps(itens_compactos, ensure_ascii=False, default=str)
    )
    resposta = chamar_claude_fn(prompt, max_tokens=6000)
    resposta = resposta.strip().replace("```json", "").replace("```", "")
    inicio = resposta.find("{")
    fim    = resposta.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError("IA nao retornou JSON valido.")
    return json.loads(resposta[inicio:fim + 1]).get("linhas", [])


def salvar_excel_conciliacao(
    resultado, pasta_saida,
    chamar_claude_fn=None,
    saldo_anterior_info=None,
    saldo_final_info=None,
):
    os.makedirs(pasta_saida, exist_ok=True)
    itens = resultado.get("itens", [])
    if not itens:
        print("Nenhum item para salvar.")
        return

    execucao = datetime.now().strftime("%d/%m/%Y %H:%M")
    caminho  = _caminho_planilha(pasta_saida)

    # Formata linhas via IA
    linhas_formatadas = []
    if chamar_claude_fn:
        print(f"\nFormatando {len(itens)} linhas via IA...")
        LOTE_IA = 8
        total_lotes = -(-len(itens) // LOTE_IA)
        for i in range(0, len(itens), LOTE_IA):
            lote = itens[i:i + LOTE_IA]
            print(f"  Lote IA planilha {i // LOTE_IA + 1}/{total_lotes}...")
            try:
                linhas_formatadas.extend(_gerar_linhas_via_ia(lote, execucao, chamar_claude_fn))
            except Exception as e:
                print(f"  Erro IA: {e}. Usando dados brutos.")
                for item in lote:
                    linhas_formatadas.append({col: item.get(col, "") for col in COLUNAS})
    else:
        for item in itens:
            linhas_formatadas.append({col: item.get(col, "") for col in COLUNAS})

    # Abre ou cria planilha
    if os.path.exists(caminho):
        wb = load_workbook(caminho)
        ws = wb[NOME_ABA] if NOME_ABA in wb.sheetnames else wb.active
        print(f"Planilha existente. Ultima linha atual: {ws.max_row}.")
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = NOME_ABA
        ws.append(COLUNAS)
        _aplicar_cabecalho(ws)
        _ajustar_colunas(ws)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUNAS))}1"
        print("Nova planilha criada.")

    # 1. Linha SALDO ANTERIOR
    row_ant = ws.max_row + 1
    if saldo_anterior_info:
        _inserir_linha_saldo(
            ws, row_ant, "SALDO ANTERIOR",
            saldo_anterior_info.get("banco", ""),
            saldo_anterior_info.get("conta", ""),
            saldo_anterior_info.get("saldo_final"),
            str(saldo_anterior_info.get("data", "")),
            execucao,
        )
    else:
        _inserir_linha_saldo(ws, row_ant, "SALDO ANTERIOR", "N/D", "N/D", None, "Sem registro", execucao)
    print(f"  Linha SALDO ANTERIOR inserida (linha {row_ant}).")

    # 2. Lancamentos
    primeira_linha_dados = ws.max_row + 1
    for item in linhas_formatadas:
        ws.append([item.get(col, "") for col in COLUNAS])
    for row_idx in range(primeira_linha_dados, ws.max_row + 1):
        idx = row_idx - primeira_linha_dados
        if idx < len(linhas_formatadas):
            _estilizar_linha_normal(ws, row_idx, linhas_formatadas[idx])
    print(f"  {len(linhas_formatadas)} lancamento(s) inserido(s) (linhas {primeira_linha_dados}-{ws.max_row}).")

    # 3. Linha SALDO FINAL
    row_fin = ws.max_row + 1
    if saldo_final_info:
        _inserir_linha_saldo(
            ws, row_fin, "SALDO FINAL",
            saldo_final_info.get("banco", ""),
            saldo_final_info.get("conta", ""),
            saldo_final_info.get("saldo_final"),
            str(saldo_final_info.get("data", "")),
            execucao,
        )
    else:
        _inserir_linha_saldo(ws, row_fin, "SALDO FINAL", "N/D", "N/D", None, "Nao capturado", execucao)
    print(f"  Linha SALDO FINAL inserida (linha {row_fin}).")

    # Aba Resumo
    val_ant = saldo_anterior_info.get("saldo_final") if saldo_anterior_info else None
    val_fin = saldo_final_info.get("saldo_final")    if saldo_final_info    else None
    _criar_ou_atualizar_aba_resumo(wb, resultado, execucao, val_ant, val_fin)

    # Garante ordem das abas
    if NOME_ABA in wb.sheetnames and wb.sheetnames[0] != NOME_ABA:
        wb.move_sheet(NOME_ABA, offset=-wb.sheetnames.index(NOME_ABA))

    wb.save(caminho)
    print(f"\nPlanilha salva: {caminho}")
    print(f"Total de linhas (incluindo historico e separadores): {ws.max_row - 1}")

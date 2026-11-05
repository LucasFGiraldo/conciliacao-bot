from leitor_txt import ler_comprovantes_txt
from leitor_pdf import ler_extratos_pdf
from claude_service import conciliar_com_claude, gerar_relatorio_com_claude, preparar_registros_planilha, chamar_claude
from gerador_saida import salvar_excel_conciliacao
from relatorio_saida import salvar_relatorio_txt
from conciliador_planilha import conciliar_resultado_com_planilha
from saldo_diario import registrar_saldo, obter_saldo_anterior, obter_saldo_mais_recente, resumo_saldos
from config import PASTA_COMP, PASTA_EXTRATOS, PASTA_SAIDA, PLANILHA, BANCO, CONTA
from datetime import timedelta, date, datetime
from collections import Counter
from leitor_excel import ler_planilha
import time
import re   

TAMANHO_LOTE = 10


def filtrar_extratos_por_lote(lote_comprovantes, extratos, dias_tolerancia=2):
    datas = []
    for c in lote_comprovantes:
        data = c.get("data_pagamento")
        if data:
            datas.append(data.date() if hasattr(data, "date") else data)
    if not datas:
        return extratos
    data_min = min(datas) - timedelta(days=dias_tolerancia)
    data_max = max(datas) + timedelta(days=dias_tolerancia)
    return [e for e in extratos if e.get("data") and data_min <= e["data"].date() <= data_max]


def normalizar_status(status):
    status = str(status or "").upper().strip()
    if status == "CONCILIADO":
        return "CONCILIADO"
    if "PROV" in status:
        return "PROVAVEL_CONCILIADO"
    if "PEND" in status:
        return "PENDENTE"
    if "DIVERG" in status:
        return "DIVERGENTE"
    if "DUPLIC" in status:
        return "DUPLICIDADE"
    return "PENDENTE"


def contar_status(itens, status_exato):
    return sum(1 for item in itens if normalizar_status(item.get("status")) == status_exato)


def extrair_saldo_do_extrato(extratos):
    """
    Retorna (banco, conta, data_ultimo_lancamento, saldo_final) a partir dos
    lançamentos extraídos. O saldo final é inferido do último lançamento do dia
    mais recente — o leitor_pdf.py armazena o saldo resultante em 'saldo_apos'.
    Se não disponível, retorna None.
    """
    if not extratos:
        return None, None, None, None

    # Ordena por data e pega o último
    com_data = [e for e in extratos if e.get("data")]
    if not com_data:
        return None, None, None, None

    ultimo = max(com_data, key=lambda e: e["data"])
    banco = BANCO  # definido no .env (config.py)
    conta = CONTA
    data_ultimo = ultimo["data"].date()

    # saldo_apos é opcional; se leitor_pdf não o expõe, retorna None
    saldo = ultimo.get("saldo_apos")
    return banco, conta, data_ultimo, saldo


def executar_conciliacao_diaria():
    print("=" * 60)
    print("  CONCILIAÇÃO BANCÁRIA DIÁRIA")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    # ── 0. SALDO DO DIA ANTERIOR ──────────────────────────────
    print("\n[0] Verificando saldo do dia anterior...")
    resumo_saldos()

    # ── 1. LEITURA DOS DADOS ──────────────────────────────────
    print("[1] Lendo comprovantes...")
    comprovantes = ler_comprovantes_txt(PASTA_COMP)
    print(f"    {len(comprovantes)} comprovante(s) encontrado(s).")

    print("[1] Lendo extratos PDF...")
    extratos = ler_extratos_pdf(PASTA_EXTRATOS)
    print(f"    {len(extratos)} lançamento(s) de extrato encontrado(s).")

    print("[1] Lendo planilha de fluxo de caixa...")
    cabecalho_planilha, registros_planilha = ler_planilha(PLANILHA)
    print(f"    {len(registros_planilha)} registro(s) na planilha.")

    # ── 2. SALDO ANTERIOR (contexto para a IA) ────────────────
    banco_ext, conta_ext, data_ultimo_ext, _ = extrair_saldo_do_extrato(extratos)
    # Busca o saldo registrado ANTES da data do extrato atual
    # (nao o mais recente absoluto, para evitar usar o saldo do mesmo dia)
    if data_ultimo_ext:
        saldo_anterior = obter_saldo_anterior(data_ultimo_ext, banco_ext, conta_ext)
    else:
        saldo_anterior = obter_saldo_mais_recente(banco_ext, conta_ext)
    if saldo_anterior:
        print(f"\n    Saldo anterior encontrado: "
              f"{saldo_anterior.get('banco')} | {saldo_anterior.get('conta')} | "
              f"R$ {saldo_anterior.get('saldo_final'):,.2f} "
              f"(data: {saldo_anterior.get('data')})")
    else:
        print("    Nenhum saldo anterior registrado para este banco/conta.")

    # ── 3. PROCESSAMENTO EM LOTES ─────────────────────────────
    print("\n[2] Iniciando conciliação com IA...")
    todos_itens = []
    contagem_status = Counter()
    comprovantes_processados = 0

    if not comprovantes:
        print("    Nenhum comprovante disponível. Pulando etapa de IA.")
    else:
        total_lotes = -(-len(comprovantes) // TAMANHO_LOTE)
        for i in range(0, len(comprovantes), TAMANHO_LOTE):
            lote = comprovantes[i:i + TAMANHO_LOTE]
            comprovantes_processados += len(lote)
            num_lote = i // TAMANHO_LOTE + 1

            print(f"\n    Lote {num_lote}/{total_lotes} ({len(lote)} comprovantes)...")

            extratos_lote = filtrar_extratos_por_lote(lote, extratos)
            planilha_lote = preparar_registros_planilha(registros_planilha, lote, extratos_lote)

            print(f"      Extratos no lote: {len(extratos_lote)}")
            print(f"      Registros planilha no lote: {len(planilha_lote)}")

            # Planilha processada em Python (conciliador_planilha.py) — nao envia para IA
            resultado_lote = conciliar_com_claude(
                lote, extratos_lote,
                saldo_anterior=saldo_anterior
            )
            itens_lote = resultado_lote.get("itens", [])

            # Garante cardinalidade 1:1
            if len(itens_lote) > len(lote):
                itens_lote = itens_lote[:len(lote)]
            if len(itens_lote) < len(lote):
                for comp in lote[len(itens_lote):]:
                    itens_lote.append({
                        "favorecido": comp.get("favorecido"),
                        "valor": comp.get("valor"),
                        "data_comprovante": str(comp.get("data_pagamento", "")),
                        "data_extrato": "",
                        "status": "PENDENTE",
                        "justificativa": "Item não processado pela IA; marcado como pendente.",
                        "status_planilha": "NAO_ENCONTRADO_PLANILHA",
                        "linha_excel_planilha": None,
                        "favorecido_planilha": None,
                        "data_planilha": None,
                        "plano_contas_planilha": None,
                        "justificativa_planilha": "Item não processado pela IA.",
                    })

            for item in itens_lote:
                item["status"] = normalizar_status(item.get("status"))

            todos_itens.extend(itens_lote)
            contagem_status = Counter(
                item.get("status", "SEM_STATUS").upper() for item in todos_itens
            )

            print(f"      Acumulado: {len(todos_itens)} item(s). Status: {dict(contagem_status)}")

            if num_lote < total_lotes:
                print("      Aguardando 45s (limite de API)...")
                time.sleep(45)

    # ── 4. RESULTADO FINAL ────────────────────────────────────
    resultado_final = {
        "escopo": {
            "tipo": "conciliacao_diaria",
            "data_execucao": datetime.now().isoformat(),
            "total_comprovantes_processados": comprovantes_processados,
            "total_extratos": len(extratos),
            "total_planilha": len(registros_planilha),
            "tamanho_lote": TAMANHO_LOTE,
        },
        "itens": todos_itens,
        "resumo": {
            "total_comprovantes_processados": comprovantes_processados,
            "total_comprovantes_disponiveis": len(comprovantes),
            "total_extratos_disponiveis": len(extratos),
            "total_planilha_disponiveis": len(registros_planilha),
            "conciliados":  contar_status(todos_itens, "CONCILIADO"),
            "provaveis":    contar_status(todos_itens, "PROVAVEL_CONCILIADO"),
            "pendentes":    contar_status(todos_itens, "PENDENTE"),
            "divergentes":  contar_status(todos_itens, "DIVERGENTE"),
            "duplicidades": contar_status(todos_itens, "DUPLICIDADE"),
        },
    }

    print("\n[3] Conciliando com fluxo de caixa (pós-IA)...")
    resultado_final = conciliar_resultado_com_planilha(resultado_final, registros_planilha)
    print(f"    Resumo planilha: {resultado_final.get('resumo_planilha')}")

    # ── 5. CAPTURAR SALDO FINAL ──────────────────────────────
    saldo_final_valor = None
    saldo_final_info  = None
    if banco_ext and data_ultimo_ext:
        com_data = [e for e in extratos if e.get("data")]
        if com_data:
            ultimo = max(com_data, key=lambda e: e["data"])
            saldo_final_valor = ultimo.get("saldo_apos")
            if saldo_final_valor is not None:
                saldo_final_info = {
                    "banco":       banco_ext,
                    "conta":       conta_ext,
                    "saldo_final": saldo_final_valor,
                    "data":        data_ultimo_ext,
                }

    saldo_anterior_info = None
    if saldo_anterior:
        saldo_anterior_info = {
            "banco":       saldo_anterior.get("banco"),
            "conta":       saldo_anterior.get("conta"),
            "saldo_final": saldo_anterior.get("saldo_final"),
            "data":        saldo_anterior.get("data", ""),
        }

    # ── 6. SALVAR PLANILHA (via IA) ──────────────────────────
    print("\n[4] Salvando planilha incremental (formatacao via IA)...")
    salvar_excel_conciliacao(
        resultado_final, PASTA_SAIDA,
        chamar_claude_fn    = chamar_claude,
        saldo_anterior_info = saldo_anterior_info,
        saldo_final_info    = saldo_final_info,
    )

    # ── 7. RELATORIO ─────────────────────────────────────────
    print("\n[5] Gerando relatorio com IA...")
    relatorio = gerar_relatorio_com_claude(resultado_final)
    salvar_relatorio_txt(relatorio, PASTA_SAIDA)

    # ── 8. REGISTRAR SALDO DO DIA ────────────────────────────
    print("\n[6] Registrando saldo do dia...")
    if saldo_final_valor is not None:
        registrar_saldo(data_ultimo_ext, banco_ext, conta_ext, saldo_final_valor)
    elif banco_ext and data_ultimo_ext:
        print("    saldo_apos nao disponivel. Registre manualmente:")
        print("    from saldo_diario import registrar_saldo; from datetime import date")
        print(f"    registrar_saldo(date({data_ultimo_ext.year},{data_ultimo_ext.month},{data_ultimo_ext.day}), '{banco_ext}', '{conta_ext}', <valor>)")
    else:
        print("    Banco/conta nao identificados. Registre o saldo manualmente.")

    print("\n" + "=" * 60)
    print("  CONCILIAÇÃO FINALIZADA COM SUCESSO")
    print("=" * 60)
    print(f"  Conciliados:  {resultado_final['resumo']['conciliados']}")
    print(f"  Prováveis:    {resultado_final['resumo']['provaveis']}")
    print(f"  Pendentes:    {resultado_final['resumo']['pendentes']}")
    print(f"  Divergentes:  {resultado_final['resumo']['divergentes']}")
    print(f"  Duplicidades: {resultado_final['resumo']['duplicidades']}")
    print("=" * 60)


if __name__ == "__main__":
    executar_conciliacao_diaria()
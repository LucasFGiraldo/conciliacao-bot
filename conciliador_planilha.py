from datetime import datetime, date, timedelta
import re

from config import FORNECEDOR_AGRUPADO, FORNECEDORES_PJ


def normalizar_texto(texto):
    if texto is None:
        return ""
    texto = str(texto).upper().strip()
    subs = {"Á":"A","À":"A","Ã":"A","Â":"A","É":"E","Ê":"E","Í":"I",
            "Ó":"O","Õ":"O","Ô":"O","Ú":"U","Ç":"C"}
    for antigo, novo in subs.items():
        texto = texto.replace(antigo, novo)
    texto = re.sub(r"[^A-Z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def converter_data(valor):
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d%m%Y"):
            try:
                return datetime.strptime(valor[:10], fmt).date()
            except Exception:
                pass
    return None


def valores_iguais(v1, v2, tolerancia=0.02):
    if v1 is None or v2 is None:
        return False
    try:
        return abs(float(v1) - float(v2)) <= tolerancia
    except Exception:
        return False


def datas_proximas(d1, d2, tolerancia_dias=3):
    d1 = converter_data(d1)
    d2 = converter_data(d2)
    if not d1 or not d2:
        return False
    return abs((d1 - d2).days) <= tolerancia_dias


def extrair_valor_planilha(linha):
    return (linha.get("valor_padrao")
            or linha.get("SAÍDA") or linha.get("SAIDA")
            or linha.get("ENTRADA"))


def extrair_descricao_planilha(linha):
    partes = [linha.get("DESPESAS"), linha.get("REFERENTE"), linha.get("PLANO DE CONTAS")]
    return normalizar_texto(" ".join(str(p) for p in partes if p))


def calcular_score_nome(favorecido, descricao):
    favorecido = normalizar_texto(favorecido)
    descricao  = normalizar_texto(descricao)
    if not favorecido or not descricao:
        return 0
    ignorar = {"LTDA","ME","EPP","SA","S","A","DE","DA","DO","DOS","DAS","E"}
    palavras = [p for p in favorecido.split() if len(p) >= 3 and p not in ignorar]
    if not palavras:
        return 0
    return sum(1 for p in palavras if p in descricao) / len(palavras)


def _data_efetiva(linha):
    """Retorna data_pagamento_padrao; se None, usa data_vencimento_padrao."""
    d = linha.get("data_pagamento_padrao") or linha.get("PAGAMENTO")
    if d is None:
        d = linha.get("data_vencimento_padrao") or linha.get("VENCIMENTO")
    return converter_data(d)


def _linhas_saida(planilha):
    """Retorna apenas linhas de saída válidas da planilha."""
    resultado = []
    for linha in planilha:
        if not isinstance(linha, dict):
            continue
        conta = normalizar_texto(linha.get("CONTA", ""))
        if conta != "SAIDA":
            continue
        if not extrair_valor_planilha(linha):
            continue
        resultado.append(linha)
    return resultado


# ── Caso fornecedor agrupado: 1 extrato → N linhas na planilha ──
# O extrato tem um único PIX para o fornecedor agrupado (FORNECEDOR_AGRUPADO
# no .env); a planilha tem N linhas detalhando o que ele pagou.
# A soma dessas linhas da planilha
# na mesma data deve bater com o valor do extrato.

def _e_linha_agrupada(linha):
    if not FORNECEDOR_AGRUPADO:
        return False
    despesas = normalizar_texto(linha.get("DESPESAS", ""))
    return despesas.startswith(FORNECEDOR_AGRUPADO)


def _tentar_match_agrupado(item, linhas_saida):
    """
    Tenta casar um item do fornecedor agrupado do extrato com as linhas dele na planilha.

    Logica com score combinado (data + valor):
    - Agrupa as linhas do fornecedor por data de pagamento/vencimento.
    - Para cada grupo (e combinacoes de 2 grupos), calcula um score que
      penaliza fortemente a distancia de data:
        score = penal_data + penal_valor
        penal_data  = dias_diff * 200   (R$200 por dia de diferenca)
        penal_valor = diff_valor
    - Escolhe o grupo com MENOR score total.
    - Aceita apenas se diff_valor <= TOLERANCIA_VALOR E dias_diff <= MAX_DIAS.
    - MAX_DIAS = 20 dias (nao aceita grupos de 2 meses atras).
    """
    favorecido = normalizar_texto(item.get("favorecido", ""))
    if not FORNECEDOR_AGRUPADO or FORNECEDOR_AGRUPADO not in favorecido:
        return None

    valor_item = abs(float(item.get("valor") or 0))
    data_item  = converter_data(item.get("data_comprovante") or item.get("data_extrato"))

    linhas_grupo_forn = [l for l in linhas_saida if _e_linha_agrupada(l)]
    if not linhas_grupo_forn:
        return None

    print(f"    [AGRUPADO] Valor extrato: R${valor_item:,.2f} | data: {data_item} | "
          f"{len(linhas_grupo_forn)} linhas do fornecedor na planilha")

    # Agrupa por data efetiva
    grupos = {}
    for linha in linhas_grupo_forn:
        dp = _data_efetiva(linha)
        if dp is not None:
            grupos.setdefault(dp, []).append(linha)

    TOLERANCIA_VALOR = max(valor_item * 0.10, 500.0)
    MAX_DIAS = 20          # maximo de dias de diferenca aceito
    PESO_DIA = 200.0       # penalidade por dia de diferenca (R$)

    melhor_score = float("inf")
    melhor = None
    melhor_linhas = None
    melhor_diff_val = float("inf")
    melhor_dias = None

    def avaliar_candidato(dp_ref, linhas_cand):
        nonlocal melhor_score, melhor, melhor_linhas, melhor_diff_val, melhor_dias
        soma = sum(abs(float(extrair_valor_planilha(l) or 0)) for l in linhas_cand)
        diff_val = abs(valor_item - soma)

        if diff_val > TOLERANCIA_VALOR:
            return  # valor muito diferente, nao considera

        if data_item and dp_ref:
            dias_diff = abs((dp_ref - data_item).days)
        else:
            dias_diff = 0

        if dias_diff > MAX_DIAS:
            return  # data muito distante, nao considera

        score = dias_diff * PESO_DIA + diff_val
        print(f"      candidato {dp_ref} ({len(linhas_cand)} linhas) "
              f"soma=R${soma:,.2f} diff_val=R${diff_val:,.2f} "
              f"dias={dias_diff} score={score:.0f}")

        if score < melhor_score:
            melhor_score = score
            melhor = (dp_ref, linhas_cand, soma, dias_diff <= 3)
            melhor_linhas = linhas_cand
            melhor_diff_val = diff_val
            melhor_dias = dias_diff

    # Avalia grupos individuais
    for dp, linhas_grupo in sorted(grupos.items()):
        avaliar_candidato(dp, linhas_grupo)

    # Avalia combinacoes de 2 grupos proximos entre si (maximo 10 dias entre eles)
    dps = sorted(grupos.keys())
    for i in range(len(dps)):
        for j in range(i + 1, len(dps)):
            dp1, dp2 = dps[i], dps[j]
            if abs((dp2 - dp1).days) > 10:
                continue  # grupos muito distantes entre si
            dp_ref = dp2  # usa a data mais recente como referencia
            linhas_comb = grupos[dp1] + grupos[dp2]
            avaliar_candidato(dp_ref, linhas_comb)

    if melhor is None:
        print(f"    [AGRUPADO] Nenhum candidato dentro de {MAX_DIAS} dias e tolerancia R${TOLERANCIA_VALOR:,.2f}")
        return None

    print(f"    [AGRUPADO] Escolhido: score={melhor_score:.0f} "
          f"diff_val=R${melhor_diff_val:,.2f} dias={melhor_dias}")

    dp, linhas_grupo, soma, data_ok = melhor
    status = "ENCONTRADO" if data_ok and melhor_diff_val < 1.0 else "PROVAVEL"
    linhas_excel = [l.get("linha_excel") for l in linhas_grupo]
    descricoes   = [str(l.get("DESPESAS", "")) for l in linhas_grupo]

    return {
        "status_planilha":         status,
        "linha_excel":             linhas_excel[0],
        "valor_planilha":          soma,
        "data_pagamento_planilha": str(dp),
        "descricao_planilha":      f"{FORNECEDOR_AGRUPADO} ({len(linhas_grupo)} linhas, soma R${soma:,.2f}): " + " | ".join(descricoes[:3]),
        "plano_contas":            linhas_grupo[0].get("plano_contas_padrao") or linhas_grupo[0].get("PLANO DE CONTAS"),
        "score_planilha":          85 if status == "ENCONTRADO" else 60,
        "observacao_planilha":     (
            f"Match agrupado: {len(linhas_grupo)} linha(s) somam R${soma:,.2f} "
            f"vs extrato R${valor_item:,.2f} (diff R${melhor_diff_val:,.2f} | dias={melhor_dias}). "
            f"Linhas Excel: {linhas_excel[:5]}"
        ),
    }


# ── Caso CLT: N extratos → 1 linha na planilha ───────────────
# Cada funcionário CLT tem um PIX individual no extrato.
# A planilha tem uma linha "FOLHA DE PAGAMENTO..." com a soma.
# O conciliador_planilha recebe um item por vez, então precisamos
# identificar quando o item pertence a um grupo CLT e usar
# a linha FOLHA como match, mesmo que o valor individual não bata.

def _e_linha_folha(linha):
    despesas = normalizar_texto(linha.get("DESPESAS", ""))
    return (despesas.startswith("FOLHA") or
            "FOLHA DE PAGAMENTO" in despesas or
            "ADIANTAMENTO DE SALARIO" in despesas)


def _tentar_match_clt(item, linhas_saida, todos_itens):
    """
    Para PIX individuais de funcionarios CLT, tenta casar com uma linha
    FOLHA DE PAGAMENTO / ADIANTAMENTO DE SALARIO da planilha.
    Criterio: linha FOLHA com data proxima e valor >= salario individual.
    Tolerancia de data progressiva: 3, 7, 15 dias.
    """
    favorecido = normalizar_texto(item.get("favorecido", ""))
    valor_item = abs(float(item.get("valor") or 0))
    data_item  = converter_data(item.get("data_comprovante") or item.get("data_extrato"))

    linhas_folha = [l for l in linhas_saida if _e_linha_folha(l)]
    if not linhas_folha:
        return None

    # Heuristica CLT: valor < R$15.000 e favorecido parece nome de pessoa fisica
    # Lista abrangente de termos que indicam pessoa juridica
    palavras_pj = [
        "LTDA", "COMPANY", "EIRELI", "EPP", "S A ", " SA ", "S.A",
        "INDUSTRIA", "COMERCIO", "SERVICES", "SOLUCOES", "SOLUÇÃO",
        "RETIFICA",
        "ADVOGADOS", "ADVOCACIA", "SOCIEDADE", "ASSOCIACAO", "ASSOCIAÇÃO",
        "SINDICATO", "INFORMATICA", "INFORMÁTICA",
        "EMPREENDIMENTOS", "EMPREENDI", "MARKETING", "PUBLICIDADE",
        "CACAMBAS", "HONORARIOS", "HONORÁRIOS",
    ] + FORNECEDORES_PJ + ([FORNECEDOR_AGRUPADO] if FORNECEDOR_AGRUPADO else [])
    favorecido_upper = favorecido.upper()
    pode_ser_clt = (
        valor_item < 15000 and
        not any(p in favorecido_upper for p in palavras_pj)
    )
    if not pode_ser_clt:
        return None

    melhor = None
    melhor_score = -1

    for tol_dias in [3, 7, 15]:
        for linha in linhas_folha:
            dp = _data_efetiva(linha)
            valor_folha = abs(float(extrair_valor_planilha(linha) or 0))

            # Data: aceita sem data ou dentro da tolerancia
            if dp and data_item and abs((dp - data_item).days) > tol_dias:
                continue
            # Folha deve ser >= salario individual
            if valor_folha < valor_item * 0.9:
                continue

            score = 40
            if dp and data_item:
                diff_dias = abs((dp - data_item).days)
                score += max(0, 20 - diff_dias * 2)
            if valor_folha >= valor_item * 3:
                score += 15  # folha claramente e soma de varios
            elif valor_folha >= valor_item * 2:
                score += 8

            if score > melhor_score:
                melhor_score = score
                melhor = (linha, dp, valor_folha)

        if melhor and melhor_score >= 50:
            break

    if melhor is None:
        return None

    linha, dp, valor_folha = melhor
    return {
        "status_planilha":         "PROVAVEL",
        "linha_excel":             linha.get("linha_excel"),
        "valor_planilha":          valor_folha,
        "data_pagamento_planilha": str(dp) if dp else "",
        "descricao_planilha":      linha.get("DESPESAS"),
        "plano_contas":            linha.get("plano_contas_padrao") or linha.get("PLANO DE CONTAS"),
        "score_planilha":          melhor_score,
        "observacao_planilha":     (
            f"Match CLT: salario individual R${valor_item:,.2f} associado "
            f"a folha R${valor_folha:,.2f} (linha {linha.get('linha_excel')}). "
            f"Data planilha: {dp}"
        ),
    }


# ── Match individual padrão ───────────────────────────────────

def encontrar_na_planilha(item, planilha, todos_itens=None):
    valor_item     = item.get("valor")
    favorecido_item = item.get("favorecido")
    data_item      = item.get("data_comprovante")

    linhas_saida = _linhas_saida(planilha)

    # 1. Tenta match agregado (fornecedor agrupado)
    resultado_agrupado = _tentar_match_agrupado(item, linhas_saida)
    if resultado_agrupado:
        return resultado_agrupado

    # 2. Tenta match individual padrão (valor exato)
    candidatos = []
    for linha in linhas_saida:
        valor_planilha = extrair_valor_planilha(linha)
        data_planilha  = linha.get("data_pagamento_padrao") or linha.get("PAGAMENTO")
        descricao      = extrair_descricao_planilha(linha)

        if not valores_iguais(valor_item, valor_planilha):
            continue

        score = 60  # valor bate
        data_ok  = datas_proximas(data_item, data_planilha, tolerancia_dias=3)
        score_nome = calcular_score_nome(favorecido_item, descricao)

        if data_ok:
            score += 25
        if score_nome >= 0.6:
            score += 15
        elif score_nome >= 0.3:
            score += 8

        candidatos.append({
            "linha": linha, "score": score,
            "data_ok": data_ok, "score_nome": score_nome,
        })

    if candidatos:
        candidatos.sort(key=lambda c: c["score"], reverse=True)
        melhor = candidatos[0]
        linha  = melhor["linha"]

        # Rejeita candidatos com data muito distante (> 20 dias)
        # Esses casos sao melhor classificados como NAO_ENCONTRADO
        # do que como PROVAVEL com data errada
        data_plan = _data_efetiva(linha)
        data_item_dt = converter_data(item.get("data_comprovante") or item.get("data_extrato"))
        if data_plan and data_item_dt:
            dias_diff = abs((data_plan - data_item_dt).days)
            if dias_diff > 20:
                # Data muito distante — nao e um match confiavel
                pass  # cai para match CLT ou NAO_ENCONTRADO abaixo
            else:
                status = "ENCONTRADO" if (melhor["data_ok"] and melhor["score_nome"] >= 0.3) else "PROVAVEL"
                return {
                    "status_planilha":         status,
                    "linha_excel":             linha.get("linha_excel"),
                    "valor_planilha":          extrair_valor_planilha(linha),
                    "data_pagamento_planilha": str(data_plan),
                    "descricao_planilha":      linha.get("DESPESAS"),
                    "plano_contas":            linha.get("plano_contas_padrao") or linha.get("PLANO DE CONTAS"),
                    "score_planilha":          melhor["score"],
                    "observacao_planilha":     (
                        ("valor e data compativeis" if melhor["data_ok"] else "valor compativel, data divergente") +
                        (", descricao compativel" if melhor["score_nome"] >= 0.3 else ", descricao com baixa compatibilidade")
                    ),
                }
        elif not data_plan or not data_item_dt:
            # Sem data para comparar — aceita com score mais baixo
            status = "PROVAVEL"
            return {
                "status_planilha":         status,
                "linha_excel":             linha.get("linha_excel"),
                "valor_planilha":          extrair_valor_planilha(linha),
                "data_pagamento_planilha": str(data_plan or ""),
                "descricao_planilha":      linha.get("DESPESAS"),
                "plano_contas":            linha.get("plano_contas_padrao") or linha.get("PLANO DE CONTAS"),
                "score_planilha":          melhor["score"],
                "observacao_planilha":     "valor compativel, data nao disponivel",
            }

    # 3. Tenta match CLT (folha de pagamento)
    resultado_clt = _tentar_match_clt(item, linhas_saida, todos_itens or [])
    if resultado_clt:
        return resultado_clt

    # 4. Não encontrado
    return {
        "status_planilha":         "NAO_ENCONTRADO",
        "linha_excel":             None,
        "valor_planilha":          None,
        "data_pagamento_planilha": None,
        "descricao_planilha":      None,
        "plano_contas":            None,
        "score_planilha":          0,
        "observacao_planilha":     "Nenhum lançamento compatível encontrado no fluxo de caixa.",
    }


def conciliar_resultado_com_planilha(resultado_final, planilha):
    if isinstance(planilha, tuple):
        planilha = planilha[1]

    itens = resultado_final.get("itens", [])
    itens_enriquecidos = []

    for item in itens:
        dados_planilha = encontrar_na_planilha(item, planilha, itens)
        itens_enriquecidos.append({**item, **dados_planilha})

    resultado_final["itens"] = itens_enriquecidos
    resultado_final["resumo_planilha"] = {
        "encontrados":    sum(1 for i in itens_enriquecidos if i.get("status_planilha") == "ENCONTRADO"),
        "provaveis":      sum(1 for i in itens_enriquecidos if i.get("status_planilha") == "PROVAVEL"),
        "nao_encontrados":sum(1 for i in itens_enriquecidos if i.get("status_planilha") == "NAO_ENCONTRADO"),
    }
    return resultado_final

from datetime import date, datetime
from difflib import SequenceMatcher
import re
from typing import Any


def normalizar_texto(valor: Any) -> str:
    texto = "" if valor is None else str(valor).upper().strip()
    for origem, destino in {
        "Á": "A", "À": "A", "Â": "A", "Ã": "A", "É": "E", "Ê": "E", "Í": "I",
        "Ó": "O", "Ô": "O", "Õ": "O", "Ú": "U", "Ç": "C",
    }.items():
        texto = texto.replace(origem, destino)
    texto = re.sub(r"[^A-Z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def similaridade(a: Any, b: Any) -> float:
    a_norm = normalizar_texto(a)
    b_norm = normalizar_texto(b)
    if not a_norm or not b_norm:
        return 0.0
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def datas_proximas(data_a: date | datetime | None, data_b: date | datetime | None, tolerancia_dias: int = 2) -> bool:
    if not data_a or not data_b:
        return False
    if isinstance(data_a, datetime):
        data_a = data_a.date()
    if isinstance(data_b, datetime):
        data_b = data_b.date()
    return abs((data_a - data_b).days) <= tolerancia_dias


def valores_iguais(valor_a: float | None, valor_b: float | None, tolerancia_centavos: float = 0.01) -> bool:
    if valor_a is None or valor_b is None:
        return False
    return abs(float(valor_a) - float(valor_b)) <= tolerancia_centavos


def preparar_documentos(documentos: list[dict], prefixo: str) -> list[dict]:
    preparados = []
    for i, item in enumerate(documentos, start=1):
        novo = dict(item)
        novo["id_documento"] = item.get("id_nsu") or item.get("arquivo") or f"{prefixo}_{i:04d}"
        novo["valor_padrao"] = item.get("valor")
        novo["favorecido_padrao"] = item.get("favorecido")
        data_doc = item.get("data_pagamento") or item.get("data")
        if isinstance(data_doc, datetime):
            data_doc = data_doc.date()
        novo["data_padrao"] = data_doc
        preparados.append(novo)
    return preparados


def classificar_pagamento(pagamento: dict, comprovantes: list[dict], extratos: list[dict], notas_fiscais: list[dict]) -> dict:
    valor_pag = pagamento.get("valor_padrao")
    fav_pag = pagamento.get("favorecido_padrao")
    data_pag = pagamento.get("data_pagamento_padrao") or pagamento.get("data_vencimento_padrao")

    comps_mesmo_valor = [c for c in comprovantes if valores_iguais(valor_pag, c.get("valor_padrao"))]
    comps_fav_ok = [c for c in comps_mesmo_valor if similaridade(fav_pag, c.get("favorecido_padrao")) >= 0.75]
    comps_data_ok = [c for c in comps_mesmo_valor if datas_proximas(data_pag, c.get("data_padrao"))]

    ext_mesmo_valor = [e for e in extratos if valores_iguais(valor_pag, e.get("valor_padrao"))]
    nf_mesmo_valor = [n for n in notas_fiscais if valores_iguais(valor_pag, n.get("valor_padrao"))]
    nf_fav_ok = [n for n in nf_mesmo_valor if similaridade(fav_pag, n.get("favorecido_padrao")) >= 0.65]

    if len(comps_fav_ok) > 1:
        status = "DUPLICIDADE"
        motivo = "Mais de um comprovante compatível por valor e favorecido."
        comp = comps_fav_ok[0]
    elif len(comps_fav_ok) == 1:
        status = "CONCILIADO"
        motivo = "Valor e favorecido compatíveis."
        comp = comps_fav_ok[0]
    elif comps_mesmo_valor and comps_data_ok:
        status = "PROVÁVEL CONCILIADO"
        motivo = "Valor igual e data com diferença de até 2 dias, mas favorecido não bateu perfeitamente."
        comp = comps_data_ok[0]
    elif comps_mesmo_valor:
        status = "DIVERGENTE"
        motivo = "Valor encontrado, porém favorecido e/ou data divergentes."
        comp = comps_mesmo_valor[0]
    else:
        status = "PENDENTE"
        motivo = "Nenhum comprovante compatível encontrado."
        comp = None

    validacao_extrato = "VALOR ENCONTRADO NO EXTRATO" if ext_mesmo_valor else "NÃO VALIDADO"
    if nf_fav_ok:
        validacao_nf = "NF COMPATÍVEL"
        nf = nf_fav_ok[0]
    elif nf_mesmo_valor:
        validacao_nf = "NF COM MESMO VALOR, MAS FAVORECIDO DIVERGENTE"
        nf = nf_mesmo_valor[0]
    else:
        validacao_nf = "NF NÃO ENCONTRADA"
        nf = None

    if status == "CONCILIADO" and nf is None:
        motivo += " Atenção: NF não localizada."

    return {
        "status": status,
        "motivo": motivo,
        "linha_excel": pagamento.get("linha_excel"),
        "favorecido_planilha": fav_pag,
        "valor_planilha": valor_pag,
        "data_planilha": data_pag,
        "id_comprovante": comp.get("id_documento") if comp else None,
        "favorecido_comprovante": comp.get("favorecido_padrao") if comp else None,
        "valor_comprovante": comp.get("valor_padrao") if comp else None,
        "data_comprovante": comp.get("data_padrao") if comp else None,
        "validacao_extrato": validacao_extrato,
        "validacao_nf": validacao_nf,
        "arquivo_nf": nf.get("arquivo") if nf else None,
        "score_nome": round(similaridade(fav_pag, comp.get("favorecido_padrao")) * 100, 2) if comp else 0,
    }


def conciliar(pagamentos: list[dict], comprovantes: list[dict], extratos: list[dict] | None = None, notas_fiscais: list[dict] | None = None) -> list[dict]:
    comprovantes_preparados = preparar_documentos(comprovantes, "COMP")
    extratos_preparados = preparar_documentos(extratos or [], "EXT")
    notas_preparadas = preparar_documentos(notas_fiscais or [], "NF")
    return [classificar_pagamento(p, comprovantes_preparados, extratos_preparados, notas_preparadas) for p in pagamentos]


def separar_por_status(resultados: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {}
    for item in resultados:
        grupos.setdefault(item.get("status", "SEM STATUS"), []).append(item)
    return grupos

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

from openpyxl import load_workbook


def _texto_limpo(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def normalizar_nome_coluna(nome: Any) -> str:
    texto = _texto_limpo(nome).upper()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def normalizar_valor(valor: Any) -> float | None:
    """Converte valores como 1500, '1.500,00', 'R$ 1.500,00' para float."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace(" ", "")

    # Remove caracteres que não sejam número, vírgula, ponto ou sinal.
    texto = re.sub(r"[^0-9,.-]", "", texto)

    if not texto:
        return None

    # Padrão brasileiro: 1.500,00
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return round(float(texto), 2)
    except ValueError:
        return None


def normalizar_data(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    formatos = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    return None


def _valor_por_alias(registro: dict, aliases: list[str]) -> Any:
    mapa = {normalizar_nome_coluna(k): v for k, v in registro.items()}
    for alias in aliases:
        if alias in mapa:
            return mapa[alias]
    return None


def padronizar_registro(registro: dict) -> dict:
    """Mantém as colunas originais e adiciona campos padronizados para conciliação."""
    valor = _valor_por_alias(registro, ["SAÍDA", "SAIDA", "VALOR", "VALOR PAGO", "PAGAMENTO VALOR"])
    favorecido = _valor_por_alias(registro, [
        "FAVORECIDO", "FORNECEDOR", "EMPRESA", "EMPRESA/OBRA", "BENEFICIÁRIO",
        "BENEFICIARIO", "CLIENTE", "DESCRIÇÃO", "DESCRICAO", "HISTÓRICO", "HISTORICO"
    ])
    data_pagamento = _valor_por_alias(registro, ["PAGAMENTO", "DATA PAGAMENTO", "DATA DE PAGAMENTO", "DATA"])
    data_vencimento = _valor_por_alias(registro, ["VENCIMENTO", "DATA VENCIMENTO", "DATA DE VENCIMENTO"])
    plano_contas = _valor_por_alias(registro, ["PLANO DE CONTAS", "PLANO", "CONTA"])

    novo = dict(registro)
    novo["valor_padrao"] = normalizar_valor(valor)
    novo["favorecido_padrao"] = _texto_limpo(favorecido)
    novo["data_pagamento_padrao"] = normalizar_data(data_pagamento)
    novo["data_vencimento_padrao"] = normalizar_data(data_vencimento)
    novo["plano_contas_padrao"] = _texto_limpo(plano_contas)
    return novo


def encontrar_cabecalho(dados: list[tuple]) -> int:
    termos_referencia = {"EMPRESA/OBRA", "PAGAMENTO", "VENCIMENTO", "SAÍDA", "SAIDA", "PLANO DE CONTAS"}
    melhor_indice = None
    melhor_pontuacao = 0

    for i, linha in enumerate(dados):
        valores = {normalizar_nome_coluna(celula) for celula in linha if celula is not None}
        pontuacao = len(valores.intersection(termos_referencia))
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_indice = i

    if melhor_indice is None or melhor_pontuacao == 0:
        raise ValueError("Cabeçalho da planilha não encontrado. Verifique se há colunas como EMPRESA/OBRA, PAGAMENTO, SAÍDA ou PLANO DE CONTAS.")

    return melhor_indice


def ler_planilha(path: str | Path, aba: str | None = None) -> tuple[list[str], list[dict]]:
    wb = load_workbook(path, data_only=True)
    ws = wb[aba] if aba else wb.active

    dados = list(ws.iter_rows(values_only=True))
    cabecalho_index = encontrar_cabecalho(dados)

    cabecalho = list(dados[cabecalho_index])
    while cabecalho and cabecalho[-1] is None:
        cabecalho.pop()

    cabecalho = [normalizar_nome_coluna(c) if c is not None else f"COLUNA_{i+1}" for i, c in enumerate(cabecalho)]

    registros = []
    for numero_linha_excel, linha in enumerate(dados[cabecalho_index + 1:], start=cabecalho_index + 2):
        linha = list(linha[:len(cabecalho)])
        if not linha or all(valor is None or valor == "" for valor in linha):
            continue

        registro = dict(zip(cabecalho, linha))
        registro["linha_excel"] = numero_linha_excel
        registros.append(padronizar_registro(registro))

    return cabecalho, registros


def filtrar_pagamentos_dia(registros: list[dict], dia: date | None = None) -> list[dict]:
    filtros = []
    for registro in registros:
        pagamento = registro.get("data_pagamento_padrao")
        valor = registro.get("valor_padrao")
        plano = str(registro.get("plano_contas_padrao") or "").strip().lower()

        if dia is not None and pagamento != dia:
            continue
        if valor in (None, 0):
            continue
        if "saldo" in plano:
            continue
        filtros.append(registro)
    return filtros

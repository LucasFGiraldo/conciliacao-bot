import os
import re
from datetime import datetime


def converter_valor(valor_str):
    if not valor_str:
        return None

    valor_str = valor_str.replace("R$", "").strip()
    valor_str = valor_str.replace(".", "").replace(",", ".")

    try:
        return float(valor_str)
    except ValueError:
        return None


def converter_data(data_str):
    if not data_str:
        return None

    formatos = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(data_str.strip(), formato)
        except ValueError:
            pass

    return None


def limpar_texto(texto):
    texto = texto.replace("\r", "\n")
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def separar_comprovantes(texto):
    texto = limpar_texto(texto)

    padrao = r"(?=Comprovante de )"
    blocos = re.split(padrao, texto)

    comprovantes = []

    for bloco in blocos:
        bloco = bloco.strip()

        if bloco.startswith("Comprovante de "):
            comprovantes.append(bloco)

    return comprovantes


def extrair_tipo_comprovante(texto):
    primeira_linha = texto.splitlines()[0].strip()
    return primeira_linha


def extrair_favorecido(texto):
    padrao = r"Favorecido\s+Nome:\s+(.*?)(?:\n\n|Instituição:|CPF/CNPJ:|Agência:|Valor:)"
    match = re.search(padrao, texto, re.DOTALL | re.IGNORECASE)

    if not match:
        return None

    nome = match.group(1)
    nome = re.sub(r"\s+", " ", nome)
    return nome.strip()


def extrair_valor(texto):
    match = re.search(r"Valor:\s*R\$\s*([\d\.\,]+)", texto, re.IGNORECASE)

    if not match:
        return None

    return converter_valor(match.group(1))


def extrair_data_pagamento(texto):
    match = re.search(
        r"Data Pagamento:\s*(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)",
        texto,
        re.IGNORECASE
    )

    if not match:
        return None

    return converter_data(match.group(1))


def extrair_data_vencimento(texto):
    match = re.search(
        r"Data de Vencimento:\s*(\d{2}/\d{2}/\d{4})",
        texto,
        re.IGNORECASE
    )

    if not match:
        return None

    return converter_data(match.group(1))


def extrair_id_nsu(texto):
    match = re.search(r"ID/NSU:\s*(\d+)", texto, re.IGNORECASE)

    if not match:
        return None

    return match.group(1).strip()


def extrair_cpf_cnpj(texto):
    trecho_favorecido = texto.split("Favorecido")[-1]

    match = re.search(r"CPF/CNPJ:\s*([^\n]+)", trecho_favorecido, re.IGNORECASE)

    if not match:
        return None

    return match.group(1).strip()


def extrair_instituicao(texto):
    match = re.search(r"Instituição:\s*([^\n]+)", texto, re.IGNORECASE)

    if not match:
        return None

    return match.group(1).strip()


def extrair_chave_pix(texto):
    match = re.search(r"Chave Pix:\s*([^\n]+)", texto, re.IGNORECASE)

    if not match:
        return None

    return match.group(1).strip()


def extrair_codigo_barras(texto):
    match = re.search(r"Código de Barras:\s*([0-9\s]+)", texto, re.IGNORECASE)

    if not match:
        return None

    codigo = re.sub(r"\s+", "", match.group(1))
    return codigo.strip()


def extrair_comprovante(texto, nome_arquivo):
    return {
        "arquivo_origem": nome_arquivo,
        "tipo_comprovante": extrair_tipo_comprovante(texto),
        "favorecido": extrair_favorecido(texto),
        "valor": extrair_valor(texto),
        "data_pagamento": extrair_data_pagamento(texto),
        "data_vencimento": extrair_data_vencimento(texto),
        "id_nsu": extrair_id_nsu(texto),
        "cpf_cnpj": extrair_cpf_cnpj(texto),
        "instituicao": extrair_instituicao(texto),
        "chave_pix": extrair_chave_pix(texto),
        "codigo_barras": extrair_codigo_barras(texto),
        "texto_original": texto
    }


def ler_arquivo_txt(caminho_arquivo):
    nome_arquivo = os.path.basename(caminho_arquivo)

    with open(caminho_arquivo, "r", encoding="utf-8") as arquivo:
        conteudo = arquivo.read()

    blocos = separar_comprovantes(conteudo)

    comprovantes = []

    for bloco in blocos:
        comprovante = extrair_comprovante(bloco, nome_arquivo)
        comprovantes.append(comprovante)

    return comprovantes


def ler_comprovantes_txt(pasta_comprovantes):
    todos_comprovantes = []

    if not os.path.exists(pasta_comprovantes):
        print(f"Pasta de comprovantes não encontrada: {pasta_comprovantes}")
        return todos_comprovantes

    for nome_arquivo in os.listdir(pasta_comprovantes):
        if nome_arquivo.lower().endswith(".txt"):
            caminho_arquivo = os.path.join(pasta_comprovantes, nome_arquivo)

            try:
                comprovantes = ler_arquivo_txt(caminho_arquivo)
                todos_comprovantes.extend(comprovantes)

                print(f"{len(comprovantes)} comprovante(s) lido(s) em: {nome_arquivo}")

            except Exception as erro:
                print(f"Erro ao ler {nome_arquivo}: {erro}")

    return todos_comprovantes
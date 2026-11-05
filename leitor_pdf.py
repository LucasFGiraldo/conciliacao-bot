import os
import re
from datetime import datetime

import pdfplumber

from config import EMPRESA_CABECALHO_PDF


# ── Lançamentos a ignorar completamente ──────────────────────
TIPOS_IGNORADOS = [
    "SALDO INICIAL", "SALDO ANTERIOR", "SALDO DO DIA", "SALDO INVEST",
    "TOTAL", "RENTAB.INVEST", "TARIFA BANCARIA", "TRANSF PGTO PIX",
    "CUSTO ENVIO PIX", "CUSTO ENVIO TED", "CUSTO PAGAMENTO",
    "CUSTO RECEBIMENTO", "MANUTENCAO DE CONTA", "TARIFA AUTORIZ",
]

# ── Tipos sem comprovante (capturados, marcados como SEM_COMPROVANTE) ──
TIPOS_SEM_COMPROVANTE = [
    "GASTOS CARTAO",
]

# ── Tipos reais de lançamento ────────────────────────────────
TIPOS_LANCAMENTO_BRADESCO = [
    "PIX RECEBIDO",
    "PIX ENVIADO",
    "PIX QR CODE DINAMICO",
    "PAGTO ELETRON COBRANCA",
    "RECEBIMENTO FORNECEDOR",
    "CONTA DE AGUA",
    "CONTA DE TELEFONE",
    "TED",
    "TRANSFERENCIA",
    "TRANSFERÊNCIA",
    "TRANSF CC PARA CC",
]

# ── Tipos cujo favorecido vem APÓS a linha de valores ────────
# O pdfplumber extrai nessa ordem para boletos/telefone:
#   PAGTO ELETRON COBRANCA
#   1234 -100,00 1.000,00      <- valores
#   FORNECEDOR X - NF 12345 - 1/3   <- favorecido (sem DES:/REM:)
TIPOS_FAVORECIDO_APOS_VALOR = [
    "PAGTO ELETRON COBRANCA",
    "CONTA DE TELEFONE",
    "CONTA DE AGUA",
]

# ── Descrições secundárias que NÃO abrem novo bloco ──────────
DESCRICOES_SECUNDARIAS = [
    "PAG COBRANCA NET EMPRESA",
    "PAG COBRANCA",
    "INTERNET --SABESP",
]

# ── Padrões de linhas a descartar ────────────────────────────
PADROES_IGNORAR_LINHA = [
    re.compile(r"^Total\b", re.IGNORECASE),
    re.compile(r"^Data Lan", re.IGNORECASE),
    re.compile(r"^Extrato", re.IGNORECASE),
    re.compile(r"^Ag[eê]ncia", re.IGNORECASE),
    re.compile(r"^\(A\+B\)", re.IGNORECASE),
    re.compile(r"^Os dados acima", re.IGNORECASE),
    re.compile(r"^[UÚ]ltimos Lan", re.IGNORECASE),
    re.compile(r"^Lan[cç]amentos Futuros", re.IGNORECASE),
    re.compile(r"^Pr[oó]ximo dia", re.IGNORECASE),
    re.compile(r"^Total do Dia", re.IGNORECASE),
    re.compile(r"^Saldos Invest", re.IGNORECASE),
    re.compile(r"^Data Hist[oó]rico", re.IGNORECASE),
    re.compile(r"^Folha\s+\d", re.IGNORECASE),
    re.compile(r"^Nome do", re.IGNORECASE),
    re.compile(r"^Data da opera", re.IGNORECASE),
    re.compile(r"^\d{2}/\d{2}/\d{4}\s+SALDO", re.IGNORECASE),
    re.compile(r"^\d{2}/\d{2}/\d{4}\s+RENTAB", re.IGNORECASE),
    re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"),
]

# Cabeçalho com o nome da empresa (definido no .env)
if EMPRESA_CABECALHO_PDF:
    PADROES_IGNORAR_LINHA.append(re.compile(r"^" + re.escape(EMPRESA_CABECALHO_PDF), re.IGNORECASE))

# Linha de valores: [data opcional] docto valor saldo
PAT_VALOR = re.compile(
    r"^(?:(\d{2}/\d{2}/\d{4})\s+)?(\d{4,8})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})$"
)

# Linha corrompida: favorecido + docto + valores juntos
# Ex: 'FORNECEDOR Y - SERVICO 1235 -200,00 800,00'
# Ex: 'DES: FORNECEDOR Z 10/07 1234567 -5.000,00 10.000,00'
PAT_VALOR_COM_FAVORECIDO = re.compile(
    r"^(?:(?:REM:|DES:)\s*)?(.+?)\s+(\d{4,8})\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s+(\d{1,3}(?:\.\d{3})*,\d{2})$"
)

# Favorecido com prefixo REM:/DES:
PAT_DESC_PREFIXO = re.compile(
    r"^(?:REM:|DES:)\s*(.+?)(?:\s+\d{2}/\d{2}(?:/\d{4})?)?$",
    re.IGNORECASE,
)

# Favorecido sem prefixo (TRANSF CC, RECEBIMENTO FORNECEDOR, boletos após valores)
PAT_TEXTO_PURO = re.compile(r"^[A-ZÁÉÍÓÚÃÕÂÊÔÇÀÜ][A-Za-záéíóúãõâêôçàü0-9\s\-\./\*]+$")


def converter_valor(s):
    return float(s.replace(".", "").replace(",", "."))


def converter_data(s):
    return datetime.strptime(s.strip(), "%d/%m/%Y")


def extrair_texto_pdf(caminho):
    texto = ""
    with pdfplumber.open(caminho) as pdf:
        total = len(pdf.pages)
        print(f"PDF aberto com {total} páginas")
        for i, pag in enumerate(pdf.pages, 1):
            print(f"\rExtraindo página {i}/{total}...", end="", flush=True)
            t = pag.extract_text()
            if t:
                texto += t + "\n"
        print()
    print("Texto extraído com sucesso")
    return texto.strip()


def deve_ignorar_linha(linha):
    return any(pat.search(linha) for pat in PADROES_IGNORAR_LINHA)


def eh_tipo_lancamento(linha):
    lu = linha.upper().strip()
    return any(lu.startswith(t) for t in TIPOS_LANCAMENTO_BRADESCO)


def eh_tipo_ignorado(linha):
    lu = linha.upper().strip()
    return any(lu.startswith(t) for t in TIPOS_IGNORADOS)


def eh_tipo_sem_comprovante(linha):
    lu = linha.upper().strip()
    return any(lu.startswith(t) for t in TIPOS_SEM_COMPROVANTE)


def eh_descricao_secundaria(linha):
    lu = linha.upper().strip()
    return any(lu.startswith(d) for d in DESCRICOES_SECUNDARIAS)


def eh_favorecido_apos_valor(tipo):
    tu = (tipo or "").upper()
    return any(tu.startswith(t) for t in TIPOS_FAVORECIDO_APOS_VALOR)


def identificar_categoria(tipo):
    tu = (tipo or "").upper()
    if any(tu.startswith(t) for t in TIPOS_SEM_COMPROVANTE):
        return "SEM_COMPROVANTE"
    if "PIX RECEBIDO" in tu or "RECEBIMENTO FORNECEDOR" in tu:
        return "RECEBIMENTO PIX"
    if "PIX ENVIADO" in tu or "PIX QR CODE" in tu:
        return "ENVIO PIX"
    if "PAGTO ELETRON" in tu or "PAG COBRANCA" in tu or "CONTA DE AGUA" in tu or "CONTA DE TELEFONE" in tu:
        return "PAGAMENTO BOLETO"
    if "TED" in tu:
        return "TED"
    if "TRANSF CC" in tu or "TRANSFEREN" in tu:
        return "TRANSFERENCIA"
    return "OUTROS"


def identificar_tipo_movimento(valor):
    return "credito" if valor > 0 else "debito"


def extrair_lancamentos_bradesco(texto, nome_arquivo):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]

    lancamentos = []
    doctos_vistos = set()
    data_vigente = None
    tipo_pendente = None
    favorecido_pendente = None
    ignorar_proximo_valor = False
    aguardando_favorecido_puro = False
    aguardando_favorecido_apos = False  # para PAGTO ELETRON, CONTA DE TELEFONE

    def registrar_lancamento(docto, valor_str, saldo_str=None, data_str=None, favorecido=None):
        nonlocal data_vigente, tipo_pendente, favorecido_pendente
        nonlocal aguardando_favorecido_puro, aguardando_favorecido_apos

        if data_str:
            data_vigente = converter_data(data_str)
        if data_vigente and data_vigente.date() > datetime.today().date():
            tipo_pendente = None; favorecido_pendente = None
            aguardando_favorecido_puro = False; aguardando_favorecido_apos = False
            return

        chave = (docto, valor_str)
        if chave in doctos_vistos:
            tipo_pendente = None; favorecido_pendente = None
            aguardando_favorecido_puro = False; aguardando_favorecido_apos = False
            return
        doctos_vistos.add(chave)

        valor = converter_valor(valor_str)
        saldo_apos = converter_valor(saldo_str) if saldo_str else None
        tipo = tipo_pendente or "OUTROS"
        fav = favorecido or favorecido_pendente

        # Define flags para captura do favorecido na linha seguinte
        aguardando_favorecido_puro = (
            fav is None and
            any(t in tipo.upper() for t in ["TRANSF CC", "RECEBIMENTO FORNECEDOR"])
        )
        aguardando_favorecido_apos = (
            fav is None and eh_favorecido_apos_valor(tipo)
        )

        lancamentos.append({
            "arquivo_origem": nome_arquivo,
            "data": data_vigente,
            "favorecido": fav,
            "valor": valor,
            "tipo_movimento": identificar_tipo_movimento(valor),
            "categoria": identificar_categoria(tipo),
            "historico": tipo,
            "docto": docto,
            "saldo_apos": saldo_apos,
        })
        tipo_pendente = None
        favorecido_pendente = None

    for linha in linhas:
        if deve_ignorar_linha(linha):
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Tipo ignorado ────────────────────────────────────
        if eh_tipo_ignorado(linha):
            tipo_pendente = None
            favorecido_pendente = None
            ignorar_proximo_valor = True
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Tipo sem comprovante ─────────────────────────────
        if eh_tipo_sem_comprovante(linha):
            tipo_pendente = linha
            ignorar_proximo_valor = False
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Tipo real de lançamento ──────────────────────────
        if eh_tipo_lancamento(linha):
            tipo_pendente = linha
            ignorar_proximo_valor = False
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Descrição secundária ─────────────────────────────
        if eh_descricao_secundaria(linha):
            if lancamentos and lancamentos[-1]["favorecido"] is None:
                lancamentos[-1]["favorecido"] = linha
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Favorecido com prefixo REM:/DES: ─────────────────
        md = PAT_DESC_PREFIXO.match(linha)
        if md:
            nome = re.sub(r"\s+\d{2}/\d{2}$", "", md.group(1)).strip()
            if tipo_pendente:
                favorecido_pendente = nome
            elif lancamentos and lancamentos[-1]["favorecido"] is None:
                lancamentos[-1]["favorecido"] = nome
            aguardando_favorecido_puro = False
            aguardando_favorecido_apos = False
            continue

        # ── Linha de valores (com favorecido embutido) ────────
        # Ex: 'FORNECEDOR Y - SERVICO 1235 -200,00 800,00'
        # Só testa se há tipo pendente e a linha não começa com data
        if tipo_pendente and not re.match(r"^\d{2}/\d{2}/\d{4}", linha):
            mc = PAT_VALOR_COM_FAVORECIDO.match(linha)
            if mc:
                if ignorar_proximo_valor:
                    ignorar_proximo_valor = False
                    tipo_pendente = None
                    continue
                nome_emb, docto, valor_str, saldo_str = mc.groups()
                nome_emb = re.sub(r"\s+\d{2}/\d{2}$", "", nome_emb).strip()
                # Garante que nome_emb não é apenas dígitos (seria docto sozinho)
                if not re.match(r"^\d+$", nome_emb):
                    registrar_lancamento(docto, valor_str, saldo_str, favorecido=nome_emb)
                    continue

        # ── Linha de valores normal ───────────────────────────
        m = PAT_VALOR.match(linha)
        if m:
            if ignorar_proximo_valor:
                ignorar_proximo_valor = False
                tipo_pendente = None
                favorecido_pendente = None
                aguardando_favorecido_puro = False
                aguardando_favorecido_apos = False
                continue
            data_str, docto, valor_str, saldo_str = m.groups()
            registrar_lancamento(docto, valor_str, saldo_str, data_str)
            continue

        # ── Favorecido puro após valores (TRANSF CC / RECEBIMENTO FORNECEDOR) ──
        if aguardando_favorecido_puro and lancamentos:
            if PAT_TEXTO_PURO.match(linha):
                lancamentos[-1]["favorecido"] = linha
            aguardando_favorecido_puro = False
            continue

        # ── Favorecido após valores (PAGTO ELETRON, CONTA DE TELEFONE) ──────
        # Ex: linha após '1234 -100,00 1.000,00' é 'FORNECEDOR X - NF 12345 - 1/3'
        if aguardando_favorecido_apos and lancamentos:
            if lancamentos[-1]["favorecido"] is None:
                lancamentos[-1]["favorecido"] = linha
            aguardando_favorecido_apos = False
            continue

    return lancamentos


def ler_extratos_pdf(pasta_extratos):
    todos = []
    if not os.path.exists(pasta_extratos):
        print(f"Pasta não encontrada: {pasta_extratos}")
        return todos

    for nome in os.listdir(pasta_extratos):
        if not nome.lower().endswith(".pdf"):
            continue
        caminho = os.path.join(pasta_extratos, nome)
        try:
            texto = extrair_texto_pdf(caminho)
            lancamentos = extrair_lancamentos_bradesco(texto, nome)
            todos.extend(lancamentos)
            print(f"{len(lancamentos)} lançamento(s) extraído(s) de: {nome}")
            for l in lancamentos:
                data_fmt = l["data"].strftime("%d/%m/%Y") if l["data"] else "SEM DATA"
                print(f"  {data_fmt} | {l['categoria']:<20} | {l['valor']:>12.2f} | {l['favorecido']}")
        except Exception as e:
            print(f"Erro ao ler {nome}: {e}")
            raise

    return todos


def converter_valor_str(valor_str):
    if not valor_str:
        return None
    return converter_valor(valor_str.replace("R$", "").strip())


def ler_notas_pdf(pasta_notas):
    return []


def ler_pdfs(pasta_pdf):
    return []

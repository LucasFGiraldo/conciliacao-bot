"""
Gerencia saldos.json na PASTA_SAIDA do config.py.
Estrutura:
{
  "Bradesco|00000-0": {
    "2026-01-31": {"banco": "Bradesco", "conta": "00000-0", "saldo_final": 1000.00, "registrado_em": "..."}
  }
}
"""
import json
import os
from datetime import date, datetime, timedelta


def _caminho_arquivo():
    try:
        from config import PASTA_SAIDA
        os.makedirs(PASTA_SAIDA, exist_ok=True)
        return os.path.join(PASTA_SAIDA, "saldos.json")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "saldos.json")


def _carregar():
    caminho = _caminho_arquivo()
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _salvar(dados):
    caminho = _caminho_arquivo()
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print(f"    [saldo] Arquivo salvo em: {caminho}")


def registrar_saldo(data: date, banco: str, conta: str, saldo_final: float, sobrescrever: bool = False):
    """Salva o saldo final do dia. Por padrao nao sobrescreve registro existente."""
    dados = _carregar()
    chave_conta = f"{banco}|{conta}"
    if chave_conta not in dados:
        dados[chave_conta] = {}
    chave_data = str(data)
    if chave_data in dados[chave_conta] and not sobrescrever:
        print(f"    [saldo] Registro {chave_data} ja existe — mantendo valor anterior "
              f"R$ {dados[chave_conta][chave_data]['saldo_final']:,.2f}. "
              f"Use sobrescrever=True para atualizar.")
        return
    dados[chave_conta][chave_data] = {
        "banco": banco,
        "conta": conta,
        "saldo_final": round(saldo_final, 2),
        "registrado_em": datetime.now().isoformat(),
    }
    _salvar(dados)
    print(f"    [saldo] Registrado: {data} | {banco} | {conta} | R$ {saldo_final:,.2f}")


def obter_saldo_mais_recente(banco: str = None, conta: str = None):
    """
    Retorna o registro de saldo mais recente disponível para o banco/conta.
    Usado para mostrar o saldo anterior no inicio de cada execucao.
    """
    dados = _carregar()
    if not dados:
        return None

    candidatos = []
    for chave_conta, historico in dados.items():
        for data_str, info in historico.items():
            if banco and info.get("banco") != banco:
                continue
            if conta and info.get("conta") != conta:
                continue
            candidatos.append((data_str, info))

    if not candidatos:
        return None

    # Retorna o mais recente
    candidatos.sort(key=lambda x: x[0], reverse=True)
    data_str, info = candidatos[0]
    info["data"] = data_str
    return info


def obter_saldo_anterior(data: date, banco: str = None, conta: str = None):
    """
    Retorna o saldo mais recente registrado ANTES da data informada (ate 30 dias).
    Se nao encontrar antes, retorna o mais recente disponivel.
    """
    dados = _carregar()
    if not dados:
        return None

    candidatos = []
    for chave_conta, historico in dados.items():
        for data_str, info in historico.items():
            if banco and info.get("banco") != banco:
                continue
            if conta and info.get("conta") != conta:
                continue
            candidatos.append((data_str, info))

    if not candidatos:
        return None

    # Prefere registros anteriores a data_informada
    anteriores = [(d, i) for d, i in candidatos if d < str(data)]
    if anteriores:
        anteriores.sort(key=lambda x: x[0], reverse=True)
        data_str, info = anteriores[0]
    else:
        # Fallback: qualquer registro disponivel
        candidatos.sort(key=lambda x: x[0], reverse=True)
        data_str, info = candidatos[0]

    info = dict(info)
    info["data"] = data_str
    return info


def listar_saldos():
    dados = _carregar()
    resultado = {}
    for chave_conta, historico in dados.items():
        for data_str, info in historico.items():
            resultado[data_str + "|" + chave_conta] = info
    return dict(sorted(resultado.items()))


def resumo_saldos():
    dados = _carregar()
    if not dados:
        print("    [saldo] Nenhum saldo registrado ainda.")
        return
    print(f"\n    {'='*58}")
    print(f"    {'DATA':<12} {'BANCO':<12} {'CONTA':<15} {'SALDO FINAL':>12}")
    print(f"    {'='*58}")
    for chave_conta, historico in dados.items():
        for data_str, info in sorted(historico.items()):
            print(f"    {data_str:<12} {info['banco']:<12} {info['conta']:<15} "
                  f"R$ {info['saldo_final']:>10,.2f}")
    print(f"    {'='*58}\n")

from datetime import datetime
import os

def garantir_pasta(pasta: str):
     if not os.path.exists(pasta):
        os.makedirs(pasta)

def salvar_relatorio_txt(relatorio, pasta_saida):
    garantir_pasta(pasta_saida)

    caminho = os.path.join(
        pasta_saida, 
        f"relatorio_conciliacao_{datetime.now().strftime('%d-%m-%Y')}.txt"
    )
    with open(caminho,"w", encoding="utf-8") as f:
        f.write(relatorio)

    print(f"\nRelatório salvo em: {caminho}")

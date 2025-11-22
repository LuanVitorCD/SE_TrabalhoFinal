import pandas as pd
import random
from datetime import datetime, timedelta

def generate_humidity_csv():
    # 1. Configuração para bater com o seu temp.csv
    # Seu CSV começa aprox em 2025-11-21 21:18:07
    start_time = datetime(2025, 11, 21, 21, 18, 0) 
    num_records = 100
    base_interval_sec = 5 # Intervalo médio de 5 segundos

    data = []
    print("🎲 Gerando 100 dados simulados de umidade...")

    for i in range(num_records):
        # Avança o tempo
        current_time = start_time + timedelta(seconds=i*base_interval_sec)
        
        # Adiciona um jitter (variação aleatória) nos milissegundos para parecer real
        current_time = current_time + timedelta(microseconds=random.randint(0, 999999))
        
        # Simula umidade oscilando suavemente entre 70.0 e 72.0
        # O random.uniform dá um float aleatório nesse intervalo
        val = round(random.uniform(70.0, 72.0), 1)
        
        # Se quiser simular uma queda ou subida no meio, pode descomentar abaixo:
        # if i > 50: val = round(random.uniform(68.0, 70.0), 1)

        data.append({
            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "value": val
        })

    # 2. Salvar em CSV
    df = pd.DataFrame(data)
    filename = "humidity.csv"
    df.to_csv(filename, index=False)
    
    print(f"✅ Arquivo '{filename}' criado com sucesso!")
    print(f"   - Início: {data[0]['timestamp']}")
    print(f"   - Fim:    {data[-1]['timestamp']}")
    print("Agora rode o script 'csv_to_firestore.py' para enviar esses dados.")

if __name__ == "__main__":
    generate_humidity_csv()
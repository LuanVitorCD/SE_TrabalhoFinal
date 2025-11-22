import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import os
from datetime import datetime
from dotenv import load_dotenv

# 1. Carregar variáveis
load_dotenv()
cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")

if not os.path.exists(cred_path):
    print(f"❌ Erro: Credencial {cred_path} não encontrada.")
    exit()

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()
COLLECTION_DATA = os.getenv("COLLECTION_DATA", "estacao_dados")

def upload_file(filename, tipo_dado):
    if not os.path.exists(filename):
        print(f"⚠️  Arquivo {filename} não encontrado. Pulando.")
        return

    print(f"\n📂 Processando {filename} (Tipo: {tipo_dado})...")
    df = pd.read_csv(filename)
    
    batch = db.batch()
    batch_counter = 0
    total_uploaded = 0

    for index, row in df.iterrows():
        try:
            # Parse do timestamp
            dt_obj = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S.%f")
            valor = float(row['value'])

            doc_ref = db.collection(COLLECTION_DATA).document()
            
            # Payload dinâmico baseado no tipo
            data_payload = {
                "timestamp": dt_obj,
                "valor": valor,
                "tipo": tipo_dado # 'temperatura' ou 'umidade'
            }
            
            batch.set(doc_ref, data_payload)
            batch_counter += 1

            if batch_counter >= 400:
                batch.commit()
                total_uploaded += batch_counter
                print(f"   ... {total_uploaded} registros enviados")
                batch = db.batch()
                batch_counter = 0
                
        except Exception as e:
            print(f"   ❌ Erro na linha {index}: {e}")

    if batch_counter > 0:
        batch.commit()
        total_uploaded += batch_counter
    
    print(f"✅ {filename}: {total_uploaded} registros enviados com sucesso.")

if __name__ == "__main__":
    print("--- Uploader de CSV para Firestore ---")
    resp = input(f"Enviar dados para coleção '{COLLECTION_DATA}'? (s/n): ")
    
    if resp.lower() == 's':
        # Tenta enviar TEMPERATURA
        upload_file("temp.csv", "temperatura")
        
        # Tenta enviar UMIDADE (o arquivo que vamos gerar)
        upload_file("humidity.csv", "umidade")
        
        print("\n🎉 Processo finalizado! Atualize seu Dashboard.")
    else:
        print("Cancelado.")
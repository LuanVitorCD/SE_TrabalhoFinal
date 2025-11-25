"""
 * ======================================================================================
 * PROJETO: Estação Meteorológica IoT com ESP32 (EcoSense IoT)
 * ======================================================================================
 * OBJETIVO:
 * - Monitorar Temperatura e Umidade com sensor DHT22;
 * - Enviar dados via MQTT para um Dashboard em Python/Streamlit;
 * - Receber comandos remotos para ajustar limites de alerta;
 * - Exibir dados em Display OLED e alertar via LEDs.
 *
 * AUTORES: Henrique Luan Fritz, Luan Vitor Casali Dallabrida e Lucas Pannebecker Sckenal
 *
 * HARDWARE: ESP32 TTGO T-Beam V1.1, Sensor DHT22, LEDs (Vermelho, Azul, Verde).
 * ======================================================================================
"""
import os
import time
import json
import logging
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from datetime import datetime

# ==============================================================================
# CONFIGURAÇÕES 
# ==============================================================================
BROKER = "broker.hivemq.com"
PORT = 1883

# Tópicos (Exatamente iguais ao ESP32_Sensor_WiFi.ino)
TOPIC_TEMP = "esp32/sensor/temperatura"
TOPIC_HUM = "esp32/sensor/umidade"
TOPIC_CONFIG_SEND = "esp32/config/limites" # Onde enviamos a config

# Configuração Firebase
load_dotenv()
cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json") # Tenta ler do .env ou usa padrão

# Configuração de Logging (Estilo "Matrix")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("Bridge")

# ==============================================================================
# 1. INICIALIZAÇÃO DO FIREBASE
# ==============================================================================
db = None
try:
    if not firebase_admin._apps:
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print(f"🔥 Firebase CONECTADO! (Lendo de: {cred_path})")
        else:
            print(f"❌ ERRO: Arquivo '{cred_path}' não encontrado!")
            print("   O script vai rodar, mas NÃO vai salvar dados no banco.")
    else:
        db = firestore.client()
except Exception as e:
    print(f"❌ Erro crítico no Firebase: {e}")

# Nomes das coleções no Firebase
COL_DATA = "estacao_dados"
COL_CONFIG = "estacao_config"
DOC_CONFIG = "limites_alerta"

# ==============================================================================
# 2. FUNÇÕES MQTT (Ouvir Sensor -> Salvar no Banco)
# ==============================================================================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ CONECTADO AO BROKER MQTT! ({BROKER})")
        client.subscribe([(TOPIC_TEMP, 0), (TOPIC_HUM, 0)])
        print(f"👂 Ouvindo sensores em: {TOPIC_TEMP} e {TOPIC_HUM}")
    else:
        print(f"❌ Falha na conexão MQTT. Código: {rc}")

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        valor = float(payload_str)
        tipo = "temperatura" if msg.topic == TOPIC_TEMP else "umidade"
        
        # Print bonitinho para ver passando
        emoji = "🌡️" if tipo == "temperatura" else "💧"
        print(f"📥 {emoji} RECEBIDO: {valor} ({tipo})")

        # Salva no Firebase
        if db:
            db.collection(COL_DATA).add({
                "tipo": tipo,
                "valor": valor,
                "timestamp": datetime.now()
            })
            # print("   💾 Salvo no Firebase") 
            # Comentei o print acima para não poluir, descomente se quiser ver
            
    except Exception as e:
        print(f"⚠️ Erro ao processar msg: {e}")

# ==============================================================================
# 3. FUNÇÃO FIREBASE LISTENER (Banco Mudou -> Enviar para ESP32)
# ==============================================================================
def on_config_change(doc_snapshot, changes, read_time):
    """
    Esta função é disparada AUTOMATICAMENTE pelo Google
    sempre que você clica em 'Enviar' no Streamlit.
    """
    for change in changes:
        doc = change.document
        data = doc.to_dict()
        if data:
            print("\n🔔 --- ALTERAÇÃO DETECTADA NO FIREBASE ---")
            print(f"   Dados lidos do banco: {data}")
            
            # Monta o JSON para o ESP32 (Garante que os campos batam)
            payload_esp32 = json.dumps({
                "temp_max": float(data.get("temp_max", 30)),
                "temp_min": float(data.get("temp_min", 15)),
                "umid_max": float(data.get("umid_max", 80)),
                "umid_min": float(data.get("umid_min", 30))
            })
            
            # Envia para o ESP32
            mqtt_client.publish(TOPIC_CONFIG_SEND, payload_esp32, retain=False)
            print(f"🚀 ENVIADO PARA ESP32 ({TOPIC_CONFIG_SEND})")
            print(f"📦 Payload: {payload_esp32}")
            print("-------------------------------------------\n")

# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    # Configura MQTT
    mqtt_client = mqtt.Client(client_id="Python_Bridge_Final")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    # Conecta o Listener do Firebase (Ouvido Biônico)
    if db:
        print("👀 Iniciando vigilância no documento de configuração...")
        config_ref = db.collection(COL_CONFIG).document(DOC_CONFIG)
        
        # Se o doc não existir, cria um padrão para não dar erro
        if not config_ref.get().exists:
            print("⚠️ Config não existia, criando padrão...")
            config_ref.set({"temp_max": 30, "temp_min": 15, "umid_max": 80, "umid_min": 30})
            
        # Liga o listener
        config_watch = config_ref.on_snapshot(on_config_change)

    # Conecta MQTT e roda para sempre
    try:
        print("⏳ Conectando MQTT...")
        mqtt_client.connect(BROKER, PORT, 60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        print("\n🛑 Bridge encerrado.")
        mqtt_client.disconnect()
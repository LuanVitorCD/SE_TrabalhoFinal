import os
import time
import json
import logging
import paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from datetime import datetime

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Bridge")

# --- CONFIGURAÇÃO FIREBASE ---
cred_path = os.getenv("FIREBASE_CREDENTIALS")
if not os.path.exists(cred_path):
    logger.error(f"Arquivo de credenciais não encontrado: {cred_path}")
    exit(1)

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)
db = firestore.client()

COLLECTION_DATA = os.getenv("COLLECTION_DATA", "estacao_dados")
COLLECTION_CONFIG = os.getenv("COLLECTION_CONFIG", "estacao_config")
DOC_CONFIG = os.getenv("DOC_CONFIG_ID", "limites_alerta")

# --- CONFIGURAÇÃO MQTT ---
BROKER = os.getenv("MQTT_BROKER")
PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_TEMP = os.getenv("MQTT_TOPIC_TEMP")
TOPIC_HUM = os.getenv("MQTT_TOPIC_HUM")
TOPIC_CONFIG = os.getenv("MQTT_TOPIC_CONFIG")

mqtt_client = mqtt.Client("Bridge_Worker_Python")

# ---------------------------------------------------------
# LÓGICA 1: RECEBER DADOS DO SENSOR -> SALVAR NO FIREBASE
# ---------------------------------------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("✅ Conectado ao MQTT Broker!")
        client.subscribe([(TOPIC_TEMP, 0), (TOPIC_HUM, 0)])
    else:
        logger.error(f"Falha na conexão MQTT. Código: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = float(msg.payload.decode())
        topic = msg.topic
        tipo = "temperatura" if topic == TOPIC_TEMP else "umidade"
        
        logger.info(f"📥 Recebido {tipo}: {payload}")

        # Salvar no Firestore
        doc_data = {
            "tipo": tipo,
            "valor": payload,
            "timestamp": datetime.now() # Firestore converte isso nativamente
        }
        # Adiciona um novo documento na coleção
        db.collection(COLLECTION_DATA).add(doc_data)
        logger.info(f"💾 Salvo no Firebase ({tipo})")

    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")

# ---------------------------------------------------------
# LÓGICA 2: OUVIR FIREBASE -> ENVIAR CONFIG PARA O SENSOR
# ---------------------------------------------------------
# Esta função roda automaticamente quando algo muda no Firestore
def on_config_snapshot(doc_snapshot, changes, read_time):
    for doc in doc_snapshot:
        data = doc.to_dict()
        if data:
            logger.info(f"⚙️ Configuração alterada no Firebase: {data}")
            
            # Prepara payload JSON para o ESP32
            # O ESP32 espera chaves: "temp_max" e "temp_min"
            payload_esp32 = json.dumps({
                "temp_max": data.get("temp_max", 30.0),
                "temp_min": data.get("temp_min", 15.0)
            })
            
            # Publica no MQTT
            mqtt_client.publish(TOPIC_CONFIG, payload_esp32, retain=True)
            logger.info(f"📡 Enviado para ESP32 via MQTT: {payload_esp32}")

# Iniciar listener do Firestore (em background)
config_ref = db.collection(COLLECTION_CONFIG).document(DOC_CONFIG)
config_watch = config_ref.on_snapshot(on_config_snapshot)

# ---------------------------------------------------------
# LOOP PRINCIPAL
# ---------------------------------------------------------
if __name__ == "__main__":
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        logger.info(f"🔗 Conectando ao Broker {BROKER}...")
        mqtt_client.connect(BROKER, PORT, 60)
        
        # Cria o documento de config padrão se não existir
        if not config_ref.get().exists:
            logger.info("Criando configuração padrão no Firebase...")
            config_ref.set({"temp_max": 30.0, "temp_min": 15.0})

        mqtt_client.loop_forever()
        
    except KeyboardInterrupt:
        logger.info("Parando Bridge...")
        mqtt_client.disconnect()
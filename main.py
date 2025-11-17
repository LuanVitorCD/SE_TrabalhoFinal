import streamlit as st
import paho.mqtt.client as mqtt
import time
import logging
from streamlit_autorefresh import st_autorefresh

# Configurar logging para ver mensagens no terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ------ CONFIGURAÇÕES MQTT ------
BROKER = "broker.hivemq.com"
PORT = 1883

TOPICO_TEMPERATURA = "esp32/streamlit/temperatura"
TOPICO_UMIDADE = "esp32/streamlit/umidade"

# ------ CONFIGURAÇÃO DO STREAMLIT ------
st.set_page_config(page_title="Dashboard MQTT", layout="centered")
st.title("📊 Dashboard de Monitoramento MQTT")
st.markdown("---")

# --- NOSSA CORREÇÃO (AUTOREFRESH) ---
# Força um 'rerun' a cada 1 segundo (1000ms).
# Isso vai disparar o client.loop() lá embaixo.
st_autorefresh(interval=1000, limit=None)
# -----------------------------------

# Inicializar estado da sessão
if "temperatura" not in st.session_state:
    st.session_state.temperatura = "Aguardando..."
if "umidade" not in st.session_state:
    st.session_state.umidade = "Aguardando..."
if "conectado" not in st.session_state:
    st.session_state.conectado = False

# ------ CALLBACKS MQTT (Sem mudanças) ------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        st.session_state.conectado = True
        logger.info("✅ CONECTADO AO BROKER MQTT COM SUCESSO")
        # Se inscreve nos tópicos
        client.subscribe(TOPICO_TEMPERATURA)
        client.subscribe(TOPICO_UMIDADE)
        logger.info(f"🎯 Inscrito nos tópicos: {TOPICO_TEMPERATURA}, {TOPICO_UMIDADE}")
    else:
        st.session_state.conectado = False
        logger.error(f"❌ FALHA NA CONEXÃO MQTT - Código: {rc}")

def on_disconnect(client, userdata, rc):
    st.session_state.conectado = False
    logger.warning(f"🔌 DESCONECTADO DO BROKER - Código: {rc}")
    # Limpa o cache para forçar uma reconexão na próxima atualização
    st.cache_resource.clear()

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        logger.info(f"📥 MENSAGEM RECEBIDA - Tópico: {msg.topic} | Payload: {payload}")
        
        # Atualizar o session_state.
        if msg.topic == TOPICO_TEMPERATURA:
            st.session_state.temperatura = f"{payload} °C"
            logger.info(f"🌡 TEMPERATURA ATUALIZADA: {payload}°C")
        elif msg.topic == TOPICO_UMIDADE:
            st.session_state.umidade = f"{payload} %"
            logger.info(f"💧 UMIDADE ATUALIZADA: {payload}%")
            
    except Exception as e:
        logger.error(f"❌ ERRO AO PROCESSAR MENSAGEM: {e}")

def on_subscribe(client, userdata, mid, granted_qos):
    logger.info(f"✅ INSCRIÇÃO CONFIRMADA - MID: {mid}, QOS: {granted_qos}")

# ------ INICIALIZAR CLIENTE MQTT (NOVO MÉTODO) ------
# Usamos @st.cache_resource para criar e manter o cliente MQTT.
# Esta função só será executada uma vez (ou quando o cache for limpo).
@st.cache_resource
def get_mqtt_client():
    try:
        logger.info("🔄 INICIANDO CLIENTE MQTT (CACHE RESOURCE)...")
        client = mqtt.Client()
        
        # Configurar callbacks
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        
        client.will_set("esp32/streamlit/status", "offline", retain=True)
        
        logger.info(f"🔗 CONECTANDO AO BROKER: {BROKER}:{PORT}")
        # Usamos connect() síncrono.
        client.connect(BROKER, PORT, 60)
        logger.info("🔄 CLIENTE CONECTADO (SINCRONAMENTE)")

        # **NÃO USAMOS MAIS client.loop_start()**
        
        return client
        
    except Exception as e:
        logger.error(f"❌ ERRO AO INICIAR MQTT: {e}")
        st.session_state.conectado = False
        st.error(f"❌ Falha crítica ao conectar ao MQTT: {e}")
        return None

# ------ INICIALIZAÇÃO E LOOP PRINCIPAL ------
def main():
    logger.info("🚀 EXECUTANDO RERUN DO STREAMLIT")
    
    # Obter o cliente (do cache ou criando um novo)
    client = get_mqtt_client()
    
    if client:
        # **A MÁGICA ACONTECE AQUI**
        # Em cada rerun, processamos o loop do MQTT por 0.1s.
        # Isso é rápido, não bloqueia o app, e processa todas as
        # mensagens na fila, disparando o on_message()
        client.loop(timeout=0.1)
    else:
        logger.warning("Cliente MQTT não está disponível.")

# ------ INTERFACE DO DASHBOARD (Sem mudanças) ------
col1, col2 = st.columns(2)
with col1:
    st.metric(label="🌡 Temperatura", value=st.session_state.temperatura)
with col2:
    st.metric(label="💧 Umidade", value=st.session_state.umidade)

st.markdown("---")
status_color = "🟢" if st.session_state.conectado else "🔴"
status_text = "Conectado" if st.session_state.conectado else "Desconectado"
st.write(f"{status_color} **Status da Conexão:** {status_text}")

st.write(f"**Broker:** {BROKER}:{PORT}")
st.write(f"**Tópicos monitorados:** `{TOPICO_TEMPERATURA}`, `{TOPICO_UMIDADE}`")

st.markdown("---")
col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    if st.button("🔄 Reiniciar Conexão MQTT"):
        logger.info("🔄 REINICIANDO CONEXÃO MQTT (LIMPANDO CACHE)...")
        # Limpa o cache do cliente.
        st.cache_resource.clear()
        # Reseta o estado
        st.session_state.conectado = False
        st.session_state.temperatura = "Reiniciando..."
        st.session_state.umidade = "Reiniciando..."
        # Força um rerun imediato para recriar o cliente
        st.rerun()

with col_btn2:
    if st.button("📊 Status Completo"):
        logger.info("📊 STATUS DO SISTEMA SOLICITADO:")
        logger.info(f"   - Conectado: {st.session_state.conectado}")
        st.info("Verifique o terminal para detalhes do status")

# Log de mensagens (Seu código original, sem mudanças)
with st.expander("📨 Log de Mensagens (Últimas 10)"):
    if st.button("🧹 Limpar Log", key="clear_log"):
        if "mensagens" in st.session_state:
            st.session_state.mensagens.clear()
            logger.info("🧹 LOG LIMPO PELO USUÁRIO")
    
    if "mensagens" not in st.session_state:
        st.session_state.mensagens = []
    
    current_time = time.strftime('%H:%M:%S')
    last_log = st.session_state.mensagens[-1] if st.session_state.mensagens else ""
    
    if st.session_state.temperatura != "Aguardando..." and st.session_state.temperatura not in last_log:
        log_entry = f"{current_time} - Temperatura: {st.session_state.temperatura}"
        st.session_state.mensagens.append(log_entry)
    
    if st.session_state.umidade != "Aguardando..." and st.session_state.umidade not in last_log:
        log_entry = f"{current_time} - Umidade: {st.session_state.umidade}"
        st.session_state.mensagens.append(log_entry)
    
    for msg in reversed(st.session_state.mensagens[-10:]):
        st.code(msg)

# ------ EXECUÇÃO ------
if __name__ == "__main__":
    main()
    logger.info("🏁 SCRIPT RENDERIZADO - AGUARDANDO PRÓXIMO RERUN DO AUTOREFRESH")
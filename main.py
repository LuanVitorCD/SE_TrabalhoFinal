import streamlit as st
import paho.mqtt.client as mqtt
import time
import logging
from streamlit_autorefresh import st_autorefresh
import pandas as pd  # ### ADICIONADO ###
import plotly.express as px  # ### ADICIONADO ###

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
st.set_page_config(page_title="Dashboard MQTT", layout="wide") # ### MODIFICADO ### (para layout="wide")
st.title("📊 Dashboard de Monitoramento MQTT com Gráficos")
st.markdown("---")

# --- NOSSA CORREÇÃO (AUTOREFRESH) ---
st_autorefresh(interval=1000, limit=None)
# -----------------------------------

# Inicializar estado da sessão
if "temperatura" not in st.session_state:
    st.session_state.temperatura = "Aguardando..."
if "umidade" not in st.session_state:
    st.session_state.umidade = "Aguardando..."
if "conectado" not in st.session_state:
    st.session_state.conectado = False
    
# ### ADICIONADO ### - Listas para guardar o histórico dos gráficos
if "temp_data" not in st.session_state:
    st.session_state.temp_data = [] # Lista de dicionários: [{'timestamp': ..., 'value': ...}]
if "umid_data" not in st.session_state:
    st.session_state.umid_data = [] # Lista de dicionários: [{'timestamp': ..., 'value': ...}]


# ------ CALLBACKS MQTT ------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        st.session_state.conectado = True
        logger.info("✅ CONECTADO AO BROKER MQTT COM SUCESSO")
        client.subscribe(TOPICO_TEMPERATURA)
        client.subscribe(TOPICO_UMIDADE)
        logger.info(f"🎯 Inscrito nos tópicos: {TOPICO_TEMPERATURA}, {TOPICO_UMIDADE}")
    else:
        st.session_state.conectado = False
        logger.error(f"❌ FALHA NA CONEXÃO MQTT - Código: {rc}")

def on_disconnect(client, userdata, rc):
    st.session_state.conectado = False
    logger.warning(f"🔌 DESCONECTADO DO BROKER - Código: {rc}")
    st.cache_resource.clear()

# ### MODIFICADO ### - Função on_message para guardar histórico
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        logger.info(f"📥 MENSAGEM RECEBIDA - Tópico: {msg.topic} | Payload: {payload}")
        
        valor_float = None
        try:
            # Tenta converter o payload para float
            valor_float = float(payload)
        except ValueError:
            logger.warning(f"Payload '{payload}' não é um número flutuante. Ignorando.")
            return

        # Pega o horário atual
        now = pd.Timestamp.now()
        
        if msg.topic == TOPICO_TEMPERATURA:
            # 1. Atualiza a métrica (formato string)
            st.session_state.temperatura = f"{valor_float:.1f} °C"
            logger.info(f"🌡 TEMPERATURA ATUALIZADA: {valor_float}°C")
            
            # 2. Adiciona dados ao histórico do gráfico
            st.session_state.temp_data.append({"timestamp": now, "value": valor_float})
            # 3. Limita o histórico aos últimos 100 pontos
            st.session_state.temp_data = st.session_state.temp_data[-100:]
            
        elif msg.topic == TOPICO_UMIDADE:
            # 1. Atualiza a métrica (formato string)
            st.session_state.umidade = f"{valor_float:.1f} %"
            logger.info(f"💧 UMIDADE ATUALIZADA: {valor_float}%")
            
            # 2. Adiciona dados ao histórico do gráfico
            st.session_state.umid_data.append({"timestamp": now, "value": valor_float})
            # 3. Limita o histórico aos últimos 100 pontos
            st.session_state.umid_data = st.session_state.umid_data[-100:]
            
    except Exception as e:
        logger.error(f"❌ ERRO AO PROCESSAR MENSAGEM: {e}")


def on_subscribe(client, userdata, mid, granted_qos):
    logger.info(f"✅ INSCRIÇÃO CONFIRMADA - MID: {mid}, QOS: {granted_qos}")

# ------ INICIALIZAR CLIENTE MQTT (Sem mudanças) ------
@st.cache_resource
def get_mqtt_client():
    try:
        logger.info("🔄 INICIANDO CLIENTE MQTT (CACHE RESOURCE)...")
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.on_subscribe = on_subscribe
        client.will_set("esp32/streamlit/status", "offline", retain=True)
        
        logger.info(f"🔗 CONECTANDO AO BROKER: {BROKER}:{PORT}")
        client.connect(BROKER, PORT, 60)
        logger.info("🔄 CLIENTE CONECTADO (SINCRONAMENTE)")
        return client
        
    except Exception as e:
        logger.error(f"❌ ERRO AO INICIAR MQTT: {e}")
        st.session_state.conectado = False
        st.error(f"❌ Falha crítica ao conectar ao MQTT: {e}")
        return None

# ------ INICIALIZAÇÃO E LOOP PRINCIPAL (Sem mudanças) ------
def main():
    logger.info("🚀 EXECUTANDO RERUN DO STREAMLIT")
    client = get_mqtt_client()
    
    if client:
        client.loop(timeout=0.1)
    else:
        logger.warning("Cliente MQTT não está disponível.")

# ------ INTERFACE DO DASHBOARD ------
# ### MODIFICADO ### - Gráficos adicionados
col1, col2 = st.columns(2)
with col1:
    st.metric(label="🌡 Temperatura", value=st.session_state.temperatura)
with col2:
    st.metric(label="💧 Umidade", value=st.session_state.umidade)

st.markdown("---")

# ### ADICIONADO ### - Seção de Gráficos
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    st.subheader("Histórico de Temperatura")
    if not st.session_state.temp_data:
        st.info("Aguardando dados de temperatura para exibir o gráfico...")
    else:
        # Cria o DataFrame a partir do session_state
        temp_df = pd.DataFrame(st.session_state.temp_data)
        temp_df.rename(columns={"timestamp": "Horário", "value": "Temperatura (°C)"}, inplace=True)
        
        fig_temp = px.line(temp_df, x="Horário", y="Temperatura (°C)", markers=True)
        fig_temp.update_layout(
            xaxis_title="Horário", 
            yaxis_title="Temperatura (°C)",
            yaxis_range=[temp_df["Temperatura (°C)"].min() - 2, temp_df["Temperatura (°C)"].max() + 2] # Ajusta eixo Y
        )
        st.plotly_chart(fig_temp, use_container_width=True)

with col_graf2:
    st.subheader("Histórico de Umidade")
    if not st.session_state.umid_data:
        st.info("Aguardando dados de umidade para exibir o gráfico...")
    else:
        # Cria o DataFrame a partir do session_state
        umid_df = pd.DataFrame(st.session_state.umid_data)
        umid_df.rename(columns={"timestamp": "Horário", "value": "Umidade (%)"}, inplace=True)
        
        fig_umid = px.line(umid_df, x="Horário", y="Umidade (%)", markers=True)
        fig_umid.update_layout(
            xaxis_title="Horário", 
            yaxis_title="Umidade (%)",
            yaxis_range=[umid_df["Umidade (%)"].min() - 5, umid_df["Umidade (%)"].max() + 5] # Ajusta eixo Y
        )
        st.plotly_chart(fig_umid, use_container_width=True)

# ### FIM DA SEÇÃO DE GRÁFICOS ###

st.markdown("---")

# Seção de Status e Botões
col_status, col_btn1, col_btn2 = st.columns([2, 1, 1])

with col_status:
    status_color = "🟢" if st.session_state.conectado else "🔴"
    status_text = "Conectado" if st.session_state.conectado else "Desconectado"
    st.write(f"{status_color} **Status da Conexão:** {status_text}")
    st.write(f"**Broker:** {BROKER}:{PORT}")
    st.write(f"**Tópicos:** `{TOPICO_TEMPERATURA}`, `{TOPICO_UMIDADE}`")

with col_btn1:
    # ### MODIFICADO ### - Botão agora também limpa o histórico
    if st.button("🔄 Reiniciar Conexão e Gráficos"):
        logger.info("🔄 REINICIANDO CONEXÃO MQTT (LIMPANDO CACHE)...")
        st.cache_resource.clear()
        st.session_state.conectado = False
        st.session_state.temperatura = "Reiniciando..."
        st.session_state.umidade = "Reiniciando..."
        
        # ### ADICIONADO ### - Limpa os dados históricos
        st.session_state.temp_data = []
        st.session_state.umid_data = []
        logger.info("🧹 HISTÓRICO DOS GRÁFICOS LIMPO.")
        
        st.rerun()

with col_btn2:
    if st.button("📊 Status Completo no Terminal"):
        logger.info("📊 STATUS DO SISTEMA SOLICITADO:")
        logger.info(f"   - Conectado: {st.session_state.conectado}")
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
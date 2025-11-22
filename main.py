import streamlit as st
import paho.mqtt.client as mqtt
import time
import logging
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.express as px

# Configurar logging
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
st.set_page_config(page_title="Dashboard MQTT Pro", layout="wide", page_icon="🎛️")
st.title("🎛️ Centro de Controle Ambiental via MQTT")
st.markdown("Monitoramento em tempo real com alertas configuráveis.")
st.markdown("---")

# --- AUTOREFRESH ---
st_autorefresh(interval=1000, limit=None)

# Inicializar estado da sessão
if "temperatura" not in st.session_state:
    st.session_state.temperatura = "Aguardando..."
if "umidade" not in st.session_state:
    st.session_state.umidade = "Aguardando..."
if "conectado" not in st.session_state:
    st.session_state.conectado = False
    
# Histórico de dados
if "temp_data" not in st.session_state:
    st.session_state.temp_data = [] 
if "umid_data" not in st.session_state:
    st.session_state.umid_data = [] 

# ------ CALLBACKS MQTT ------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        st.session_state.conectado = True
        logger.info("✅ CONECTADO AO BROKER")
        client.subscribe(TOPICO_TEMPERATURA)
        client.subscribe(TOPICO_UMIDADE)
    else:
        st.session_state.conectado = False
        logger.error(f"❌ FALHA NA CONEXÃO - Código: {rc}")

def on_disconnect(client, userdata, rc):
    st.session_state.conectado = False
    logger.warning(f"🔌 DESCONECTADO - Código: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        valor_float = None
        try:
            valor_float = float(payload)
        except ValueError:
            return

        now = pd.Timestamp.now()
        
        if msg.topic == TOPICO_TEMPERATURA:
            st.session_state.temperatura = f"{valor_float:.1f} °C"
            st.session_state.temp_data.append({"timestamp": now, "value": valor_float})
            st.session_state.temp_data = st.session_state.temp_data[-100:]
            
        elif msg.topic == TOPICO_UMIDADE:
            st.session_state.umidade = f"{valor_float:.1f} %"
            st.session_state.umid_data.append({"timestamp": now, "value": valor_float})
            st.session_state.umid_data = st.session_state.umid_data[-100:]
            
    except Exception as e:
        logger.error(f"❌ ERRO: {e}")

# ------ CLIENTE MQTT ------
@st.cache_resource
def get_mqtt_client():
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.connect(BROKER, PORT, 60)
        client.loop_start() 
        return client
    except Exception as e:
        return None

# ------ HELPER PARA PARSEAR VALORES ------
def parse_value(val_str):
    """Extrai número de string como '25.5 °C'"""
    try:
        if isinstance(val_str, str) and " " in val_str:
            return float(val_str.split()[0])
        return None
    except:
        return None

# ------ INTERFACE ------
def main():
    client = get_mqtt_client()
    
    # ==============================================================================
    # SIDEBAR: CONFIGURAÇÕES DE ALERTA (Destaque)
    # ==============================================================================
    st.sidebar.header("⚙️ Configuração de Alertas")
    
    st.sidebar.subheader("🌡️ Temperatura")
    temp_min_alert = st.sidebar.number_input("Mínimo (°C)", value=18.0, step=0.5)
    temp_max_alert = st.sidebar.number_input("Máximo (°C)", value=28.0, step=0.5)
    
    st.sidebar.markdown("---")
    
    st.sidebar.subheader("💧 Umidade")
    umid_min_alert = st.sidebar.slider("Mínima (%)", 0, 100, 30)
    umid_max_alert = st.sidebar.slider("Máxima (%)", 0, 100, 70)

    st.sidebar.markdown("---")

    # ==============================================================================
    # SIDEBAR: EXPORTAÇÃO (Recolhido para limpar visual)
    # ==============================================================================
    with st.sidebar.expander("💾 Exportar Dados"):
        st.markdown("Baixar histórico CSV/JSON.")
        
        # Temp Export
        if st.session_state.temp_data:
            df_t = pd.DataFrame(st.session_state.temp_data)
            st.download_button("📥 CSV Temperatura", df_t.to_csv(index=False).encode('utf-8'), "temp.csv", "text/csv")
        else:
            st.text("Sem dados Temp.")
            
        # Umid Export
        if st.session_state.umid_data:
            df_u = pd.DataFrame(st.session_state.umid_data)
            st.download_button("📥 CSV Umidade", df_u.to_csv(index=False).encode('utf-8'), "umid.csv", "text/csv")
        else:
            st.text("Sem dados Umid.")

    # ==============================================================================
    # PAINEL PRINCIPAL: MÉTRICAS COM LÓGICA DE ALERTA
    # ==============================================================================
    
    # Parsear valores atuais para checar limites
    curr_temp_val = parse_value(st.session_state.temperatura)
    curr_umid_val = parse_value(st.session_state.umidade)

    col1, col2 = st.columns(2)

    # --- Cartão de Temperatura ---
    with col1:
        st.subheader("Temperatura")
        delta_temp = 0
        temp_status = "Normal"
        
        if curr_temp_val is not None:
            # Lógica de Alerta
            if curr_temp_val > temp_max_alert:
                st.error(f"⚠️ ALERTA: Temperatura Alta (> {temp_max_alert}°C)")
                delta_temp = f"+{curr_temp_val - temp_max_alert:.1f} acima do limite"
                temp_status = "CRÍTICO"
            elif curr_temp_val < temp_min_alert:
                st.warning(f"⚠️ ALERTA: Temperatura Baixa (< {temp_min_alert}°C)")
                delta_temp = f"{curr_temp_val - temp_min_alert:.1f} abaixo do limite"
                temp_status = "CRÍTICO"
            else:
                st.success("Temperatura dentro da faixa ideal")
                delta_temp = "Estável"
        
        st.metric(
            label="Atual", 
            value=st.session_state.temperatura, 
            delta=delta_temp,
            delta_color="inverse" if temp_status == "CRÍTICO" else "normal"
        )

    # --- Cartão de Umidade ---
    with col2:
        st.subheader("Umidade")
        delta_umid = 0
        umid_status = "Normal"

        if curr_umid_val is not None:
            # Lógica de Alerta
            if curr_umid_val > umid_max_alert:
                st.error(f"⚠️ ALERTA: Umidade Alta (> {umid_max_alert}%)")
                delta_umid = f"+{curr_umid_val - umid_max_alert:.1f}% acima do limite"
                umid_status = "CRÍTICO"
            elif curr_umid_val < umid_min_alert:
                st.warning(f"⚠️ ALERTA: Umidade Baixa (< {umid_min_alert}%)")
                delta_umid = f"{curr_umid_val - umid_min_alert:.1f}% abaixo do limite"
                umid_status = "CRÍTICO"
            else:
                st.success("Umidade dentro da faixa ideal")
                delta_umid = "Estável"

        st.metric(
            label="Atual", 
            value=st.session_state.umidade, 
            delta=delta_umid,
            delta_color="inverse" if umid_status == "CRÍTICO" else "normal"
        )

    st.markdown("---")

    # ==============================================================================
    # GRÁFICOS (VISUALIZANDO OS LIMITES)
    # ==============================================================================
    col_graf1, col_graf2 = st.columns(2)

    with col_graf1:
        st.markdown("### 📈 Tendência Térmica")
        if st.session_state.temp_data:
            df_temp = pd.DataFrame(st.session_state.temp_data)
            df_temp.rename(columns={"timestamp": "Horário", "value": "Temperatura"}, inplace=True)
            
            fig_temp = px.line(df_temp, x="Horário", y="Temperatura", markers=True)
            
            # Adicionar linhas de limite no gráfico
            fig_temp.add_hline(y=temp_max_alert, line_dash="dash", line_color="red", annotation_text="Max")
            fig_temp.add_hline(y=temp_min_alert, line_dash="dash", line_color="blue", annotation_text="Min")
            
            fig_temp.update_layout(yaxis_title="Temperatura (°C)", hovermode="x unified")
            st.plotly_chart(fig_temp, use_container_width=True)
        else:
            st.info("Aguardando dados...")

    with col_graf2:
        st.markdown("### 💧 Tendência Higrométrica")
        if st.session_state.umid_data:
            df_umid = pd.DataFrame(st.session_state.umid_data)
            df_umid.rename(columns={"timestamp": "Horário", "value": "Umidade"}, inplace=True)
            
            fig_umid = px.line(df_umid, x="Horário", y="Umidade", markers=True, color_discrete_sequence=['#00CC96'])
            
            # Adicionar linhas de limite no gráfico
            fig_umid.add_hline(y=umid_max_alert, line_dash="dash", line_color="red", annotation_text="Max")
            fig_umid.add_hline(y=umid_min_alert, line_dash="dash", line_color="orange", annotation_text="Min")
            
            fig_umid.update_layout(yaxis_title="Umidade (%)", hovermode="x unified")
            st.plotly_chart(fig_umid, use_container_width=True)
        else:
            st.info("Aguardando dados...")

    st.markdown("---")
    
    # Rodapé de Status
    col_status, col_reset = st.columns([3, 1])
    with col_status:
        st.caption(f"Broker: {BROKER} | Status: {'Conectado 🟢' if st.session_state.conectado else 'Desconectado 🔴'}")
    with col_reset:
        if st.button("🧹 Resetar Sistema"):
            st.session_state.temp_data = []
            st.session_state.umid_data = []
            st.cache_resource.clear()
            st.rerun()

if __name__ == "__main__":
    main()
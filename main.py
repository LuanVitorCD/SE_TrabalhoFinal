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
import streamlit as st
import pandas as pd
import plotly.express as px
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. CONFIGURAÇÃO E ESTADO INICIAL
# ==========================================
st.set_page_config(page_title="EcoSense IoT", layout="wide", page_icon="🌤️")
load_dotenv()

# Inicializa Session State
if 'historico_temp' not in st.session_state: st.session_state.historico_temp = pd.DataFrame()
if 'historico_umid' not in st.session_state: st.session_state.historico_umid = pd.DataFrame()
if 'kpi_temp' not in st.session_state: st.session_state.kpi_temp = {}
if 'kpi_umid' not in st.session_state: st.session_state.kpi_umid = {}
if 'last_history_update' not in st.session_state: st.session_state.last_history_update = None
if 'config_cache' not in st.session_state: 
    st.session_state.config_cache = {"temp_max": 30, "temp_min": 15, "umid_max": 80, "umid_min": 30}

# ==========================================
# 2. CONEXÃO FIREBASE
# ==========================================
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        st.error("🚨 Credenciais não encontradas.")
        st.stop()

db = firestore.client()
COLLECTION_DATA = os.getenv("COLLECTION_DATA", "estacao_dados")
COLLECTION_CONFIG = os.getenv("COLLECTION_CONFIG", "estacao_config")
DOC_CONFIG_ID = "limites_alerta"

# ==========================================
# 3. SIDEBAR (CONTROLE & CONFIGURAÇÃO)
# ==========================================
with st.sidebar:
    st.title("🎛️ Controle EcoSense")
    
    # --- BLOCO A: STATUS ---
    st.markdown("### 🚦 Monitoramento")
    ativo = st.toggle("ATIVAR ATUALIZAÇÃO", value=True)
    if ativo:
        st.caption("🟢 Online (KPIs a cada 15s)")
    else:
        st.caption("🔴 Pausado")

    intervalo_kpi = st.slider("Cooldown (segundos)", 10, 60, 15)
    
    st.markdown("---")
    
    # --- BLOCO B: CONFIGURAÇÃO DE LIMITES ---
    st.markdown("### 📡 Ajuste de Alertas (Remoto)")
    st.caption("Define quando os LEDs do ESP32 acendem.")
    
    # Botão para carregar config atual
    if st.button("🔄 Carregar Configuração Atual"):
        try:
            cfg = db.collection(COLLECTION_CONFIG).document(DOC_CONFIG_ID).get()
            if cfg.exists:
                st.session_state.config_cache = cfg.to_dict()
                st.success("✅ Configuração carregada do ARDUINO!")
            else:
                st.warning("Configuração não encontrada no banco.")
        except Exception as e:
            st.error(f"Erro ao ler: {e}")
    
    # Carrega do cache
    curr_cfg = st.session_state.config_cache
    
    with st.form("conf_form_sidebar"):
        st.markdown("**Temperatura (°C)**")
        c1, c2 = st.columns(2)
        nt_max = c1.number_input("Máx", value=float(curr_cfg.get('temp_max', 30)), key="in_t_max", label_visibility="collapsed")
        nt_min = c2.number_input("Mín", value=float(curr_cfg.get('temp_min', 15)), key="in_t_min", label_visibility="collapsed")
        
        st.markdown("**Umidade (%)**")
        c3, c4 = st.columns(2)
        nu_max = c3.number_input("Máx", value=float(curr_cfg.get('umid_max', 80)), key="in_u_max", label_visibility="collapsed")
        nu_min = c4.number_input("Mín", value=float(curr_cfg.get('umid_min', 30)), key="in_u_min", label_visibility="collapsed")
            
        if st.form_submit_button("💾 Enviar para ESP32"):
            # LÓGICA CORRIGIDA: Compara os valores digitados (nt/nu)
            if (nt_min >= nt_max) or (nu_min >= nu_max): 
                st.error("🚨 Erro de Lógica: O valor Mínimo não pode ser maior ou igual ao Máximo!")
            else:
                new_conf = {
                    "temp_max": nt_max, "temp_min": nt_min,
                    "umid_max": nu_max, "umid_min": nu_min
                }
                db.collection(COLLECTION_CONFIG).document(DOC_CONFIG_ID).set(new_conf)
                # Atualiza o cache local também para refletir a mudança imediata
                st.session_state.config_cache = new_conf
                st.success("✅ Comando enviado!")

    st.markdown("---")
    st.info(f"Última carga gráfica: {st.session_state.last_history_update if st.session_state.last_history_update else 'Nunca'}")

# Refresh automático
if ativo:
    st_autorefresh(interval=intervalo_kpi * 1000, key="kpi_refresher")

# ==========================================
# 4. FUNÇÕES OTIMIZADAS
# ==========================================

def update_kpis_with_delta():
    """Busca os 2 últimos registros para calcular o Delta (Tendência)."""
    try:
        # Temperatura (Pega 2 últimos)
        docs_t = db.collection(COLLECTION_DATA).where("tipo", "==", "temperatura")\
                   .order_by("timestamp", direction=firestore.Query.DESCENDING).limit(2).get()
        
        # Umidade (Pega 2 últimos)
        docs_h = db.collection(COLLECTION_DATA).where("tipo", "==", "umidade")\
                   .order_by("timestamp", direction=firestore.Query.DESCENDING).limit(2).get()
        
        # Processa Temp
        if docs_t:
            curr = docs_t[0].to_dict()
            prev = docs_t[1].to_dict() if len(docs_t) > 1 else curr
            st.session_state.kpi_temp = {
                "valor": curr['valor'],
                "delta": curr['valor'] - prev['valor'],
                "time": curr['timestamp']
            }
            
        # Processa Umid
        if docs_h:
            curr = docs_h[0].to_dict()
            prev = docs_h[1].to_dict() if len(docs_h) > 1 else curr
            st.session_state.kpi_umid = {
                "valor": curr['valor'],
                "delta": curr['valor'] - prev['valor'],
                "time": curr['timestamp']
            }
            
    except Exception as e:
        st.error(f"Erro KPI: {e}")

def update_history_heavy():
    """CUSTO: ALTO. Executado apenas manualmente."""
    try:
        limit_docs = 200
        
        docs_t = db.collection(COLLECTION_DATA).where("tipo", "==", "temperatura")\
                   .order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit_docs).stream()
        docs_h = db.collection(COLLECTION_DATA).where("tipo", "==", "umidade")\
                   .order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit_docs).stream()
            
        dt_t = [d.to_dict() for d in docs_t]
        dt_h = [d.to_dict() for d in docs_h]
        
        df_t = pd.DataFrame(dt_t)
        df_h = pd.DataFrame(dt_h)
        
        for df in [df_t, df_h]:
            if not df.empty and 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
        
        st.session_state.historico_temp = df_t
        st.session_state.historico_umid = df_h
        st.session_state.last_history_update = datetime.now().strftime("%H:%M:%S")
        
    except Exception as e:
        st.error(f"Erro Histórico: {e}")

# Executa KPI se ativo
if ativo:
    update_kpis_with_delta()

# ==========================================
# 5. INTERFACE DO DASHBOARD
# ==========================================

st.title("🌤️ EcoSense IoT")

# --- BLOCO VISUAL DE ALERTAS ---
# Recupera valores atuais e limites
v_temp = st.session_state.kpi_temp.get('valor')
v_umid = st.session_state.kpi_umid.get('valor')

# Se não tiver dados ainda, usa limites padrão para não quebrar a lógica
l_t_max = curr_cfg.get('temp_max', 30)
l_t_min = curr_cfg.get('temp_min', 15)
l_u_max = curr_cfg.get('umid_max', 80)
l_u_min = curr_cfg.get('umid_min', 30)

alert_t = False
alert_u = False

# Verifica Temp
if v_temp is not None:
    if v_temp > l_t_max or v_temp < l_t_min:
        alert_t = True

# Verifica Umid
if v_umid is not None:
    if v_umid > l_u_max or v_umid < l_u_min:
        alert_u = True

# Exibe o Alerta Visual
if alert_t and alert_u:
    st.error(f"🚨 ALERTA CRÍTICO: Temperatura ({v_temp}°C) e Umidade ({v_umid}%) fora dos limites!")
elif alert_t:
    st.warning(f"⚠️ Atenção: Temperatura de {v_temp}°C está fora do limite ({l_t_min}°C - {l_t_max}°C)!")
elif alert_u:
    st.warning(f"⚠️ Atenção: Umidade de {v_umid}% está fora do limite ({l_u_min}% - {l_u_max}%)!")
else:
    st.success("✅ Sistema Estável: Todos os parâmetros dentro dos limites.")

st.markdown("---")

# --- BLOCO 1: INDICADORES (KPIs) ---
col1, col2, col3 = st.columns(3)

def get_kpi_display(key, unit):
    data = st.session_state.get(key, {})
    val = data.get('valor', '--')
    delta = data.get('delta', 0)
    
    if val != '--':
        return f"{val:.1f} {unit}", f"{delta:.1f} {unit}"
    return "--", None

val_t, delta_t = get_kpi_display('kpi_temp', '°C')
val_u, delta_u = get_kpi_display('kpi_umid', '%')

col1.metric("Temperatura", val_t, delta_t)
col2.metric("Umidade", val_u, delta_u)

last_time = st.session_state.kpi_temp.get('time')
if last_time:
    t_str = last_time.strftime("%H:%M:%S") if isinstance(last_time, datetime) else str(last_time)
    col3.metric("Última Leitura", t_str, "Online")
else:
    col3.metric("Status", "Aguardando...", "Offline")

st.markdown("---")

# --- BLOCO 2: GRÁFICOS (SOB DEMANDA) ---
col_head, col_act = st.columns([3, 1])
col_head.subheader("📊 Análise Gráfica")

if col_act.button("🔄 ATUALIZAR GRÁFICOS (Custo Alto)"):
    with st.spinner("Baixando histórico..."):
        update_history_heavy()
    st.rerun()

tab1, tab2 = st.tabs(["🔥 Temperatura", "💧 Umidade"])

with tab1:
    if not st.session_state.historico_temp.empty:
        fig = px.line(st.session_state.historico_temp, x='timestamp', y='valor', markers=True, line_shape='spline')
        fig.update_traces(line_color='#FF4B4B')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados recentes na memória. Clique em 'Atualizar Gráficos'.")

with tab2:
    if not st.session_state.historico_umid.empty:
        fig = px.line(st.session_state.historico_umid, x='timestamp', y='valor', markers=True, line_shape='spline')
        fig.update_traces(line_color='#00CC96')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados recentes na memória. Clique em 'Atualizar Gráficos'.")

# --- BLOCO 3: DADOS BRUTOS & DOWNLOAD ---
st.markdown("---")
with st.expander("📂 Dados Brutos & Downloads"):
    st.markdown("Estes dados refletem o que está carregado na memória atual.")
    
    col_t, col_h = st.columns(2)
    
    with col_t:
        st.markdown("#### Temperatura")
        if not st.session_state.historico_temp.empty:
            csv_t = st.session_state.historico_temp.to_csv(index=False)
            st.download_button("📥 Baixar CSV (Temp)", csv_t, "temperatura.csv", "text/csv")
            st.dataframe(st.session_state.historico_temp, use_container_width=True, height=300)
        else:
            st.caption("Sem dados.")

    with col_h:
        st.markdown("#### Umidade")
        if not st.session_state.historico_umid.empty:
            csv_u = st.session_state.historico_umid.to_csv(index=False)
            st.download_button("📥 Baixar CSV (Umid)", csv_u, "umidade.csv", "text/csv")
            st.dataframe(st.session_state.historico_umid, use_container_width=True, height=300)
        else:
            st.caption("Sem dados.")
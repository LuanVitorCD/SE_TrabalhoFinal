import streamlit as st
import pandas as pd
import plotly.express as px
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
import os
import json
from streamlit_autorefresh import st_autorefresh

# ------ CONFIGURAÇÃO DA PÁGINA (Deve ser a primeira linha) ------
st.set_page_config(
    page_title="Monitoramento Ambiental",
    layout="wide",
    page_icon="🌡️",
    initial_sidebar_state="expanded"
)

# Carrega variáveis de ambiente
load_dotenv()

# ------ CSS PARA REMOVER PADDING E MELHORAR VISUAL (Anti-Flicker visual) ------
st.markdown("""
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        /* Esconde menu padrão do Streamlit para limpar visual */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ------ CONEXÃO FIREBASE ------
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")
    
    # Fallback local
    if not os.path.exists(cred_path) and os.path.exists("firebase_key.json"):
        cred_path = "firebase_key.json"
        
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        st.error("🚨 Erro Crítico: Credenciais do Firebase não encontradas.")
        st.stop()

db = firestore.client()
COLLECTION_DATA = os.getenv("COLLECTION_DATA", "estacao_dados")

# ------ BARRA LATERAL (CONTROLES) ------
with st.sidebar:
    st.header("🎛️ Controles")
    
    # 1. Seletor de Modo de Visualização
    modo_visualizacao = st.radio(
        "Período de Análise:",
        ("Monitoramento Real-Time (24h)", "Histórico por Data")
    )
    
    data_selecionada = None
    if modo_visualizacao == "Histórico por Data":
        data_selecionada = st.date_input("Selecione a data:", datetime.now())
    
    st.markdown("---")
    
    # 2. Controle de Atualização
    # Se estiver vendo histórico antigo, não precisa atualizar sozinho
    if modo_visualizacao == "Monitoramento Real-Time (24h)":
        auto_refresh = st.checkbox("Atualização Automática", value=True)
        if auto_refresh:
            # Intervalo de 5 segundos. key ajuda a manter o estado e evitar flicker excessivo
            st_autorefresh(interval=5000, key="data_refresh")
    else:
        st.info("Atualização automática pausada no modo Histórico.")

    st.markdown("---")
    st.caption(f"Conectado a: {COLLECTION_DATA}")

# ------ FUNÇÃO DE DADOS (COM CACHE PARA PERFORMANCE) ------
@st.cache_data(ttl=10 if modo_visualizacao == "Monitoramento Real-Time (24h)" else 3600)
def get_firestore_data(mode, selected_date=None):
    """
    Busca dados no Firestore.
    - mode='realtime': Últimas 24h
    - mode='history': Dia específico (00:00 a 23:59)
    """
    collection_ref = db.collection(COLLECTION_DATA)
    
    if mode == "realtime":
        start_time = datetime.now() - timedelta(hours=24)
        query = collection_ref.where("timestamp", ">=", start_time)
    else:
        # Filtro para o dia inteiro selecionado
        start_time = datetime.combine(selected_date, time.min)
        end_time = datetime.combine(selected_date, time.max)
        query = collection_ref.where("timestamp", ">=", start_time).where("timestamp", "<=", end_time)

    docs = query.order_by("timestamp", direction=firestore.Query.ASCENDING).stream()

    data_list = []
    for doc in docs:
        d = doc.to_dict()
        data_list.append(d)

    if not data_list:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(data_list)
    
    # Garantir datetime
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        # Remover fuso horário para evitar erros no Excel/JSON se houver mistura
        df['timestamp'] = df['timestamp'].dt.tz_localize(None)

    # Separação segura (verifica se coluna existe)
    col_tipo = 'valor_tipo' if 'valor_tipo' in df.columns else 'tipo'
    
    df_temp = df[df[col_tipo] == 'temperatura'].copy()
    df_hum = df[df[col_tipo] == 'umidade'].copy()
    
    return df_temp, df_hum

# ------ CARREGAMENTO DE DADOS ------
mode_param = "realtime" if modo_visualizacao == "Monitoramento Real-Time (24h)" else "history"
df_temp, df_hum = get_firestore_data(mode_param, data_selecionada)

# ------ LAYOUT PRINCIPAL ------
st.title("🎛️ Centro de Controle Ambiental")
st.markdown("Monitoramento IoT integrado com Firebase Firestore")
st.markdown("---")

# 1. KPIs (Métricas do Topo)
kpi1, kpi2, kpi3 = st.columns(3)

# KPI Temperatura
with kpi1:
    if not df_temp.empty:
        last_val = df_temp.iloc[-1]['valor']
        # Calcula delta se houver mais de 1 registro
        delta = float(last_val - df_temp.iloc[-2]['valor']) if len(df_temp) > 1 else 0.0
        st.metric("Temperatura", f"{last_val:.1f} °C", f"{delta:.1f} °C")
    else:
        st.metric("Temperatura", "--", None)

# KPI Umidade
with kpi2:
    if not df_hum.empty:
        last_val_h = df_hum.iloc[-1]['valor']
        delta_h = float(last_val_h - df_hum.iloc[-2]['valor']) if len(df_hum) > 1 else 0.0
        st.metric("Umidade", f"{last_val_h:.1f} %", f"{delta_h:.1f} %")
    else:
        st.metric("Umidade", "--", None)

# KPI Status / Info
with kpi3:
    if not df_temp.empty:
        last_time = df_temp.iloc[-1]['timestamp'].strftime("%H:%M:%S - %d/%m")
        st.metric("Última Atualização", last_time, delta_color="off")
    else:
        st.metric("Status", "Sem Dados", delta_color="off")

st.markdown("---")

# 2. Gráficos (Lado a Lado)
col_graf1, col_graf2 = st.columns(2)

with col_graf1:
    st.subheader("🔥 Evolução Térmica")
    if not df_temp.empty:
        fig_t = px.line(
            df_temp, 
            x="timestamp", 
            y="valor",
            labels={"timestamp": "Horário", "valor": "Temperatura (°C)"},
            color_discrete_sequence=['#FF4B4B'] # Vermelho estilo main.py
        )
        fig_t.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_t, use_container_width=True)
    else:
        st.warning("Aguardando dados de temperatura...")

with col_graf2:
    st.subheader("💧 Tendência Higrométrica")
    if not df_hum.empty:
        fig_h = px.line(
            df_hum, 
            x="timestamp", 
            y="valor",
            labels={"timestamp": "Horário", "valor": "Umidade (%)"},
            color_discrete_sequence=['#00CC96'] # Verde estilo main.py
        )
        # Adicionar linhas de referência visual (opcional, igual ao seu main original)
        fig_h.add_hline(y=75, line_dash="dot", line_color="gray", opacity=0.5)
        fig_h.update_layout(height=350, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.info("Aguardando dados de umidade...")

# 3. Área de Dados e Downloads
st.markdown("---")
with st.expander("📂 Exportar Dados (CSV / JSON)"):
    tab_t, tab_h = st.tabs(["Dados Temperatura", "Dados Umidade"])
    
    with tab_t:
        if not df_temp.empty:
            # Botão CSV
            csv_t = df_temp.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Temperatura (CSV)",
                data=csv_t,
                file_name="temperatura.csv",
                mime="text/csv"
            )
            # Botão JSON
            json_t = df_temp.to_json(orient="records", date_format="iso")
            st.download_button(
                label="📥 Baixar Temperatura (JSON)",
                data=json_t,
                file_name="temperatura.json",
                mime="application/json"
            )
            st.dataframe(df_temp.tail(10), use_container_width=True)
        else:
            st.write("Sem dados para exportar.")

    with tab_h:
        if not df_hum.empty:
            csv_h = df_hum.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Umidade (CSV)",
                data=csv_h,
                file_name="umidade.csv",
                mime="text/csv"
            )
            json_h = df_hum.to_json(orient="records", date_format="iso")
            st.download_button(
                label="📥 Baixar Umidade (JSON)",
                data=json_h,
                file_name="umidade.json",
                mime="application/json"
            )
            st.dataframe(df_hum.tail(10), use_container_width=True)
        else:
            st.write("Sem dados para exportar.")
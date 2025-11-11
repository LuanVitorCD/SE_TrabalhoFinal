import streamlit as st
import serial
import time
import pandas as pd
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- Configuração ---
PORTA_SERIAL = "COM5"  # <--- CONFIRME A PORTA
BAUD_RATE = 115200
# --------------------

# --- Funções Auxiliares ---
@st.cache_resource
def abrir_conexao_serial():
    try:
        # Timeout de 0.1s para leitura não-bloqueante
        ser = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=0.1) 
        time.sleep(2)
        return ser
    except serial.SerialException as e:
        st.error(f"❌ Erro ao abrir porta serial: {e}")
        st.error("Verifique a PORTA e se o Monitor Serial do Arduino esta FECHADO.")
        return None

def criar_grafico_interativo(dados):
    # Otimização: Se não há dados, retorna figura vazia
    if dados.empty:
        return go.Figure(layout={"template": "plotly_dark", "title": "Aguardando dados..."})
        
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    fig.add_trace(
        go.Scatter(
            x=dados['Timestamp'], 
            y=dados['Temperatura'],
            name="Temperatura",
            line=dict(color="#FF6B6B", width=3),
            mode="lines", # Otimização: 'lines' é mais rápido que 'lines+markers'
        ),
        secondary_y=False,
    )
    
    fig.add_trace(
        go.Scatter(
            x=dados['Timestamp'], 
            y=dados['Umidade'],
            name="Umidade",
            line=dict(color="#4ECDC4", width=3),
            mode="lines",
        ),
        secondary_y=True,
    )
    
    fig.update_layout(
        # title="Histórico de Temperatura e Umidade", # Título já está no st.markdown
        template="plotly_dark",
        hovermode="x unified",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=60, b=50),
        xaxis_rangeslider_visible=True # Adiciona um slider de zoom
    )
    
    fig.update_xaxes(title_text="Tempo")
    fig.update_yaxes(title_text="Temperatura (°C)", secondary_y=False)
    fig.update_yaxes(title_text="Umidade (%)", secondary_y=True)
    
    return fig

# --- Conexão Serial ---
ser = abrir_conexao_serial()
if ser is None:
    st.stop()

# --- Inicialização do Estado da Sessão ---
if 'dados_hist' not in st.session_state:
    # Otimização CRÍTICA: Usar lista, não DataFrame
    st.session_state.dados_hist = [] 
if 'ultima_temp' not in st.session_state:
    st.session_state.ultima_temp = 0.0
if 'ultima_umid' not in st.session_state:
    st.session_state.ultima_umid = 0.0
if 'alertas' not in st.session_state:
    st.session_state.alertas = []
if 'estatisticas' not in st.session_state:
    st.session_state.estatisticas = {
        'temp_max': -float('inf'),
        'temp_min': float('inf'),
        'umid_max': -float('inf'),
        'umid_min': float('inf'),
        'inicio_monitoramento': datetime.datetime.now()
    }
# Correção de Bug (Buffer Serial): Buffer para guardar dados incompletos
if 'serial_buffer' not in st.session_state:
    st.session_state.serial_buffer = ""

# --- Configuração da Página ---
st.set_page_config(
    page_title="Monitor de Ambiente Inteligente",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS Customizado (Restaurado) ---
st.markdown("""
<style>
    .main-header {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        border-radius: 15px;
        padding: 1.5rem;
        box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        border-left: 5px solid;
        transition: transform 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
    }
    
    .metric-value {
        font-size: 2.8rem;
        font-weight: 800;
        margin: 0.5rem 0;
    }
    
    .metric-label {
        font-size: 1.1rem;
        color: #bdc3c7;
        margin-bottom: 0.5rem;
    }
    
    .metric-unit {
        font-size: 1.2rem;
        color: #95a5a6;
    }
    
    .status-indicator {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-online {
        background-color: #2ecc71;
        box-shadow: 0 0 10px #2ecc71;
    }
    
    .alerta-item {
        background: rgba(231, 76, 60, 0.1);
        border-left: 4px solid #e74c3c;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 5px;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    
    .stats-card {
        background: rgba(52, 73, 94, 0.5);
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# --- Processamento de Dados (Correção Estrutural com Buffer) ---
max_pontos_sidebar = 200 # Valor padrão

# Correção de Bug (Buffer Serial): Lógica de leitura robusta
if ser.in_waiting > 0:
    # Lê todos os dados disponíveis no buffer serial
    dados_bytes = ser.read(ser.in_waiting)
    try:
        # Adiciona os novos dados ao nosso buffer de sessão
        st.session_state.serial_buffer += dados_bytes.decode('utf-8')
    except UnicodeDecodeError:
        print("Erro de decode, byte corrompido ignorado.")
        st.session_state.serial_buffer = "" # Limpa buffer em caso de lixo

# Processa o buffer linha por linha
linhas = st.session_state.serial_buffer.split('\n')

# A última linha pode estar incompleta, então a guardamos de volta no buffer
st.session_state.serial_buffer = linhas[-1]

# Processa todas as linhas completas (todas menos a última)
for linha in linhas[:-1]:
    mensagem = linha.strip() # Limpa espaços em branco e \r
    if not mensagem:
        continue # Ignora linhas vazias

    try:
        if mensagem.startswith("T:"):
            nova_temp = float(mensagem[2:])
            st.session_state.ultima_temp = nova_temp
            st.session_state.estatisticas['temp_max'] = max(st.session_state.estatisticas['temp_max'], nova_temp)
            st.session_state.estatisticas['temp_min'] = min(st.session_state.estatisticas['temp_min'], nova_temp)
            
        elif mensagem.startswith("U:"):
            nova_umid = float(mensagem[2:])
            st.session_state.ultima_umid = nova_umid
            st.session_state.estatisticas['umid_max'] = max(st.session_state.estatisticas['umid_max'], nova_umid)
            st.session_state.estatisticas['umid_min'] = min(st.session_state.estatisticas['umid_min'], nova_umid)
            
            # Adiciona ao histórico (somente após receber U, para ter o par T/U)
            novo_ponto_dict = {
                'Timestamp': datetime.datetime.now(),
                'Temperatura': st.session_state.ultima_temp,
                'Umidade': st.session_state.ultima_umid
            }
            st.session_state.dados_hist.append(novo_ponto_dict)

    except Exception as e:
        # Se a linha estava corrompida (ex: "T:22.3U:50"), o float() falha.
        # Esta exceção pega o erro e o descarta, evitando o bug "2230".
        print(f"Erro ao processar linha: {e} | Linha: '{mensagem}'")


# --- Sidebar (Agora é interativa) ---
with st.sidebar:
    st.markdown("## ⚙️ Configurações")
    
    st.markdown("### 🔔 Alertas")
    temp_alerta = st.slider("Temperatura de Alerta (°C)", -10, 50, 30)
    umid_alerta = st.slider("Umidade de Alerta (%)", 0, 100, 80)
    
    st.markdown("### 📊 Gráfico")
    # Correção: O slider agora funciona em tempo real
    max_pontos_sidebar = st.slider("Pontos no gráfico", 50, 500, 200)
    
    # Trunca a lista de dados aqui, usando o valor do slider
    if len(st.session_state.dados_hist) > max_pontos_sidebar:
        st.session_state.dados_hist = st.session_state.dados_hist[-max_pontos_sidebar:]
    
    # Estatísticas (movidas para o final para estarem sempre atualizadas)
    st.markdown("### 📈 Estatísticas")
    tempo_monitoramento = datetime.datetime.now() - st.session_state.estatisticas['inicio_monitoramento']
    st.metric("Tempo de Monitoramento", f"{str(tempo_monitoramento).split('.')[0]}")
    st.metric("Leituras Coletadas", len(st.session_state.dados_hist))
    
    col1, col2 = st.columns(2)
    with col1:
        temp_max_val = st.session_state.estatisticas['temp_max'] if st.session_state.estatisticas['temp_max'] > -float('inf') else 0
        temp_min_val = st.session_state.estatisticas['temp_min'] if st.session_state.estatisticas['temp_min'] < float('inf') else 0
        st.metric("Temp Máxima", f"{temp_max_val:.1f}°C")
        st.metric("Temp Mínima", f"{temp_min_val:.1f}°C")
    with col2:
        umid_max_val = st.session_state.estatisticas['umid_max'] if st.session_state.estatisticas['umid_max'] > -float('inf') else 0
        umid_min_val = st.session_state.estatisticas['umid_min'] if st.session_state.estatisticas['umid_min'] < float('inf') else 0
        st.metric("Umid Máxima", f"{umid_max_val:.1f}%")
        st.metric("Umid Mínima", f"{umid_min_val:.1f}%")


# --- Layout Principal ---
# (O layout agora é desenhado *depois* da leitura dos dados)
st.markdown('<p class="main-header">🌡️ Monitor de Ambiente Inteligente</p>', unsafe_allow_html=True)

col_status, col_temp, col_umid = st.columns([1, 2, 2])
with col_status:
    st.markdown("### Status do Sistema")
    st.markdown('<span class="status-indicator status-online"></span> Conectado', unsafe_allow_html=True)
    st.metric("Porta Serial", PORTA_SERIAL)

# Métricas principais (desenhadas uma vez com dados do session_state)
with col_temp:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #FF6B6B;">
        <div class="metric-label">🌡️ Temperatura Atual</div>
        <div class="metric-value">{st.session_state.ultima_temp:.1f} <span class="metric-unit">°C</span></div>
    </div>
    """, unsafe_allow_html=True)

with col_umid:
    st.markdown(f"""
    <div class="metric-card" style="border-left-color: #4ECDC4;">
        <div class="metric-label">💧 Umidade Atual</div>
        <div class="metric-value">{st.session_state.ultima_umid:.1f} <span class="metric-unit">%</span></div>
    </div>
    """, unsafe_allow_html=True)

# Alertas (processados em tempo real)
if st.session_state.ultima_temp > temp_alerta:
    alerta_msg = f"⚠️ Temperatura alta: {st.session_state.ultima_temp:.1f}°C"
    if alerta_msg not in st.session_state.alertas:
        st.session_state.alertas.append(alerta_msg)
        
if st.session_state.ultima_umid > umid_alerta:
    alerta_msg = f"⚠️ Umidade alta: {st.session_state.ultima_umid:.1f}%"
    if alerta_msg not in st.session_state.alertas:
        st.session_state.alertas.append(alerta_msg)

# Limpa alertas antigos se as condições voltarem ao normal
if st.session_state.ultima_temp <= temp_alerta and st.session_state.ultima_umid <= umid_alerta:
    st.session_state.alertas = []

if st.session_state.alertas:
    st.markdown("### 🔔 Alertas Ativos")
    # Mostra apenas os 3 alertas mais recentes
    for alerta in st.session_state.alertas[-3:]: 
        st.markdown(f'<div class="alerta-item">{alerta}</div>', unsafe_allow_html=True)

# Gráfico interativo
st.markdown("### 📊 Histórico em Tempo Real")
# Otimização: Criar o DataFrame uma vez, aqui.
df_para_grafico = pd.DataFrame(st.session_state.dados_hist)
fig = criar_grafico_interativo(df_para_grafico)
st.plotly_chart(fig, use_container_width=True)

# Tabela de dados recentes
st.markdown("### 📋 Dados Recentes")
if not df_para_grafico.empty:
    dados_recentes = df_para_grafico.tail(10).copy()
    # Converte Timestamp para H:M:S (mais limpo)
    dados_recentes['Timestamp'] = dados_recentes['Timestamp'].dt.strftime('%H:%M:%S')
    # Arredonda valores para 1 casa decimal
    dados_recentes['Temperatura'] = dados_recentes['Temperatura'].round(1)
    dados_recentes['Umidade'] = dados_recentes['Umidade'].round(1)
    
    st.dataframe(dados_recentes.set_index('Timestamp'), use_container_width=True)

# --- Loop de Atualização (Correção Estrutural) ---
# Removemos o `while True` e usamos `st.rerun()`
# Isso mantém o app interativo
time.sleep(0.1) # Uma pequena pausa para não sobrecarregar a CPU
st.rerun()
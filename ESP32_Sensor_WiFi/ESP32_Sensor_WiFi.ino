/*
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
 */

// --- BIBLIOTECAS NECESSÁRIAS ---
// Certifique-se de instalá-las via Gerenciador de Bibliotecas da Arduino IDE.
#include <WiFi.h>             // Para conexão com a rede Wi-Fi
#include <PubSubClient.h>     // Para comunicação via protocolo MQTT
#include <Wire.h>             // Para comunicação I2C (Display)
#include <Adafruit_GFX.h>     // Gráficos do Display
#include <Adafruit_SSD1306.h> // Driver do Display OLED SSD1306
#include <DHT.h>              // Driver do sensor de temperatura/umidade
#include <ArduinoJson.h>      // Essencial para interpretar as configurações enviadas pelo PC (JSON)

// --- CONFIGURAÇÕES DE REDE (CREDENCIAIS) ---
const char* ssid = "Visitante";      // Nome da sua rede Wi-Fi
const char* password = "";           // Senha da rede (vazio se for aberta)
const char* mqtt_server = "broker.hivemq.com"; // Endereço do Broker MQTT (Nuvem)
const int mqtt_port = 1883;          // Porta padrão MQTT

// --- DEFINIÇÃO DOS TÓPICOS MQTT ---
// É através destes endereços que o ESP32 e o PC conversam.
const char* topic_pub_temp = "esp32/streamlit/temperatura"; // Tópico de envio (Temperatura)
const char* topic_pub_hum  = "esp32/streamlit/umidade";     // Tópico de envio (Umidade)
const char* topic_sub_conf = "esp32/streamlit/config";      // Tópico de escuta (Configurações)

// --- MAPEAMENTO DE HARDWARE (PINOS) ---
#define DHTPIN 2       // Pino de dados do sensor DHT22
#define DHTTYPE DHT22  // Modelo do sensor
#define LED_RED   25   // LED de Alerta de Temperatura
#define LED_BLUE  26   // LED de Alerta de Umidade
#define LED_GREEN 27   // LED de Status Normal
#define BUTTON_PIN 38  // Botão central do T-Beam (para menu local)

// --- CONFIGURAÇÃO DO DISPLAY OLED ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// --- OBJETOS GLOBAIS ---
DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

// --- VARIÁVEIS DE CONTROLE DO SISTEMA ---
// Armazenam os limites recebidos da nuvem. Iniciam com valores padrão de segurança.
float conf_temp_max = 30.0;
float conf_temp_min = 15.0;
float conf_umid_max = 80.0;
float conf_umid_min = 30.0;

// Variáveis para controlar o estado dos Alertas (Verdadeiro/Falso)
bool alerta_temp_ativo = false;
bool alerta_umid_ativo = false;

// Controle do Menu no Display (0 = Monitoramento, 1 = Configuração)
int menu_state = 0;
unsigned long lastDebounceTime = 0; // Para evitar leituras falsas do botão

// Controle de tempo para Piscar LEDs (Non-blocking)
unsigned long previousMillisBlink = 0; 
const long blinkInterval = 300; // Velocidade da piscada em ms (300ms = rápido/urgente)
bool ledState = LOW; // Estado atual da piscada (Ligado/Desligado)

// ======================================================================================
// FUNÇÃO 1: CALLBACK MQTT
// Esta função é executada AUTOMATICAMENTE sempre que chega uma mensagem no tópico de config.
// ======================================================================================
void callback(char* topic, byte* payload, unsigned int length) {
  // 1. Converte a mensagem recebida (bytes) para uma String legível
  String msg;
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  
  Serial.print("Nova configuração recebida: ");
  Serial.println(msg);

  // 2. Interpreta o formato JSON (Ex: {"temp_max": 30, ...})
  StaticJsonDocument<256> doc; 
  DeserializationError error = deserializeJson(doc, msg);

  if (!error) {
    // 3. Se o JSON for válido, atualiza as variáveis globais do sistema
    if (doc.containsKey("temp_max")) conf_temp_max = doc["temp_max"];
    if (doc.containsKey("temp_min")) conf_temp_min = doc["temp_min"];
    if (doc.containsKey("umid_max")) conf_umid_max = doc["umid_max"];
    if (doc.containsKey("umid_min")) conf_umid_min = doc["umid_min"];
    Serial.println("Limites atualizados com sucesso!");
  } else {
    Serial.println("Erro ao ler JSON da configuração.");
  }
}

// ======================================================================================
// FUNÇÃO 2: ATUALIZAR STATUS DOS ALERTAS
// Verifica se os valores lidos estão dentro ou fora dos limites estabelecidos.
// ======================================================================================
void verificarAlertas(float t, float h) {
  // Define se há alerta de temperatura (Acima do máx OU abaixo do mín)
  alerta_temp_ativo = (t > conf_temp_max || t < conf_temp_min);
  
  // Define se há alerta de umidade
  alerta_umid_ativo = (h > conf_umid_max || h < conf_umid_min);
}

// ======================================================================================
// FUNÇÃO 3: CONTROLE DE LEDS (COM PISCADA DE URGÊNCIA)
// Executada a cada ciclo do loop para criar o efeito de piscar sem parar o código.
// ======================================================================================
void gerenciarLeds() {
  unsigned long currentMillis = millis();

  // Verifica se passou o tempo do intervalo (300ms)
  if (currentMillis - previousMillisBlink >= blinkInterval) {
    // Salva o último tempo que piscou
    previousMillisBlink = currentMillis;

    // Inverte o estado do LED (Se estava acesso, apaga. Se apagado, acende)
    if (ledState == LOW) {
      ledState = HIGH;
    } else {
      ledState = LOW;
    }

    // --- LÓGICA DO LED VERMELHO (TEMPERATURA) ---
    if (alerta_temp_ativo) {
      digitalWrite(LED_RED, ledState); // Pisca indicando perigo
    } else {
      digitalWrite(LED_RED, LOW);      // Mantém desligado se normal
    }

    // --- LÓGICA DO LED AZUL (UMIDADE) ---
    if (alerta_umid_ativo) {
      digitalWrite(LED_BLUE, ledState); // Pisca indicando perigo
    } else {
      digitalWrite(LED_BLUE, LOW);      // Mantém desligado se normal
    }

    // --- LÓGICA DO LED VERDE (NORMALIDADE) ---
    // O verde fica ACESO DIRETO se não houver nenhum problema.
    // Se houver qualquer alerta, o verde apaga para chamar atenção ao erro.
    if (!alerta_temp_ativo && !alerta_umid_ativo) {
      digitalWrite(LED_GREEN, HIGH);
    } else {
      digitalWrite(LED_GREEN, LOW);
    }
  }
}

// ======================================================================================
// FUNÇÃO 4: ATUALIZAR DISPLAY OLED
// Mostra as informações para o usuário localmente.
// ======================================================================================
void showDisplay(float t, float h) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE);
  
  if (menu_state == 0) {
    // TELA PRINCIPAL: Dados em tempo real
    display.setCursor(0, 0); display.println("EcoSense IoT - ESP32");
    
    // Mostra leituras atuais
    display.setCursor(0, 15); display.printf("T:%.1f C  H:%.1f %%", t, h);
    
    // Mostra os limites configurados (para verificação visual)
    display.setCursor(0, 35); 
    display.printf("Lim T: %.0f-%.0f", conf_temp_min, conf_temp_max);
    display.setCursor(0, 45); 
    display.printf("Lim H: %.0f-%.0f", conf_umid_min, conf_umid_max);
    
    // Indicador visual de alerta no display
    if(alerta_temp_ativo || alerta_umid_ativo) {
        display.setCursor(90, 55); display.print("ALERTA!");
    }
  } else {
    // TELA SECUNDÁRIA: Menu de informações
    display.setCursor(0, 0); display.println("-- INFO SISTEMA --");
    display.setCursor(0, 20); display.println("Config via Dashboard");
    display.setCursor(0, 35); display.print("IP: "); display.println(WiFi.localIP());
    display.setCursor(0, 50); display.print("Broker: "); display.println(client.connected() ? "OK" : "Erro");
  }
  display.display();
}

// ======================================================================================
// FUNÇÃO 5: RECONEXÃO MQTT
// Garante que o ESP32 volte a se conectar se a internet cair.
// ======================================================================================
void reconnect() {
  // Loop até conectar
  while (!client.connected()) {
    Serial.print("Tentando conexão MQTT...");
    // Tenta conectar com um ID único
    if (client.connect("ESP32_EcoSense_Client")) {
      Serial.println("Conectado!");
      // IMPORTANTE: Inscreve-se no tópico para VOLTAR a receber configurações
      client.subscribe(topic_sub_conf); 
    } else {
      Serial.print("Falha rc=");
      Serial.print(client.state());
      Serial.println(" tentando novamente em 5s");
      delay(5000); // Bloqueante apenas na falha de conexão (segurança)
    }
  }
}

// ======================================================================================
// SETUP (CONFIGURAÇÃO INICIAL)
// Executado apenas uma vez ao ligar o ESP32.
// ======================================================================================
void setup() {
  Serial.begin(115200);

  // 1. Configura Pinos dos LEDs e Botão
  pinMode(LED_RED, OUTPUT); 
  pinMode(LED_BLUE, OUTPUT); 
  pinMode(LED_GREEN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP); // Resistor interno para evitar ruído

  // 2. Inicia Sensor e Display
  dht.begin();
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("Falha no Display OLED"));
    for(;;); // Trava o código se não tiver display
  }
  
  // 3. Conecta ao Wi-Fi
  Serial.print("Conectando WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Conectado!");

  // 4. Configura Servidor MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback); // Define a função que processa mensagens recebidas
}

// ======================================================================================
// LOOP PRINCIPAL
// Este código roda infinitamente e o mais rápido possível.
// ======================================================================================
void loop() {
  // 1. Mantém a conexão MQTT viva
  if (!client.connected()) reconnect();
  client.loop();

  // 2. Gerencia o Piscar dos LEDs (Roda muito rápido para efeito visual suave)
  gerenciarLeds();

  // 3. Leitura do Botão Físico (Alterna telas do display)
  if (digitalRead(BUTTON_PIN) == LOW) {
    if (millis() - lastDebounceTime > 300) { // Debounce de 300ms
      menu_state = !menu_state;
      lastDebounceTime = millis();
    }
  }

  // 4. Leitura do Sensor e Envio de Dados (Temporizado)
  // Usamos millis() em vez de delay() para NÃO parar o piscar dos LEDs
  static unsigned long lastMsg = 0;
  if (millis() - lastMsg > 15000) { // Executa a cada 15 segundos (Economia Firebase)
    lastMsg = millis();
    
    // Lê temperatura e umidade
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    // Verifica se a leitura é válida (não é NaN)
    if (!isnan(t) && !isnan(h)) {
      // a) Verifica se precisa ativar alertas
      verificarAlertas(t, h);

      // b) Atualiza o Display
      showDisplay(t, h);
      
      // c) Envia para a nuvem via MQTT
      char buf[8];
      dtostrf(t, 1, 2, buf); client.publish(topic_pub_temp, buf);
      dtostrf(h, 1, 2, buf); client.publish(topic_pub_hum, buf);
      
      Serial.printf("Dados Enviados -> T: %.2f | H: %.2f\n", t, h);
    } else {
      Serial.println("Erro na leitura do sensor DHT!");
    }
  }
}
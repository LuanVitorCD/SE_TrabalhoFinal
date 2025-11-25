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

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <ArduinoJson.h>

// --- CONFIGURAÇÕES DE REDE ---
const char* ssid = "Visitante";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;

// --- TÓPICOS MQTT (ALINHADOS COM O PYTHON) ---
// O Python espera ler nestes canais:
const char* topic_pub_temp = "esp32/sensor/temperatura";
const char* topic_pub_hum  = "esp32/sensor/umidade";

// O Python envia configuração neste canal (AGORA CORRIGIDO):
const char* topic_sub_conf = "esp32/config/limites";

// --- HARDWARE ---
#define DHTPIN 2
#define DHTTYPE DHT22
#define LED_RED 13   // Alerta Temperatura
#define LED_BLUE 25   // Alerta Umidade
#define LED_GREEN 32   // Status OK (Conectado e sem alertas)
#define BUTTON_PIN 38

// --- DISPLAY ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// --- OBJETOS ---
DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

// --- VARIÁVEIS GLOBAIS (DADOS) ---
float current_temp = 0.0;
float current_hum = 0.0;

// --- CONFIGURAÇÕES (LIMITES INICIAIS) ---
float conf_temp_max = 30.0;
float conf_temp_min = 15.0;
float conf_umid_max = 80.0;
float conf_umid_min = 30.0;

// --- CONTROLE DE ESTADO ---
bool alerta_temp_ativo = false;
bool alerta_umid_ativo = false;
int menu_state = 0; // 0 = Home, 1 = Info
unsigned long lastDebounceTime = 0;

// Timers
unsigned long previousMillisBlink = 0;
unsigned long previousMillisReconnect = 0;
const long blinkInterval = 300;
bool ledStateBlink = LOW;

// ======================================================================================
// CALLBACK MQTT (A MÁGICA ACONTECE AQUI)
// ======================================================================================
void callback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (int i = 0; i < length; i++) msg += (char)payload[i];
  
  Serial.println("\n--- 📩 CHEGOU MENSAGEM ---");
  Serial.print("Tópico: "); Serial.println(topic);
  Serial.print("Payload: "); Serial.println(msg);

  // Buffer aumentado para garantir que cabe o JSON inteiro
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, msg);

  if (!error) {
    // Atualiza as variáveis SOMENTE se o campo existir no JSON
    if (doc.containsKey("temp_max")) conf_temp_max = doc["temp_max"];
    if (doc.containsKey("temp_min")) conf_temp_min = doc["temp_min"];
    if (doc.containsKey("umid_max")) conf_umid_max = doc["umid_max"];
    if (doc.containsKey("umid_min")) conf_umid_min = doc["umid_min"];
    
    Serial.println("✅ Configurações aplicadas!");
    Serial.printf("Novo Range Temp: %.1f - %.1f\n", conf_temp_min, conf_temp_max);
    Serial.printf("Novo Range Umid: %.1f - %.1f\n", conf_umid_min, conf_umid_max);
    
    // Feedback Visual no Display (Para você saber que funcionou)
    display.clearDisplay();
    display.setTextSize(2);
    display.setCursor(10, 20);
    display.println("CONFIG OK!");
    display.setTextSize(1);
    display.setCursor(10, 45);
    display.println("Atualizado.");
    display.display();
    delay(2000); // Pausa breve para ler a mensagem
    
    // Recalcula alertas com os novos limites imediatamente
    verificarAlertas(current_temp, current_hum);
    showDisplay(); 
  } else {
    Serial.print("❌ Erro JSON: ");
    Serial.println(error.c_str());
  }
}

// ======================================================================================
// VERIFICAR ALERTAS
// ======================================================================================
void verificarAlertas(float t, float h) {
  if (isnan(t) || isnan(h)) return;

  alerta_temp_ativo = (t > conf_temp_max || t < conf_temp_min);
  alerta_umid_ativo = (h > conf_umid_max || h < conf_umid_min);
}

// ======================================================================================
// GERENCIAR LEDS
// ======================================================================================
void gerenciarLeds() {
  unsigned long currentMillis = millis();

  // Pisca LEDs de Alerta
  if (currentMillis - previousMillisBlink >= blinkInterval) {
    previousMillisBlink = currentMillis;
    ledStateBlink = !ledStateBlink;

    if (alerta_temp_ativo) digitalWrite(LED_RED, ledStateBlink ? HIGH : LOW);
    else digitalWrite(LED_RED, LOW);

    if (alerta_umid_ativo) digitalWrite(LED_BLUE, ledStateBlink ? HIGH : LOW);
    else digitalWrite(LED_BLUE, LOW);
  }

  // LED Verde: Aceso se tudo estiver normal e conectado
  if (WiFi.status() == WL_CONNECTED && client.connected() && !alerta_temp_ativo && !alerta_umid_ativo) {
    digitalWrite(LED_GREEN, HIGH);
  } else {
    digitalWrite(LED_GREEN, LOW);
  }
}

// ======================================================================================
// DISPLAY
// ======================================================================================
void showDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(WHITE);
  
  if (menu_state == 0) {
    // TELA 1: MONITORAMENTO
    display.setCursor(0, 0); display.println("EcoSense - Monitor");
    display.drawFastHLine(0, 10, 128, WHITE);

    display.setTextSize(1);
    display.setCursor(0, 20); display.printf("Temp: %.1f C", current_temp);
    display.setCursor(0, 35); display.printf("Umid: %.1f %%", current_hum);

    // Rodapé de status
    display.setCursor(0, 55);
    if(alerta_temp_ativo || alerta_umid_ativo) {
       display.print("!! ALERTA ATIVO !!");
    } else {
       display.print("Status: Normal");
    }
    
  } else {
    // TELA 2: CONFIGURAÇÃO (Aqui você verá se atualizou)
    display.setCursor(0, 0); display.println("LIMITES ATUAIS");
    display.drawFastHLine(0, 10, 128, WHITE);
    
    // Mostra float com 1 casa decimal para confirmar precisão
    display.setCursor(0, 20); display.printf("T.Max:%.1f T.Min:%.1f", conf_temp_max, conf_temp_min);
    display.setCursor(0, 35); display.printf("U.Max:%.1f U.Min:%.1f", conf_umid_max, conf_umid_min);
    
    display.setCursor(0, 55);
    display.print(client.connected() ? "MQTT: ON" : "MQTT: OFF");
  }
  display.display();
}

// ======================================================================================
// RECONEXÃO MQTT
// ======================================================================================
void attemptReconnect() {
  unsigned long now = millis();
  if (now - previousMillisReconnect > 5000) {
    previousMillisReconnect = now;
    
    Serial.print("Conectando MQTT... ");
    // ID Aleatório para evitar desconexão por conflito
    String clientId = "ESP32_Eco_" + String(random(0xffff), HEX);

    if (client.connect(clientId.c_str())) {
      Serial.println("OK!");
      // *** O PULO DO GATO ESTÁ AQUI EMBAIXO ***
      client.subscribe(topic_sub_conf);
      Serial.print("Ouvindo em: "); Serial.println(topic_sub_conf);
    } else {
      Serial.print("Falha rc="); Serial.println(client.state());
    }
  }
}

// ======================================================================================
// SETUP
// ======================================================================================
void setup() {
  Serial.begin(115200);

  // Configuração Pinos
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Teste Rápido de LEDs
  digitalWrite(LED_RED, HIGH); delay(100); digitalWrite(LED_RED, LOW);
  digitalWrite(LED_BLUE, HIGH); delay(100); digitalWrite(LED_BLUE, LOW);

  // Sensor e Display
  dht.begin();
  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("Falha OLED")); for(;;);
  }
  display.clearDisplay();
  display.setCursor(0,20); display.println("Conectando WiFi...");
  display.display();

  // WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\nWiFi OK");
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

// ======================================================================================
// LOOP
// ======================================================================================
void loop() {
  // 1. MQTT
  if (!client.connected()) {
    attemptReconnect();
  } else {
    client.loop(); // Essencial para receber as mensagens
  }

  // 2. LEDs
  gerenciarLeds();

  // 3. Botão (Alterna telas)
  if (digitalRead(BUTTON_PIN) == LOW) {
    if (millis() - lastDebounceTime > 250) {
      menu_state = !menu_state;
      lastDebounceTime = millis();
      showDisplay();
    }
  }

  // 4. Leitura Sensor (A cada 15s)
  static unsigned long lastMsg = 0;
  if (millis() - lastMsg > 15000) {
    lastMsg = millis();
    
    float t = dht.readTemperature();
    float h = dht.readHumidity();

    if (!isnan(t) && !isnan(h)) {
      current_temp = t;
      current_hum = h;

      verificarAlertas(current_temp, current_hum);
      showDisplay();
      
      if (client.connected()) {
        char buf[8];
        dtostrf(current_temp, 1, 2, buf); client.publish(topic_pub_temp, buf);
        dtostrf(current_hum, 1, 2, buf); client.publish(topic_pub_hum, buf);
        Serial.println("Dados enviados.");
      }
    } else {
      Serial.println("Erro DHT!");
    }
  }
}
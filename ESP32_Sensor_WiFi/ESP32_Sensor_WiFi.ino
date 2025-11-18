/*
 * Código ESP32: Cliente MQTT com Display OLED
 *
 * 1. Conecta-se ao Wi-Fi.
 * 2. Conecta-se ao broker MQTT (broker.hivemq.com).
 * 3. Lê o sensor DHT22.
 * 4. Mostra o status e as leituras no display OLED.
 * 5. Publica (envia) os dados para os tópicos MQTT.
 *
 * Bibliotecas necessárias na IDE do Arduino:
 * - "DHT sensor library" (da Adafruit)
 * - "Adafruit GFX Library"
 * - "Adafruit SSD1306"
 * - "PubSubClient" (por Nick O'Leary)
 */

#include <WiFi.h>
#include <PubSubClient.h> // Biblioteca MQTT
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>

// --- Configurações do Usuário ---
const char* ssid = "Visitante";
// const char* password = ""; // Deixe comentado se a rede for aberta

#define DHTPIN 2
#define DHTTYPE DHT22

// --- Configurações do Display ---
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C

// --- Configurações MQTT ---
const char* mqtt_server = "broker.hivemq.com";
const int mqtt_port = 1883;
// Tópicos para onde vamos enviar os dados
const char* topico_temperatura = "esp32/streamlit/temperatura";
const char* topico_umidade = "esp32/streamlit/umidade";

// --- Inicializa os objetos ---
DHT dht(DHTPIN, DHTTYPE);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);
WiFiClient espClient;
PubSubClient client(espClient);

// --- Função showDisplay ---
void showDisplay(const String &line1, const String &line2 = "", const String &line3 = "") {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(line1);
  if (line2 != "") {
    display.setCursor(0, 20);
    display.println(line2);
  }
  if (line3 != "") {
    display.setCursor(0, 40);
    display.println(line3);
  }
  display.display();
}

// --- Funções de Conexão ---
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid); // Se tiver senha, use: WiFi.begin(ssid, password);
  showDisplay("Conectando WiFi...");
  Serial.print("Conectando ao WiFi: ");
  Serial.println(ssid);
  
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi conectado!");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
    showDisplay("WiFi conectado!", "IP:", WiFi.localIP().toString());
  } else {
    Serial.println("\nFalha ao conectar WiFi.");
    showDisplay("WiFi falhou!", "Sem conexao...");
  }
  delay(1000);
}

void reconnectMQTT() {
  while (!client.connected()) {
    Serial.print("Tentando MQTT...");
    showDisplay("Conectando MQTT...", "Broker:", mqtt_server);

    // Tenta se conectar
    if (client.connect("ESP32-Streamlit-Client")) { // ID único do cliente
      Serial.println("conectado!");
      showDisplay("MQTT Conectado!");
    } else {
      Serial.print("falhou rc=");
      Serial.print(client.state());
      Serial.println(" - tentando de novo em 5s");
      showDisplay("MQTT falhou!", "Tentando reconexao...");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  if(!display.begin(SSD1306_SWITCHCAPVCC, SCREEN_ADDRESS)) {
    Serial.println(F("Erro ao iniciar display SSD1306!"));
    for(;;);
  }
  display.clearDisplay();
  display.display();

  connectWiFi();
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  // Garante que o WiFi está conectado
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }
  
  // Garante que o MQTT está conectado
  if (!client.connected()) {
    reconnectMQTT();
  }

  // Permite que o cliente MQTT processe mensagens
  client.loop();

  // Leitura do sensor (a cada 5 segundos)
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (isnan(h) || isnan(t)) {
    Serial.println("Falha ao ler DHT!");
    showDisplay("Erro sensor DHT!", "Verifique conexao");
  } else {
    // Converte os floats para strings
    char bufT[8], bufH[8];
    dtostrf(t, 4, 1, bufT); // formato (float, min_width, precision, buffer)
    dtostrf(h, 4, 1, bufH);

    // Publica os dados nos tópicos
    client.publish(topico_temperatura, bufT, true); // true = reter a mensagem
    client.publish(topico_umidade, bufH, true);

    Serial.printf("Publicado: Temp: %s C | Umid: %s %%\n", bufT, bufH);

    // Mostra no display
    String l1 = "MQTT: OK (Enviando)";
    String l2 = "Temp: " + String(bufT) + " C";
    String l3 = "Umid: " + String(bufH) + " %";
    showDisplay(l1, l2, l3);
  }

  delay(5000); // Envia dados a cada 5 segundos
}
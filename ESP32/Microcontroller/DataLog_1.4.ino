/*
  ESP32 Datalogger - Microcontroller

  Description:
  This program logs sensor data and transmits it over Bluetooth using an ESP32 microcontroller.

  Author:
  Blaine Wu 

  Date:
  2024-07-10

  Version:
  1.4

  Changes in Version 1.4:
  - Client Specified Sensor Inputs
  
  Future Updates:
  - Automatic resistor switching
  - Add support for additional sensors.

  Notes:
  - Adjust settings in setup() as needed.
  
  Connections:
  - Sensor connected to GPIO pins.
  - Bluetooth module connected to UART pins.
*/

#include <Arduino.h>
#include <FS.h>
#include <SPIFFS.h>
#include "DHT.h"
#include "BluetoothSerial.h"
#include <Ticker.h>

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run make menuconfig to and enable it
#endif

#define DHTPIN 5     // Digital pin connected to the DHT sensor
#define DHTTYPE DHT11   // DHT 11
const int sensorPin = A5; // Define the ADC5 pin 
const int buttonPin = 4; // GPIO 4 for the button

String DataLogFileName = "/datalog1.csv";

DHT dht(DHTPIN, DHTTYPE); 
BluetoothSerial SerialBT;
Ticker dataGrabTimer;

volatile bool autoUpdate = false; // Global flag for autoupdating (live data transmission)

// Variables to store sensor data
int adcValue = 0;
float voltage = 0.0;
float humidity = 0.0;
float temperature = 0.0;
float heatIndex = 0.0;

void handleBluetoothData(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  if (event == ESP_SPP_DATA_IND_EVT) {
    if (SerialBT.available()) {
      String receivedData = SerialBT.readStringUntil('\n');
      receivedData.trim(); // Remove any leading/trailing whitespace
      Serial.print("Received via Bluetooth: ");
      Serial.println(receivedData); // Debug print

      if (receivedData.equals("DATALOG")) {
        Serial.println("Sending File...");
        sendFileOverBluetooth();
      } else if (receivedData.equals("TOGGLE ON AUTOUPDATE")) {
        autoUpdate = true;
      } else if (receivedData.equals("TOGGLE OFF AUTOUPDATE")) {
        autoUpdate = false;
      }
    }
  } else if (event == ESP_SPP_SRV_OPEN_EVT) {
    Serial.println("Bluetooth Connected");
  } else if (event == ESP_SPP_CLOSE_EVT) {
    Serial.println("Bluetooth Disconnected");
    autoUpdate = false;
  }
}

void setup() {
  // Initialize serial communication at 115200 baud
  Serial.begin(115200);

  // Initialize Bluetooth
  SerialBT.begin("ESP32"); // Bluetooth device name
  Serial.println("The device started, now you can pair it with bluetooth!");

  // Initialize SPIFFS and format if needed
  if (!SPIFFS.begin(true)) {
    Serial.println("An error occurred while mounting SPIFFS");
    return;
  }
  Serial.println("SPIFFS mounted successfully.");

  // Set the button pin as input
  pinMode(buttonPin, INPUT_PULLUP);

  // Register Bluetooth callback
  SerialBT.register_callback(handleBluetoothData);

  // Start DHT sensing
  dht.begin();

  // Create/Open a file on SPIFFS
  File dataFile = SPIFFS.open(DataLogFileName, FILE_APPEND);
  if (!dataFile) {
    Serial.println("Failed to open file for writing");
    return;
  }

  // Write a header to the file if it's empty
  if (dataFile.size() == 0) {
    dataFile.println("Time,ADC Value,Voltage,Humidity,Temperature,Heat Index");
  }
  dataFile.close();

  // Set up a timer to call grabData every 5 seconds
  dataGrabTimer.attach(1, grabData);
}

void loop() {
  delay(10);
}

void grabData() {
  // Reading temperature or humidity takes about 250 milliseconds!
  // Sensor readings may also be up to 2 seconds 'old' (its a very slow sensor)
  Serial.println("Reading...");
  humidity = dht.readHumidity();
  // Read temperature as Celsius (the default)
  temperature = dht.readTemperature();
  // Check if any reads failed and exit early (to try again).
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println(F("Failed to read from DHT sensor!"));
    return;
  }

  // Compute heat index in Celsius (isFahreheit = false)
  heatIndex = dht.computeHeatIndex(temperature, humidity, false);

  // Read the analog value from the sensor
  adcValue = analogRead(sensorPin);
  
  // Convert the ADC value to voltage
  voltage = adcValue * (3.3 / 4095.0);
  
  // Open the file for appending
  File dataFile = SPIFFS.open(DataLogFileName, FILE_APPEND);
  if (dataFile) {
    // Log the data with timestamp
    dataFile.print(millis() / 1000); // Time in seconds
    dataFile.print(",");
    dataFile.print(humidity);
    dataFile.print(",");
    dataFile.print(temperature);
    dataFile.print(",");
    dataFile.print(heatIndex);
    dataFile.print(",");  
    dataFile.print(adcValue);
    dataFile.print(",");
    dataFile.println(voltage);
    dataFile.close(); // Close the file to save changes
  } else {
    Serial.println("Error opening datalog");
  }

  if (SerialBT.hasClient()){
    if (autoUpdate) {
      Serial.println("Sending Live Data");
      sendReadings();
    }
  }
}

void sendReadings() {
  Serial.print(millis() / 1000);
  Serial.print(",");
  Serial.print(humidity);
  Serial.print(",");
  Serial.print(temperature);
  Serial.print(",");
  Serial.print(heatIndex);
  Serial.print(",");
  Serial.print(adcValue);
  Serial.print(",");
  Serial.print(voltage);
  SerialBT.print(millis() / 1000);
  SerialBT.print(",");
  SerialBT.print(humidity);
  SerialBT.print(",");
  SerialBT.print(temperature);
  SerialBT.print(",");
  SerialBT.print(heatIndex);
  SerialBT.print(",");
  SerialBT.print(adcValue);
  SerialBT.print(",");
  SerialBT.println(voltage);
}

void sendFileOverBluetooth() {
  File file = SPIFFS.open(DataLogFileName, "r");
  if (!file) {
    Serial.println("Failed to open file!");
    return; 
  }
  // Define the size of the data chunk to read and send
  const int chunkSize = 2048; // Adjust chunk size as needed
  char chunk[chunkSize];

  // Read and send the file content via Bluetooth in chunks
  while (file.available()) {
    int bytesRead = file.readBytes(chunk, chunkSize);
    if (bytesRead > 0) {
      SerialBT.write((const uint8_t*)chunk, bytesRead); // Cast chunk to const uint8_t* before sending
      Serial.print("Chunk: ");
      Serial.write(chunk, bytesRead); // Print the chunk to serial monitor
      Serial.println(); // Add a new line for readability
    }
    else {
      Serial.println("No Data Read");
      break;
    }
  }

  file.close(); // Close the file after sending 
  Serial.println("File sent successfully.");
}

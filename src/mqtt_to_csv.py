import paho.mqtt.client as mqtt
import csv
import time


input_file = 'sensor_data.csv'
output_file = 'cleaned_sensor_data.csv'

sensor_data = {
    "temperature": None,
    "humidity": None,
    "light": None,
    "timestamp": None
}


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT connected successfully!")
        client.subscribe("swsc/data/temperature")
        client.subscribe("swsc/data/humidity")
        client.subscribe("swsc/data/light")
    else:
        print(f"MQTT connection failed with code {rc}")

def on_message(client, userdata, msg):
    # Mendapatkan data dari payload
    data = msg.payload.decode("utf-8")
    timestamp = time.time()  # Mengambil timestamp saat data diterima
    
    if msg.topic == "swsc/data/temperature":
        sensor_data["temperature"] = data
    elif msg.topic == "swsc/data/humidity":
        sensor_data["humidity"] = data
    elif msg.topic == "swsc/data/light":
        sensor_data["light"] = data

    if sensor_data["temperature"] is not None and sensor_data["humidity"] is not None and sensor_data["light"] is not None:
        # Menyimpan data lengkap ke dalam CSV
        write_to_csv(sensor_data["temperature"], sensor_data["humidity"], sensor_data["light"], timestamp)

        # Reset data setelah menyimpannya
        sensor_data["temperature"] = None
        sensor_data["humidity"] = None
        sensor_data["light"] = None

# Menulis data ke file CSV
def write_to_csv(temperature, humidity, light, timestamp):
    with open(output_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        
        # Jika file kosong, tulis header
        if file.tell() == 0:  # Mengecek apakah file kosong
            writer.writerow(["Timestamp", "Temperature (C)", "Humidity (%)", "Light (Lux)"])

        # Menulis data ke file CSV
        writer.writerow([timestamp, temperature, humidity, light])

    print(f"Data diterima dan disimpan: Temperature={temperature}, Humidity={humidity}, Light={light}")

# Setup MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Menghubungkan ke broker MQTT
client.connect("broker.hivemq.com", 1883, 60)

client.loop_forever()

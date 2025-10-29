# Smart Wellness and Study Companion

<p align="center">
  <img src="testing/Screenshot%202025-10-29%20124015.png" width="500">
</p>

<br>
Proyek Smart Wellness & Study Companion (SWSC) merupakan sistem IoT berbasis ESP32 yang dirancang untuk membantu pelajar menjaga kesehatan dan produktivitas selama belajar. Sistem ini memantau kondisi lingkungan seperti suhu, kelembapan, dan pencahayaan menggunakan sensor DHT11 dan LDR, lalu menampilkan data secara real-time melalui layar OLED dan antarmuka web. Selain itu, SWSC menyediakan fitur pengingat istirahat dan minum air otomatis dengan alarm buzzer serta indikator LED yang dikendalikan melalui protokol MQTT dan backend Flask. Melalui integrasi sensor, aktuator, serta kontrol waktu berbasis logika pemrograman, sistem ini bertujuan menciptakan pengalaman belajar yang lebih sehat, interaktif, dan adaptif terhadap kebutuhan pengguna

## Menjalankan Program

1. Pastikan Perangkat IoT (hardware) tersedia dan terhubung

2. Clone repository

```bash
git clone <repository_url>
cd SIC7_SMART-WELLNESS-AND-STUDY-COMPANION
```
3. Buat virtual environment (opsional)

```bash
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows
```

4. Install dependensi

```bash
pip install -r requirements.txt
```

5. Jalankan server Flask

```bash
python src/controller.py
```

6. Akses di browser

```bash
http://127.0.0.1:5000
```

## Kontributor

|          Nama          |
| :--------------------: |
|    Guntara Hambali     |
| Nahiza Hazim Valensi M |
|  Muh. Rusmin Nurwadin  |
|   Reza Ahmad Syarif    |

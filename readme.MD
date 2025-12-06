# Smart Wellness and Study Companion

<p align="center">
  <img src="testing/Screenshot%202025-10-29%20124015.png" width="500">
</p>

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
pip install -r requirements.txt --default-timeout=300
```

5. Jalankan server Flask

```bash
cd src
python main.py
```

6. Akses di browser

```bash
http://127.0.0.1:5000
```

## Pipeline AI/ML Lingkungan (baru)

- **Data**: kumpulkan CSV minimal 150 baris dari sensor (`temperature, humidity, light, label`) ke `data/raw/environment.csv`.
- **Training**: jalankan `python scripts/train_env_model.py --input data/raw/environment.csv --output models/environment.pkl`.
- **Serving**: backend otomatis memuat model dari `models/environment.pkl` (atau melatih model sintetis fallback jika belum ada) lalu mengirim label & confidence ke dashboard dan MQTT alert.

Struktur tambahan:
```
data/raw/              # simpan dataset mentah
data/processed/        # opsional untuk dataset hasil bersih
models/environment.pkl # hasil training classifier lingkungan
scripts/train_env_model.py
```

## Kontributor

|          Nama          |
| :--------------------: |
|    Guntara Hambali     |
| Nahiza Hazim Valensi M |
|  Muh. Rusmin Nurwadin  |
|   Reza Ahmad Syarif    |

# Smart Wellness and Study Companion

<p align="center">
  <img src="testing/Screenshot%202025-10-29%20124015.png" width="500">
</p>

Proyek Smart Wellness & Study Companion (SWSC) merupakan sistem IoT berbasis ESP32 yang dirancang untuk membantu pelajar menjaga kesehatan dan produktivitas selama belajar. Sistem ini memantau kondisi lingkungan seperti suhu, kelembapan, dan pencahayaan menggunakan sensor DHT11 dan LDR, lalu menampilkan data secara real-time melalui layar OLED dan antarmuka web. Selain itu, SWSC menyediakan fitur pengingat istirahat dan minum air otomatis dengan alarm buzzer serta indikator LED yang dikendalikan melalui protokol MQTT dan backend Flask. Melalui integrasi sensor, aktuator, serta kontrol waktu berbasis logika pemrograman, sistem ini bertujuan menciptakan pengalaman belajar yang lebih sehat, interaktif, dan adaptif terhadap kebutuhan pengguna

## Struktur Singkat

- `src/` : kode backend (FastAPI, scheduler, model inference) **dan** modul training ML (`app/training/env_model.py`).
- `dashboard/` : UI Streamlit yang memanggil API backend.
- `scripts/train_env_model.py` : wrapper CLI untuk memanggil modul training di `src/`.
- `data/` & `src/models/` : lokasi dataset dan model terlatih.
- `src/firmware/` : kode ESP32 (tidak dieksekusi Python, tetap dipertahankan).

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

5. Jalankan server FastAPI (hanya API, UI utama via Streamlit)

```bash
cd src
python main.py
```

6. Jalankan dashboard Streamlit (UI utama)

```bash
cd ..
streamlit run dashboard/streamlit_app.py --server.port 8501
```

> Catatan: UI HTML/CSS lama tidak lagi dipakai; API tetap tersedia di port FastAPI (default 5000) untuk diakses Streamlit.

## Pipeline AI/ML Lingkungan (baru)

- **Data**: kumpulkan CSV minimal 150 baris dari sensor (`temperature, humidity, light, label`) ke `data/raw/environment.csv`.
- **Training**: jalankan dari root repo:
  - `python scripts/train_env_model.py --input data/processed/final_dataset.csv --output src/models/environment.pkl`
  - atau (jika berada di folder `src/`): `python -m app.training.env_model --input ../data/processed/final_dataset.csv --output ./models/environment.pkl`
- **Serving**: backend otomatis memuat model dari `src/models/environment.pkl` (atau melatih model sintetis fallback jika belum ada) lalu mengirim label & confidence ke dashboard dan MQTT alert.

Struktur tambahan:
```
data/raw/              # simpan dataset mentah
data/processed/        # opsional untuk dataset hasil bersih
src/models/environment.pkl # hasil training classifier lingkungan
scripts/train_env_model.py
src/app/training/env_model.py
```

## Dashboard Streamlit

Jalankan dashboard yang membaca API FastAPI:
```bash
streamlit run dashboard/streamlit_app.py --server.port 8501
```
Atur `API Base URL` di UI (default `http://localhost:5000`). Tombol: Start/Stop/Reset plan, dan panel status sensor + prediksi ML realtime (klik Refresh bila perlu).

## Kontributor

|          Nama          |
| :--------------------: |
|    Guntara Hambali     |
| Nahiza Hazim Valensi M |
|  Muh. Rusmin Nurwadin  |
|   Reza Ahmad Syarif    |

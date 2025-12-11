# Smart Wellness and Study Companion

Smart Wellness & Study Companion (SWSC) adalah sistem IoT berbasis ESP32 untuk membantu pelajar menjaga kesehatan dan fokus belajar. Sensor DHT11 dan LDR memantau suhu, kelembapan, serta cahaya, lalu data dikirim ke backend FastAPI dan ditampilkan di dashboard Streamlit. Sistem menambahkan pengingat minum, jadwal istirahat, serta deteksi emosi melalui kamera sebagai masukan kondisi belajar.

## Fitur Utama
- Pemantauan suhu, kelembapan, dan cahaya secara real-time via MQTT dan WebSocket.
- Perhitungan rencana belajar (durasi belajar, jeda, dan target konsumsi air) dengan kontrol Start/Stop/Reset.
- Prediksi kenyamanan lingkungan memakai model DTL (tersimpan di `src/models/environment.pkl`).
- Deteksi emosi dari kamera, summary sesi, dan ekspor CSV.
- Mode simulasi untuk demo tanpa perangkat IoT.

## Arsitektur Singkat
- **Backend** (`src/`): FastAPI, scheduler, MQTT client, dan inference model lingkungan.
- **Dashboard** (`dashboard/`): Streamlit UI yang memanggil API dan WebSocket backend.
- **Training** (`scripts/train_env_model.py`, `src/app/training/env_model.py`): melatih model lingkungan dari CSV.
- **Firmware** (`src/firmware/`): kode ESP32 CAM dan SWSC (tidak dijalankan di Python).
- **Data/Model**: dataset di `data/`, model terlatih di `src/models/`.

## Struktur Folder
- `src/` – backend dan modul ML.
- `dashboard/` – antarmuka Streamlit.
- `scripts/` – utilitas pelatihan.
- `data/` – data mentah dan olahan.
- `src/models/` – model lingkungan terlatih.
- `src/firmware/` – kode mikrokontroler.

## Cara Menjalankan
1) Siapkan Python 3 dan (opsional) virtualenv.  
2) Instal dependensi:
```bash
pip install -r requirements.txt
```
3) Jalankan backend FastAPI:
```bash
cd src
python main.py
```
Backend default di `http://localhost:5000`.

4) Jalankan dashboard Streamlit (dari root repo):
```bash
streamlit run dashboard/streamlit_app.py --server.port 8501
```
Sesuaikan `API Base URL` di UI bila backend berada di host/port lain.

## Dataset dan Pelatihan Model Lingkungan
- Dataset olahan: `data/processed/final_dataset.csv` (format kolom: `temperature, humidity, light, label`).
- Latih ulang model:
```bash
python scripts/train_env_model.py --input data/processed/final_dataset.csv --output src/models/environment.pkl
```
Backend akan memuat berkas model tersebut; jika tidak ada, ia melatih model sintetis bawaan agar prediksi tetap tersedia.

## Dashboard dan Endpoint Utama
- `/status` dan `ws://.../ws/status` – kirim data sensor, status scheduler, serta prediksi lingkungan ke UI.
- `/camera/analyze` – terima gambar webcam untuk deteksi emosi dan pakaian.
- `/emotion/summary` dan `/emotion/export` – ringkasan emosi sesi dan ekspor CSV.
- Kontrol belajar: `/start`, `/stop`, `/reset`, serta `/water_ack` untuk kuota minum.

## Kontributor

| Nama                  | Tugas                                                         |
|-----------------------|--------------------------------------------------------------|
| Guntara Hambali       | Menyusun laporan dan membuat kode model Machine Learning      |
| Nahiza Hazim Valensi M| Merangkai komponen IoT dan membuat kode                       |
| Muh. Rusmin Nurwadin  | Menyusun laporan dan membuat kode Dashboard                   |
| Reza Ahmad Syarif     | Merangkai komponen IoT dan membuat kode                       |

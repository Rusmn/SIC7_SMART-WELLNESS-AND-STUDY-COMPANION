import pandas as pd
import numpy as np

try:
    df = pd.read_csv('data/raw/unlabeled_sensor_data.csv')
    print("Data sensor berhasil dimuat.")
except FileNotFoundError:
    print("Error: File unlabeled_sensor_data.csv tidak ditemukan. Jalankan script generator dulu.")
    exit()

total_rows = len(df)
part_size = total_rows // 3

df['Pakaian'] = 'Sedang'

df.loc[0:part_size-1, 'Pakaian'] = 'Tipis'
df.loc[part_size : (part_size*2)-1, 'Pakaian'] = 'Sedang'
df.loc[(part_size*2):, 'Pakaian'] = 'Tebal'

print("Deteksi pakaian selesai.")

def labeling_sni_3_kelas(row):
    temp = row['Temperature']
    hum = row['Humidity']
    clothing = row['Pakaian']

    if hum < 30 or hum > 70:
        return "Tidak Nyaman"
    
    is_humidity_ideal = (40 <= hum <= 60)

    shift = 0
    if clothing == 'Tipis':
        shift = 1.5
    elif clothing == 'Tebal':
        shift = -1.5
    
    opt_min = 22.8 + shift
    opt_max = 25.8 + shift
    
    tol_min = 20.5 + shift
    tol_max = 27.1 + shift

    if temp < tol_min or temp > tol_max:
        return "Tidak Nyaman"
    
    if opt_min <= temp <= opt_max:
        if is_humidity_ideal:
            return "Nyaman"
        else:
            return "Kurang Nyaman"
    else:
        return "Kurang Nyaman"

print("Memproses labeling SNI...")
df['Label_Prediksi'] = df.apply(labeling_sni_3_kelas, axis=1)

output_filename = 'data/processed/final_dataset_labeled.csv'
df.to_csv(output_filename, index=False)
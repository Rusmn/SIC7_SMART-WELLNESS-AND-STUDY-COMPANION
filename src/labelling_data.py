import csv

# Fungsi untuk menentukan apakah lingkungan ideal untuk belajar
def get_status(temperature, humidity, light):
    issues = []
    
    # Mengecek suhu
    if temperature < 20 or temperature > 30:
        issues.append("Temperature")
    
    # Mengecek kelembapan
    if humidity < 40 or humidity > 70:
        issues.append("Humidity")
    
    # Mengecek kecerahan
    if light == 0:
        issues.append("Light (Too Dark)")
    
    # Jika tidak ada masalah, lingkungan dianggap ideal
    if len(issues) == 0:
        return "Ideal"  # Ideal for studying
    else:
        return "Not Ideal"  # Not ideal for studying

# Membaca data CSV dan melabeli status lingkungan
def label_ideal_for_studying(input_csv, output_csv):
    with open(input_csv, mode='r') as infile:
        reader = csv.DictReader(infile)
        rows = list(reader)
        
        # Menambahkan kolom baru untuk status "Label"
        for row in rows:
            # Mengambil data suhu, kelembapan, dan kecerahan
            temperature = float(row["Temperature (C)"]) if row["Temperature (C)"] else 0
            humidity = float(row["Humidity (%)"]) if row["Humidity (%)"] else 0
            light = float(row["Light (Lux)"]) if row["Light (Lux)"] else 0
            
            # Menentukan status lingkungan
            row["Label"] = get_status(temperature, humidity, light)
        
        # Menulis ulang data yang sudah dilabeli ke file CSV baru
        with open(output_csv, mode='w', newline='') as outfile:
            fieldnames = reader.fieldnames + ["Label"]
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

# Nama file CSV input dan output
input_file = 'cleaned_sensor_data.csv'  # Ganti dengan nama file input CSV yang sesuai
output_file = 'labeled_data.csv'  # Nama file output yang ingin dibuat

label_ideal_for_studying(input_file, output_file)

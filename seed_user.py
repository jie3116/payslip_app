import pandas as pd
from utils.helpers import add_user

EXCEL_FILE = 'data/user_seed.xlsx'

def seed_users_from_excel():
    # Paksa baca kolom NUP sebagai string supaya tidak jadi float (64306.0)
    df = pd.read_excel(EXCEL_FILE, dtype={'NUP': str})

    success_count = 0
    fail_count = 0

    for _, row in df.iterrows():
        nup_raw = row['NUP']
        ttl_raw = pd.to_datetime(row['TTL'], errors='coerce')

        # Cek jika NUP kosong
        if pd.isna(nup_raw):
            print("⚠️  Baris dengan NUP kosong dilewati.")
            fail_count += 1
            continue

        # Cek jika TTL tidak valid
        if pd.isna(ttl_raw):
            print(f"⚠️  Baris dengan NUP {nup_raw} memiliki TTL kosong atau tidak valid, dilewati.")
            fail_count += 1
            continue

        # Normalisasi NUP agar tidak ada spasi
        nup = nup_raw.strip()

        # Format password dari TTL → ddmmyyyy
        ttl = ttl_raw.strftime('%d%m%Y')

        # Tambahkan user ke database
        add_user(nup, ttl, role='pegawai')
        success_count += 1

    print(f"\n✅ {success_count} user berhasil dimasukkan ke database.")
    print(f"❌ {fail_count} user dilewati karena data tidak valid.")

if __name__ == '__main__':
    seed_users_from_excel()

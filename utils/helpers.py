# helpers.py
from werkzeug.security import generate_password_hash, check_password_hash
from models.db import get_db_connection, get_db_cursor
import math
import pandas as pd
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

# ==========================
# UTILITY FUNCTIONS
# ==========================

def clean_column_names(df):
    """
    Bersihkan nama kolom DataFrame: strip, ganti spasi/dash jadi underscore, UPPERCASE.
    """
    df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('-', '_').str.upper()
    return df

def round_half_up(n):
    """
    Pembulatan ke atas jika >=0.5, ke bawah jika <0.5
    """
    if n >= 0:
        return math.floor(n + 0.5)
    else:
        return math.ceil(n - 0.5)

def format_rupiah(value):
    """
    Format angka ke Rupiah: 10000 -> 10.000
    """
    try:
        value = float(value)
        value = round_half_up(value)
        return f"{int(value):,}".replace(",", ".")
    except:
        return "0"

# ==========================
# DATABASE USER FUNCTIONS
# ==========================

def get_user_by_nup(nup):
    """
    Get user by NUP from database
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE nup = %s", (nup,))
            result = cur.fetchone()
            return result  # Returns dict or None due to RealDictCursor
    except Exception as e:
        logger.error(f"Error getting user {nup}: {str(e)}")
        return None

def check_user_password(nup, password):
    """
    Cek password user
    """
    try:
        user = get_user_by_nup(nup)
        if user:
            return check_password_hash(user['password'], password)
        return False
    except Exception as e:
        logger.error(f"Error checking password for {nup}: {str(e)}")
        return False

def update_password(nup, new_password):
    """
    Update password user
    """
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "UPDATE users SET password = %s, updated_at = CURRENT_TIMESTAMP WHERE nup = %s",
                (generate_password_hash(new_password), nup)
            )
            return True
    except Exception as e:
        logger.error(f"Error updating password for {nup}: {str(e)}")
        return False

def add_user(nup, plain_password, role='pegawai'):
    """
    Tambah user baru atau update jika NUP sudah ada
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO users (nup, password, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (nup) DO UPDATE
                SET password = EXCLUDED.password,
                    role = EXCLUDED.role,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING nup
            """, (nup, generate_password_hash(plain_password), role))
            
            result = cur.fetchone()
            if result:
                logger.info(f"User {nup} successfully added/updated with role {role}")
                return True
            return False
            
    except Exception as e:
        logger.error(f"Error adding user {nup}: {str(e)}")
        return False

# ==========================
# KOMPOSISI GAJI
# ==========================

def get_komponen_by_status(user_dict):
    """
    Pisahkan komponen THP, komponen lain, dan potongan berdasarkan status pegawai
    """
    status = str(user_dict.get('STATUS_PEGAWAI', '')).lower()

    if status == 'pkwtt':
        komponen_thp = {
            "Gaji Dasar 1": user_dict.get("GAJI_DASAR_1", 0),
            "Gaji Dasar 2": user_dict.get("GAJI_DASAR_2", 0),
            "Tunjangan Grade": user_dict.get("TUNJ_GRADE", 0)
        }
        komponen_lain = {
            "Insentif": user_dict.get("INSENTIF", 0),
            "Rapel": user_dict.get("RAPEL", 0),
            "Tunjangan Struktural": user_dict.get("TUNJ_STRUKTURAL", 0),
            "Uang Makan": user_dict.get("FOODING", 0),
            "Uang Transport": user_dict.get("TRANSPORT", 0),
            "Telpon": user_dict.get("TELPON", 0),
            "Uang Bensin": user_dict.get("BENSIN", 0),
            "Uang Perumahan": user_dict.get("PERUMAHAN", 0),
            "EToll": user_dict.get("ETOLL", 0),
            "Tunjangan Kendaraan": user_dict.get("KENDARAAN", 0)
        }
        komponen_potongan = {
            "IDP": user_dict.get("IDP", 0),
            "PIP": user_dict.get("PIP", 0),
            "DPLK": user_dict.get("DPLK", 0),
            "Simp. Wajib Koperasi": user_dict.get("SIKOP", 0),
            "Pinjaman Koperasi": user_dict.get("PINKOP", 0),
            "Serikat Pekerja": user_dict.get("SP", 0),
            "BPJS Ketenagakerjaan - JHT": user_dict.get("JAMSOSTEK", 0),
            "BPJS Ketenagakerjaan - JP": user_dict.get("JAMINAN_PENSIUN", 0),
            "BPJS Kesehatan": user_dict.get("BPJS_KESEHATAN", 0),
            "Lain-Lain": user_dict.get("LAIN_LAIN", 0)
        }

    elif status == 'pkwt':
        komponen_thp = {
            "Honorarium": user_dict.get("GAJI_KONTRAK", 0),
            "Bantuan DPLK": user_dict.get("BANTUAN_DPLK", 0)
        }
        komponen_lain = {
            "Insentif": user_dict.get("INSENTIF", 0),
            "Uang Makan": user_dict.get("FOODING", 0),
            "Uang Transport": user_dict.get("TRANSPORT", 0)
        }
        komponen_potongan = {
            "DPLK": user_dict.get("DPLK", 0),
            "Simp. Wajib Koperasi": user_dict.get("SIKOP", 0),
            "Pinjaman Koperasi": user_dict.get("PINKOP", 0),
            "Serikat Pekerja": user_dict.get("SP", 0),
            "BPJS Ketenagakerjaan - JHT": user_dict.get("JAMSOSTEK", 0),
            "BPJS Ketenagakerjaan - JP": user_dict.get("JAMINAN_PENSIUN", 0),
            "BPJS Kesehatan": user_dict.get("BPJS_KESEHATAN", 0),
            "Lain-Lain": user_dict.get("LAIN_LAIN", 0)
        }

    elif status == 'tambahan':
        komponen_thp = {
            "Honorarium": user_dict.get("GAJI_KONTRAK", 0)
        }
        komponen_lain = {
            "Uang Perumahan": user_dict.get("PERUMAHAN", 0),
            "Uang Transport": user_dict.get("TRANSPORT", 0)
        }
        komponen_potongan = {
            "Simp. Wajib Koperasi": user_dict.get("SIKOP", 0),
            "Pinjaman Koperasi": user_dict.get("PINKOP", 0),
            "BPJS Ketenagakerjaan - JHT": user_dict.get("JAMSOSTEK", 0),
            "BPJS Ketenagakerjaan - JP": user_dict.get("JAMINAN_PENSIUN", 0),
            "BPJS Kesehatan": user_dict.get("BPJS_KESEHATAN", 0),
        }

    else:
        komponen_thp = {}
        komponen_lain = {}
        komponen_potongan = {}

    return komponen_thp, komponen_lain, komponen_potongan
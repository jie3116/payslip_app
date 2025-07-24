from werkzeug.security import generate_password_hash, check_password_hash
from models.db import get_db_connection

def clean_column_names(df):
    df.columns = df.columns.str.strip().str.replace(' ', '_').str.replace('-', '_').str.upper()
    return df


def get_user_by_nup(nup):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE nup = ?', (nup,)).fetchone()
    conn.close()
    if user:
        return dict(user)
    return None


def check_user_password(nup, password):
    user = get_user_by_nup(nup)
    if user:
        return check_password_hash(user['password'], password)
    return False

def update_password(nup, new_password):
    conn = get_db_connection()
    conn.execute(
        'UPDATE users SET password = ? WHERE nup = ?',
        (generate_password_hash(new_password), nup)
    )
    conn.commit()
    conn.close()

def add_user(nup, plain_password, role='pegawai'):
    conn = get_db_connection()
    conn.execute(
        'INSERT OR REPLACE INTO users (nup, password, role) VALUES (?, ?, ?)',
        (nup, generate_password_hash(plain_password), role)
    )
    conn.commit()
    conn.close()

def format_rupiah(value):
    """
    Format angka menjadi string dengan format Rupiah, misal: 1500000 -> 1.500.000
    """
    try:
        value = int(value)
        return f"{value:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"

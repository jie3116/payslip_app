from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import pandas as pd
from utils.generate_pdf import generate_pdf
from utils.helpers import (
    format_rupiah, update_password, check_user_password, get_user_by_nup,
    clean_column_names, get_komponen_by_status, add_user
)
import os
from werkzeug.utils import secure_filename
from models.db import init_db
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'gaji-2024'

UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'xlsx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.jinja_env.filters['rupiah'] = format_rupiah

# ====== HELPER FUNCTIONS ======
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_previous_month():
    now = datetime.now()
    if now.month == 1:
        return "12", str(now.year - 1)
    return str(now.month - 1).zfill(2), str(now.year)


def format_password_ttl(ttl_value):
    if pd.isna(ttl_value):
        return "00000000"
    if isinstance(ttl_value, datetime):
        return ttl_value.strftime("%d%m%Y")
    if isinstance(ttl_value, (int, float)):
        try:
            parsed = pd.to_datetime(ttl_value, origin='1899-12-30', unit='D')
            return parsed.strftime("%d%m%Y")
        except:
            pass
    try:
        parsed = pd.to_datetime(str(ttl_value), dayfirst=True, errors='coerce')
        if not pd.isna(parsed):
            return parsed.strftime("%d%m%Y")
    except:
        pass
    return str(ttl_value).zfill(8)

def load_all_salary_data():
    all_data = []
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.endswith('.xlsx'):
            try:
                path = os.path.join(app.config['UPLOAD_FOLDER'], file)
                df = pd.read_excel(path)
                df = clean_column_names(df)
                tahun, bulan = file.replace('.xlsx', '').split('_')[1:]
                df['BULAN'] = int(bulan)
                df['TAHUN'] = int(tahun)
                df['PASSWORD'] = df['TTL'].apply(format_password_ttl)
                df['SOURCE_FILE'] = file
                all_data.append(df)
            except Exception as e:
                print(f"Gagal membaca {file}: {e}")
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

# Placeholder: Implementasi sesuai DB kamu
def get_slip_from_db(bulan, tahun):
    df = load_all_salary_data()
    if df.empty:
        return []
    return df[(df['BULAN'] == int(bulan)) & (df['TAHUN'] == int(tahun))].to_dict(orient='records')

# ====== ROUTES ======
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nup = request.form['nup']
        password = request.form['password']
        user = get_user_by_nup(nup)

        if user and check_user_password(nup, password):
            session['nup'] = nup
            session['role'] = user['role']

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))

            files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.xlsx') and not f.startswith('~$')]
            bulan_available = []
            for file in files:
                try:
                    df = pd.read_excel(os.path.join(app.config['UPLOAD_FOLDER'], file), nrows=1)
                    if 'BULAN' in df.columns and 'TAHUN' in df.columns:
                        bulan = str(df.iloc[0]['BULAN']).zfill(2)
                        tahun = str(df.iloc[0]['TAHUN']).strip()
                        bulan_available.append({'BULAN': bulan, 'TAHUN': tahun, 'source_file': file})
                except Exception as e:
                    print(f"Gagal membaca {file}: {e}")

            session['available_months'] = bulan_available
            bulan, tahun = get_previous_month()
            filename = f'gaji_{tahun}_{bulan}.xlsx'
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                session['selected_file'] = filename
            elif bulan_available:
                session['selected_file'] = bulan_available[0]['source_file']
            else:
                session['selected_file'] = None

            return redirect(url_for('slip'))

        return render_template('login.html', error='Login gagal.')
    return render_template('login.html')

@app.route('/ubah_password', methods=['GET', 'POST'])
def ubah_password():
    if 'nup' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        old_pw = request.form['old_password']
        new_pw = request.form['new_password']
        confirm_pw = request.form['confirm_password']

        if not check_user_password(session['nup'], old_pw):
            message = '❌ Password lama salah.'
        elif new_pw != confirm_pw:
            message = '❌ Konfirmasi password tidak cocok.'
        else:
            update_password(session['nup'], new_pw)
            session.clear()
            return redirect(url_for('login', success=1))

        return render_template('ubah_password.html', message=message)

    return render_template('ubah_password.html', message='')


@app.route('/select_month', methods=['GET', 'POST'])
def select_month():
    if 'nup' not in session:
        return redirect(url_for('login'))

    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER'])
             if f.endswith('.xlsx') and not f.startswith('~$')]

    bulan_available = []
    for file in files:
        try:
            df = pd.read_excel(os.path.join(app.config['UPLOAD_FOLDER'], file), nrows=1)
            if 'BULAN' in df.columns and 'TAHUN' in df.columns:
                bulan = df.iloc[0]['BULAN']
                tahun = df.iloc[0]['TAHUN']
                bulan_available.append({'BULAN': bulan, 'TAHUN': tahun, 'source_file': file})
        except Exception as e:
            print(f"Gagal membaca {file}: {e}")

    if request.method == 'POST':
        selected_file = request.form.get('file')
        if selected_file:
            session['selected_file'] = selected_file
            return redirect(url_for('slip'))
        else:
            return "Silakan pilih file terlebih dahulu", 400

    return render_template('select_month.html', bulan_available=bulan_available)

@app.route('/slip')
def slip():
    if 'nup' not in session or 'selected_file' not in session:
        return redirect(url_for('login'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
    df_selected = pd.read_excel(file_path)
    df_selected = clean_column_names(df_selected)
    df_selected['PASSWORD'] = df_selected['TTL'].apply(format_password_ttl)

    user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
    if user_data.empty:
        return "Data tidak ditemukan", 404

    user_dict = user_data.iloc[0].to_dict()
    komponen_thp, komponen_lain, komponen_potongan = get_komponen_by_status(user_dict)

    return render_template(
        'slip.html',
        **user_dict,
        status=user_dict.get('STATUS_PEGAWAI', '').lower(),
        komponen_thp=komponen_thp,
        komponen_lain=komponen_lain,
        komponen_potongan=komponen_potongan,
        total_thp=user_dict.get("TOTAL_THP"),
        total_lain=user_dict.get("PENGHASILAN_LAIN"),
        available_months=session.get('available_months', []),
        selected_month=session.get('selected_month', None)
    )

@app.route('/download')
def download():
    if 'nup' not in session or 'selected_file' not in session:
        return redirect(url_for('login'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
    df_selected = pd.read_excel(file_path)
    df_selected = clean_column_names(df_selected)
    df_selected['PASSWORD'] = df_selected['TTL'].apply(format_password_ttl)

    user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
    if user_data.empty:
        return "Data tidak ditemukan", 404

    user_dict = user_data.iloc[0].to_dict()
    komponen_thp, komponen_lain, komponen_potongan = get_komponen_by_status(user_dict)
    pdf_path = generate_pdf({
        **user_dict,
        "komponen_thp": komponen_thp,
        "komponen_lain": komponen_lain,
        "komponen_potongan": komponen_potongan,
        "status": user_dict.get('STATUS_PEGAWAI', '').lower()
    })
    return send_file(pdf_path, as_attachment=True)

@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    active_tab = request.args.get("tab", "slip")
    bulan = request.args.get("bulan", datetime.now().month)
    tahun = request.args.get("tahun", datetime.now().year)
    data_slip = get_slip_from_db(bulan, tahun)

    return render_template("admin_dashboard.html",
                           active_tab=active_tab,
                           bulan=int(bulan),
                           tahun=int(tahun),
                           data_slip=data_slip)

@app.route("/admin/upload_gaji", methods=["POST"])
def upload_gaji():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    file = request.files.get("file")
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash("Data gaji berhasil diupload", "success")
    else:
        flash("Format file tidak valid. Gunakan .xlsx", "danger")
    return redirect(url_for("admin_dashboard", tab="gaji"))

@app.route("/admin/upload_user", methods=["POST"])
def upload_user():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    file = request.files.get("file")
    if not file or not allowed_file(file.filename):
        flash("Format file tidak valid. Gunakan .xlsx", "danger")
        return redirect(url_for("admin_dashboard", tab="user"))
    try:
        df = pd.read_excel(file, dtype={'NUP': str})
    except Exception as e:
        flash(f"Error membaca file: {str(e)}", "danger")
        return redirect(url_for("admin_dashboard", tab="user"))

    success, fail = 0, 0
    for _, row in df.iterrows():
        nup_raw = row.get('NUP')
        ttl_raw = pd.to_datetime(row.get('TTL'), errors='coerce')
        if pd.isna(nup_raw) or pd.isna(ttl_raw):
            fail += 1
            continue
        try:
            add_user(str(nup_raw).strip(), ttl_raw.strftime('%d%m%Y'), role='pegawai')
            success += 1
        except:
            fail += 1
    flash(f"{success} user berhasil ditambahkan, {fail} gagal.", "info")
    return redirect(url_for("admin_dashboard", tab="user"))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

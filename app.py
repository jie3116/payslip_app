from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from utils.generate_pdf import generate_pdf
from utils import send_email
from utils.helpers import format_rupiah, update_password, check_user_password, get_user_by_nup, clean_column_names
import os
from werkzeug.utils import secure_filename
from models.db import init_db
import re
import calendar
from datetime import datetime



app = Flask(__name__)
app.secret_key = 'gaji-2024'


UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'xlsx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.jinja_env.filters['rupiah'] = format_rupiah


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def load_all_salary_data():
    all_data = []
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.endswith('.xlsx'):
            path = os.path.join(app.config['UPLOAD_FOLDER'], file)
            try:
                df = pd.read_excel(path)
                df = clean_column_names(df)
                tahun, bulan = file.replace('.xlsx', '').split('_')[1:]  # gaji_2025_01.xlsx
                df['BULAN'] = int(bulan)
                df['TAHUN'] = int(tahun)
                df['PASSWORD'] = df['TTL'].astype(str).str.zfill(8)
                df['SOURCE_FILE'] = file
                all_data.append(df)
            except Exception as e:
                print(f"Gagal membaca {file}: {e}")
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


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

            # Dapatkan bulan & tahun sekarang
            now = datetime.now()
            bulan = str(now.month).zfill(2)
            tahun = str(now.year)

            filename = f'gaji_{tahun}_{bulan}.xlsx'
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            if os.path.exists(file_path):
                session['selected_file'] = filename
            else:
                session['selected_file'] = None  # ditangani di /slip nanti

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
            session.clear()  # supaya langsung logout
            return redirect(url_for('login', success=1))  # ini penting!

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
    if 'nup' not in session:
        return redirect(url_for('login'))

    # Kalau belum ada selected_file, cari otomatis berdasarkan bulan sekarang
    if 'selected_file' not in session or not session['selected_file']:
        now = datetime.now()
        bulan = str(now.month).zfill(2)
        tahun = str(now.year)
        filename = f'gaji_{tahun}_{bulan}.xlsx'
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            session['selected_file'] = filename
        else:
            return f"❌ Data gaji bulan {bulan}/{tahun} tidak ditemukan.", 404

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
    df = pd.read_excel(file_path)
    df = clean_column_names(df)
    df['PASSWORD'] = df['TTL'].astype(str).str.zfill(8)

    if 'BULAN' not in df.columns or 'TAHUN' not in df.columns:
        return "Data tidak memiliki informasi BULAN dan TAHUN", 400

    df['PERIODE'] = df['BULAN'].astype(str) + ' ' + df['TAHUN'].astype(str)
    available_months = sorted(df['PERIODE'].unique().tolist())

    selected_month = request.args.get('month')
    if selected_month is None or selected_month not in available_months:
        selected_month = available_months[-1]  # default: bulan terbaru

    df_selected = df[df['PERIODE'] == selected_month]
    user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
    if user_data.empty:
        return f"Tidak ditemukan slip untuk bulan {selected_month}", 404

    user_data = user_data.iloc[0].to_dict()
    bulan, tahun = selected_month.split()

    return render_template(
        'slip.html',
        **user_data,
        available_months=available_months,
        selected_month=selected_month,
        logo_path=url_for('static', filename='logobki.png'),
        signature_path=url_for('static', filename='tandatangan.png'),
        css_path=url_for('static', filename='css/styles.css'),
        is_pdf=False
    )

@app.route('/download')
def download():
    if 'nup' not in session or 'selected_file' not in session:
        return redirect(url_for('login'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
    df_selected = pd.read_excel(file_path)
    df_selected = clean_column_names(df_selected)
    df_selected['PASSWORD'] = df_selected['TTL'].astype(str).str.zfill(8)

    user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
    if user_data.empty:
        return "Data tidak ditemukan", 404

    pdf_path = generate_pdf(user_data.iloc[0].to_dict())
    return send_file(pdf_path, as_attachment=True)

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    # Ambil parameter dari URL (?bulan=xx&tahun=xxxx)
    selected_bulan = request.args.get('bulan')
    selected_tahun = request.args.get('tahun')

    df = load_all_salary_data()

    slip_data = []

    # Filter hanya jika bulan dan tahun dipilih
    if selected_bulan and selected_tahun:
        filtered_df = df[(df['BULAN'].astype(str).str.zfill(2) == selected_bulan) &
                         (df['TAHUN'].astype(str) == selected_tahun)]
    else:
        filtered_df = pd.DataFrame()  # atau tampilkan semua jika ingin default

    for _, user in filtered_df.iterrows():
        bulan_str = str(user['BULAN']).zfill(2)
        bulan_nama = calendar.month_name[int(user['BULAN'])] if user['BULAN'] else "Unknown"
        tahun = str(user['TAHUN']).strip()
        slip_data.append({
            'nup': user['NUP'],
            'nama': user['NAMA'],
            'email': user.get('EMAIL', ''),
            'bulan': bulan_str,
            'tahun': tahun,
            'file_path': user.get('SOURCE_FILE'),
            'status_kirim': user.get('STATUS_KIRIM', 'Belum')
        })

    return render_template(
        "admin_dashboard.html",
        slips=slip_data,
        bulan=selected_bulan,
        tahun=selected_tahun
    )

@app.route('/admin/download/<nup>/<bulan>/<tahun>')
def admin_download(nup, bulan, tahun):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    filename = f'gaji_{tahun}_{bulan}.xlsx'
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        df = pd.read_excel(file_path)
        df = clean_column_names(df)
        df['PASSWORD'] = df['TTL'].astype(str).str.zfill(8)

        user_data = df[df['NUP'].astype(str) == str(nup)]
        if user_data.empty:
            return "Data tidak ditemukan", 404

        pdf_path = generate_pdf(user_data.iloc[0].to_dict())
        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        return f"Gagal mengunduh slip: {str(e)}", 500


def find_excel_file(bulan, tahun):
    """
    Fungsi pembantu untuk mencari file Excel berdasarkan bulan dan tahun
    """
    bulan_lc = bulan.lower()
    for file in os.listdir(app.config['UPLOAD_FOLDER']):
        if file.endswith('.xlsx') and re.search(fr"{tahun}.*{bulan_lc}", file.lower()):
            return os.path.join(app.config['UPLOAD_FOLDER'], file)
    return None


@app.route('/admin/sendall/<bulan>/<tahun>')
def sendall(bulan, tahun):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    file_path = find_excel_file(bulan, tahun)
    if not file_path or not os.path.exists(file_path):
        return f"❌ File data untuk {bulan}-{tahun} tidak ditemukan.", 404

    df = pd.read_excel(file_path)
    df = clean_column_names(df)
    df['PASSWORD'] = df['TTL'].astype(str).str.zfill(8)

    success_count = 0
    failed = []

    for _, row in df.iterrows():
        user_data = row.to_dict()
        try:
            pdf_path = generate_pdf(user_data)
            send_email(
                to_email=user_data['EMAIL'],
                pdf_path=pdf_path,
                nama=user_data['NAMA'],
                bulan=str(bulan),
                tahun=str(tahun)
            )
            success_count += 1
        except Exception as e:
            failed.append({
                'nup': user_data.get('NUP', 'Tidak Diketahui'),
                'nama': user_data.get('NAMA', 'Tidak Diketahui'),
                'error': str(e)
            })

    return {
        "status": "selesai",
        "bulan": bulan,
        "tahun": tahun,
        "berhasil": success_count,
        "gagal": failed
    }


@app.route('/admin/send_email/<nup>/<bulan>/<tahun>')
def send_email_by_admin(nup, bulan, tahun):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    file_path = find_excel_file(bulan, tahun)
    if not file_path or not os.path.exists(file_path):
        return f"❌ File data untuk {bulan}-{tahun} tidak ditemukan.", 404

    df = pd.read_excel(file_path)
    df = clean_column_names(df)
    df['PASSWORD'] = df['TTL'].astype(str).str.zfill(8)

    user_data = df[df['NUP'].astype(str) == nup]

    if user_data.empty:
        return f"❌ Data NUP {nup} tidak ditemukan.", 404

    user_data = user_data.iloc[0].to_dict()

    try:
        pdf_path = generate_pdf(user_data)
        send_email(
            to_email=user_data['EMAIL'],
            pdf_path=pdf_path,
            nama=user_data['NAMA'],
            bulan=str(bulan),
            tahun=str(tahun)
        )
        return f"✅ Slip gaji berhasil dikirim ke {user_data['EMAIL']}."
    except Exception as e:
        return f"❌ Gagal mengirim ulang: {str(e)}"

@app.route('/admin/upload', methods=['GET', 'POST'])
def upload_excel():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return "✅ Data berhasil diunggah."
        return "❌ Format file tidak didukung.", 400

    return '''
    <h3>Upload Data Gaji (.xlsx)</h3>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" accept=".xlsx">
        <input type="submit" value="Upload">
    </form>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

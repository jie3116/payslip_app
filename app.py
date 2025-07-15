from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
from utils import generate_pdf, send_email, format_rupiah
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = 'gaji-2024'

# Load data
DATA_PATH = 'data/data_gaji.xlsx'
df = pd.read_excel(DATA_PATH)

# Kolom password dari TTL (format ddmmyyyy)
df['password'] = df['TTL'].astype(str).str.zfill(8)

# Filter rupiah
app.jinja_env.filters['rupiah'] = format_rupiah

# Data admin hardcoded sementara
ADMINS = {
    "admin": {
        "password": generate_password_hash("bki2025"),
        "role": "admin"
    }
}

# Data untuk upload excel data gaji
UPLOAD_FOLDER = 'data'
ALLOWED_EXTENSIONS = {'xlsx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_nup = request.form['nup']
        password = request.form['password']

        # Jika login sebagai admin
        admin = ADMINS.get(username_or_nup)
        if admin and check_password_hash(admin['password'], password):
            session['username'] = username_or_nup
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))

        # Jika login sebagai pegawai
        user = df[df['NUP'].astype(str) == username_or_nup]
        if not user.empty and user.iloc[0]['password'] == password:
            session['nup'] = username_or_nup
            session['role'] = 'pegawai'
            return redirect(url_for('slip'))

        return render_template('login.html', error='Login gagal. Periksa kembali NUP/Username dan password.')

    return render_template('login.html')


@app.route('/slip')
def slip():
    if 'nup' not in session:
        return redirect(url_for('login'))

    user_data = df[df['NUP'].astype(str) == session['nup']].iloc[0].to_dict()
    return render_template(
        'slip.html',
        **user_data,
        logo_path=url_for('static', filename='logobki.png'),
        signature_path=url_for('static', filename='tandatangan.png'),
        css_path=url_for('static', filename='css/styles.css'),
        is_pdf=False
    )

@app.route('/download')
def download():
    if 'nup' not in session:
        return redirect(url_for('login'))

    user_data = df[df['NUP'].astype(str) == session['nup']].iloc[0].to_dict()
    pdf_path = generate_pdf(user_data)
    return send_file(pdf_path, as_attachment=True)


@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    import calendar  # untuk mengubah angka jadi nama bulan

    slip_data = []
    for _, row in df.iterrows():
        user = row.to_dict()

        try:
            bulan_angka = int(user.get("BULAN", 0))
            bulan = calendar.month_name[bulan_angka]  # Misal: 4 → "April"
        except:
            bulan = "Unknown"

        tahun = str(user.get("TAHUN", "0000")).strip()
        folder = f"{tahun}-{bulan}"
        folder_path = os.path.join('static', 'slips', folder)
        file_path = None

        if os.path.exists(folder_path):
            for file in os.listdir(folder_path):
                if (file.startswith(f"slip_{user['NUP']}_") and
                    file.endswith(f"_{bulan}_{tahun}.pdf")):
                    file_path = os.path.join(folder_path, file)
                    break

        slip_data.append({
            'nup': user['NUP'],
            'nama': user['NAMA'],
            'email': user.get('EMAIL', ''),
            'file_path': file_path,
            'bulan': bulan,
            'tahun': tahun,
            'status_kirim': user.get('status_kirim', 'Belum')
        })

    return render_template("admin_dashboard.html", slips=slip_data)



@app.route('/admin/resend/<nup>')
def resend_email(nup):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    user_row = df[df['NUP'].astype(str) == str(nup)]
    if user_row.empty:
        return "Data tidak ditemukan", 404

    data = user_row.iloc[0].to_dict()
    pdf_path = generate_pdf(data)

    send_email(
        to_email=data['EMAIL'],
        pdf_path=pdf_path,
        nama=data['NAMA'],
        bulan=str(data['BULAN']),
        tahun=str(data['TAHUN'])
    )
    return f"Slip gaji berhasil dikirim ulang ke {data['EMAIL']}."


@app.route('/sendall')
def sendall():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

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
                bulan=str(user_data.get('BULAN', '')),
                tahun=str(user_data.get('TAHUN', ''))
            )
            success_count += 1
        except Exception as e:
            failed.append({'nup': user_data['NUP'], 'nama': user_data['NAMA'], 'error': str(e)})

    return {
        "status": "selesai",
        "berhasil": success_count,
        "gagal": failed
    }

@app.route('/admin/upload', methods=['GET', 'POST'])
def upload_excel():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename("data_gaji.xlsx")  # overwrite
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return "✅ Data berhasil diunggah. Silakan refresh aplikasi."
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
    app.run(debug=True)

import os
import logging
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import pandas as pd
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from datetime import datetime
from utils.generate_pdf import generate_pdf
from utils.helpers import (
    format_rupiah, update_password, check_user_password, get_user_by_nup,
    clean_column_names, get_komponen_by_status, add_user
)
from models.db import init_db, get_db_connection
from utils.generate_barcode import generate_payslip_barcode_uri

# =============================================
# SETUP LOGGING
# =============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================
# KONFIGURASI APLIKASI
# =============================================
app = Flask(__name__)

# Membaca variabel lingkungan untuk menentukan mode aplikasi
flask_env = os.getenv('FLASK_ENV', 'production')

if flask_env == 'development':
    app.config.update(
        SECRET_KEY='dev-fallback-key',
        DEBUG=True,  # Mengaktifkan mode debug untuk pengembangan
    )
    logging.getLogger().setLevel(logging.DEBUG)
    logger.info("Aplikasi berjalan dalam mode DEVELOPMENT")
else: # production
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'xxx-default-production-key-xxx'),
        DEBUG=False,  # Menonaktifkan mode debug untuk produksi
    )
    logging.getLogger().setLevel(logging.INFO)
    logger.info("Aplikasi berjalan dalam mode PRODUCTION")

# Konfigurasi dari Environment Variables
app.config.update(
    # Menggunakan SECRET_KEY dari blok sebelumnya
    UPLOAD_FOLDER=os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data'),
    ALLOWED_EXTENSIONS={'xlsx'},
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB
    
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

app.jinja_env.filters['rupiah'] = format_rupiah

# =============================================
# INISIALISASI DATABASE
# =============================================

def initialize_database():
    try:
        logger.info("Memulai inisialisasi database...")
        init_db()
        logger.info("Database berhasil diinisialisasi")
        
        # Buat admin default jika tidak ada
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (nup, password, role)
                    VALUES ('admin', %s, 'admin')
                    ON CONFLICT (nup) DO NOTHING
                """, (generate_password_hash('admin123'),))
                conn.commit()
    except Exception as e:
        logger.error(f"Gagal inisialisasi database: {str(e)}")
        raise

# =============================================
# HELPER FUNCTIONS
# =============================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_previous_month():
    now = datetime.now()
    if now.month == 1:
        return "12", str(now.year - 1)
    return str(now.month - 1).zfill(2), str(now.year)

def format_password_ttl(ttl_value):
    try:
        if pd.isna(ttl_value):
            return "00000000"
        
        if isinstance(ttl_value, datetime):
            return ttl_value.strftime("%d%m%Y")
        
        if isinstance(ttl_value, (int, float)):
            parsed = pd.to_datetime(ttl_value, origin='1899-12-30', unit='D')
            return parsed.strftime("%d%m%Y")
        
        parsed = pd.to_datetime(str(ttl_value), dayfirst=True, errors='coerce')
        if not pd.isna(parsed):
            return parsed.strftime("%d%m%Y")
            
        return str(ttl_value).zfill(8)
    except Exception as e:
        logger.error(f"Error formatting password TTL: {e}")
        return "00000000"

def load_all_salary_data():
    all_data = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Buat folder jika belum ada
    os.makedirs(upload_folder, exist_ok=True)

    for file in os.listdir(upload_folder):
        if file.endswith('.xlsx') and not file.startswith('~$'):
            try:
                path = os.path.join(upload_folder, file)
                df = pd.read_excel(path)
                df = clean_column_names(df)
                
                # Ekstrak bulan dan tahun dari nama file (format: gaji_YYYY_MM.xlsx)
                try:
                    # Menambahkan 'gaji_' jika format nama file memiliki awalan ini
                    parts = file.replace('.xlsx', '').split('_')
                    if len(parts) == 3 and parts[0] == 'gaji':
                        tahun, bulan = parts[1], parts[2]
                    else:
                        tahun, bulan = parts
                    df['BULAN'] = int(bulan)
                    df['TAHUN'] = int(tahun)
                except ValueError:
                    logger.warning(f"Format nama file salah: {file}")
                    continue
                
                df['PASSWORD'] = df['TTL'].apply(format_password_ttl)
                df['SOURCE_FILE'] = file
                all_data.append(df)
                
            except Exception as e:
                logger.error(f"Gagal memproses file {file}: {str(e)}")
    
    return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()

# =============================================
# ROUTES
# =============================================

# ---------- Login & Logout ----------

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            nup = request.form.get('nup', '').strip()
            password = request.form.get('password', '')

            if not nup or not password:
                flash('NUP dan password harus diisi', 'danger')
                return redirect(url_for('login'))

            logger.info(f"Percobaan login NUP: {nup}")
            user = get_user_by_nup(nup)

            if user and check_user_password(nup, password):
                session['nup'] = nup
                session['role'] = user['role']
                logger.info(f"Login berhasil untuk NUP: {nup}")
                flash('Login berhasil', 'success')

                if user['role'] == 'admin':
                    return redirect(url_for('admin_dashboard'))

                # Untuk user biasa
                files = [f for f in os.listdir(app.config['UPLOAD_FOLDER'])
                         if f.endswith('.xlsx') and not f.startswith('~$')]

                bulan_available = []
                for file in files:
                    try:
                        df = pd.read_excel(os.path.join(app.config['UPLOAD_FOLDER'], file), nrows=1)
                        if 'BULAN' in df.columns and 'TAHUN' in df.columns:
                            bulan = str(df.iloc[0]['BULAN']).zfill(2)
                            tahun = str(df.iloc[0]['TAHUN']).strip()
                            bulan_available.append({
                                'BULAN': bulan,
                                'TAHUN': tahun,
                                'source_file': file
                            })
                    except Exception as e:
                        logger.error(f"Error membaca file {file}: {str(e)}")

                session['available_months'] = bulan_available

                # Set default bulan saat login
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

            logger.warning(f"Login gagal untuk NUP: {nup}")
            flash('NUP atau password salah', 'danger')

        except Exception as e:
            logger.error(f"Error saat login: {str(e)}", exc_info=True)
            flash('Terjadi kesalahan sistem', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah logout', 'info')
    return redirect(url_for('login'))

# ---------- User Biasa ----------
@app.route('/slip')
def slip():
    if 'nup' not in session or 'selected_file' not in session:
        flash('Silakan login terlebih dahulu', 'warning')
        return redirect(url_for('login'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
        df_selected = pd.read_excel(file_path)
        df_selected = clean_column_names(df_selected)
        df_selected['PASSWORD'] = df_selected['TTL'].apply(format_password_ttl)

        user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
        if user_data.empty:
            flash('Data gaji tidak ditemukan', 'danger')
            return redirect(url_for('select_month'))

        user_dict = user_data.iloc[0].to_dict()
        komponen_thp, komponen_lain, komponen_potongan = get_komponen_by_status(user_dict)

        # Data tambahan
        employee_id = user_dict.get('NUP')
        pay_period = f"{user_dict.get('BULAN')}-{user_dict.get('TAHUN')}"
        signer_name = user_dict.get('PENANDATANGAN')
        signer_title = user_dict.get('JABATAN_PENANDATANGAN')

        barcode_uri = generate_payslip_barcode_uri(
            employee_id,
            pay_period,
            signer_name,
            signer_title
        )

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
            selected_month=session.get('selected_file', None),  # ✅ konsisten
            barcode_uri=barcode_uri,
            signer_name=signer_name,
            signer_title=signer_title
        )

    except Exception as e:
        logger.error(f"Error saat memproses slip: {str(e)}", exc_info=True)
        flash('Terjadi kesalahan saat memproses slip gaji', 'danger')
        return redirect(url_for('select_month'))

# ---------- Pilih Bulan ----------
@app.route('/select_month', methods=['GET', 'POST'])
def select_month():
    if 'nup' not in session:
        flash('Silakan login terlebih dahulu', 'warning')
        return redirect(url_for('login'))

    try:
        files = [f for f in os.listdir(app.config['UPLOAD_FOLDER'])
                 if f.endswith('.xlsx') and not f.startswith('~$')]

        bulan_available = []
        for file in files:
            try:
                df = pd.read_excel(os.path.join(app.config['UPLOAD_FOLDER'], file), nrows=1)
                if 'BULAN' in df.columns and 'TAHUN' in df.columns:
                    bulan = df.iloc[0]['BULAN']
                    tahun = df.iloc[0]['TAHUN']
                    bulan_available.append({
                        'BULAN': bulan,
                        'TAHUN': tahun,
                        'source_file': file
                    })
            except Exception as e:
                logger.error(f"Error membaca file {file}: {str(e)}")

        if request.method == 'POST':
            selected_file = request.form.get('file')
            if selected_file:
                session['selected_file'] = selected_file
                return redirect(url_for('slip'))
            else:
                flash('Silakan pilih bulan terlebih dahulu', 'warning')
                return redirect(url_for('select_month'))

        return render_template('select_month.html', bulan_available=bulan_available)
    except Exception as e:
        logger.error(f"Error saat memilih bulan: {str(e)}", exc_info=True)
        flash('Terjadi kesalahan saat memilih bulan', 'danger')
        return redirect(url_for('login'))


@app.route('/download')
def download():
    if 'nup' not in session or 'selected_file' not in session:
        flash('Silakan login terlebih dahulu', 'warning')
        return redirect(url_for('login'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], session['selected_file'])
        df_selected = pd.read_excel(file_path)
        df_selected = clean_column_names(df_selected)
        df_selected['PASSWORD'] = df_selected['TTL'].apply(format_password_ttl)

        user_data = df_selected[df_selected['NUP'].astype(str) == session['nup']]
        if user_data.empty:
            flash('Data gaji tidak ditemukan', 'danger')
            return redirect(url_for('select_month'))

        user_dict = user_data.iloc[0].to_dict()
        komponen_thp, komponen_lain, komponen_potongan = get_komponen_by_status(user_dict)

        # --- Penyesuaian untuk Barcode ---
        # Dapatkan data yang diperlukan
        employee_id = user_dict.get('NUP')
        pay_period = f"{user_dict.get('BULAN')}-{user_dict.get('TAHUN')}"
        signer_name = user_dict.get('PENANDATANGAN')
        signer_title = user_dict.get('JABATAN_PENANDATANGAN')

        # Panggil fungsi generate_payslip_barcode_uri dengan argumen lengkap
        barcode_uri = generate_payslip_barcode_uri(
            employee_id,
            pay_period,
            signer_name,
            signer_title
        )
        # --------------------------------

        # Kirimkan data lengkap, termasuk barcode_uri, ke fungsi generate_pdf
        pdf_path = generate_pdf({
        **user_dict,
        "komponen_thp": komponen_thp,
        "komponen_lain": komponen_lain,
        "komponen_potongan": komponen_potongan,
        "status": user_dict.get('STATUS_PEGAWAI', '').lower(),
        "barcode_uri": barcode_uri,
        "total_thp": user_dict.get("TOTAL_THP"),
        "total_lain": user_dict.get("PENGHASILAN_LAIN")
    })

        return send_file(pdf_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Error saat mengunduh slip: {str(e)}", exc_info=True)
        flash('Terjadi kesalahan saat mengunduh slip', 'danger')
        return redirect(url_for('slip'))


@app.route('/ubah_password', methods=['GET', 'POST'])
def ubah_password():
    if 'nup' not in session:
        flash('Silakan login terlebih dahulu', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            old_pw = request.form.get('old_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not old_pw or not new_pw or not confirm_pw:
                flash('Semua field harus diisi', 'danger')
                return redirect(url_for('ubah_password'))

            if not check_user_password(session['nup'], old_pw):
                flash('Password lama salah', 'danger')
            elif new_pw != confirm_pw:
                flash('Konfirmasi password tidak cocok', 'danger')
            else:
                update_password(session['nup'], new_pw)
                session.clear()
                flash('Password berhasil diubah. Silakan login kembali', 'success')
                return redirect(url_for('login'))

        except Exception as e:
            logger.error(f"Error saat mengubah password: {str(e)}", exc_info=True)
            flash('Terjadi kesalahan saat mengubah password', 'danger')

    return render_template('ubah_password.html')


# ---------- Admin ----------
@app.route("/admin")
def admin_dashboard():
    # Periksa apakah pengguna adalah admin
    if session.get('role') != 'admin':
        flash('Akses ditolak. Hanya untuk admin', 'danger')
        return redirect(url_for('login'))

    try:
        active_tab = request.args.get("tab", "slip")
        
        # Mengambil parameter "periode" dari form
        periode_str = request.args.get("periode")
        bulan_str, tahun_str = None, None
        data_slip = pd.DataFrame()  # Inisialisasi DataFrame kosong

        if periode_str:
            try:
                # Memisahkan string "YYYY-MM" menjadi tahun dan bulan
                tahun_str, bulan_str = periode_str.split('-')
                bulan = int(bulan_str)
                tahun = int(tahun_str)
                
                logger.info(f"Memuat data untuk bulan {bulan} dan tahun {tahun}")
                
                all_data = load_all_salary_data()
                if not all_data.empty:
                    data_slip = all_data[(all_data['BULAN'] == bulan) & (all_data['TAHUN'] == tahun)]
            except (ValueError, KeyError) as e:
                logger.error(f"Error memfilter data slip gaji: {str(e)}")
                flash('Format bulan atau tahun tidak valid.', 'danger')

        # Dictionary untuk konversi nama bulan Indonesia ke angka
        month_mapping = {
            'januari': 1, 'jan': 1,
            'februari': 2, 'feb': 2,
            'maret': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'mei': 5,
            'juni': 6, 'jun': 6,
            'juli': 7, 'jul': 7,
            'agustus': 8, 'agu': 8,
            'september': 9, 'sep': 9,
            'oktober': 10, 'okt': 10,
            'november': 11, 'nov': 11,
            'desember': 12, 'des': 12
        }

        # Mengambil bulan dan tahun yang unik dari semua file di UPLOAD_FOLDER
        available_months_years = set()
        
        for file in os.listdir(app.config['UPLOAD_FOLDER']):
            if file.endswith('.xlsx') and not file.startswith('~$'):
                try:
                    df_temp = pd.read_excel(os.path.join(app.config['UPLOAD_FOLDER'], file), nrows=1)
                    df_temp.columns = [col.upper().replace(' ', '_') for col in df_temp.columns]
                    
                    if 'BULAN' in df_temp.columns and 'TAHUN' in df_temp.columns:
                        bulan_value = df_temp.iloc[0]['BULAN']
                        tahun_value = df_temp.iloc[0]['TAHUN']
                        
                        # Konversi bulan
                        if isinstance(bulan_value, str):
                            # Jika bulan berupa string (nama bulan)
                            bulan_lower = bulan_value.lower().strip()
                            if bulan_lower in month_mapping:
                                bulan_file = month_mapping[bulan_lower]
                            else:
                                logger.warning(f"Nama bulan tidak dikenali: {bulan_value}")
                                continue
                        else:
                            # Jika bulan sudah berupa angka
                            try:
                                bulan_file = int(bulan_value)
                            except (ValueError, TypeError):
                                logger.warning(f"Format bulan tidak valid: {bulan_value}")
                                continue
                        
                        # Konversi tahun
                        try:
                            tahun_file = int(tahun_value)
                        except (ValueError, TypeError):
                            logger.warning(f"Format tahun tidak valid: {tahun_value}")
                            continue
                            
                        available_months_years.add((tahun_file, bulan_file))
                        
                except Exception as e:
                    logger.error(f"Error memproses file {file} untuk dropdown: {str(e)}")

        # Mengurutkan bulan/tahun
        sorted_months = sorted(list(available_months_years))

        # Mengirimkan data ke template
        return render_template(
            "admin_dashboard.html",
            active_tab=active_tab,
            data_slip=data_slip,
            available_months=sorted_months,
            bulan=bulan_str,
            tahun=tahun_str
        )

    except Exception as e:
        logger.error(f"Error di admin dashboard: {str(e)}", exc_info=True)
        flash('Terjadi kesalahan sistem', 'danger')
        return redirect(url_for('login'))


@app.route("/admin/upload_gaji", methods=["POST"])
def upload_gaji():
    if session.get('role') != 'admin':
        flash('Akses ditolak. Hanya untuk admin', 'danger')
        return redirect(url_for('login'))

    try:
        file = request.files.get("file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            flash("Data gaji berhasil diupload", "success")
        else:
            flash("Format file tidak valid. Hanya file Excel (.xlsx) yang diperbolehkan", "danger")
    except Exception as e:
        logger.error(f"Error saat upload gaji: {str(e)}", exc_info=True)
        flash("Terjadi kesalahan saat mengupload file", "danger")

    return redirect(url_for("admin_dashboard", tab="gaji"))

@app.route("/admin/upload_user", methods=["POST"])
def upload_user():
    if session.get('role') != 'admin':
        flash('Akses ditolak. Hanya untuk admin', 'danger')
        return redirect(url_for('login'))

    try:
        file = request.files.get("file")
        if not file or not allowed_file(file.filename):
            flash("Format file tidak valid. Hanya file Excel (.xlsx) yang diperbolehkan", "danger")
            return redirect(url_for("admin_dashboard", tab="user"))

        # Baca file Excel dengan berbagai kemungkinan tipe kolom
        df = pd.read_excel(file, dtype={'NUP': str, 'nup': str})
        
        # Normalisasi nama kolom ke uppercase
        df.columns = df.columns.str.upper()
        
        # Log struktur data untuk debugging
        logger.info(f"Kolom dalam file (setelah normalisasi): {df.columns.tolist()}")
        logger.info(f"Jumlah baris: {len(df)}")
        logger.info(f"Sample data:\n{df.head()}")

        # Hapus baris kosong
        df = df.dropna(how='all')
        logger.info(f"Jumlah baris setelah menghapus baris kosong: {len(df)}")

        success, fail = 0, 0
        error_details = []

        # Pemetaan kolom yang mungkin
        column_mapping = {
            'NUP': ['NUP', 'ID', 'EMPLOYEE_ID'],
            'TTL': ['TTL', 'PASSWORD', 'TANGGAL_LAHIR', 'BIRTH_DATE'],
            'ROLE': ['ROLE', 'JABATAN', 'POSITION']
        }

        # Deteksi kolom yang ada
        nup_col = None
        ttl_col = None
        role_col = None

        for col in df.columns:
            if col in column_mapping['NUP']:
                nup_col = col
            elif col in column_mapping['TTL']:
                ttl_col = col
            elif col in column_mapping['ROLE']:
                role_col = col

        logger.info(f"Kolom terdeteksi - NUP: {nup_col}, TTL: {ttl_col}, ROLE: {role_col}")

        if not nup_col:
            flash("Kolom NUP tidak ditemukan. Pastikan ada kolom 'NUP' atau 'nup'", "danger")
            return redirect(url_for("admin_dashboard", tab="user"))

        if not ttl_col:
            flash("Kolom TTL/Password tidak ditemukan. Pastikan ada kolom 'TTL' atau 'password'", "danger")
            return redirect(url_for("admin_dashboard", tab="user"))

        for index, row in df.iterrows():
            try:
                # Ambil data dari kolom yang terdeteksi
                nup_raw = row.get(nup_col)
                ttl_raw = row.get(ttl_col)
                role_raw = row.get(role_col, 'pegawai') if role_col else 'pegawai'

                # Validasi NUP
                if pd.isna(nup_raw) or str(nup_raw).strip() == '':
                    error_details.append(f"Baris {index + 2}: NUP kosong")
                    fail += 1
                    continue

                nup_clean = str(nup_raw).strip()

                # Validasi dan konversi TTL
                if pd.isna(ttl_raw):
                    error_details.append(f"Baris {index + 2}: TTL kosong")
                    fail += 1
                    continue

                # Konversi TTL ke datetime
                password = None
                try:
                    if isinstance(ttl_raw, str):
                        # Coba berbagai format tanggal
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                            try:
                                ttl_datetime = datetime.strptime(ttl_raw.strip(), fmt)
                                password = ttl_datetime.strftime('%d%m%Y')
                                break
                            except ValueError:
                                continue
                        
                        if not password:
                            # Jika semua format gagal, coba dengan pandas
                            ttl_datetime = pd.to_datetime(ttl_raw, errors='coerce')
                            if not pd.isna(ttl_datetime):
                                password = ttl_datetime.strftime('%d%m%Y')
                    else:
                        # Jika sudah berupa datetime atau timestamp
                        ttl_datetime = pd.to_datetime(ttl_raw, errors='coerce')
                        if not pd.isna(ttl_datetime):
                            password = ttl_datetime.strftime('%d%m%Y')
                
                except Exception as date_error:
                    logger.warning(f"Error konversi tanggal pada baris {index + 2}: {str(date_error)}")

                if not password:
                    error_details.append(f"Baris {index + 2}: Format TTL tidak valid ({ttl_raw})")
                    fail += 1
                    continue

                role_clean = str(role_raw).strip().lower() if not pd.isna(role_raw) else 'pegawai'

                logger.info(f"Menambahkan user: NUP={nup_clean}, Password={password}, Role={role_clean}")

                # Panggil fungsi add_user
                try:
                    result = add_user(nup_clean, password, role=role_clean)
                    
                    if result is not False:  # add_user bisa return None atau True
                        success += 1
                        logger.info(f"User {nup_clean} berhasil ditambahkan")
                    else:
                        error_details.append(f"Baris {index + 2}: User {nup_clean} sudah ada atau gagal ditambahkan")
                        fail += 1
                        
                except Exception as add_error:
                    error_details.append(f"Baris {index + 2}: Error saat menambahkan {nup_clean} - {str(add_error)}")
                    logger.error(f"Error add_user untuk {nup_clean}: {str(add_error)}")
                    fail += 1

            except Exception as e:
                error_msg = f"Baris {index + 2}: {str(e)}"
                error_details.append(error_msg)
                logger.warning(f"Gagal memproses baris {index + 2}: {str(e)}")
                fail += 1

        # Flash message dengan detail
        if success > 0:
            flash(f"{success} user berhasil ditambahkan", "success")
        if fail > 0:
            flash(f"{fail} user gagal ditambahkan", "warning")
            
        # Log error details untuk debugging
        if error_details:
            logger.warning("Detail error upload user:")
            for detail in error_details[:15]:  # Log maksimal 15 error pertama
                logger.warning(detail)

    except Exception as e:
        logger.error(f"Error saat upload user: {str(e)}", exc_info=True)
        flash("Terjadi kesalahan saat memproses file", "danger")

    return redirect(url_for("admin_dashboard", tab="user"))


# Fungsi helper untuk debug database
@app.route("/admin/debug_users")
def debug_users():
    if session.get('role') != 'admin':
        flash('Akses ditolak. Hanya untuk admin', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Query semua user dari database untuk debugging
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nup, role, created_at FROM users ORDER BY created_at DESC LIMIT 50")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        
        users_info = []
        for user in users:
            users_info.append({
                'nup': user[0],
                'role': user[1],
                'created_at': user[2]
            })
        
        logger.info(f"Total users dalam database: {len(users_info)}")
        return {"users": users_info, "total": len(users_info)}
        
    except Exception as e:
        logger.error(f"Error debug users: {str(e)}")
        return {"error": str(e)}

# =============================================
# RUN APLIKASI
# =============================================
if __name__ == '__main__':
    try:
        port = int(os.getenv('PORT', 8000))
        host = os.getenv('HOST', '0.0.0.0')
        logger.info(f"Memulai aplikasi di {host}:{port}")
        app.run(host=host, port=port, debug=False)
    except Exception as e:
        logger.critical(f"Gagal memulai aplikasi: {str(e)}")
        raise

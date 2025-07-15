import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from flask import current_app as app
import pdfkit
import os
import pikepdf
import shutil
from graph_email import get_token, send_graph_email



load_dotenv()

EMAIL_ADDRESS = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASS')
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER')

if not EMAIL_ADDRESS or not EMAIL_PASSWORD or not EMAIL_PROVIDER:
    raise EnvironmentError("EMAIL_USER, EMAIL_PASS dan EMAIL_PROVIDER harus diset di file .env")


def format_rupiah(value):
    """Format angka menjadi format rupiah (dengan titik sebagai pemisah ribuan)."""
    try:
        value = int(float(value))
        return f"{value:,}".replace(",", ".")
    except:
        return "0"



def generate_pdf(data):
    env = app.jinja_env
    template = env.get_template('slip.html')

    # Path untuk resource
    logo_path = os.path.abspath("static/logobki.png")
    signature_path = os.path.abspath("static/tandatangan.png")
    css_path = os.path.abspath("static/css/styles.css")

    logo_uri = f"file:///{logo_path}"
    signature_uri = f"file:///{signature_path}"
    css_uri = f"file:///{css_path}"

    # Render HTML
    html_out = template.render(
        **data,
        logo_path=logo_uri,
        signature_path=signature_uri,
        css_path=css_uri,
        is_pdf=True
    )

    # Folder penyimpanan berdasarkan bulan dan tahun
    bulan = str(data.get('BULAN', 'Unknown')).strip()
    tahun = str(data.get('TAHUN', '0000')).strip()

    folder_path = os.path.join("static", "slips", f"{tahun}-{bulan}")
    os.makedirs(folder_path, exist_ok=True)

    # Nama file PDF
    filename = f"slip_{data['NUP']}_{data['NAMA']}_{data['BULAN']}_{data['TAHUN']}.pdf"
    output_path = os.path.join(folder_path, filename)

    # Buat PDF dari HTML
    wkhtmltopdf_path = shutil.which("wkhtmltopdf") or r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)

    options = {
        "enable-local-file-access": "",
        "no-stop-slow-scripts": "",
        "disable-smart-shrinking": "",
        "load-error-handling": "ignore"
    }

    pdfkit.from_string(html_out, output_path, configuration=config, options=options)

    # Gunakan TTL sebagai password, misalnya: "25-04-1990" → "25041990"
    ttl_raw = str(data.get("TTL", ""))
    ttl = ttl_raw.zfill(8)

    if ttl:
        protect_pdf(output_path, output_path, ttl)

    return output_path


def protect_pdf(input_path, output_path, password):
    pdf = pikepdf.open(input_path, allow_overwriting_input=True)
    pdf.save(output_path, encryption=pikepdf.Encryption(owner=password, user=password, R=4))




# Send email

EMAIL_ADDRESS = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASS')
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'gmail').lower()

def send_email(to_email, pdf_path, nama, bulan, tahun):
    subject = f'Slip Gaji {bulan} {tahun} - PT BKI'

    body = f"""Yth. Bapak/Ibu {nama},

Dengan hormat,

Bersama email ini kami sampaikan slip gaji Bapak/Ibu untuk periode {bulan} {tahun}.
Mohon untuk dapat memeriksa dokumen terlampir dengan seksama.

Slip gaji ini dilindungi dengan sandi (password) berupa tanggal lahir Bapak/Ibu
dengan format ddmmyyyy (contoh: 25051980).

Apabila terdapat pertanyaan, koreksi, atau ketidaksesuaian dalam dokumen tersebut,
silakan menghubungi Divisi Human Capital & Teknologi Informasi,
cq. Layanan Human Capital.

Atas perhatian dan kerja sama Bapak/Ibu, kami ucapkan terima kasih.

Hormat kami,
Layanan Human Capital
Divisi Human Capital & Teknologi Informasi
PT Biro Klasifikasi Indonesia (Persero)
"""

    if EMAIL_PROVIDER == 'graph':
        send_graph_email(to_email, subject, body, pdf_path)
        return

    # SMTP method
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg.set_content(body)

    with open(pdf_path, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename=os.path.basename(pdf_path))

    try:
        if EMAIL_PROVIDER == 'gmail':
            smtp_server = 'smtp.gmail.com'
            smtp_port = 587
        elif EMAIL_PROVIDER == 'outlook':
            smtp_server = 'smtp.office365.com'
            smtp_port = 587
        else:
            raise ValueError("EMAIL_PROVIDER harus 'gmail', 'outlook', atau 'graph'.")

        with smtplib.SMTP(smtp_server, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

        print(f"✅ Email terkirim ke {to_email}")
    except Exception as e:
        print(f"❌ Gagal kirim ke {to_email}: {e}")



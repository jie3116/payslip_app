
import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv
from utils.graph_email import send_graph_email

load_dotenv()

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

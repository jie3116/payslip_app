import os
import pdfkit
import shutil
import pikepdf
from flask import current_app as app


def generate_pdf(data):
    env = app.jinja_env
    template = env.get_template('slip.html')

    logo_path = os.path.abspath("static/logobki.png")
    signature_path = os.path.abspath("static/tandatangan.png")
    css_path = os.path.abspath("static/css/styles.css")

    logo_uri = f"file:///{logo_path}"
    signature_uri = f"file:///{signature_path}"
    css_uri = f"file:///{css_path}"

    html_out = template.render(
        **data,
        logo_path=logo_uri,
        signature_path=signature_uri,
        css_path=css_uri,
        is_pdf=True
    )

    bulan = str(data.get('BULAN', 'Unknown')).strip()
    tahun = str(data.get('TAHUN', '0000')).strip()
    folder_path = os.path.join("static", "slips", f"{tahun}-{bulan}")
    os.makedirs(folder_path, exist_ok=True)

    filename = f"slip_{data['NUP']}_{data['NAMA']}_{bulan}_{tahun}.pdf"
    output_path = os.path.join(folder_path, filename)

    wkhtmltopdf_path = shutil.which("wkhtmltopdf") or r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
    options = {
        "enable-local-file-access": "",
        "no-stop-slow-scripts": "",
        "disable-smart-shrinking": "",
        "load-error-handling": "ignore"
    }

    pdfkit.from_string(html_out, output_path, configuration=config, options=options)

    # Gunakan langsung password yang sudah diformat di app.py
    ttl_password = str(data.get("PASSWORD", "")).strip()

    if ttl_password:
        protect_pdf(output_path, output_path, ttl_password)

    return output_path

def protect_pdf(input_path, output_path, password):
    pdf = pikepdf.open(input_path, allow_overwriting_input=True)
    pdf.save(output_path, encryption=pikepdf.Encryption(owner=password, user=password, R=4))

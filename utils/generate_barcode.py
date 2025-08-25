import io
import base64
import qrcode


def generate_payslip_barcode_uri(employee_id, pay_period, signer_name, signer_title):
    """
    Generates a Base64 encoded QR Code string for a payslip.

    Returns:
        str: A Data URI string (base64 encoded).
    """
    # Gabungkan semua data ke dalam satu string tunggal
    barcode_data = f"Slip Gaji : {employee_id}|{pay_period}|\nSigned by : {signer_name}|{signer_title}"

    # Buat objek QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(barcode_data)
    qr.make(fit=True)

    # Buat gambar dari QR Code
    img = qr.make_image(fill_color="black", back_color="white")

    # Simpan gambar ke buffer memori
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')

    # Dapatkan byte dari buffer
    image_bytes = buffer.getvalue()

    # Encode byte ke Base64
    base64_encoded = base64.b64encode(image_bytes).decode('utf-8')

    # Buat string Data URI
    data_uri = f"data:image/png;base64,{base64_encoded}"

    return data_uri
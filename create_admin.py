from utils.helpers import  add_user

# Contoh data admin
nup = 'admin'  # ID unik untuk admin
password = 'hc1964'  # Password bisa diganti
role = 'admin'

# Tambahkan ke database
add_user(nup, password, role)
print("✅ Admin berhasil ditambahkan.")

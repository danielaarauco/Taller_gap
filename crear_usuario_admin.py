import sqlite3
from werkzeug.security import generate_password_hash

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

nombre_usuario = "admin"
password = "123456"
nombre_completo = "Administrador del Taller"
rol = "ADMIN"

password_hash = generate_password_hash(password)

try:
    cursor.execute("""
        INSERT INTO usuarios (nombre_usuario, password_hash, nombre_completo, rol, activo)
        VALUES (?, ?, ?, ?, 1)
    """, (nombre_usuario, password_hash, nombre_completo, rol))
    print("Usuario administrador creado correctamente.")
    print("Usuario: admin")
    print("Contraseña: 123456")
except sqlite3.IntegrityError:
    print("El usuario 'admin' ya existe.")

conexion.commit()
conexion.close()
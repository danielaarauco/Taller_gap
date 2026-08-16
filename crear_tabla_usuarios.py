import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nombre_completo TEXT,
    rol TEXT NOT NULL DEFAULT 'ADMIN',
    activo INTEGER NOT NULL DEFAULT 1
)
""")

conexion.commit()
conexion.close()

print("Tabla 'usuarios' creada correctamente.")
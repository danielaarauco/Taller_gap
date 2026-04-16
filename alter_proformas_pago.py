import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

print("Iniciando cambio en base de datos...")

try:
    cursor.execute("ALTER TABLE proformas ADD COLUMN pago TEXT DEFAULT 'Pendiente'")
    print("Columna 'pago' agregada correctamente.")
except sqlite3.OperationalError as e:
    print("No se pudo agregar la columna:", e)

conexion.commit()
conexion.close()

print("Proceso finalizado.")
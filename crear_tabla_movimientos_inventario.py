import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS movimientos_inventario (
    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_item INTEGER NOT NULL,
    fecha_movimiento TEXT NOT NULL,
    tipo_movimiento TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    motivo TEXT NOT NULL,
    referencia TEXT,
    observaciones TEXT,
    FOREIGN KEY (id_item) REFERENCES inventario(id_item)
)
""")

conexion.commit()
conexion.close()

print("Tabla 'movimientos_inventario' creada correctamente.")
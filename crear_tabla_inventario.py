import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS inventario (
    id_item INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 0,
    unidad_medida TEXT NOT NULL,
    estado TEXT NOT NULL,
    categoria TEXT NOT NULL,
    marca TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conexion.commit()
conexion.close()

print("Tabla 'inventario' creada correctamente.")
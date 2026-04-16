import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_completo TEXT NOT NULL,
    telefono TEXT NOT NULL,
    ci_nit TEXT,
    direccion TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS vehiculos (
    id_vehiculo INTEGER PRIMARY KEY AUTOINCREMENT,
    id_cliente INTEGER NOT NULL,
    placa TEXT NOT NULL UNIQUE,
    marca TEXT NOT NULL,
    modelo TEXT NOT NULL,
    tipo TEXT,
    vin TEXT,
    color TEXT,
    anio INTEGER,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
)

""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS ingresos (
    id_ingreso INTEGER PRIMARY KEY AUTOINCREMENT,
    id_vehiculo INTEGER NOT NULL,
    fecha_ingreso TEXT NOT NULL,
    motivo TEXT NOT NULL,
    observaciones TEXT,
    estado TEXT NOT NULL,
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS proformas (
    id_proforma INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_proforma TEXT NOT NULL UNIQUE,
    id_cliente INTEGER NOT NULL,
    id_vehiculo INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    subtotal_repuestos REAL DEFAULT 0,
    subtotal_mano_obra REAL DEFAULT 0,
    total_general REAL DEFAULT 0,
    total_literal TEXT,
    observaciones TEXT,
    nota_documento TEXT DEFAULT 'NO ES VALIDO COMO FACTURA',
    estado TEXT DEFAULT 'Pendiente',
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo)
)
""")
conexion.commit()
conexion.close()

print("Base de datos y tabla clientes creadas correctamente.")
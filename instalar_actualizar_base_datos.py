"""
Crea o actualiza taller.db para que tenga exactamente el esquema que
necesita la aplicación (todas las tablas y columnas), sin borrar ni
tocar los datos que ya existan.

Es seguro ejecutarlo las veces que hagan falta: cada tabla se crea solo
si no existe, y cada columna se agrega solo si todavía no está.

Usalo:
  - En una instalación nueva (para crear la base de datos desde cero).
  - En una instalación existente, después de actualizar el código del
    sistema, para asegurarte de que la base de datos tenga las columnas
    más nuevas (por ejemplo, precios de inventario, o el control de
    stock descontado en proformas).

Uso:
    venv\\Scripts\\python.exe instalar_actualizar_base_datos.py
"""

import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()


def columna_existe(tabla, columna):
    cursor.execute(f"PRAGMA table_info({tabla})")
    return columna in [fila[1] for fila in cursor.fetchall()]


def agregar_columna_si_falta(tabla, columna, definicion):
    if not columna_existe(tabla, columna):
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"  + columna '{columna}' agregada a '{tabla}'.")


# ===== Tablas base =====

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
    id_cliente INTEGER,
    id_vehiculo INTEGER,
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS detalle_proforma (
    id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
    id_proforma INTEGER NOT NULL,
    tipo_item TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario REAL NOT NULL,
    subtotal REAL NOT NULL,
    FOREIGN KEY (id_proforma) REFERENCES proformas(id_proforma)
)
""")

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS recibos (
    id_recibo INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_recibo TEXT NOT NULL,
    id_proforma INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    monto_recibido REAL NOT NULL DEFAULT 0,
    concepto TEXT,
    observaciones TEXT,
    nombre_recibe TEXT,
    ci_recibe TEXT,
    recibi_conforme TEXT DEFAULT 'RECIBI CONFORME',
    nota_documento TEXT DEFAULT 'DOCUMENTO INTERNO',
    FOREIGN KEY (id_proforma) REFERENCES proformas(id_proforma)
)
""")

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS gastos (
    id_gasto INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    categoria TEXT NOT NULL,
    descripcion TEXT,
    monto REAL NOT NULL,
    id_item INTEGER REFERENCES inventario(id_item),
    cantidad INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conexion.commit()
print("Tablas verificadas/creadas.")

# ===== Columnas agregadas después de la versión inicial =====
# (cada una se agrega solo si todavía no existe)

print("Revisando columnas...")

agregar_columna_si_falta("ingresos", "mecanico_encargado", "TEXT")

agregar_columna_si_falta("proformas", "pago", "TEXT DEFAULT 'Pendiente'")
agregar_columna_si_falta("proformas", "tipo_proforma", "TEXT DEFAULT 'FORMAL'")
agregar_columna_si_falta("proformas", "nombre_cliente_manual", "TEXT")
agregar_columna_si_falta("proformas", "telefono_manual", "TEXT")
agregar_columna_si_falta("proformas", "marca_manual", "TEXT")
agregar_columna_si_falta("proformas", "modelo_manual", "TEXT")
agregar_columna_si_falta("proformas", "tipo_manual", "TEXT")
agregar_columna_si_falta("proformas", "placa_manual", "TEXT")
agregar_columna_si_falta("proformas", "vin_manual", "TEXT")
agregar_columna_si_falta("proformas", "stock_descontado", "INTEGER NOT NULL DEFAULT 0")

agregar_columna_si_falta("inventario", "precio_compra", "REAL NOT NULL DEFAULT 0")
agregar_columna_si_falta("inventario", "precio_venta", "REAL NOT NULL DEFAULT 0")

agregar_columna_si_falta("detalle_proforma", "id_item", "INTEGER REFERENCES inventario(id_item)")

# Papelera (baja lógica): en vez de borrar definitivamente, clientes,
# vehículos y proformas se marcan como inactivos y se pueden restaurar.
agregar_columna_si_falta("clientes", "activo", "INTEGER NOT NULL DEFAULT 1")
agregar_columna_si_falta("vehiculos", "activo", "INTEGER NOT NULL DEFAULT 1")
agregar_columna_si_falta("proformas", "activo", "INTEGER NOT NULL DEFAULT 1")

conexion.commit()
conexion.close()

print("Listo: la base de datos tiene el esquema completo y actualizado.")

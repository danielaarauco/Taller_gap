"""
Script de migración: agrega la columna stock_descontado a la tabla proformas,
si todavía no existe. Se usa para saber si el stock de los repuestos de
inventario de una proforma ya fue descontado (al emitir el primer recibo)
o todavía no (la proforma es solo una cotización y aún no se "concretó").

También marca como ya concretadas (stock_descontado = 1) las proformas que
ya tengan al menos un recibo registrado, para no descontar el stock por
segunda vez sobre datos históricos.

Ejecutar una sola vez:
    python agregar_stock_descontado_proformas.py
"""

import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("PRAGMA table_info(proformas)")
columnas = [fila[1] for fila in cursor.fetchall()]

if "stock_descontado" not in columnas:
    cursor.execute("ALTER TABLE proformas ADD COLUMN stock_descontado INTEGER NOT NULL DEFAULT 0")
    print("Columna 'stock_descontado' agregada a proformas.")
else:
    print("La columna 'stock_descontado' ya existe en proformas.")

cursor.execute("""
    UPDATE proformas
    SET stock_descontado = 1
    WHERE id_proforma IN (SELECT DISTINCT id_proforma FROM recibos)
""")
print(f"Proformas marcadas como ya concretadas (con recibo existente): {cursor.rowcount}")

conexion.commit()
conexion.close()

print("Migración completada.")

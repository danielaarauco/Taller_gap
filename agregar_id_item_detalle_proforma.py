"""
Script de migración: agrega la columna id_item a la tabla detalle_proforma,
si todavía no existe. Permite vincular un repuesto de una proforma con
un ítem del inventario (cuando el repuesto se toma del almacén en vez de
comprarse de forma externa).

Ejecutar una sola vez:
    python agregar_id_item_detalle_proforma.py
"""

import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("PRAGMA table_info(detalle_proforma)")
columnas = [fila[1] for fila in cursor.fetchall()]

if "id_item" not in columnas:
    cursor.execute("ALTER TABLE detalle_proforma ADD COLUMN id_item INTEGER REFERENCES inventario(id_item)")
    print("Columna 'id_item' agregada a detalle_proforma.")
else:
    print("La columna 'id_item' ya existe en detalle_proforma.")

conexion.commit()
conexion.close()

print("Migración completada.")

"""
Script de migración: agrega las columnas precio_compra y precio_venta
a la tabla inventario, si todavía no existen.

Ejecutar una sola vez:
    python agregar_precios_inventario.py
"""

import sqlite3

conexion = sqlite3.connect("taller.db")
cursor = conexion.cursor()

cursor.execute("PRAGMA table_info(inventario)")
columnas = [fila[1] for fila in cursor.fetchall()]

if "precio_compra" not in columnas:
    cursor.execute("ALTER TABLE inventario ADD COLUMN precio_compra REAL NOT NULL DEFAULT 0")
    print("Columna 'precio_compra' agregada.")
else:
    print("La columna 'precio_compra' ya existe.")

if "precio_venta" not in columnas:
    cursor.execute("ALTER TABLE inventario ADD COLUMN precio_venta REAL NOT NULL DEFAULT 0")
    print("Columna 'precio_venta' agregada.")
else:
    print("La columna 'precio_venta' ya existe.")

conexion.commit()
conexion.close()

print("Migración completada.")

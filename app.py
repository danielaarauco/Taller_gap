import os
from flask import Flask, render_template, request, redirect, url_for, make_response, flash
from xhtml2pdf import pisa
from io import BytesIO
import sqlite3
import re


def link_callback(uri, rel):
    ruta_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    ruta = os.path.join(ruta_static, uri.replace("/static/", ""))
    return ruta

app = Flask(__name__)
app.secret_key = "clave_secreta_taller"


def conectar_db():
    conexion = sqlite3.connect("taller.db")
    conexion.row_factory = sqlite3.Row
    return conexion
######################
def limpiar_texto(texto):
    return " ".join(texto.strip().split()) if texto else ""

def normalizar_nombre(texto):
    return limpiar_texto(texto).upper()

def normalizar_placa(texto):
    return limpiar_texto(texto).upper()

def normalizar_vin(texto):
    return limpiar_texto(texto).upper()

def es_telefono_valido(telefono):
    telefono = limpiar_texto(telefono)
    return bool(re.fullmatch(r"[0-9+\-\s]{6,20}", telefono))

def es_ci_nit_valido(ci_nit):
    ci_nit = limpiar_texto(ci_nit)
    return len(ci_nit) <= 30

def es_vin_valido(vin):
    vin = normalizar_vin(vin)
    if not vin:
        return True
    return len(vin) >= 8 and len(vin) <= 25


#######################
def es_numero_proforma_valido(numero):
    numero = limpiar_texto(numero)
    return bool(re.fullmatch(r"PF-\d{4,}", numero))

#####################
def numero_a_literal(numero):
    unidades = [
        "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS",
        "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
        "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE",
        "DIECIOCHO", "DIECINUEVE", "VEINTE"
    ]

    decenas = [
        "", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA",
        "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"
    ]

    centenas = [
        "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
        "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
        "OCHOCIENTOS", "NOVECIENTOS"
    ]

    def convertir_menor_100(n):
        if n <= 20:
            return unidades[n]
        if n < 30:
            return "VEINTI" + unidades[n - 20].lower().upper()
        d = n // 10
        r = n % 10
        if r == 0:
            return decenas[d]
        return decenas[d] + " Y " + unidades[r]

    def convertir_menor_1000(n):
        if n == 100:
            return "CIEN"
        if n < 100:
            return convertir_menor_100(n)
        c = n // 100
        r = n % 100
        if r == 0:
            return centenas[c]
        return centenas[c] + " " + convertir_menor_100(r)

    entero = int(numero)
    decimal = int(round((numero - entero) * 100))

    if entero == 0:
        literal = "CERO"
    elif entero < 1000:
        literal = convertir_menor_1000(entero)
    elif entero < 1000000:
        miles = entero // 1000
        resto = entero % 1000

        if miles == 1:
            literal = "MIL"
        else:
            literal = convertir_menor_1000(miles) + " MIL"

        if resto > 0:
            literal += " " + convertir_menor_1000(resto)
    else:
        literal = str(entero)

    return f"{literal} CON {decimal:02d}/100 BOLIVIANOS"
#######
def recalcular_totales_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT COALESCE(SUM(subtotal), 0)
        FROM detalle_proforma
        WHERE id_proforma = ? AND tipo_item = 'REPUESTO'
    """, (id_proforma,))
    subtotal_repuestos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(subtotal), 0)
        FROM detalle_proforma
        WHERE id_proforma = ? AND tipo_item = 'MANO_OBRA'
    """, (id_proforma,))
    subtotal_mano_obra = cursor.fetchone()[0]

    total_general = subtotal_repuestos + subtotal_mano_obra
    total_literal = numero_a_literal(total_general) if total_general > 0 else ""

    cursor.execute("""
        UPDATE proformas
        SET subtotal_repuestos = ?, subtotal_mano_obra = ?, total_general = ?, total_literal = ?
        WHERE id_proforma = ?
    """, (subtotal_repuestos, subtotal_mano_obra, total_general, total_literal, id_proforma))

    conexion.commit()
    conexion.close()
#################
def convertir_html_a_pdf(html):
    resultado = BytesIO()
    pdf = pisa.CreatePDF(
        src=html,
        dest=resultado,
        link_callback=link_callback
    )
    if pdf.err:
        return None
    return resultado.getvalue()
#################

@app.route("/")
def inicio():
    return render_template("index.html")


#REGISTRAR NUEVO CLIENTE
@app.route("/clientes/nuevo", methods=["GET", "POST"])
def nuevo_cliente():
    if request.method == "POST":
        nombre_completo = normalizar_nombre(request.form["nombre_completo"])
        telefono = limpiar_texto(request.form["telefono"])
        ci_nit = limpiar_texto(request.form["ci_nit"])
        direccion = limpiar_texto(request.form["direccion"])

        if not nombre_completo:
            flash("El nombre completo es obligatorio.", "warning")
            return render_template("nuevo_cliente.html")

        if not telefono:
            flash("El teléfono es obligatorio.", "warning")
            return render_template("nuevo_cliente.html")

        if not es_telefono_valido(telefono):
            flash("El teléfono no tiene un formato válido.", "warning")
            return render_template("nuevo_cliente.html")

        if ci_nit and not es_ci_nit_valido(ci_nit):
            flash("El CI / NIT no tiene un formato válido.", "warning")
            return render_template("nuevo_cliente.html")

        conexion = conectar_db()
        cursor = conexion.cursor()

        if ci_nit:
            cursor.execute("SELECT id_cliente FROM clientes WHERE ci_nit = ?", (ci_nit,))
            cliente_ci = cursor.fetchone()
            if cliente_ci:
                conexion.close()
                flash("Ya existe un cliente registrado con ese CI / NIT.", "warning")
                return render_template("nuevo_cliente.html")

        cursor.execute("SELECT id_cliente FROM clientes WHERE telefono = ?", (telefono,))
        cliente_telefono = cursor.fetchone()
        if cliente_telefono:
            conexion.close()
            flash("Ya existe un cliente registrado con ese teléfono.", "warning")
            return render_template("nuevo_cliente.html")

        cursor.execute("""
            SELECT id_cliente
            FROM clientes
            WHERE nombre_completo = ? AND telefono = ?
        """, (nombre_completo, telefono))
        cliente_nombre = cursor.fetchone()
        if cliente_nombre:
            conexion.close()
            flash("Ya existe un cliente registrado con ese nombre y teléfono.", "warning")
            return render_template("nuevo_cliente.html")

        cursor.execute("""
            INSERT INTO clientes (nombre_completo, telefono, ci_nit, direccion)
            VALUES (?, ?, ?, ?)
        """, (nombre_completo, telefono, ci_nit if ci_nit else None, direccion))

        conexion.commit()
        conexion.close()

        flash("Cliente registrado correctamente.", "success")
        return redirect(url_for("listar_clientes"))

    return render_template("nuevo_cliente.html")


#LISTAR CLIENTES REGISTRADOS
@app.route("/clientes")
def listar_clientes():
    busqueda = request.args.get("busqueda", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    if busqueda:
        cursor.execute("""
            SELECT *
            FROM clientes
            WHERE nombre_completo LIKE ? OR ci_nit LIKE ?
            ORDER BY id_cliente DESC
        """, (f"%{busqueda}%", f"%{busqueda}%"))
    else:
        cursor.execute("SELECT * FROM clientes ORDER BY id_cliente DESC")

    clientes = cursor.fetchall()
    conexion.close()

    return render_template("clientes.html", clientes=clientes, busqueda=busqueda)

#REGISTRAR NUEVO VEHICULO
@app.route("/vehiculos/nuevo", methods=["GET", "POST"])
def nuevo_vehiculo():
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        id_cliente = request.form["id_cliente"]
        placa = normalizar_placa(request.form["placa"])
        marca = limpiar_texto(request.form["marca"]).upper()
        modelo = limpiar_texto(request.form["modelo"]).upper()
        tipo = limpiar_texto(request.form["tipo"]).upper()
        vin = normalizar_vin(request.form["vin"])
        color = limpiar_texto(request.form["color"]).upper()
        anio = limpiar_texto(request.form["anio"])

        if not id_cliente:
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Debes seleccionar un cliente.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if not placa:
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("La placa es obligatoria.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if not marca or not modelo:
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("La marca y el modelo son obligatorios.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if vin and not es_vin_valido(vin):
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El VIN no tiene un formato válido.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if anio and (not anio.isdigit() or int(anio) < 1900 or int(anio) > 2100):
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El año no es válido.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        cursor.execute("SELECT id_vehiculo FROM vehiculos WHERE placa = ?", (placa,))
        vehiculo_existente = cursor.fetchone()
        if vehiculo_existente:
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Ya existe un vehículo registrado con esa placa.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if vin:
            cursor.execute("SELECT id_vehiculo FROM vehiculos WHERE vin = ?", (vin,))
            vin_existente = cursor.fetchone()
            if vin_existente:
                cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
                clientes = cursor.fetchall()
                conexion.close()
                flash("Ya existe un vehículo registrado con ese VIN.", "warning")
                return render_template("nuevo_vehiculo.html", clientes=clientes)

        cursor.execute("""
            INSERT INTO vehiculos (id_cliente, placa, marca, modelo, tipo, vin, color, anio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (id_cliente, placa, marca, modelo, tipo, vin if vin else None, color, int(anio) if anio else None))

        conexion.commit()
        conexion.close()

        flash("Vehículo registrado correctamente.", "success")
        return redirect(url_for("listar_vehiculos"))

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()
    conexion.close()

    return render_template("nuevo_vehiculo.html", clientes=clientes)

#LISTAR VEHICULOS REGISTRADOS
@app.route("/vehiculos")
def listar_vehiculos():
    busqueda = request.args.get("busqueda", "").strip()
    id_cliente = request.args.get("id_cliente", "").strip()
    modelo = request.args.get("modelo", "").strip()
    tipo = request.args.get("tipo", "").strip()
    anio = request.args.get("anio", "").strip()
    color = request.args.get("color", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE 1=1
    """
    parametros = []

    if busqueda:
        query += " AND (v.placa LIKE ? OR v.vin LIKE ?)"
        parametros.extend([f"%{busqueda}%", f"%{busqueda}%"])

    if id_cliente:
        query += " AND v.id_cliente = ?"
        parametros.append(id_cliente)

    if modelo:
        query += " AND v.modelo LIKE ?"
        parametros.append(f"%{modelo}%")

    if tipo:
        query += " AND v.tipo LIKE ?"
        parametros.append(f"%{tipo}%")

    if anio:
        query += " AND v.anio = ?"
        parametros.append(anio)

    if color:
        query += " AND v.color LIKE ?"
        parametros.append(f"%{color}%")

    query += " ORDER BY v.id_vehiculo DESC"

    cursor.execute(query, parametros)
    vehiculos = cursor.fetchall()

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()

    return render_template(
        "vehiculos.html",
        vehiculos=vehiculos,
        clientes=clientes,
        busqueda=busqueda,
        id_cliente=id_cliente,
        modelo=modelo,
        tipo=tipo,
        anio=anio,
        color=color
    )

#NUEVO INGRESO VEHICULOS
@app.route("/ingresos/nuevo", methods=["GET", "POST"])
def nuevo_ingreso():
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        id_vehiculo = request.form["id_vehiculo"]
        fecha_ingreso = request.form["fecha_ingreso"]
        motivo = limpiar_texto(request.form["motivo"])
        observaciones = limpiar_texto(request.form["observaciones"])
        estado = limpiar_texto(request.form["estado"])
        mecanico_encargado = limpiar_texto(request.form["mecanico_encargado"]).upper()

        if not id_vehiculo or not fecha_ingreso or not motivo or not estado:
            cursor.execute("""
                SELECT v.*, c.nombre_completo
                FROM vehiculos v
                INNER JOIN clientes c ON v.id_cliente = c.id_cliente
                ORDER BY v.placa ASC
            """)
            vehiculos = cursor.fetchall()
            conexion.close()
            flash("Vehículo, fecha, motivo y estado son obligatorios.", "warning")
            return render_template("nuevo_ingreso.html", vehiculos=vehiculos)

        cursor.execute("""
            INSERT INTO ingresos (id_vehiculo, fecha_ingreso, motivo, observaciones, estado, mecanico_encargado)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_vehiculo, fecha_ingreso, motivo, observaciones, estado, mecanico_encargado))

        conexion.commit()
        conexion.close()

        flash("Ingreso registrado correctamente.", "success")
        return redirect(url_for("listar_ingresos"))

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        ORDER BY v.placa ASC
    """)
    vehiculos = cursor.fetchall()
    conexion.close()

    return render_template("nuevo_ingreso.html", vehiculos=vehiculos)

#LISTAR INGRESOS VEHICULOS
@app.route("/ingresos")
def listar_ingresos():
    placa = request.args.get("placa", "").strip()
    id_cliente = request.args.get("id_cliente", "").strip()
    mecanico = request.args.get("mecanico", "").strip()
    estado = request.args.get("estado", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT i.*, v.placa, v.marca, v.modelo, c.nombre_completo
        FROM ingresos i
        INNER JOIN vehiculos v ON i.id_vehiculo = v.id_vehiculo
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE 1=1
    """
    parametros = []

    if placa:
        query += " AND v.placa LIKE ?"
        parametros.append(f"%{placa}%")

    if id_cliente:
        query += " AND c.id_cliente = ?"
        parametros.append(id_cliente)

    if mecanico:
        query += " AND i.mecanico_encargado LIKE ?"
        parametros.append(f"%{mecanico}%")

    if estado:
        query += " AND i.estado = ?"
        parametros.append(estado)

    if fecha_desde:
        query += " AND i.fecha_ingreso >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND i.fecha_ingreso <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY i.id_ingreso DESC"

    cursor.execute(query, parametros)
    ingresos = cursor.fetchall()

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()

    return render_template(
        "ingresos.html",
        ingresos=ingresos,
        clientes=clientes,
        placa=placa,
        id_cliente=id_cliente,
        mecanico=mecanico,
        estado=estado,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

#HISTORIAL VEHICULO
@app.route("/vehiculos/<int:id_vehiculo>/historial")
def historial_vehiculo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT v.*, c.nombre_completo, c.telefono
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE v.id_vehiculo = ?
    """, (id_vehiculo,))
    vehiculo = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM ingresos
        WHERE id_vehiculo = ?
        ORDER BY id_ingreso DESC
    """, (id_vehiculo,))
    historial = cursor.fetchall()

    conexion.close()

    return render_template("historial_vehiculo.html", vehiculo=vehiculo, historial=historial)


#NUEVA  PROFORMA
@app.route("/proformas/nuevo", methods=["GET", "POST"])
def nueva_proforma():
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT numero_proforma
        FROM proformas
        ORDER BY id_proforma DESC
        LIMIT 1
    """)
    ultima_proforma = cursor.fetchone()

    if ultima_proforma and ultima_proforma["numero_proforma"]:
        ultimo_numero = ultima_proforma["numero_proforma"]

        if "-" in ultimo_numero:
            partes = ultimo_numero.split("-")
            if len(partes) > 1 and partes[1].isdigit():
                ultimo_id = int(partes[1])
                nuevo_numero = f"PF-{ultimo_id + 1:04d}"
            else:
                nuevo_numero = "PF-0001"
        else:
            nuevo_numero = "PF-0001"
    else:
        nuevo_numero = "PF-0001"

    if request.method == "POST":
        id_cliente = request.form["id_cliente"]
        id_vehiculo = request.form["id_vehiculo"]
        fecha = request.form["fecha"]
        observaciones = request.form["observaciones"]

        cursor.execute("""
            INSERT INTO proformas (
                numero_proforma, id_cliente, id_vehiculo, fecha,
                subtotal_repuestos, subtotal_mano_obra, total_general,
                total_literal, observaciones, pago
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, '', ?, 'Pendiente')
        """, (nuevo_numero, id_cliente, id_vehiculo, fecha, observaciones))

        conexion.commit()
        conexion.close()

        return redirect(url_for("listar_proformas"))

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        ORDER BY v.id_vehiculo DESC
    """)
    vehiculos = cursor.fetchall()

    conexion.close()

    return render_template(
        "nueva_proforma.html",
        clientes=clientes,
        vehiculos=vehiculos,
        nuevo_numero=nuevo_numero
    )


#LISTAR PROFORMAS
@app.route("/proformas")
def listar_proformas():
    id_cliente = request.args.get("id_cliente", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT p.*, c.nombre_completo, v.placa, v.marca, v.modelo
        FROM proformas p
        INNER JOIN clientes c ON p.id_cliente = c.id_cliente
        INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE 1=1
    """
    parametros = []

    if id_cliente:
        query += " AND p.id_cliente = ?"
        parametros.append(id_cliente)

    if fecha_desde:
        query += " AND p.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND p.fecha <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY p.id_proforma DESC"

    cursor.execute(query, parametros)
    proformas = cursor.fetchall()

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()

    return render_template(
        "proformas.html",
        proformas=proformas,
        clientes=clientes,
        id_cliente=id_cliente,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

#VER PROFORMA
@app.route("/proformas/<int:id_proforma>")
def ver_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT p.*, c.nombre_completo, c.telefono, v.placa, v.marca, v.modelo, v.tipo, v.vin
        FROM proformas p
        INNER JOIN clientes c ON p.id_cliente = c.id_cliente
        INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE p.id_proforma = ?
    """, (id_proforma,))
    proforma = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM detalle_proforma
        WHERE id_proforma = ?
        ORDER BY id_detalle ASC
    """, (id_proforma,))
    detalles = cursor.fetchall()

    conexion.close()

    return render_template("ver_proforma.html", proforma=proforma, detalles=detalles)

#AGREGAR DETALLE PROFORMA
@app.route("/proformas/<int:id_proforma>/agregar-detalle", methods=["GET", "POST"])
def agregar_detalle_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        tipo_item = request.form["tipo_item"]
        descripcion = request.form["descripcion"]
        cantidad = int(request.form["cantidad"])
        precio_unitario = float(request.form["precio_unitario"])
        subtotal = cantidad * precio_unitario

        cursor.execute("""
            INSERT INTO detalle_proforma (
                id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal))

        cursor.execute("""
            SELECT COALESCE(SUM(subtotal), 0)
            FROM detalle_proforma
            WHERE id_proforma = ? AND tipo_item = 'REPUESTO'
        """, (id_proforma,))
        subtotal_repuestos = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COALESCE(SUM(subtotal), 0)
            FROM detalle_proforma
            WHERE id_proforma = ? AND tipo_item = 'MANO_OBRA'
        """, (id_proforma,))
        subtotal_mano_obra = cursor.fetchone()[0]

        total_general = subtotal_repuestos + subtotal_mano_obra
        total_literal = numero_a_literal(total_general)

        cursor.execute("""
            UPDATE proformas
            SET subtotal_repuestos = ?, subtotal_mano_obra = ?, total_general = ?, total_literal = ?
            WHERE id_proforma = ?
        """, (subtotal_repuestos, subtotal_mano_obra, total_general, total_literal, id_proforma))

        conexion.commit()
        conexion.close()

        return redirect(url_for("ver_proforma", id_proforma=id_proforma))

    cursor.execute("""
        SELECT p.*, c.nombre_completo, v.placa, v.marca, v.modelo
        FROM proformas p
        INNER JOIN clientes c ON p.id_cliente = c.id_cliente
        INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE p.id_proforma = ?
    """, (id_proforma,))
    proforma = cursor.fetchone()

    conexion.close()

    return render_template("agregar_detalle_proforma.html", proforma=proforma)

#EXPORTAR PROFORMA A PDF
@app.route("/proformas/<int:id_proforma>/pdf")
def exportar_proforma_pdf(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT p.*, c.nombre_completo, c.telefono, v.placa, v.marca, v.modelo, v.tipo, v.vin
        FROM proformas p
        INNER JOIN clientes c ON p.id_cliente = c.id_cliente
        INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE p.id_proforma = ?
    """, (id_proforma,))
    proforma = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM detalle_proforma
        WHERE id_proforma = ?
        ORDER BY id_detalle ASC
    """, (id_proforma,))
    detalles = cursor.fetchall()

    conexion.close()

    repuestos = [item for item in detalles if item["tipo_item"] == "REPUESTO"]
    mano_obra = [item for item in detalles if item["tipo_item"] == "MANO_OBRA"]

    html = render_template(
        "proforma_pdf.html",
        proforma=proforma,
        repuestos=repuestos,
        mano_obra=mano_obra
    )

    pdf = convertir_html_a_pdf(html)

    if pdf is None:
        return "Error al generar el PDF"

    respuesta = make_response(pdf)
    respuesta.headers["Content-Type"] = "application/pdf"
    respuesta.headers["Content-Disposition"] = f"inline; filename=proforma_{proforma['numero_proforma']}.pdf"
    
    return respuesta


#############ACCIONES#############
#ACCIONES VEHICULOS
@app.route("/vehiculos/<int:id_vehiculo>/editar", methods=["GET", "POST"])
def editar_vehiculo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        id_cliente = request.form["id_cliente"]
        placa = normalizar_placa(request.form["placa"])
        marca = limpiar_texto(request.form["marca"]).upper()
        modelo = limpiar_texto(request.form["modelo"]).upper()
        tipo = limpiar_texto(request.form["tipo"]).upper()
        vin = normalizar_vin(request.form["vin"])
        color = limpiar_texto(request.form["color"]).upper()
        anio = limpiar_texto(request.form["anio"])

        if not id_cliente or not placa or not marca or not modelo:
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Cliente, placa, marca y modelo son obligatorios.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        if vin and not es_vin_valido(vin):
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El VIN no tiene un formato válido.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        if anio and (not anio.isdigit() or int(anio) < 1900 or int(anio) > 2100):
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El año no es válido.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        cursor.execute("""
            SELECT id_vehiculo
            FROM vehiculos
            WHERE placa = ? AND id_vehiculo != ?
        """, (placa, id_vehiculo))
        vehiculo_existente = cursor.fetchone()

        if vehiculo_existente:
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("No puedes guardar esa placa porque ya pertenece a otro vehículo.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        if vin:
            cursor.execute("""
                SELECT id_vehiculo
                FROM vehiculos
                WHERE vin = ? AND id_vehiculo != ?
            """, (vin, id_vehiculo))
            vin_existente = cursor.fetchone()

            if vin_existente:
                cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
                vehiculo = cursor.fetchone()
                cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
                clientes = cursor.fetchall()
                conexion.close()
                flash("No puedes guardar ese VIN porque ya pertenece a otro vehículo.", "warning")
                return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        cursor.execute("""
            UPDATE vehiculos
            SET id_cliente = ?, placa = ?, marca = ?, modelo = ?, tipo = ?, vin = ?, color = ?, anio = ?
            WHERE id_vehiculo = ?
        """, (id_cliente, placa, marca, modelo, tipo, vin if vin else None, color, int(anio) if anio else None, id_vehiculo))

        conexion.commit()
        conexion.close()

        flash("Vehículo actualizado correctamente.", "success")
        return redirect(url_for("listar_vehiculos"))

    cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
    vehiculo = cursor.fetchone()

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()
    return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

#ELIMINAR VEHICULO
@app.route("/vehiculos/<int:id_vehiculo>/eliminar", methods=["POST"])
def eliminar_vehiculo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT COUNT(*) FROM ingresos WHERE id_vehiculo = ?", (id_vehiculo,))
    cantidad_ingresos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM proformas WHERE id_vehiculo = ?", (id_vehiculo,))
    cantidad_proformas = cursor.fetchone()[0]

    if cantidad_ingresos > 0 or cantidad_proformas > 0:
        conexion.close()
        return "No se puede eliminar el vehículo porque tiene ingresos o proformas asociadas."

    cursor.execute("DELETE FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
    conexion.commit()
    conexion.close()

    flash("Vehiculo eliminado correctamente.", "success")
    return redirect(url_for("listar_vehiculos"))

#ACCIONES CLIENTES
#editar cliente
@app.route("/clientes/<int:id_cliente>/editar", methods=["GET", "POST"])
def editar_cliente(id_cliente):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        nombre_completo = normalizar_nombre(request.form["nombre_completo"])
        telefono = limpiar_texto(request.form["telefono"])
        ci_nit = limpiar_texto(request.form["ci_nit"])
        direccion = limpiar_texto(request.form["direccion"])

        if not nombre_completo:
            flash("El nombre completo es obligatorio.", "warning")
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
            cliente = cursor.fetchone()
            conexion.close()
            return render_template("editar_cliente.html", cliente=cliente)

        if not telefono:
            flash("El teléfono es obligatorio.", "warning")
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
            cliente = cursor.fetchone()
            conexion.close()
            return render_template("editar_cliente.html", cliente=cliente)

        if not es_telefono_valido(telefono):
            flash("El teléfono no tiene un formato válido.", "warning")
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
            cliente = cursor.fetchone()
            conexion.close()
            return render_template("editar_cliente.html", cliente=cliente)

        if ci_nit and not es_ci_nit_valido(ci_nit):
            flash("El CI / NIT no tiene un formato válido.", "warning")
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
            cliente = cursor.fetchone()
            conexion.close()
            return render_template("editar_cliente.html", cliente=cliente)

        if ci_nit:
            cursor.execute("""
                SELECT id_cliente
                FROM clientes
                WHERE ci_nit = ? AND id_cliente != ?
            """, (ci_nit, id_cliente))
            cliente_ci = cursor.fetchone()
            if cliente_ci:
                cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
                cliente = cursor.fetchone()
                conexion.close()
                flash("No puedes guardar ese CI / NIT porque ya pertenece a otro cliente.", "warning")
                return render_template("editar_cliente.html", cliente=cliente)

        cursor.execute("""
            SELECT id_cliente
            FROM clientes
            WHERE telefono = ? AND id_cliente != ?
        """, (telefono, id_cliente))
        cliente_telefono = cursor.fetchone()
        if cliente_telefono:
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
            cliente = cursor.fetchone()
            conexion.close()
            flash("No puedes guardar ese teléfono porque ya pertenece a otro cliente.", "warning")
            return render_template("editar_cliente.html", cliente=cliente)

        cursor.execute("""
            UPDATE clientes
            SET nombre_completo = ?, telefono = ?, ci_nit = ?, direccion = ?
            WHERE id_cliente = ?
        """, (nombre_completo, telefono, ci_nit if ci_nit else None, direccion, id_cliente))

        conexion.commit()
        conexion.close()

        flash("Cliente actualizado correctamente.", "success")
        return redirect(url_for("listar_clientes"))

    cursor.execute("SELECT * FROM clientes WHERE id_cliente = ?", (id_cliente,))
    cliente = cursor.fetchone()
    conexion.close()

    return render_template("editar_cliente.html", cliente=cliente)

#eliminar cliente
@app.route("/clientes/<int:id_cliente>/eliminar", methods=["POST"])
def eliminar_cliente(id_cliente):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT COUNT(*) FROM vehiculos WHERE id_cliente = ?", (id_cliente,))
    cantidad_vehiculos = cursor.fetchone()[0]

    if cantidad_vehiculos > 0:
        conexion.close()
        return "No se puede eliminar el cliente porque tiene vehículos asociados."

    cursor.execute("DELETE FROM clientes WHERE id_cliente = ?", (id_cliente,))
    conexion.commit()
    conexion.close()

    flash("Cliente eliminado correctamente.", "success")
    return redirect(url_for("listar_clientes"))


#ACCIONES INGRESOS
#editar ingreso
@app.route("/ingresos/<int:id_ingreso>/editar", methods=["GET", "POST"])
def editar_ingreso(id_ingreso):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        id_vehiculo = request.form["id_vehiculo"]
        fecha_ingreso = request.form["fecha_ingreso"]
        motivo = request.form["motivo"]
        observaciones = request.form["observaciones"]
        estado = request.form["estado"]
        mecanico_encargado = limpiar_texto(request.form["mecanico_encargado"]).upper()

        cursor.execute("""
            UPDATE ingresos
            SET id_vehiculo = ?, fecha_ingreso = ?, motivo = ?, observaciones = ?, estado = ?, mecanico_encargado = ?
            WHERE id_ingreso = ?
        """, (id_vehiculo, fecha_ingreso, motivo, observaciones, estado, mecanico_encargado, id_ingreso))

        conexion.commit()
        conexion.close()

        flash("Ingreso actualizado correctamente.", "success")
        return redirect(url_for("listar_ingresos"))

    cursor.execute("SELECT * FROM ingresos WHERE id_ingreso = ?", (id_ingreso,))
    ingreso = cursor.fetchone()

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        ORDER BY v.placa ASC
    """)
    vehiculos = cursor.fetchall()

    conexion.close()
    return render_template("editar_ingreso.html", ingreso=ingreso, vehiculos=vehiculos)
#eliminar ingreso
@app.route("/ingresos/<int:id_ingreso>/eliminar", methods=["POST"])
def eliminar_ingreso(id_ingreso):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("DELETE FROM ingresos WHERE id_ingreso = ?", (id_ingreso,))
    conexion.commit()
    conexion.close()

    flash("Ingreso eliminado correctamente.", "success")
    return redirect(url_for("listar_ingresos"))

#ACCIONES PROFORMA
#editar proforma
@app.route("/proformas/<int:id_proforma>/editar", methods=["GET", "POST"])
def editar_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        id_cliente = request.form["id_cliente"]
        id_vehiculo = request.form["id_vehiculo"]
        fecha = request.form["fecha"]
        observaciones = request.form["observaciones"]
        estado = request.form["estado"]
        pago = request.form["pago"]

        cursor.execute("""
            UPDATE proformas
            SET id_cliente = ?, id_vehiculo = ?, fecha = ?, observaciones = ?, estado = ?, pago = ?
            WHERE id_proforma = ?
        """, (id_cliente, id_vehiculo, fecha, observaciones, estado, pago, id_proforma))

        conexion.commit()
        conexion.close()

        flash("Proforma actualizada correctamente.", "success")
        return redirect(url_for("ver_proforma", id_proforma=id_proforma))

    cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
    proforma = cursor.fetchone()

    cursor.execute("SELECT * FROM clientes ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        ORDER BY v.id_vehiculo DESC
    """)
    vehiculos = cursor.fetchall()

    conexion.close()

    return render_template("editar_proforma.html", proforma=proforma, clientes=clientes, vehiculos=vehiculos)

#eliminar proforma
@app.route("/proformas/<int:id_proforma>/eliminar", methods=["POST"])
def eliminar_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("DELETE FROM detalle_proforma WHERE id_proforma = ?", (id_proforma,))
    cursor.execute("DELETE FROM proformas WHERE id_proforma = ?", (id_proforma,))

    conexion.commit()
    conexion.close()

    flash("Proforma eliminada correctamente.", "success")

    return redirect(url_for("listar_proformas"))

#ACCIONES DETALLE PROFORMA
#editar detalle proforma
@app.route("/detalle-proforma/<int:id_detalle>/editar", methods=["GET", "POST"])
def editar_detalle_proforma(id_detalle):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    detalle = cursor.fetchone()

    if request.method == "POST":
        tipo_item = request.form["tipo_item"]
        descripcion = request.form["descripcion"]
        cantidad = int(request.form["cantidad"])
        precio_unitario = float(request.form["precio_unitario"])
        subtotal = cantidad * precio_unitario

        cursor.execute("""
            UPDATE detalle_proforma
            SET tipo_item = ?, descripcion = ?, cantidad = ?, precio_unitario = ?, subtotal = ?
            WHERE id_detalle = ?
        """, (tipo_item, descripcion, cantidad, precio_unitario, subtotal, id_detalle))

        conexion.commit()
        conexion.close()

        recalcular_totales_proforma(detalle["id_proforma"])
        
        flash("Detalle de proforma actualizado correctamente.", "success")

        return redirect(url_for("ver_proforma", id_proforma=detalle["id_proforma"]))

    conexion.close()
    return render_template("editar_detalle_proforma.html", detalle=detalle)

#eliminar detalle proforma
@app.route("/detalle-proforma/<int:id_detalle>/eliminar", methods=["POST"])
def eliminar_detalle_proforma(id_detalle):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT id_proforma FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    detalle = cursor.fetchone()

    if detalle is None:
        conexion.close()
        return redirect(url_for("listar_proformas"))

    id_proforma = detalle["id_proforma"]

    cursor.execute("DELETE FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    conexion.commit()
    conexion.close()

    recalcular_totales_proforma(id_proforma)
    flash("Detalle de proforma eliminado correctamente.", "success")
    return redirect(url_for("ver_proforma", id_proforma=id_proforma))


#INVENTARIO
#LISTAR INVENTARIO
@app.route("/inventario")
def listar_inventario():
    busqueda = request.args.get("busqueda", "").strip()
    categoria = request.args.get("categoria", "").strip()
    marca = request.args.get("marca", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT *
        FROM inventario
        WHERE 1=1
    """
    parametros = []

    if busqueda:
        query += " AND descripcion LIKE ?"
        parametros.append(f"%{busqueda}%")

    if categoria:
        query += " AND categoria LIKE ?"
        parametros.append(f"%{categoria}%")

    if marca:
        query += " AND marca LIKE ?"
        parametros.append(f"%{marca}%")

    query += " ORDER BY id_item DESC"

    cursor.execute(query, parametros)
    items = cursor.fetchall()

    conexion.close()

    return render_template(
        "inventario.html",
        items=items,
        busqueda=busqueda,
        categoria=categoria,
        marca=marca
    )
#Nuevo item inventario
@app.route("/inventario/nuevo", methods=["GET", "POST"])
def nuevo_item_inventario():
    if request.method == "POST":
        descripcion = limpiar_texto(request.form["descripcion"]).upper()
        cantidad_texto = limpiar_texto(request.form["cantidad"])
        unidad_medida = limpiar_texto(request.form["unidad_medida"]).upper()
        estado = limpiar_texto(request.form["estado"]).capitalize()
        categoria = limpiar_texto(request.form["categoria"]).upper()
        marca = limpiar_texto(request.form["marca"]).upper()

        if not descripcion:
            flash("La descripción es obligatoria.", "warning")
            return render_template("nuevo_item.html")

        if not cantidad_texto:
            flash("La cantidad es obligatoria.", "warning")
            return render_template("nuevo_item.html")

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            flash("La cantidad debe ser numérica.", "warning")
            return render_template("nuevo_item.html")

        if cantidad < 0:
            flash("La cantidad no puede ser negativa.", "warning")
            return render_template("nuevo_item.html")

        if not unidad_medida:
            flash("La unidad de medida es obligatoria.", "warning")
            return render_template("nuevo_item.html")

        if estado not in ["Nuevo", "Usado"]:
            flash("El estado debe ser Nuevo o Usado.", "warning")
            return render_template("nuevo_item.html")

        if not categoria:
            flash("La categoría es obligatoria.", "warning")
            return render_template("nuevo_item.html")

        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO inventario (descripcion, cantidad, unidad_medida, estado, categoria, marca)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (descripcion, cantidad, unidad_medida, estado, categoria, marca))

        conexion.commit()
        conexion.close()

        flash("Ítem registrado correctamente en inventario.", "success")
        return redirect(url_for("listar_inventario"))

    return render_template("nuevo_item.html")
#Acciones inventario
@app.route("/inventario/<int:id_item>/editar", methods=["GET", "POST"])
def editar_item_inventario(id_item):
    conexion = conectar_db()
    cursor = conexion.cursor()

    if request.method == "POST":
        descripcion = limpiar_texto(request.form["descripcion"]).upper()
        cantidad_texto = limpiar_texto(request.form["cantidad"])
        unidad_medida = limpiar_texto(request.form["unidad_medida"]).upper()
        estado = limpiar_texto(request.form["estado"]).capitalize()
        categoria = limpiar_texto(request.form["categoria"]).upper()
        marca = limpiar_texto(request.form["marca"]).upper()

        if not descripcion:
            flash("La descripción es obligatoria.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            flash("La cantidad debe ser numérica.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        if cantidad < 0:
            flash("La cantidad no puede ser negativa.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        if not unidad_medida:
            flash("La unidad de medida es obligatoria.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        if estado not in ["Nuevo", "Usado"]:
            flash("El estado debe ser Nuevo o Usado.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        if not categoria:
            flash("La categoría es obligatoria.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        cursor.execute("""
            UPDATE inventario
            SET descripcion = ?, cantidad = ?, unidad_medida = ?, estado = ?, categoria = ?, marca = ?
            WHERE id_item = ?
        """, (descripcion, cantidad, unidad_medida, estado, categoria, marca, id_item))

        conexion.commit()
        conexion.close()

        flash("Ítem actualizado correctamente.", "success")
        return redirect(url_for("listar_inventario"))

    cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
    item = cursor.fetchone()
    conexion.close()

    return render_template("editar_item.html", item=item)

#eliminar item inventario
@app.route("/inventario/<int:id_item>/eliminar", methods=["POST"])
def eliminar_item_inventario(id_item):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("DELETE FROM inventario WHERE id_item = ?", (id_item,))
    conexion.commit()
    conexion.close()

    flash("Ítem eliminado correctamente.", "success")
    return redirect(url_for("listar_inventario"))
#Movimientos de inventario
@app.route("/inventario/<int:id_item>/movimientos")
def ver_movimientos_inventario(id_item):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
    item = cursor.fetchone()

    cursor.execute("""
        SELECT *
        FROM movimientos_inventario
        WHERE id_item = ?
        ORDER BY id_movimiento DESC
    """, (id_item,))
    movimientos = cursor.fetchall()

    conexion.close()

    return render_template("movimientos_inventario.html", item=item, movimientos=movimientos)

#Registrar nuevo movimiento de inventario
@app.route("/inventario/<int:id_item>/movimientos/nuevo", methods=["GET", "POST"])
def nuevo_movimiento_inventario(id_item):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
    item = cursor.fetchone()

    if item is None:
        conexion.close()
        flash("El ítem no existe.", "warning")
        return redirect(url_for("listar_inventario"))

    if request.method == "POST":
        fecha_movimiento = request.form["fecha_movimiento"]
        tipo_movimiento = limpiar_texto(request.form["tipo_movimiento"]).upper()
        cantidad_texto = limpiar_texto(request.form["cantidad"])
        motivo = limpiar_texto(request.form["motivo"])
        referencia = limpiar_texto(request.form["referencia"])
        observaciones = limpiar_texto(request.form["observaciones"])

        if not fecha_movimiento or not tipo_movimiento or not cantidad_texto or not motivo:
            conexion.close()
            flash("Fecha, tipo, cantidad y motivo son obligatorios.", "warning")
            return render_template("nuevo_movimiento_inventario.html", item=item)

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            conexion.close()
            flash("La cantidad debe ser numérica.", "warning")
            return render_template("nuevo_movimiento_inventario.html", item=item)

        if cantidad <= 0:
            conexion.close()
            flash("La cantidad debe ser mayor a cero.", "warning")
            return render_template("nuevo_movimiento_inventario.html", item=item)

        if tipo_movimiento not in ["ENTRADA", "SALIDA", "AJUSTE"]:
            conexion.close()
            flash("Tipo de movimiento inválido.", "warning")
            return render_template("nuevo_movimiento_inventario.html", item=item)

        stock_actual = item["cantidad"]

        if tipo_movimiento == "ENTRADA":
            nueva_cantidad = stock_actual + cantidad
            cantidad_movimiento = cantidad

        elif tipo_movimiento == "SALIDA":
            if cantidad > stock_actual:
                conexion.close()
                flash("No hay suficiente stock para registrar esa salida.", "warning")
                return render_template("nuevo_movimiento_inventario.html", item=item)

            nueva_cantidad = stock_actual - cantidad
            cantidad_movimiento = -cantidad

        else:  # AJUSTE
            # En ajuste, el usuario pondrá el cambio: por ejemplo 2 o -1
            # Para permitir negativos en ajuste, lo leemos aparte
            ajuste_texto = limpiar_texto(request.form["cantidad"])
            try:
                cantidad_movimiento = int(ajuste_texto)
            except ValueError:
                conexion.close()
                flash("La cantidad del ajuste debe ser numérica.", "warning")
                return render_template("nuevo_movimiento_inventario.html", item=item)

            if cantidad_movimiento == 0:
                conexion.close()
                flash("El ajuste no puede ser cero.", "warning")
                return render_template("nuevo_movimiento_inventario.html", item=item)

            nueva_cantidad = stock_actual + cantidad_movimiento

            if nueva_cantidad < 0:
                conexion.close()
                flash("El ajuste dejaría el stock en negativo.", "warning")
                return render_template("nuevo_movimiento_inventario.html", item=item)

        cursor.execute("""
            INSERT INTO movimientos_inventario (
                id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia, observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            id_item, fecha_movimiento, tipo_movimiento, cantidad_movimiento, motivo, referencia, observaciones
        ))

        cursor.execute("""
            UPDATE inventario
            SET cantidad = ?
            WHERE id_item = ?
        """, (nueva_cantidad, id_item))

        conexion.commit()
        conexion.close()

        flash("Movimiento registrado correctamente.", "success")
        return redirect(url_for("ver_movimientos_inventario", id_item=id_item))

    conexion.close()
    return render_template("nuevo_movimiento_inventario.html", item=item)


if __name__ == "__main__":
    app.run(debug=True)
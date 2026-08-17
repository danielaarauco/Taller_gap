import os
import unicodedata
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, make_response, flash, session, jsonify
from xhtml2pdf import pisa
from io import BytesIO
import sqlite3
import re
from datetime import date
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash



def link_callback(uri, rel):
    ruta_static = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    ruta = os.path.join(ruta_static, uri.replace("/static/", ""))
    return ruta

app = Flask(__name__)
app.secret_key = "clave_super_secreta_taller_2026"


def _sin_acentos(texto):
    """Normaliza texto para comparar ignorando acentos y mayúsculas
    (para que buscar "jose" encuentre "José", por ejemplo)."""
    if texto is None:
        return texto
    texto = str(texto)
    sin_tildes = "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caracter)
    )
    return sin_tildes.lower()


def conectar_db():
    conexion = sqlite3.connect("taller.db")
    conexion.row_factory = sqlite3.Row
    conexion.create_function("SIN_ACENTOS", 1, _sin_acentos)
    return conexion


@app.template_global()
def url_sin_filtro(*claves):
    """URL de la página actual quitando los parámetros de filtro indicados
    (para el botón 'x' de cada chip de filtro activo)."""
    args = request.args.to_dict(flat=True)
    for clave in claves:
        args.pop(clave, None)
    return url_for(request.endpoint, **args)


@app.template_global()
def url_sin_filtros():
    """URL de la página actual sin ningún filtro (para 'Limpiar todo')."""
    return url_for(request.endpoint)


@app.template_global()
def link_whatsapp(telefono, mensaje):
    """Arma el link de WhatsApp (wa.me) para escribirle a un cliente: el
    teléfono se normaliza al formato internacional de Bolivia (+591) y el
    mensaje va precargado. WhatsApp no permite adjuntar archivos por
    link, así que esto solo prepara el texto — el PDF se comparte aparte."""
    numero = "".join(caracter for caracter in str(telefono or "") if caracter.isdigit())

    if not numero:
        return None

    if not numero.startswith("591"):
        numero = "591" + numero

    return f"https://wa.me/{numero}?text={quote(mensaje)}"


@app.template_filter("moneda")
def formato_moneda(valor):
    """Formatea un número como moneda: Bs 1,234.56 (para que se vea igual
    en toda la app, en vez de floats crudos de Python)."""
    try:
        numero = float(valor) if valor is not None else 0.0
    except (TypeError, ValueError):
        numero = 0.0
    return f"Bs {numero:,.2f}"


@app.template_filter("fecha_es")
def formato_fecha(valor):
    """Convierte una fecha guardada como AAAA-MM-DD a DD/MM/AAAA. Si no
    tiene ese formato (o está vacía), la devuelve tal cual."""
    if not valor:
        return ""
    try:
        return date.fromisoformat(str(valor)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return valor
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


def _guardar_items_proforma(cursor, id_proforma):
    """Guarda los ítems (repuestos de inventario, repuestos externos y
    mano de obra) que se arman en la misma pantalla al crear una
    proforma. Usa el mismo cursor/transacción de quien la llama (no hace
    commit acá). Devuelve una lista de mensajes de error: si viene vacía,
    todos los ítems se guardaron bien."""
    modos = request.form.getlist("item_modo")
    ids_item = request.form.getlist("item_id_item")
    descripciones = request.form.getlist("item_descripcion")
    cantidades = request.form.getlist("item_cantidad")
    precios = request.form.getlist("item_precio_unitario")

    errores = []

    for indice, modo in enumerate(modos):
        modo = modo.strip()
        if not modo:
            continue

        numero_item = indice + 1
        cantidad_texto = cantidades[indice].strip() if indice < len(cantidades) else ""

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            errores.append(f"Ítem #{numero_item}: la cantidad no es válida.")
            continue

        if cantidad <= 0:
            errores.append(f"Ítem #{numero_item}: la cantidad debe ser mayor a cero.")
            continue

        id_item = None

        if modo == "inventario":
            id_item_texto = ids_item[indice].strip() if indice < len(ids_item) else ""

            if not id_item_texto:
                errores.append(f"Ítem #{numero_item}: falta seleccionar el repuesto del inventario.")
                continue

            try:
                id_item = int(id_item_texto)
            except ValueError:
                errores.append(f"Ítem #{numero_item}: repuesto de inventario inválido.")
                continue

            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item_inventario = cursor.fetchone()

            if item_inventario is None:
                errores.append(f"Ítem #{numero_item}: el repuesto seleccionado ya no existe en inventario.")
                continue

            if cantidad > item_inventario["cantidad"]:
                errores.append(
                    f"Ítem #{numero_item}: stock insuficiente de \"{item_inventario['descripcion']}\" "
                    f"(disponible: {item_inventario['cantidad']})."
                )
                continue

            tipo_item = "REPUESTO"
            descripcion = item_inventario["descripcion"]
            precio_unitario = item_inventario["precio_venta"] or 0

        elif modo in ("externo", "mano_obra"):
            descripcion = limpiar_texto(descripciones[indice]).upper() if indice < len(descripciones) else ""
            precio_texto = precios[indice].strip() if indice < len(precios) else ""

            if not descripcion:
                errores.append(f"Ítem #{numero_item}: falta la descripción.")
                continue

            try:
                precio_unitario = float(precio_texto)
            except ValueError:
                errores.append(f"Ítem #{numero_item}: el precio unitario no es válido.")
                continue

            if precio_unitario < 0:
                errores.append(f"Ítem #{numero_item}: el precio unitario no puede ser negativo.")
                continue

            tipo_item = "MANO_OBRA" if modo == "mano_obra" else "REPUESTO"

        else:
            errores.append(f"Ítem #{numero_item}: tipo de ítem inválido.")
            continue

        subtotal = cantidad * precio_unitario

        cursor.execute("""
            INSERT INTO detalle_proforma (
                id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal, id_item
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal, id_item))

    return errores
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


##################
def login_requerido(f):
    @wraps(f)
    def funcion_protegida(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Debes iniciar sesión para acceder al sistema.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return funcion_protegida


def roles_requeridos(*roles_permitidos):
    def decorador(f):
        @wraps(f)
        def funcion_protegida(*args, **kwargs):
            if "usuario_id" not in session:
                flash("Debes iniciar sesión.", "warning")
                return redirect(url_for("login"))

            rol_usuario = session.get("rol")
            if rol_usuario not in roles_permitidos:
                flash("No tienes permiso para acceder a esta sección.", "danger")
                return redirect(url_for("inicio"))

            return f(*args, **kwargs)
        return funcion_protegida
    return decorador



#################
#LOGIN
@app.route("/")
@login_requerido
def inicio():
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM proformas
        WHERE activo = 1 AND pago = 'Pendiente'
    """)
    proformas_pendientes_pago = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM ingresos
        WHERE estado != 'Entregado'
    """)
    vehiculos_en_taller = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM inventario WHERE cantidad = 0")
    items_agotados = cursor.fetchone()[0]

    mes_actual = date.today().strftime("%Y-%m")
    cursor.execute("""
        SELECT COALESCE(SUM(monto_recibido), 0), COUNT(*) FROM recibos
        WHERE substr(fecha, 1, 7) = ?
    """, (mes_actual,))
    fila_recibos_mes = cursor.fetchone()
    monto_recibido_mes = fila_recibos_mes[0]
    cantidad_recibos_mes = fila_recibos_mes[1]

    conexion.close()

    return render_template(
        "index.html",
        proformas_pendientes_pago=proformas_pendientes_pago,
        vehiculos_en_taller=vehiculos_en_taller,
        items_agotados=items_agotados,
        cantidad_recibos_mes=cantidad_recibos_mes,
        monto_recibido_mes=monto_recibido_mes
    )


#PAPELERA (clientes, vehículos y proformas eliminados, para restaurar o borrar definitivamente)
@app.route("/papelera")
@login_requerido
@roles_requeridos("ADMIN")
def papelera():
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM clientes WHERE activo = 0 ORDER BY id_cliente DESC")
    clientes = cursor.fetchall()

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        LEFT JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE v.activo = 0
        ORDER BY v.id_vehiculo DESC
    """)
    vehiculos = cursor.fetchall()

    cursor.execute("""
        SELECT p.*, c.nombre_completo, v.placa
        FROM proformas p
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        LEFT JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE p.activo = 0
        ORDER BY p.id_proforma DESC
    """)
    proformas = cursor.fetchall()

    conexion.close()

    return render_template(
        "papelera.html",
        clientes=clientes,
        vehiculos=vehiculos,
        proformas=proformas
    )


#BUSQUEDA GLOBAL (Ctrl+K): busca en clientes, vehículos, proformas e inventario a la vez
@app.route("/buscar-global")
@login_requerido
def buscar_global():
    consulta = request.args.get("q", "").strip()

    if len(consulta) < 2:
        return jsonify({"resultados": []})

    conexion = conectar_db()
    cursor = conexion.cursor()
    patron = f"%{consulta}%"
    resultados = []

    cursor.execute("""
        SELECT id_cliente, nombre_completo, telefono, ci_nit
        FROM clientes
        WHERE activo = 1 AND (
            SIN_ACENTOS(nombre_completo) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(ci_nit) LIKE SIN_ACENTOS(?)
            OR telefono LIKE ?
        )
        ORDER BY nombre_completo ASC
        LIMIT 6
    """, (patron, patron, patron))
    for fila in cursor.fetchall():
        resultados.append({
            "tipo": "Cliente",
            "etiqueta": fila["nombre_completo"],
            "subtitulo": fila["telefono"] or fila["ci_nit"] or "",
            "url": url_for("editar_cliente", id_cliente=fila["id_cliente"])
        })

    cursor.execute("""
        SELECT v.id_vehiculo, v.placa, v.marca, v.modelo, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE v.activo = 1 AND (
            SIN_ACENTOS(v.placa) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(v.vin) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(v.marca) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(v.modelo) LIKE SIN_ACENTOS(?)
        )
        ORDER BY v.placa ASC
        LIMIT 6
    """, (patron, patron, patron, patron))
    for fila in cursor.fetchall():
        resultados.append({
            "tipo": "Vehículo",
            "etiqueta": f"{fila['placa']} - {fila['marca']} {fila['modelo']}",
            "subtitulo": fila["nombre_completo"] or "",
            "url": url_for("historial_vehiculo", id_vehiculo=fila["id_vehiculo"])
        })

    cursor.execute("""
        SELECT p.id_proforma, p.numero_proforma, p.tipo_proforma, c.nombre_completo, p.nombre_cliente_manual
        FROM proformas p
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        WHERE p.activo = 1 AND (
            SIN_ACENTOS(p.numero_proforma) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(c.nombre_completo) LIKE SIN_ACENTOS(?)
            OR SIN_ACENTOS(p.nombre_cliente_manual) LIKE SIN_ACENTOS(?)
        )
        ORDER BY p.id_proforma DESC
        LIMIT 6
    """, (patron, patron, patron))
    for fila in cursor.fetchall():
        nombre = fila["nombre_completo"] if fila["tipo_proforma"] == "FORMAL" else fila["nombre_cliente_manual"]
        resultados.append({
            "tipo": "Proforma",
            "etiqueta": fila["numero_proforma"],
            "subtitulo": nombre or "",
            "url": url_for("ver_proforma", id_proforma=fila["id_proforma"])
        })

    cursor.execute("""
        SELECT id_item, descripcion, marca, categoria
        FROM inventario
        WHERE SIN_ACENTOS(descripcion) LIKE SIN_ACENTOS(?) OR SIN_ACENTOS(marca) LIKE SIN_ACENTOS(?)
        ORDER BY descripcion ASC
        LIMIT 6
    """, (patron, patron))
    for fila in cursor.fetchall():
        resultados.append({
            "tipo": "Inventario",
            "etiqueta": fila["descripcion"],
            "subtitulo": fila["marca"] or fila["categoria"] or "",
            "url": url_for("editar_item_inventario", id_item=fila["id_item"])
        })

    conexion.close()

    return jsonify({"resultados": resultados})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre_usuario = request.form["nombre_usuario"].strip()
        password = request.form["password"]

        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("""
            SELECT *
            FROM usuarios
            WHERE nombre_usuario = ? AND activo = 1
        """, (nombre_usuario,))
        usuario = cursor.fetchone()
        conexion.close()

        if usuario and check_password_hash(usuario["password_hash"], password):
            session["usuario_id"] = usuario["id_usuario"]
            session["nombre_usuario"] = usuario["nombre_usuario"]
            session["nombre_completo"] = usuario["nombre_completo"]
            session["rol"] = usuario["rol"]

            flash("Inicio de sesión correcto.", "success")
            return redirect(url_for("inicio"))

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("login"))

#CAMBIAR CONTRASEÑA
@app.route("/cambiar-password", methods=["GET", "POST"])
@login_requerido
def cambiar_password():
    if request.method == "POST":
        password_actual = request.form["password_actual"]
        password_nueva = request.form["password_nueva"]
        password_confirmacion = request.form["password_confirmacion"]

        if not password_actual or not password_nueva or not password_confirmacion:
            flash("Todos los campos son obligatorios.", "warning")
            return render_template("cambiar_password.html")

        if password_nueva != password_confirmacion:
            flash("La nueva contraseña y la confirmación no coinciden.", "warning")
            return render_template("cambiar_password.html")

        if len(password_nueva) < 6:
            flash("La nueva contraseña debe tener al menos 6 caracteres.", "warning")
            return render_template("cambiar_password.html")

        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE id_usuario = ?", (session["usuario_id"],))
        usuario = cursor.fetchone()

        if not usuario or not check_password_hash(usuario["password_hash"], password_actual):
            conexion.close()
            flash("La contraseña actual es incorrecta.", "danger")
            return render_template("cambiar_password.html")

        nuevo_hash = generate_password_hash(password_nueva)

        cursor.execute("""
            UPDATE usuarios
            SET password_hash = ?
            WHERE id_usuario = ?
        """, (nuevo_hash, session["usuario_id"]))

        conexion.commit()
        conexion.close()

        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("inicio"))

    return render_template("cambiar_password.html")

#NUEVO USUARIO
@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_requerido
@roles_requeridos("ADMIN")
def nuevo_usuario():
    if request.method == "POST":
        nombre_usuario = request.form["nombre_usuario"].strip()
        nombre_completo = request.form["nombre_completo"].strip()
        password = request.form["password"]
        rol = request.form["rol"].strip().upper()

        if not nombre_usuario or not password or not rol:
            flash("Usuario, contraseña y rol son obligatorios.", "warning")
            return render_template("nuevo_usuario.html")

        if rol not in ["ADMIN", "TRABAJADOR"]:
            flash("Rol inválido.", "warning")
            return render_template("nuevo_usuario.html")

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "warning")
            return render_template("nuevo_usuario.html")

        password_hash = generate_password_hash(password)

        conexion = conectar_db()
        cursor = conexion.cursor()

        try:
            cursor.execute("""
                INSERT INTO usuarios (nombre_usuario, password_hash, nombre_completo, rol, activo)
                VALUES (?, ?, ?, ?, 1)
            """, (nombre_usuario, password_hash, nombre_completo, rol))
            conexion.commit()
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("listar_usuarios"))
        except sqlite3.IntegrityError:
            flash("Ese nombre de usuario ya existe.", "warning")
            return render_template("nuevo_usuario.html")
        finally:
            conexion.close()

    return render_template("nuevo_usuario.html")



#RESETEAR CONTRASEÑA USUARIO
@app.route("/usuarios/<int:id_usuario>/resetear-password", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def resetear_password_usuario(id_usuario):
    nueva_password = "123456"

    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id_usuario = ?", (id_usuario,))
    usuario = cursor.fetchone()

    if not usuario:
        conexion.close()
        flash("El usuario no existe.", "warning")
        return redirect(url_for("listar_usuarios"))

    nuevo_hash = generate_password_hash(nueva_password)

    cursor.execute("""
        UPDATE usuarios
        SET password_hash = ?
        WHERE id_usuario = ?
    """, (nuevo_hash, id_usuario))

    conexion.commit()
    conexion.close()

    flash("Contraseña restablecida a 123456.", "success")
    return redirect(url_for("listar_usuarios"))

#EDITAR USUARIO
@app.route("/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
@login_requerido
@roles_requeridos("ADMIN")
def editar_usuario(id_usuario):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM usuarios WHERE id_usuario = ?", (id_usuario,))
    usuario = cursor.fetchone()

    if not usuario:
        conexion.close()
        flash("El usuario no existe.", "warning")
        return redirect(url_for("listar_usuarios"))

    if request.method == "POST":
        nombre_usuario = request.form["nombre_usuario"].strip()
        nombre_completo = request.form["nombre_completo"].strip()
        rol = request.form["rol"].strip().upper()
        activo = request.form["activo"]

        if not nombre_usuario or not rol:
            flash("Usuario y rol son obligatorios.", "warning")
            return render_template("editar_usuario.html", usuario=usuario)

        if rol not in ["ADMIN", "TRABAJADOR"]:
            flash("Rol inválido.", "warning")
            return render_template("editar_usuario.html", usuario=usuario)

        try:
            cursor.execute("""
                UPDATE usuarios
                SET nombre_usuario = ?, nombre_completo = ?, rol = ?, activo = ?
                WHERE id_usuario = ?
            """, (nombre_usuario, nombre_completo, rol, int(activo), id_usuario))
            conexion.commit()
            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("listar_usuarios"))
        except sqlite3.IntegrityError:
            flash("Ese nombre de usuario ya existe.", "warning")
            return render_template("editar_usuario.html", usuario=usuario)
        finally:
            conexion.close()

    conexion.close()
    return render_template("editar_usuario.html", usuario=usuario)
#LISTAR USUARIOS
@app.route("/usuarios")
@login_requerido
@roles_requeridos("ADMIN")
def listar_usuarios():
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM usuarios ORDER BY id_usuario DESC")
    usuarios = cursor.fetchall()

    conexion.close()
    return render_template("usuarios.html", usuarios=usuarios)

#REGISTRAR NUEVO CLIENTE
@app.route("/clientes/nuevo", methods=["GET", "POST"])
@login_requerido
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
@login_requerido
def listar_clientes():
    busqueda = request.args.get("busqueda", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    if busqueda:
        patron = f"%{busqueda}%"
        cursor.execute("""
            SELECT *
            FROM clientes
            WHERE activo = 1
            AND (SIN_ACENTOS(nombre_completo) LIKE SIN_ACENTOS(?) OR SIN_ACENTOS(ci_nit) LIKE SIN_ACENTOS(?))
            ORDER BY id_cliente DESC
        """, (patron, patron))
    else:
        cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY id_cliente DESC")

    clientes = cursor.fetchall()
    conexion.close()

    return render_template("clientes.html", clientes=clientes, busqueda=busqueda)


#REGISTRAR NUEVO VEHICULO
@app.route("/vehiculos/nuevo", methods=["GET", "POST"])
@login_requerido
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
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Debes seleccionar un cliente.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if not placa:
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("La placa es obligatoria.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if not marca or not modelo:
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("La marca y el modelo son obligatorios.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if vin and not es_vin_valido(vin):
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El VIN no tiene un formato válido.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if anio and (not anio.isdigit() or int(anio) < 1900 or int(anio) > 2100):
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El año no es válido.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        cursor.execute("SELECT id_vehiculo FROM vehiculos WHERE placa = ?", (placa,))
        vehiculo_existente = cursor.fetchone()
        if vehiculo_existente:
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Ya existe un vehículo registrado con esa placa.", "warning")
            return render_template("nuevo_vehiculo.html", clientes=clientes)

        if vin:
            cursor.execute("SELECT id_vehiculo FROM vehiculos WHERE vin = ?", (vin,))
            vin_existente = cursor.fetchone()
            if vin_existente:
                cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()
    conexion.close()

    return render_template("nuevo_vehiculo.html", clientes=clientes)

#LISTAR VEHICULOS REGISTRADOS
@app.route("/vehiculos")
@login_requerido
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
        WHERE v.activo = 1
    """
    parametros = []

    if busqueda:
        query += " AND (SIN_ACENTOS(v.placa) LIKE SIN_ACENTOS(?) OR SIN_ACENTOS(v.vin) LIKE SIN_ACENTOS(?))"
        patron = f"%{busqueda}%"
        parametros.extend([patron, patron])

    if id_cliente:
        query += " AND v.id_cliente = ?"
        parametros.append(id_cliente)

    if modelo:
        query += " AND SIN_ACENTOS(v.modelo) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{modelo}%")

    if tipo:
        query += " AND SIN_ACENTOS(v.tipo) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{tipo}%")

    if anio:
        query += " AND v.anio = ?"
        parametros.append(anio)

    if color:
        query += " AND SIN_ACENTOS(v.color) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{color}%")

    query += " ORDER BY v.id_vehiculo DESC"

    cursor.execute(query, parametros)
    vehiculos = cursor.fetchall()

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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
@login_requerido
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
                WHERE v.activo = 1
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
        WHERE v.activo = 1
        ORDER BY v.placa ASC
    """)
    vehiculos = cursor.fetchall()
    conexion.close()

    return render_template("nuevo_ingreso.html", vehiculos=vehiculos)

#LISTAR INGRESOS VEHICULOS
@app.route("/ingresos")
@login_requerido
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
        query += " AND SIN_ACENTOS(v.placa) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{placa}%")

    if id_cliente:
        query += " AND c.id_cliente = ?"
        parametros.append(id_cliente)

    if mecanico:
        query += " AND SIN_ACENTOS(i.mecanico_encargado) LIKE SIN_ACENTOS(?)"
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

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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
@login_requerido
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
@login_requerido
def nueva_proforma():
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT numero_proforma
        FROM proformas
        WHERE numero_proforma LIKE 'PF-%'
        ORDER BY id_proforma DESC
        LIMIT 1
    """)
    ultima_proforma = cursor.fetchone()

    if ultima_proforma and ultima_proforma["numero_proforma"]:
        ultimo_numero = ultima_proforma["numero_proforma"]
        partes = ultimo_numero.split("-")
        if len(partes) > 1 and partes[1].isdigit():
            ultimo_id = int(partes[1])
            nuevo_numero = f"PF-{ultimo_id + 1:04d}"
        else:
            nuevo_numero = "PF-0001"
    else:
        nuevo_numero = "PF-0001"

    def _formulario_con_datos():
        cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
        clientes = cursor.fetchall()

        cursor.execute("""
            SELECT v.*, c.nombre_completo
            FROM vehiculos v
            INNER JOIN clientes c ON v.id_cliente = c.id_cliente
            WHERE v.activo = 1
            ORDER BY v.id_vehiculo DESC
        """)
        vehiculos = cursor.fetchall()

        cursor.execute("SELECT * FROM inventario ORDER BY descripcion ASC")
        items_inventario = cursor.fetchall()

        conexion.close()

        return render_template(
            "nueva_proforma.html",
            clientes=clientes,
            vehiculos=vehiculos,
            items_inventario=items_inventario,
            nuevo_numero=nuevo_numero
        )

    if request.method == "POST":
        tipo_proforma = request.form["tipo_proforma"]
        fecha = request.form["fecha"]
        observaciones = limpiar_texto(request.form["observaciones"])

        if not fecha:
            flash("La fecha es obligatoria.", "warning")
            return _formulario_con_datos()

        if tipo_proforma == "FORMAL":
            id_cliente = request.form["id_cliente"]
            id_vehiculo = request.form["id_vehiculo"]

            if not id_cliente or not id_vehiculo:
                flash("En la proforma formal debes seleccionar cliente y vehículo.", "warning")
                return _formulario_con_datos()

            cursor.execute("""
                INSERT INTO proformas (
                    numero_proforma, id_cliente, id_vehiculo, fecha,
                    subtotal_repuestos, subtotal_mano_obra, total_general,
                    total_literal, observaciones, pago, tipo_proforma
                )
                VALUES (?, ?, ?, ?, 0, 0, 0, '', ?, 'Pendiente', 'FORMAL')
            """, (nuevo_numero, id_cliente, id_vehiculo, fecha, observaciones))

        else:
            nombre_cliente_manual = normalizar_nombre(request.form["nombre_cliente_manual"])
            telefono_manual = limpiar_texto(request.form["telefono_manual"])
            marca_manual = limpiar_texto(request.form["marca_manual"]).upper()
            modelo_manual = limpiar_texto(request.form["modelo_manual"]).upper()
            tipo_manual = limpiar_texto(request.form["tipo_manual"]).upper()
            placa_manual = normalizar_placa(request.form["placa_manual"])
            vin_manual = normalizar_vin(request.form["vin_manual"])

            if not nombre_cliente_manual:
                flash("En la proforma rápida debes ingresar al menos el nombre del cliente.", "warning")
                return _formulario_con_datos()

            cursor.execute("""
                INSERT INTO proformas (
                    numero_proforma, id_cliente, id_vehiculo, fecha,
                    subtotal_repuestos, subtotal_mano_obra, total_general,
                    total_literal, observaciones, pago, tipo_proforma,
                    nombre_cliente_manual, telefono_manual, marca_manual,
                    modelo_manual, tipo_manual, placa_manual, vin_manual
                )
                VALUES (?, NULL, NULL, ?, 0, 0, 0, '', ?, 'Pendiente', 'RAPIDA',
                        ?, ?, ?, ?, ?, ?, ?)
            """, (
                nuevo_numero, fecha, observaciones,
                nombre_cliente_manual, telefono_manual, marca_manual,
                modelo_manual, tipo_manual, placa_manual, vin_manual
            ))

        id_proforma = cursor.lastrowid

        # Repuestos y mano de obra que se hayan armado en la misma
        # pantalla. Si algo falla, se deshace TODO (ni la proforma queda
        # creada a medias) y se le muestra el detalle al usuario.
        errores_items = _guardar_items_proforma(cursor, id_proforma)

        if errores_items:
            conexion.rollback()
            for error in errores_items:
                flash(error, "warning")
            return _formulario_con_datos()

        conexion.commit()
        conexion.close()

        recalcular_totales_proforma(id_proforma)

        flash("Proforma registrada correctamente.", "success")
        return redirect(url_for("ver_proforma", id_proforma=id_proforma))

    return _formulario_con_datos()


#LISTAR PROFORMAS
@app.route("/proformas")
@login_requerido
def listar_proformas():
    id_cliente = request.args.get("id_cliente", "").strip()
    estado = request.args.get("estado", "").strip()
    pago = request.args.get("pago", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT
            p.*,
            c.nombre_completo,
            v.placa,
            v.marca,
            v.modelo
        FROM proformas p
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        LEFT JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE p.activo = 1
    """
    parametros = []

    if id_cliente:
        query += " AND p.id_cliente = ?"
        parametros.append(id_cliente)

    if estado:
        query += " AND p.estado = ?"
        parametros.append(estado)

    if pago:
        query += " AND p.pago = ?"
        parametros.append(pago)

    if fecha_desde:
        query += " AND p.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND p.fecha <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY p.id_proforma DESC"

    cursor.execute(query, parametros)
    proformas = cursor.fetchall()

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()

    return render_template(
        "proformas.html",
        proformas=proformas,
        clientes=clientes,
        id_cliente=id_cliente,
        estado=estado,
        pago=pago,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

#VER PROFORMA
@app.route("/proformas/<int:id_proforma>")
@login_requerido
def ver_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
    proforma = cursor.fetchone()

    if proforma["tipo_proforma"] == "FORMAL":
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
@login_requerido
def agregar_detalle_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
    proforma_actual = cursor.fetchone()

    if proforma_actual is None:
        conexion.close()
        flash("La proforma no existe.", "warning")
        return redirect(url_for("listar_proformas"))

    def _proforma_con_relaciones():
        if proforma_actual["tipo_proforma"] == "FORMAL":
            cursor.execute("""
                SELECT p.*, c.nombre_completo, v.placa, v.marca, v.modelo
                FROM proformas p
                INNER JOIN clientes c ON p.id_cliente = c.id_cliente
                INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
                WHERE p.id_proforma = ?
            """, (id_proforma,))
            return cursor.fetchone()
        return proforma_actual

    def _reintentar(mensaje):
        flash(mensaje, "warning")
        cursor.execute("SELECT * FROM inventario ORDER BY descripcion ASC")
        items_inventario = cursor.fetchall()
        proforma_render = _proforma_con_relaciones()
        conexion.close()
        return render_template(
            "agregar_detalle_proforma.html",
            proforma=proforma_render,
            items_inventario=items_inventario
        )

    if request.method == "POST":
        modo = request.form.get("modo", "").strip()
        cantidad_texto = limpiar_texto(request.form.get("cantidad", ""))

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            return _reintentar("La cantidad debe ser numérica.")

        if cantidad <= 0:
            return _reintentar("La cantidad debe ser mayor a cero.")

        id_item = None
        item_inventario = None

        if modo == "inventario":
            id_item_texto = request.form.get("id_item", "").strip()

            if not id_item_texto:
                return _reintentar("Selecciona un repuesto del inventario.")

            try:
                id_item = int(id_item_texto)
            except ValueError:
                return _reintentar("Repuesto de inventario inválido.")

            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item_inventario = cursor.fetchone()

            if item_inventario is None:
                return _reintentar("El repuesto seleccionado no existe en inventario.")

            if cantidad > item_inventario["cantidad"]:
                return _reintentar(f"Stock insuficiente. Disponible: {item_inventario['cantidad']}.")

            tipo_item = "REPUESTO"
            descripcion = item_inventario["descripcion"]
            precio_unitario = item_inventario["precio_venta"] or 0

        elif modo in ("externo", "mano_obra"):
            descripcion = limpiar_texto(request.form.get("descripcion", "")).upper()
            precio_unitario_texto = limpiar_texto(request.form.get("precio_unitario", ""))

            if not descripcion:
                return _reintentar("La descripción es obligatoria.")

            try:
                precio_unitario = float(precio_unitario_texto)
            except ValueError:
                return _reintentar("El precio unitario debe ser numérico.")

            if precio_unitario < 0:
                return _reintentar("El precio unitario no puede ser negativo.")

            tipo_item = "MANO_OBRA" if modo == "mano_obra" else "REPUESTO"

        else:
            return _reintentar("Selecciona un tipo de ítem válido.")

        subtotal = cantidad * precio_unitario

        cursor.execute("""
            INSERT INTO detalle_proforma (
                id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal, id_item
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (id_proforma, tipo_item, descripcion, cantidad, precio_unitario, subtotal, id_item))

        # El stock del repuesto de inventario recién se descuenta cuando se
        # emite el recibo (ahí se concreta la compra). Si la proforma ya
        # tiene el stock descontado (porque ya se emitió un recibo antes),
        # este nuevo repuesto también se descuenta de una vez.
        if modo == "inventario" and proforma_actual["stock_descontado"]:
            nuevo_stock = item_inventario["cantidad"] - cantidad
            cursor.execute("UPDATE inventario SET cantidad = ? WHERE id_item = ?", (nuevo_stock, id_item))
            cursor.execute("""
                INSERT INTO movimientos_inventario (
                    id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                )
                VALUES (?, ?, 'SALIDA', ?, ?, ?)
            """, (
                id_item,
                date.today().isoformat(),
                -cantidad,
                "Uso en proforma",
                proforma_actual["numero_proforma"]
            ))

        conexion.commit()
        conexion.close()

        recalcular_totales_proforma(id_proforma)

        flash("Detalle agregado correctamente.", "success")
        return redirect(url_for("ver_proforma", id_proforma=id_proforma))

    cursor.execute("SELECT * FROM inventario ORDER BY descripcion ASC")
    items_inventario = cursor.fetchall()

    proforma = _proforma_con_relaciones()

    conexion.close()

    return render_template(
        "agregar_detalle_proforma.html",
        proforma=proforma,
        items_inventario=items_inventario
    )

#EXPORTAR PROFORMA A PDF
@app.route("/proformas/<int:id_proforma>/pdf")
@login_requerido
def exportar_proforma_pdf(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
    proforma_base = cursor.fetchone()

    if proforma_base["tipo_proforma"] == "FORMAL":
        cursor.execute("""
            SELECT p.*, c.nombre_completo, c.telefono, v.placa, v.marca, v.modelo, v.tipo, v.vin
            FROM proformas p
            INNER JOIN clientes c ON p.id_cliente = c.id_cliente
            INNER JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
            WHERE p.id_proforma = ?
        """, (id_proforma,))
        proforma = cursor.fetchone()
    else:
        proforma = proforma_base

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
@login_requerido
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
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("Cliente, placa, marca y modelo son obligatorios.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        if vin and not es_vin_valido(vin):
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
            clientes = cursor.fetchall()
            conexion.close()
            flash("El VIN no tiene un formato válido.", "warning")
            return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

        if anio and (not anio.isdigit() or int(anio) < 1900 or int(anio) > 2100):
            cursor.execute("SELECT * FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
            vehiculo = cursor.fetchone()
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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
            cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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
                cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
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

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    conexion.close()
    return render_template("editar_vehiculo.html", vehiculo=vehiculo, clientes=clientes)

#ELIMINAR VEHICULO (baja lógica: se manda a la papelera, se puede restaurar)
@app.route("/vehiculos/<int:id_vehiculo>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_vehiculo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE vehiculos SET activo = 0 WHERE id_vehiculo = ?", (id_vehiculo,))
    conexion.commit()
    conexion.close()

    flash("Vehículo movido a la papelera. Podés restaurarlo desde ahí si fue un error.", "success")
    return redirect(url_for("listar_vehiculos"))

#RESTAURAR VEHICULO
@app.route("/vehiculos/<int:id_vehiculo>/restaurar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def restaurar_vehiculo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE vehiculos SET activo = 1 WHERE id_vehiculo = ?", (id_vehiculo,))
    conexion.commit()
    conexion.close()

    flash("Vehículo restaurado correctamente.", "success")
    return redirect(url_for("papelera"))

#ELIMINAR VEHICULO DEFINITIVAMENTE (desde la papelera, sin vuelta atrás)
@app.route("/vehiculos/<int:id_vehiculo>/eliminar-definitivo", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_vehiculo_definitivo(id_vehiculo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT COUNT(*) FROM ingresos WHERE id_vehiculo = ?", (id_vehiculo,))
    cantidad_ingresos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM proformas WHERE id_vehiculo = ?", (id_vehiculo,))
    cantidad_proformas = cursor.fetchone()[0]

    if cantidad_ingresos > 0 or cantidad_proformas > 0:
        conexion.close()
        flash("No se puede eliminar definitivamente: el vehículo tiene ingresos o proformas asociadas.", "warning")
        return redirect(url_for("papelera"))

    cursor.execute("DELETE FROM vehiculos WHERE id_vehiculo = ?", (id_vehiculo,))
    conexion.commit()
    conexion.close()

    flash("Vehículo eliminado definitivamente.", "success")
    return redirect(url_for("papelera"))

#ACCIONES CLIENTES
#editar cliente
@app.route("/clientes/<int:id_cliente>/editar", methods=["GET", "POST"])
@login_requerido
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

#eliminar cliente (baja lógica: se manda a la papelera, se puede restaurar)
@app.route("/clientes/<int:id_cliente>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_cliente(id_cliente):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE clientes SET activo = 0 WHERE id_cliente = ?", (id_cliente,))
    conexion.commit()
    conexion.close()

    flash("Cliente movido a la papelera. Podés restaurarlo desde ahí si fue un error.", "success")
    return redirect(url_for("listar_clientes"))

#restaurar cliente
@app.route("/clientes/<int:id_cliente>/restaurar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def restaurar_cliente(id_cliente):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE clientes SET activo = 1 WHERE id_cliente = ?", (id_cliente,))
    conexion.commit()
    conexion.close()

    flash("Cliente restaurado correctamente.", "success")
    return redirect(url_for("papelera"))

#eliminar cliente definitivamente (desde la papelera, sin vuelta atrás)
@app.route("/clientes/<int:id_cliente>/eliminar-definitivo", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_cliente_definitivo(id_cliente):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT COUNT(*) FROM vehiculos WHERE id_cliente = ?", (id_cliente,))
    cantidad_vehiculos = cursor.fetchone()[0]

    if cantidad_vehiculos > 0:
        conexion.close()
        flash("No se puede eliminar definitivamente: el cliente tiene vehículos asociados.", "warning")
        return redirect(url_for("papelera"))

    cursor.execute("DELETE FROM clientes WHERE id_cliente = ?", (id_cliente,))
    conexion.commit()
    conexion.close()

    flash("Cliente eliminado definitivamente.", "success")
    return redirect(url_for("papelera"))


#ACCIONES INGRESOS
#editar ingreso
@app.route("/ingresos/<int:id_ingreso>/editar", methods=["GET", "POST"])
@login_requerido
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
        WHERE v.activo = 1
        ORDER BY v.placa ASC
    """)
    vehiculos = cursor.fetchall()

    conexion.close()
    return render_template("editar_ingreso.html", ingreso=ingreso, vehiculos=vehiculos)
#eliminar ingreso
@app.route("/ingresos/<int:id_ingreso>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
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
@login_requerido
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

    cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre_completo ASC")
    clientes = cursor.fetchall()

    cursor.execute("""
        SELECT v.*, c.nombre_completo
        FROM vehiculos v
        INNER JOIN clientes c ON v.id_cliente = c.id_cliente
        WHERE v.activo = 1
        ORDER BY v.id_vehiculo DESC
    """)
    vehiculos = cursor.fetchall()

    conexion.close()

    return render_template("editar_proforma.html", proforma=proforma, clientes=clientes, vehiculos=vehiculos)

#eliminar proforma (baja lógica: se manda a la papelera, se puede restaurar)
@app.route("/proformas/<int:id_proforma>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE proformas SET activo = 0 WHERE id_proforma = ?", (id_proforma,))
    conexion.commit()
    conexion.close()

    flash("Proforma movida a la papelera. Podés restaurarla desde ahí si fue un error.", "success")

    return redirect(url_for("listar_proformas"))

#restaurar proforma
@app.route("/proformas/<int:id_proforma>/restaurar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def restaurar_proforma(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE proformas SET activo = 1 WHERE id_proforma = ?", (id_proforma,))
    conexion.commit()
    conexion.close()

    flash("Proforma restaurada correctamente.", "success")
    return redirect(url_for("papelera"))

#eliminar proforma definitivamente (desde la papelera, sin vuelta atrás)
@app.route("/proformas/<int:id_proforma>/eliminar-definitivo", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_proforma_definitivo(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT stock_descontado FROM proformas WHERE id_proforma = ?", (id_proforma,))
    fila_proforma = cursor.fetchone()

    if fila_proforma is None:
        conexion.close()
        flash("La proforma no existe.", "warning")
        return redirect(url_for("papelera"))

    stock_descontado = bool(fila_proforma["stock_descontado"])

    # Solo se repone el stock si ya se había descontado (es decir, si la
    # proforma ya tenía un recibo emitido). Si era solo una cotización, el
    # inventario nunca se llegó a mover.
    if stock_descontado:
        cursor.execute("""
            SELECT id_item, cantidad FROM detalle_proforma
            WHERE id_proforma = ? AND id_item IS NOT NULL
        """, (id_proforma,))
        repuestos_inventario = cursor.fetchall()

        for repuesto in repuestos_inventario:
            cursor.execute("UPDATE inventario SET cantidad = cantidad + ? WHERE id_item = ?",
                           (repuesto["cantidad"], repuesto["id_item"]))
            cursor.execute("""
                INSERT INTO movimientos_inventario (
                    id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                )
                VALUES (?, ?, 'ENTRADA', ?, ?, ?)
            """, (
                repuesto["id_item"],
                date.today().isoformat(),
                repuesto["cantidad"],
                "Reverso por eliminación definitiva de proforma",
                str(id_proforma)
            ))

    cursor.execute("DELETE FROM recibos WHERE id_proforma = ?", (id_proforma,))
    cursor.execute("DELETE FROM detalle_proforma WHERE id_proforma = ?", (id_proforma,))
    cursor.execute("DELETE FROM proformas WHERE id_proforma = ?", (id_proforma,))

    conexion.commit()
    conexion.close()

    flash("Proforma eliminada definitivamente.", "success")

    return redirect(url_for("papelera"))

#ACCIONES DETALLE PROFORMA
#editar detalle proforma
@app.route("/detalle-proforma/<int:id_detalle>/editar", methods=["GET", "POST"])
@login_requerido
def editar_detalle_proforma(id_detalle):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    detalle = cursor.fetchone()

    if detalle is None:
        conexion.close()
        flash("El detalle no existe.", "warning")
        return redirect(url_for("listar_proformas"))

    item_inventario = None
    if detalle["id_item"]:
        cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (detalle["id_item"],))
        item_inventario = cursor.fetchone()

    cursor.execute("SELECT stock_descontado FROM proformas WHERE id_proforma = ?", (detalle["id_proforma"],))
    fila_proforma = cursor.fetchone()
    stock_descontado = bool(fila_proforma["stock_descontado"]) if fila_proforma else False

    if request.method == "POST":
        cantidad_texto = limpiar_texto(request.form.get("cantidad", ""))
        precio_unitario_texto = limpiar_texto(request.form.get("precio_unitario", ""))

        try:
            cantidad = int(cantidad_texto)
        except ValueError:
            flash("La cantidad debe ser numérica.", "warning")
            conexion.close()
            return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

        if cantidad <= 0:
            flash("La cantidad debe ser mayor a cero.", "warning")
            conexion.close()
            return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

        try:
            precio_unitario = float(precio_unitario_texto)
        except ValueError:
            flash("El precio unitario debe ser numérico.", "warning")
            conexion.close()
            return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

        if precio_unitario < 0:
            flash("El precio unitario no puede ser negativo.", "warning")
            conexion.close()
            return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

        if item_inventario is not None:
            # Repuesto vinculado al inventario: la descripción se mantiene
            # ligada al ítem. El stock solo se toca acá si esta proforma ya
            # tiene el stock descontado (o sea, ya se emitió un recibo); si
            # todavía es solo una cotización, la cantidad se guarda pero el
            # inventario no se mueve hasta que se genere el recibo.
            if stock_descontado:
                delta = cantidad - detalle["cantidad"]

                if delta > item_inventario["cantidad"]:
                    flash(f"Stock insuficiente para este cambio. Disponible: {item_inventario['cantidad']}.", "warning")
                    conexion.close()
                    return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

                if delta != 0:
                    nuevo_stock = item_inventario["cantidad"] - delta
                    cursor.execute("UPDATE inventario SET cantidad = ? WHERE id_item = ?", (nuevo_stock, item_inventario["id_item"]))
                    cursor.execute("""
                        INSERT INTO movimientos_inventario (
                            id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                        )
                        VALUES (?, ?, 'AJUSTE', ?, ?, ?)
                    """, (
                        item_inventario["id_item"],
                        date.today().isoformat(),
                        -delta,
                        "Ajuste por edición de detalle de proforma",
                        str(detalle["id_proforma"])
                    ))
            elif cantidad > item_inventario["cantidad"]:
                flash(f"Stock insuficiente. Disponible: {item_inventario['cantidad']}.", "warning")
                conexion.close()
                return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

            tipo_item = "REPUESTO"
            descripcion = item_inventario["descripcion"]
        else:
            descripcion = limpiar_texto(request.form.get("descripcion", "")).upper()

            if not descripcion:
                flash("La descripción es obligatoria.", "warning")
                conexion.close()
                return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

            tipo_item = request.form.get("tipo_item", detalle["tipo_item"])
            if tipo_item not in ("REPUESTO", "MANO_OBRA"):
                tipo_item = detalle["tipo_item"]

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
    return render_template("editar_detalle_proforma.html", detalle=detalle, item_inventario=item_inventario)

#eliminar detalle proforma
@app.route("/detalle-proforma/<int:id_detalle>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_detalle_proforma(id_detalle):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    detalle = cursor.fetchone()

    if detalle is None:
        conexion.close()
        return redirect(url_for("listar_proformas"))

    id_proforma = detalle["id_proforma"]

    cursor.execute("SELECT stock_descontado FROM proformas WHERE id_proforma = ?", (id_proforma,))
    fila_proforma = cursor.fetchone()
    stock_descontado = bool(fila_proforma["stock_descontado"]) if fila_proforma else False

    # Solo se repone el stock si ya se había descontado (o sea, si ya se
    # emitió un recibo para esta proforma). Si todavía es una cotización,
    # el inventario nunca se tocó.
    if detalle["id_item"] and stock_descontado:
        cursor.execute("UPDATE inventario SET cantidad = cantidad + ? WHERE id_item = ?",
                       (detalle["cantidad"], detalle["id_item"]))
        cursor.execute("""
            INSERT INTO movimientos_inventario (
                id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
            )
            VALUES (?, ?, 'ENTRADA', ?, ?, ?)
        """, (
            detalle["id_item"],
            date.today().isoformat(),
            detalle["cantidad"],
            "Reverso por eliminación de detalle de proforma",
            str(id_proforma)
        ))

    cursor.execute("DELETE FROM detalle_proforma WHERE id_detalle = ?", (id_detalle,))
    conexion.commit()
    conexion.close()

    recalcular_totales_proforma(id_proforma)
    flash("Detalle de proforma eliminado correctamente.", "success")
    return redirect(url_for("ver_proforma", id_proforma=id_proforma))


#INVENTARIO
#LISTAR INVENTARIO
@app.route("/inventario")
@login_requerido
def listar_inventario():
    busqueda = request.args.get("busqueda", "").strip()
    categoria = request.args.get("categoria", "").strip()
    marca = request.args.get("marca", "").strip()
    estado = request.args.get("estado", "").strip()
    disponibilidad = request.args.get("disponibilidad", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT *
        FROM inventario
        WHERE 1=1
    """
    parametros = []

    if busqueda:
        query += " AND SIN_ACENTOS(descripcion) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{busqueda}%")

    if categoria:
        query += " AND SIN_ACENTOS(categoria) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{categoria}%")

    if marca:
        query += " AND SIN_ACENTOS(marca) LIKE SIN_ACENTOS(?)"
        parametros.append(f"%{marca}%")

    if estado:
        query += " AND estado = ?"
        parametros.append(estado)

    if disponibilidad == "disponible":
        query += " AND cantidad > 0"
    elif disponibilidad == "agotado":
        query += " AND cantidad = 0"

    query += " ORDER BY id_item DESC"

    cursor.execute(query, parametros)
    items = cursor.fetchall()

    conexion.close()

    return render_template(
        "inventario.html",
        items=items,
        busqueda=busqueda,
        categoria=categoria,
        marca=marca,
        estado=estado,
        disponibilidad=disponibilidad
    )
#Nuevo item inventario
@app.route("/inventario/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo_item_inventario():
    if request.method == "POST":
        descripcion = limpiar_texto(request.form["descripcion"]).upper()
        cantidad_texto = limpiar_texto(request.form["cantidad"])
        unidad_medida = limpiar_texto(request.form["unidad_medida"]).upper()
        estado = limpiar_texto(request.form["estado"]).capitalize()
        categoria = limpiar_texto(request.form["categoria"]).upper()
        marca = limpiar_texto(request.form["marca"]).upper()
        precio_compra_texto = limpiar_texto(request.form.get("precio_compra", ""))
        precio_venta_texto = limpiar_texto(request.form.get("precio_venta", ""))

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

        try:
            precio_compra = float(precio_compra_texto) if precio_compra_texto else 0
            precio_venta = float(precio_venta_texto) if precio_venta_texto else 0
        except ValueError:
            flash("El precio de compra y el precio de venta deben ser numéricos.", "warning")
            return render_template("nuevo_item.html")

        if precio_compra < 0 or precio_venta < 0:
            flash("Los precios no pueden ser negativos.", "warning")
            return render_template("nuevo_item.html")

        conexion = conectar_db()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO inventario (descripcion, cantidad, unidad_medida, estado, categoria, marca, precio_compra, precio_venta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (descripcion, cantidad, unidad_medida, estado, categoria, marca, precio_compra, precio_venta))

        conexion.commit()
        conexion.close()

        flash("Ítem registrado correctamente en inventario.", "success")
        return redirect(url_for("listar_inventario"))

    return render_template("nuevo_item.html")
#Acciones inventario
@app.route("/inventario/<int:id_item>/editar", methods=["GET", "POST"])
@login_requerido
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
        precio_compra_texto = limpiar_texto(request.form.get("precio_compra", ""))
        precio_venta_texto = limpiar_texto(request.form.get("precio_venta", ""))

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

        try:
            precio_compra = float(precio_compra_texto) if precio_compra_texto else 0
            precio_venta = float(precio_venta_texto) if precio_venta_texto else 0
        except ValueError:
            flash("El precio de compra y el precio de venta deben ser numéricos.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        if precio_compra < 0 or precio_venta < 0:
            flash("Los precios no pueden ser negativos.", "warning")
            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item = cursor.fetchone()
            conexion.close()
            return render_template("editar_item.html", item=item)

        cursor.execute("""
            UPDATE inventario
            SET descripcion = ?, cantidad = ?, unidad_medida = ?, estado = ?, categoria = ?, marca = ?, precio_compra = ?, precio_venta = ?
            WHERE id_item = ?
        """, (descripcion, cantidad, unidad_medida, estado, categoria, marca, precio_compra, precio_venta, id_item))

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
@login_requerido
@roles_requeridos("ADMIN")
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
@login_requerido
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
@login_requerido
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


#################
#GASTOS (compras de repuestos y otros gastos del taller, para el reporte de caja)
CATEGORIAS_GASTO = ["Compra de repuestos", "Sueldos", "Alquiler", "Servicios", "Otro"]

#LISTAR GASTOS
@app.route("/gastos")
@login_requerido
@roles_requeridos("ADMIN")
def listar_gastos():
    categoria = request.args.get("categoria", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT g.*, i.descripcion AS descripcion_item
        FROM gastos g
        LEFT JOIN inventario i ON g.id_item = i.id_item
        WHERE 1=1
    """
    parametros = []

    if categoria:
        query += " AND g.categoria = ?"
        parametros.append(categoria)

    if fecha_desde:
        query += " AND g.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND g.fecha <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY g.fecha DESC, g.id_gasto DESC"

    cursor.execute(query, parametros)
    gastos = cursor.fetchall()

    conexion.close()

    return render_template(
        "gastos.html",
        gastos=gastos,
        categorias=CATEGORIAS_GASTO,
        categoria=categoria,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

#NUEVO GASTO
@app.route("/gastos/nuevo", methods=["GET", "POST"])
@login_requerido
@roles_requeridos("ADMIN")
def nuevo_gasto():
    conexion = conectar_db()
    cursor = conexion.cursor()

    def _formulario_gasto():
        cursor.execute("SELECT * FROM inventario ORDER BY descripcion ASC")
        items_inventario = cursor.fetchall()
        conexion.close()
        return render_template("nuevo_gasto.html", categorias=CATEGORIAS_GASTO, items_inventario=items_inventario)

    if request.method == "POST":
        fecha = request.form.get("fecha", "").strip()
        categoria = request.form.get("categoria", "").strip()
        descripcion = limpiar_texto(request.form.get("descripcion", ""))
        monto_texto = limpiar_texto(request.form.get("monto", ""))

        if not fecha or categoria not in CATEGORIAS_GASTO:
            flash("Completá la fecha y elegí una categoría válida.", "warning")
            return _formulario_gasto()

        try:
            monto = float(monto_texto)
        except ValueError:
            flash("El monto no es válido.", "warning")
            return _formulario_gasto()

        if monto <= 0:
            flash("El monto debe ser mayor a cero.", "warning")
            return _formulario_gasto()

        id_item = None
        cantidad = None

        if categoria == "Compra de repuestos":
            id_item_texto = request.form.get("id_item", "").strip()
            cantidad_texto = limpiar_texto(request.form.get("cantidad", ""))

            if not id_item_texto:
                flash("Elegí qué repuesto compraste.", "warning")
                return _formulario_gasto()

            try:
                id_item = int(id_item_texto)
                cantidad = int(cantidad_texto)
            except ValueError:
                flash("La cantidad no es válida.", "warning")
                return _formulario_gasto()

            if cantidad <= 0:
                flash("La cantidad debe ser mayor a cero.", "warning")
                return _formulario_gasto()

            cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (id_item,))
            item_inventario = cursor.fetchone()

            if item_inventario is None:
                flash("El repuesto seleccionado ya no existe.", "warning")
                return _formulario_gasto()
        else:
            descripcion = descripcion or categoria
            if not descripcion:
                flash("Escribí una breve descripción del gasto.", "warning")
                return _formulario_gasto()

        cursor.execute("""
            INSERT INTO gastos (fecha, categoria, descripcion, monto, id_item, cantidad)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fecha, categoria, descripcion, monto, id_item, cantidad))
        id_gasto = cursor.lastrowid

        # Si es compra de repuestos, esto además repone el stock y
        # actualiza el precio de compra del ítem con el costo real pagado.
        if categoria == "Compra de repuestos":
            nuevo_stock = item_inventario["cantidad"] + cantidad
            costo_unitario = round(monto / cantidad, 2)

            cursor.execute("UPDATE inventario SET cantidad = ?, precio_compra = ? WHERE id_item = ?",
                           (nuevo_stock, costo_unitario, id_item))
            cursor.execute("""
                INSERT INTO movimientos_inventario (
                    id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                )
                VALUES (?, ?, 'ENTRADA', ?, ?, ?)
            """, (id_item, fecha, cantidad, "Compra de repuestos (gasto registrado)", f"Gasto #{id_gasto}"))

        conexion.commit()
        conexion.close()

        flash("Gasto registrado correctamente.", "success")
        return redirect(url_for("listar_gastos"))

    return _formulario_gasto()

#EDITAR GASTO
@app.route("/gastos/<int:id_gasto>/editar", methods=["GET", "POST"])
@login_requerido
@roles_requeridos("ADMIN")
def editar_gasto(id_gasto):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT g.*, i.descripcion AS descripcion_item
        FROM gastos g
        LEFT JOIN inventario i ON g.id_item = i.id_item
        WHERE g.id_gasto = ?
    """, (id_gasto,))
    gasto = cursor.fetchone()

    if gasto is None:
        conexion.close()
        flash("El gasto no existe.", "warning")
        return redirect(url_for("listar_gastos"))

    if request.method == "POST":
        fecha = request.form.get("fecha", "").strip()
        descripcion = limpiar_texto(request.form.get("descripcion", ""))
        monto_texto = limpiar_texto(request.form.get("monto", ""))

        if not fecha:
            flash("La fecha es obligatoria.", "warning")
            conexion.close()
            return render_template("editar_gasto.html", gasto=gasto)

        try:
            monto = float(monto_texto)
        except ValueError:
            flash("El monto no es válido.", "warning")
            conexion.close()
            return render_template("editar_gasto.html", gasto=gasto)

        if monto <= 0:
            flash("El monto debe ser mayor a cero.", "warning")
            conexion.close()
            return render_template("editar_gasto.html", gasto=gasto)

        cursor.execute("""
            UPDATE gastos SET fecha = ?, descripcion = ?, monto = ? WHERE id_gasto = ?
        """, (fecha, descripcion, monto, id_gasto))

        conexion.commit()
        conexion.close()

        flash("Gasto actualizado correctamente.", "success")
        return redirect(url_for("listar_gastos"))

    conexion.close()
    return render_template("editar_gasto.html", gasto=gasto)

#ELIMINAR GASTO
@app.route("/gastos/<int:id_gasto>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_gasto(id_gasto):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM gastos WHERE id_gasto = ?", (id_gasto,))
    gasto = cursor.fetchone()

    if gasto is None:
        conexion.close()
        flash("El gasto no existe.", "warning")
        return redirect(url_for("listar_gastos"))

    # Si era una compra de repuestos, hay que devolver el stock que había
    # sumado (a menos que ya se haya usado, en cuyo caso no se puede).
    if gasto["categoria"] == "Compra de repuestos" and gasto["id_item"] and gasto["cantidad"]:
        cursor.execute("SELECT * FROM inventario WHERE id_item = ?", (gasto["id_item"],))
        item_inventario = cursor.fetchone()

        if item_inventario is not None:
            if item_inventario["cantidad"] < gasto["cantidad"]:
                conexion.close()
                flash("No se puede eliminar: parte de ese stock ya se usó, el inventario quedaría negativo.", "warning")
                return redirect(url_for("listar_gastos"))

            cursor.execute("UPDATE inventario SET cantidad = cantidad - ? WHERE id_item = ?",
                           (gasto["cantidad"], gasto["id_item"]))
            cursor.execute("""
                INSERT INTO movimientos_inventario (
                    id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                )
                VALUES (?, ?, 'AJUSTE', ?, ?, ?)
            """, (
                gasto["id_item"], date.today().isoformat(), -gasto["cantidad"],
                "Reverso por eliminación de gasto de compra", f"Gasto #{id_gasto}"
            ))

    cursor.execute("DELETE FROM gastos WHERE id_gasto = ?", (id_gasto,))
    conexion.commit()
    conexion.close()

    flash("Gasto eliminado correctamente.", "success")
    return redirect(url_for("listar_gastos"))


#################
#REPORTES

def _rango_fechas_por_defecto():
    """Si no se especifica un rango, usa el mes actual (del día 1 a hoy)."""
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    if not fecha_desde and not fecha_hasta:
        hoy = date.today()
        fecha_desde = hoy.replace(day=1).isoformat()
        fecha_hasta = hoy.isoformat()

    return fecha_desde, fecha_hasta

def _datos_reporte_caja(fecha_desde, fecha_hasta):
    """Trae las entradas (recibos) y salidas (gastos) de un período, ya
    con los totales calculados. La usan tanto la pantalla del reporte de
    caja como su exportación a PDF, para no duplicar la consulta."""
    conexion = conectar_db()
    cursor = conexion.cursor()

    query_entradas = """
        SELECT r.id_recibo, r.numero_recibo, r.fecha, r.monto_recibido, r.concepto,
               p.numero_proforma, p.tipo_proforma, c.nombre_completo, p.nombre_cliente_manual
        FROM recibos r
        INNER JOIN proformas p ON r.id_proforma = p.id_proforma
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        WHERE 1=1
    """
    parametros = []

    if fecha_desde:
        query_entradas += " AND r.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query_entradas += " AND r.fecha <= ?"
        parametros.append(fecha_hasta)

    query_entradas += " ORDER BY r.fecha ASC, r.id_recibo ASC"

    cursor.execute(query_entradas, parametros)
    entradas = cursor.fetchall()

    query_salidas = "SELECT * FROM gastos WHERE 1=1"
    parametros2 = []

    if fecha_desde:
        query_salidas += " AND fecha >= ?"
        parametros2.append(fecha_desde)

    if fecha_hasta:
        query_salidas += " AND fecha <= ?"
        parametros2.append(fecha_hasta)

    query_salidas += " ORDER BY fecha ASC, id_gasto ASC"

    cursor.execute(query_salidas, parametros2)
    salidas = cursor.fetchall()

    conexion.close()

    total_entradas = sum(fila["monto_recibido"] or 0 for fila in entradas)
    total_salidas = sum(fila["monto"] or 0 for fila in salidas)

    return {
        "entradas": entradas,
        "salidas": salidas,
        "total_entradas": total_entradas,
        "total_salidas": total_salidas,
        "resultado_neto": total_entradas - total_salidas,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta
    }

#REPORTE DE CAJA (flujo de caja: entradas por recibos, salidas por gastos)
@app.route("/reportes/caja")
@login_requerido
@roles_requeridos("ADMIN")
def reporte_caja():
    fecha_desde, fecha_hasta = _rango_fechas_por_defecto()
    datos = _datos_reporte_caja(fecha_desde, fecha_hasta)
    return render_template("reporte_caja.html", **datos)

#EXPORTAR REPORTE DE CAJA A PDF
@app.route("/reportes/caja/pdf")
@login_requerido
@roles_requeridos("ADMIN")
def exportar_reporte_caja_pdf():
    fecha_desde, fecha_hasta = _rango_fechas_por_defecto()
    datos = _datos_reporte_caja(fecha_desde, fecha_hasta)
    datos["fecha_generacion"] = date.today().isoformat()

    html = render_template("reporte_caja_pdf.html", **datos)
    pdf = convertir_html_a_pdf(html)

    if pdf is None:
        return "Error al generar el PDF"

    respuesta = make_response(pdf)
    respuesta.headers["Content-Type"] = "application/pdf"
    respuesta.headers["Content-Disposition"] = (
        f"inline; filename=reporte_caja_{fecha_desde}_a_{fecha_hasta}.pdf"
    )
    return respuesta

def _datos_reporte_ganancia_repuestos(fecha_desde, fecha_hasta):
    """Trae los repuestos de inventario ya vendidos (con recibo emitido)
    en un período, con costo/venta/ganancia calculados. La usan tanto la
    pantalla del reporte como su exportación a PDF."""
    conexion = conectar_db()
    cursor = conexion.cursor()

    # Solo cuenta repuestos de proformas que ya se "concretaron" (con
    # recibo emitido): antes de eso son solo una cotización, no una venta.
    query = """
        SELECT dp.descripcion, dp.cantidad, dp.precio_unitario, dp.subtotal,
               i.precio_compra, p.numero_proforma, p.fecha
        FROM detalle_proforma dp
        INNER JOIN proformas p ON dp.id_proforma = p.id_proforma
        INNER JOIN inventario i ON dp.id_item = i.id_item
        WHERE dp.id_item IS NOT NULL AND p.stock_descontado = 1
    """
    parametros = []

    if fecha_desde:
        query += " AND p.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND p.fecha <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY p.fecha ASC"

    cursor.execute(query, parametros)
    filas = cursor.fetchall()

    conexion.close()

    items = []
    total_venta = 0.0
    total_costo = 0.0

    for fila in filas:
        precio_compra = fila["precio_compra"] or 0
        costo_total = precio_compra * fila["cantidad"]
        venta_total = fila["subtotal"]

        total_venta += venta_total
        total_costo += costo_total

        items.append({
            "descripcion": fila["descripcion"],
            "cantidad": fila["cantidad"],
            "precio_venta": fila["precio_unitario"],
            "precio_compra": precio_compra,
            "costo_total": costo_total,
            "venta_total": venta_total,
            "ganancia": venta_total - costo_total,
            "numero_proforma": fila["numero_proforma"],
            "fecha": fila["fecha"]
        })

    return {
        "items": items,
        "total_venta": total_venta,
        "total_costo": total_costo,
        "total_ganancia": total_venta - total_costo,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta
    }

#REPORTE DE GANANCIA DE REPUESTOS
@app.route("/reportes/ganancia-repuestos")
@login_requerido
@roles_requeridos("ADMIN")
def reporte_ganancia_repuestos():
    fecha_desde, fecha_hasta = _rango_fechas_por_defecto()
    datos = _datos_reporte_ganancia_repuestos(fecha_desde, fecha_hasta)
    return render_template("reporte_ganancia_repuestos.html", **datos)

#EXPORTAR REPORTE DE GANANCIA DE REPUESTOS A PDF
@app.route("/reportes/ganancia-repuestos/pdf")
@login_requerido
@roles_requeridos("ADMIN")
def exportar_reporte_ganancia_repuestos_pdf():
    fecha_desde, fecha_hasta = _rango_fechas_por_defecto()
    datos = _datos_reporte_ganancia_repuestos(fecha_desde, fecha_hasta)
    datos["fecha_generacion"] = date.today().isoformat()

    html = render_template("reporte_ganancia_repuestos_pdf.html", **datos)
    pdf = convertir_html_a_pdf(html)

    if pdf is None:
        return "Error al generar el PDF"

    respuesta = make_response(pdf)
    respuesta.headers["Content-Type"] = "application/pdf"
    respuesta.headers["Content-Disposition"] = (
        f"inline; filename=ganancia_repuestos_{fecha_desde}_a_{fecha_hasta}.pdf"
    )
    return respuesta


#RECIBOS
@app.route("/recibos")
@login_requerido
def listar_recibos():
    numero_recibo = request.args.get("numero_recibo", "").strip()
    numero_proforma = request.args.get("numero_proforma", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    conexion = conectar_db()
    cursor = conexion.cursor()

    query = """
        SELECT r.*, p.numero_proforma
        FROM recibos r
        INNER JOIN proformas p ON r.id_proforma = p.id_proforma
        WHERE 1=1
    """
    parametros = []

    if numero_recibo:
        query += " AND r.numero_recibo LIKE ?"
        parametros.append(f"%{numero_recibo}%")

    if numero_proforma:
        query += " AND p.numero_proforma LIKE ?"
        parametros.append(f"%{numero_proforma}%")

    if fecha_desde:
        query += " AND r.fecha >= ?"
        parametros.append(fecha_desde)

    if fecha_hasta:
        query += " AND r.fecha <= ?"
        parametros.append(fecha_hasta)

    query += " ORDER BY r.id_recibo DESC"

    cursor.execute(query, parametros)
    recibos = cursor.fetchall()

    conexion.close()

    return render_template(
        "recibos.html",
        recibos=recibos,
        numero_recibo=numero_recibo,
        numero_proforma=numero_proforma,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )
@app.route("/recibos/nuevo/<int:id_proforma>", methods=["GET", "POST"])
@login_requerido
def nuevo_recibo(id_proforma):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
    proforma = cursor.fetchone()

    if not proforma:
        conexion.close()
        flash("La proforma no existe.", "warning")
        return redirect(url_for("listar_proformas"))

    cursor.execute("""
        SELECT numero_recibo
        FROM recibos
        WHERE numero_recibo LIKE 'RC-%'
        ORDER BY id_recibo DESC
        LIMIT 1
    """)
    ultimo = cursor.fetchone()

    if ultimo and ultimo["numero_recibo"]:
        partes = ultimo["numero_recibo"].split("-")
        if len(partes) > 1 and partes[1].isdigit():
            nuevo_numero = f"RC-{int(partes[1]) + 1:04d}"
        else:
            nuevo_numero = "RC-0001"
    else:
        nuevo_numero = "RC-0001"

    if request.method == "POST":
        fecha = request.form["fecha"]
        monto_recibido = request.form["monto_recibido"]
        concepto = request.form["concepto"]
        observaciones = request.form["observaciones"]
        nombre_recibe = request.form["nombre_recibe"]
        ci_recibe = request.form["ci_recibe"]
        recibi_conforme = request.form["recibi_conforme"]

        # El repuesto se descuenta del inventario recién acá, al emitir el
        # recibo, porque es el momento en que la compra se concreta. Solo
        # se hace una vez por proforma (en el primer recibo que se emita);
        # si ya estaba descontado (por un recibo anterior) no se vuelve a tocar.
        primer_recibo = not proforma["stock_descontado"]
        detalles_inventario = []

        if primer_recibo:
            cursor.execute("""
                SELECT dp.id_detalle, dp.id_item, dp.cantidad, i.cantidad AS stock_actual, i.descripcion AS descripcion_item
                FROM detalle_proforma dp
                INNER JOIN inventario i ON dp.id_item = i.id_item
                WHERE dp.id_proforma = ? AND dp.tipo_item = 'REPUESTO' AND dp.id_item IS NOT NULL
            """, (id_proforma,))
            detalles_inventario = cursor.fetchall()

            faltantes = [d for d in detalles_inventario if d["cantidad"] > d["stock_actual"]]
            if faltantes:
                conexion.close()
                nombres = ", ".join(f"{d['descripcion_item']} (disponible: {d['stock_actual']})" for d in faltantes)
                flash(f"No hay stock suficiente para emitir el recibo. Revisa: {nombres}.", "warning")
                return render_template("nuevo_recibo.html", proforma=proforma, nuevo_numero=nuevo_numero)

        cursor.execute("""
            INSERT INTO recibos (
                numero_recibo, id_proforma, fecha, monto_recibido,
                concepto, observaciones, nombre_recibe, ci_recibe, recibi_conforme
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nuevo_numero, id_proforma, fecha, monto_recibido,
            concepto, observaciones, nombre_recibe, ci_recibe, recibi_conforme
        ))

        if primer_recibo:
            for detalle in detalles_inventario:
                nuevo_stock = detalle["stock_actual"] - detalle["cantidad"]
                cursor.execute("UPDATE inventario SET cantidad = ? WHERE id_item = ?", (nuevo_stock, detalle["id_item"]))
                cursor.execute("""
                    INSERT INTO movimientos_inventario (
                        id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                    )
                    VALUES (?, ?, 'SALIDA', ?, ?, ?)
                """, (
                    detalle["id_item"],
                    date.today().isoformat(),
                    -detalle["cantidad"],
                    "Uso en proforma (recibo emitido)",
                    proforma["numero_proforma"]
                ))

            cursor.execute("UPDATE proformas SET stock_descontado = 1 WHERE id_proforma = ?", (id_proforma,))

        conexion.commit()
        conexion.close()

        flash("Recibo registrado correctamente.", "success")
        return redirect(url_for("listar_recibos"))

    conexion.close()
    return render_template("nuevo_recibo.html", proforma=proforma, nuevo_numero=nuevo_numero)

@app.route("/recibos/<int:id_recibo>")
@login_requerido
def ver_recibo(id_recibo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT r.*, p.numero_proforma, p.tipo_proforma, p.total_general, p.total_literal,
               p.observaciones AS observaciones_proforma,
               p.nombre_cliente_manual, p.telefono_manual,
               p.marca_manual, p.modelo_manual, p.tipo_manual, p.placa_manual, p.vin_manual,
               c.nombre_completo, c.telefono,
               v.marca, v.modelo, v.tipo, v.placa, v.vin
        FROM recibos r
        INNER JOIN proformas p ON r.id_proforma = p.id_proforma
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        LEFT JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE r.id_recibo = ?
    """, (id_recibo,))
    recibo = cursor.fetchone()

    if not recibo:
        conexion.close()
        flash("El recibo no existe.", "warning")
        return redirect(url_for("listar_recibos"))

    cursor.execute("""
        SELECT *
        FROM detalle_proforma
        WHERE id_proforma = ?
        ORDER BY id_detalle ASC
    """, (recibo["id_proforma"],))
    detalles = cursor.fetchall()

    conexion.close()

    repuestos = [item for item in detalles if item["tipo_item"] == "REPUESTO"]
    mano_obra = [item for item in detalles if item["tipo_item"] == "MANO_OBRA"]

    total_general = float(recibo["total_general"] or 0)
    monto_recibido = float(recibo["monto_recibido"] or 0)
    saldo = total_general - monto_recibido
    if saldo < 0:
        saldo = 0

    return render_template(
        "ver_recibo.html",
        recibo=recibo,
        repuestos=repuestos,
        mano_obra=mano_obra,
        saldo=saldo
    )

@app.route("/recibos/<int:id_recibo>/pdf")
@login_requerido
def exportar_recibo_pdf(id_recibo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT r.*, p.numero_proforma, p.tipo_proforma, p.total_general, p.total_literal,
               p.observaciones AS observaciones_proforma,
               p.nombre_cliente_manual, p.telefono_manual,
               p.marca_manual, p.modelo_manual, p.tipo_manual, p.placa_manual, p.vin_manual,
               c.nombre_completo, c.telefono,
               v.marca, v.modelo, v.tipo, v.placa, v.vin
        FROM recibos r
        INNER JOIN proformas p ON r.id_proforma = p.id_proforma
        LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
        LEFT JOIN vehiculos v ON p.id_vehiculo = v.id_vehiculo
        WHERE r.id_recibo = ?
    """, (id_recibo,))
    recibo = cursor.fetchone()

    if not recibo:
        conexion.close()
        return "El recibo no existe."

    cursor.execute("""
        SELECT *
        FROM detalle_proforma
        WHERE id_proforma = ?
        ORDER BY id_detalle ASC
    """, (recibo["id_proforma"],))
    detalles = cursor.fetchall()

    conexion.close()

    repuestos = [item for item in detalles if item["tipo_item"] == "REPUESTO"]
    mano_obra = [item for item in detalles if item["tipo_item"] == "MANO_OBRA"]

    total_general = float(recibo["total_general"] or 0)
    monto_recibido = float(recibo["monto_recibido"] or 0)
    saldo = total_general - monto_recibido
    if saldo < 0:
        saldo = 0

    html = render_template(
        "recibo_pdf.html",
        recibo=recibo,
        repuestos=repuestos,
        mano_obra=mano_obra,
        saldo=saldo
    )

    pdf = convertir_html_a_pdf(html)

    if pdf is None:
        return "Error al generar el PDF"

    respuesta = make_response(pdf)
    respuesta.headers["Content-Type"] = "application/pdf"
    respuesta.headers["Content-Disposition"] = f"inline; filename=recibo_{recibo['numero_recibo']}.pdf"

    return respuesta
#ELIMINAR RECIBO
@app.route("/recibos/<int:id_recibo>/eliminar", methods=["POST"])
@login_requerido
@roles_requeridos("ADMIN")
def eliminar_recibo(id_recibo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT * FROM recibos WHERE id_recibo = ?", (id_recibo,))
    recibo = cursor.fetchone()

    if not recibo:
        conexion.close()
        flash("El recibo no existe.", "warning")
        return redirect(url_for("listar_recibos"))

    id_proforma = recibo["id_proforma"]

    cursor.execute("DELETE FROM recibos WHERE id_recibo = ?", (id_recibo,))

    # Si este era el último recibo de la proforma y el stock ya se había
    # descontado, se repone: sin recibo, la compra deja de estar concretada.
    cursor.execute("SELECT COUNT(*) AS total FROM recibos WHERE id_proforma = ?", (id_proforma,))
    quedan_recibos = cursor.fetchone()["total"]

    if quedan_recibos == 0:
        cursor.execute("SELECT * FROM proformas WHERE id_proforma = ?", (id_proforma,))
        proforma = cursor.fetchone()

        if proforma is not None and proforma["stock_descontado"]:
            cursor.execute("""
                SELECT id_item, cantidad FROM detalle_proforma
                WHERE id_proforma = ? AND tipo_item = 'REPUESTO' AND id_item IS NOT NULL
            """, (id_proforma,))
            detalles_inventario = cursor.fetchall()

            for detalle in detalles_inventario:
                cursor.execute("UPDATE inventario SET cantidad = cantidad + ? WHERE id_item = ?",
                               (detalle["cantidad"], detalle["id_item"]))
                cursor.execute("""
                    INSERT INTO movimientos_inventario (
                        id_item, fecha_movimiento, tipo_movimiento, cantidad, motivo, referencia
                    )
                    VALUES (?, ?, 'ENTRADA', ?, ?, ?)
                """, (
                    detalle["id_item"],
                    date.today().isoformat(),
                    detalle["cantidad"],
                    "Reverso por eliminación de recibo",
                    proforma["numero_proforma"]
                ))

            cursor.execute("UPDATE proformas SET stock_descontado = 0 WHERE id_proforma = ?", (id_proforma,))

    conexion.commit()
    conexion.close()

    flash("Recibo eliminado correctamente.", "success")
    return redirect(url_for("listar_recibos"))
@app.route("/recibos/<int:id_recibo>/editar", methods=["GET", "POST"])
@login_requerido
def editar_recibo(id_recibo):
    conexion = conectar_db()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT r.*, p.numero_proforma
        FROM recibos r
        INNER JOIN proformas p ON r.id_proforma = p.id_proforma
        WHERE r.id_recibo = ?
    """, (id_recibo,))
    recibo = cursor.fetchone()

    if not recibo:
        conexion.close()
        flash("El recibo no existe.", "warning")
        return redirect(url_for("listar_recibos"))

    if request.method == "POST":
        fecha = request.form["fecha"]
        monto_recibido = request.form["monto_recibido"]
        concepto = request.form["concepto"]
        observaciones = request.form["observaciones"]
        nombre_recibe = request.form["nombre_recibe"]
        ci_recibe = request.form["ci_recibe"]
        recibi_conforme = request.form["recibi_conforme"]

        if not fecha or not monto_recibido:
            conexion.close()
            flash("La fecha y el monto recibido son obligatorios.", "warning")
            return render_template("editar_recibo.html", recibo=recibo)

        try:
            monto_recibido_float = float(monto_recibido)
        except ValueError:
            conexion.close()
            flash("El monto recibido debe ser numérico.", "warning")
            return render_template("editar_recibo.html", recibo=recibo)

        if monto_recibido_float < 0:
            conexion.close()
            flash("El monto recibido no puede ser negativo.", "warning")
            return render_template("editar_recibo.html", recibo=recibo)

        cursor.execute("""
            UPDATE recibos
            SET fecha = ?, monto_recibido = ?, concepto = ?, observaciones = ?,
                nombre_recibe = ?, ci_recibe = ?, recibi_conforme = ?
            WHERE id_recibo = ?
        """, (
            fecha, monto_recibido_float, concepto, observaciones,
            nombre_recibe, ci_recibe, recibi_conforme, id_recibo
        ))

        conexion.commit()
        conexion.close()

        flash("Recibo actualizado correctamente.", "success")
        return redirect(url_for("ver_recibo", id_recibo=id_recibo))

    conexion.close()
    return render_template("editar_recibo.html", recibo=recibo)








if __name__ == "__main__":
    app.run(debug=True)
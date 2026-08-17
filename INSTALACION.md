# Instalación en la computadora del cliente (servidor local)

Esta guía explica cómo instalar el sistema del taller en la computadora
del cliente, para que funcione como "servidor local": el programa corre
en esa PC, y se puede usar desde esa misma computadora y, si querés,
también desde otras computadoras/celulares conectados al mismo WiFi del
taller (por ejemplo, una tablet en el mostrador).

## 1. Qué necesitás antes de empezar

- La carpeta completa del proyecto (`taller_gap7`), **sin** la carpeta
  `venv` (no la copies, se recrea en el paso 3 — copiarla no funciona
  porque un entorno virtual de Python queda "atado" a la computadora
  donde se creó).
- Python 3.11 o más nuevo instalado en la PC del cliente.
  Se descarga de https://www.python.org/downloads/ — durante la
  instalación, es importante tildar la casilla **"Add python.exe to PATH"**
  antes de darle a instalar.

## 2. Copiar el proyecto a la PC del cliente

Opciones, la que te resulte más práctica:

- **USB**: copiar la carpeta `taller_gap7` completa (de nuevo, sin `venv`)
  a, por ejemplo, `C:\taller_gap7`.
- **Git** (si el cliente tiene internet y ya tenés el repositorio en
  GitHub/GitLab): `git clone <URL-del-repositorio>`.

## 3. Crear el entorno virtual e instalar las dependencias

Abrí la terminal (`cmd` o PowerShell) dentro de la carpeta del proyecto
y ejecutá:

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
```

> **Importante:** usá siempre `venv\Scripts\python.exe -m pip ...` (no
> `venv\Scripts\pip.exe` directo) para instalar paquetes. En esta misma
> compu de desarrollo detectamos que el `pip.exe` del entorno virtual
> puede quedar apuntando a la carpeta equivocada si el `venv` se copió
> o mudó de lugar — usando `python -m pip` ese problema no existe,
> porque siempre instala en el Python que lo está ejecutando.

## 4. Crear (o actualizar) la base de datos

**Instalación nueva** (no hay un `taller.db` con datos para copiar):

```bash
venv\Scripts\python.exe instalar_actualizar_base_datos.py
venv\Scripts\python.exe crear_usuario_admin.py
```

El primer comando crea `taller.db` con todas las tablas que necesita el
sistema. El segundo crea un usuario `admin` con contraseña `123456`.
**Cambiala** desde "Cambiar contraseña" apenas entres por primera vez.

**Si ya tenías el sistema funcionando en otra compu** y estás migrando:
copiá el archivo `taller.db` de esa compu a la carpeta del proyecto acá
(reemplazando el que se haya generado), y después igual corré:

```bash
venv\Scripts\python.exe instalar_actualizar_base_datos.py
```

Este comando es seguro de correr **siempre**, las veces que haga falta:
no borra ni toca los datos que ya existan, solo crea las tablas o
columnas que falten. Conviene correrlo también cada vez que se
actualiza el sistema con una versión más nueva del código, por si esa
actualización agregó algo nuevo a la base de datos (por ejemplo, un
campo de precio en el inventario) — si no se corre y falta una columna
nueva, esa pantalla del sistema da **Internal Server Error**.

## 5. Iniciar el servidor

Para el uso diario, **no** se usa `python app.py` (ese es el modo de
programar: es más lento, menos estable, y muestra errores técnicos si
algo falla). Se usa el servidor de producción:

- **Más fácil:** doble clic en `iniciar_servidor.bat`.
- **Por terminal:** `venv\Scripts\python.exe servidor.py`.

Vas a ver un mensaje confirmando que el servidor está corriendo. Dejá
esa ventana abierta mientras se use el sistema — si la cerrás, el
sistema deja de estar disponible.

## 6. Acceder al sistema

- **Desde la misma PC:** abrir el navegador en `http://localhost:5000`.
- **Desde otra computadora/celular en el mismo WiFi del taller:**
  1. En la PC donde corre el servidor, abrir una terminal y ejecutar
     `ipconfig`. Buscar la "Dirección IPv4" (algo como `192.168.1.XX`).
  2. En el otro dispositivo, abrir el navegador en
     `http://192.168.1.XX:5000` (con esa IP).
  3. Si no conecta, revisar el punto 7 (firewall).

Para que la IP no cambie sola cada tanto (y tengas que estar buscándola
de nuevo), es recomendable configurar una **IP fija** para esa PC desde
el router del taller — es un paso opcional, pero cómodo a largo plazo.

## 7. Firewall de Windows (solo si vas a usarlo desde otros dispositivos)

La primera vez que se inicia el servidor, Windows puede preguntar si
querés permitir que Python se comunique en redes públicas/privadas —
elegí **"Permitir acceso"** (al menos para redes privadas).

Si no aparece esa ventana y otros dispositivos no logran conectarse,
hay que agregar una regla manualmente: Panel de Control → Firewall de
Windows Defender → Configuración avanzada → Reglas de entrada → Nueva
regla → Puerto → TCP → puerto `5000` → Permitir la conexión.

## 8. (Opcional) Que el servidor arranque solo con la PC

Si querés que el sistema esté disponible automáticamente cada vez que
se prende la computadora del taller (sin tener que abrir el `.bat` a
mano):

1. Crear un acceso directo a `iniciar_servidor.bat`.
2. Presionar `Win + R`, escribir `shell:startup` y Enter (abre la
   carpeta de inicio de Windows).
3. Pegar el acceso directo ahí.

Windows va a abrir esa ventana (minimizada o no) cada vez que se
inicie sesión en esa cuenta de usuario.

## 9. Respaldo de la base de datos

Todo el sistema (clientes, vehículos, proformas, inventario, etc.) vive
en un único archivo: `taller.db`, en la carpeta del proyecto. Se
recomienda copiarlo a un pendrive o a la nube (Google Drive, etc.) de
forma periódica — si ese archivo se pierde o se corrompe, se pierde
todo lo cargado.

## Notas de seguridad

- Cambiá la contraseña del usuario `admin` (`123456`) apenas instales.
- Este servidor está pensado para la **red local del taller**, no para
  exponerlo directamente a internet. Si en algún momento quieren
  acceder desde fuera del local (por ejemplo, desde la casa), lo
  correcto es investigar una VPN o un túnel seguro — no abrir el
  puerto directo al router.

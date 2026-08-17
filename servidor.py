"""
Servidor de USO REAL para el sistema del taller (no para programar).

"python app.py" usa el servidor de desarrollo de Flask: es ideal para
programar (se reinicia solo al guardar cambios, muestra errores
detallados), pero NO es seguro ni estable para dejarlo funcionando todo
el día atendiendo al taller.

Este script en cambio levanta la aplicación con Waitress, un servidor
mucho más robusto, pensado justamente para quedar corriendo de forma
permanente en una computadora.

Uso (con el entorno virtual ya creado, ver INSTALACION.md):
    venv\\Scripts\\python.exe servidor.py

o simplemente hacer doble clic en "iniciar_servidor.bat".

La aplicación queda disponible en:
    - Desde esta misma computadora:      http://localhost:5000
    - Desde otras computadoras/celulares
      conectados al mismo WiFi/red:      http://<IP de esta PC>:5000
      (la IP se ve con el comando "ipconfig" en la terminal de Windows)
"""

from waitress import serve
from app import app

if __name__ == "__main__":
    print("Iniciando el sistema del taller en el puerto 5000...")
    print("Dejá esta ventana abierta mientras el sistema esté en uso.")
    print("Para acceder desde esta PC: http://localhost:5000")
    serve(app, host="0.0.0.0", port=5000)

# Arena Burger (Django)

## Configuración después de clonar

Crear `.env` a partir de `.env.example`, completar la conexión a una base PostgreSQL
propia y definir `DJANGO_SECRET_KEY` antes de ejecutar Django. Para generar una clave:

```powershell
.\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Guardar el valor solamente en el `.env` local. Las credenciales, las bases, el
entorno virtual y las fotos subidas en `media/` no se incluyen en el repositorio.
Estas últimas y los datos de PostgreSQL requieren un respaldo separado.

Estado actual del envío: tarifa fija de $1.500, con dirección, localidad y
aclaración opcional. El mapa y el cálculo por distancia están pausados.

## Cómo correrlo

```bash
cd django_arena
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Abrí http://127.0.0.1:8000/

En este equipo, con el entorno ya preparado, para arrancar solo hace falta el
último comando. No es necesario volver a crear el administrador existente.
También podés ejecutar `.\iniciar.cmd`, que usa el entorno correcto.
`requirements.txt` fija las versiones exactas verificadas del entorno.

## Base de datos local

Se utiliza PostgreSQL 17 para desarrollo y se prevé la misma versión principal
en Cloud SQL para producción. Son bases separadas: las pruebas locales nunca
deben usar pedidos reales.

La conexión se configura en `.env`, que no se debe compartir ni guardar en Git.
`.env.example` contiene los nombres de las variables sin secretos. También se
pueden proporcionar directamente mediante variables de entorno en el servidor.
PostgreSQL es el único motor admitido: si faltan datos de conexión, Django
muestra un error y se detiene. No crea una base SQLite ni cambia de motor si
PostgreSQL no está disponible. La base PostgreSQL debe existir previamente.

El traslado inicial desde SQLite ya se completó. Los archivos usados para ese
traslado se archivaron en `.local/history/` como referencia; no forman parte de
la configuración activa y no deben volver a ejecutarse.

Los respaldos y credenciales de instalación quedan en `.local/`, excluido de Git.
Contienen información privada: no compartirlos. El usuario local `arena_dev`
puede crear bases para las pruebas automáticas y no es superusuario. En producción
se configurará un usuario distinto con permisos adecuados y copias de seguridad.
Las pruebas crean y eliminan una base temporal separada `test_arena_dev`;
el arranque normal de la web no crea bases de datos.
El archivo SQLite original se conserva; una vez activo PostgreSQL ya no recibe
los cambios nuevos y no sirve como respaldo actualizado.

Para verificar usando el entorno del proyecto:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test menu
```

## Qué editar

- **Hamburguesas, aderezos y extras (precios, disponibilidad):** desde el panel http://127.0.0.1:8000/admin/
- **Logo:** reemplazá `menu/static/menu/logo.jpeg`.
- **Fotos de hamburguesas:** desde `/admin/` → Hamburguesas → elegir un producto → Foto. Se pueden subir, reemplazar o quitar, con vista previa. El nombre del archivo ya no necesita coincidir con el del producto.
- **Flujo del pedido (personalización, carrito y datos de entrega):** `menu/static/menu/app.js`.

## Animaciones del menú

Las tarjetas aparecen suavemente al entrar en pantalla; las fotos tienen un
acercamiento leve al pasar el cursor. El contador del carrito reacciona a los
cambios y aparece una confirmación al agregar un producto. Las ventanas abren y
cierran con transiciones breves y conservan el foco del teclado dentro del diálogo.
Al cerrarlas, el foco vuelve al control de origen. Las animaciones respetan
`prefers-reduced-motion` y las tarjetas siguen visibles si no hay soporte para
IntersectionObserver o animaciones del navegador. No se agregaron dependencias.

## Fotos subidas

Se aceptan JPG/JPEG, PNG y WebP sin animación, de hasta 5 MB y 16 megapíxeles.
Se comprueba el contenido del archivo, además de su extensión. Los archivos reciben
nombres únicos: reemplazar una foto no queda bloqueado por la caché del navegador.
Una hamburguesa sin foto muestra «Foto próximamente».

En desarrollo, los archivos se guardan en `media/hamburguesas/` y PostgreSQL guarda
su referencia en el campo `photo`. Django los sirve en `/media/` solo con DEBUG
activado. `media/` está excluido de Git; las copias de seguridad deben incluir tanto
PostgreSQL como los archivos de esta carpeta. Reemplazar o quitar una foto cambia
la referencia del producto; no elimina automáticamente los archivos anteriores.

Las tres fotos iniciales se copiaron y vincularon mediante
`manage.py import_burger_photos`. El comando es para el traslado inicial y no se
ejecuta al arrancar la web. Conserva las fotos ya cargadas; si se vuelve a ejecutar,
puede reponer una foto inicial que se haya quitado manualmente.

Google Cloud Storage todavía no está conectado. Al preparar producción, se
configurará como almacenamiento predeterminado de Django y se copiarán allí las
fotos existentes. El campo y las plantillas usan la API de almacenamiento de
Django para que ese cambio no requiera modificar el flujo de administración.

## Carrito

El botón «Agregar al carrito» guarda cada hamburguesa personalizada como un renglón
independiente. Desde «Carrito» se pueden cambiar cantidades (1 a 99), quitar
productos, vaciarlo o seguir eligiendo. El carrito se conserva al recargar mediante
la sesión de Django, sin crear una cuenta; requiere que el navegador acepte cookies.
Los precios y la disponibilidad se comprueban en el servidor. Si un producto deja
de estar disponible, hay que quitar ese renglón para continuar.

Las bebidas y acompañamientos son productos independientes administrados en
`/admin/` → «Bebidas y acompañamientos». Tienen categoría, precio, disponibilidad,
foto opcional, «Sugerir antes de pagar» y orden. Un producto no puede habilitarse
sin un precio mayor que cero. Se cargaron Coca-Cola, Sprite y Fanta de 600 ml a
$2.500 cada una, y papas fritas a $5.000. La opción anterior de papas como extra
se deshabilitó; los pedidos ya guardados conservan su detalle original.

Al pasar del carrito a los datos aparece «¿Sumamos algo más?» una vez por recorrido
en la página, con hasta tres productos habilitados como sugerencias, en su orden
de administración. No ofrece productos independientes que ya estén en el carrito.
Al agregar uno se actualiza el total y se puede elegir otra sugerencia o continuar
sin agregar nada. Si no hay sugerencias elegibles, se pasa directamente a los datos.
Al recargar la página comienza un nuevo recorrido. Los productos también se pueden
agregar directamente desde la sección «Bebidas y acompañamientos» del menú.

«Ir a pagar» abre el formulario con nombre, teléfono y modalidad (retiro o
domicilio). Para domicilio son obligatorios la dirección y un punto de entrega
seleccionado en el mapa. El retiro no tiene costo.

## Entrega y tarifas

El local está en Uriburu 4757, Ingeniero Adolfo Sourdeaux. El centro del reparto
es el pin confirmado por el dueño: `-34.49823192111888, -58.67063072883498`.
Se puede configurar mediante `STORE_LATITUDE` y `STORE_LONGITUDE` en el entorno.
La cobertura es un radio máximo de 3.000 metros en línea recta (Haversine), no un
recorrido por calles. No se usa el centro de la localidad como aproximación.

La tarifa es $1.000 de base más $500 por cada tramo de 500 metros iniciado:
en el punto del local cuesta $1.000; más de 0 y hasta 500 m, $1.500;
hasta 1 km, $2.000; hasta 1,5 km, $2.500; hasta 2 km, $3.000;
hasta 2,5 km, $3.500; hasta 3 km, $4.000. Fuera del radio se rechaza la entrega.

El cliente escribe su dirección y marca el punto correspondiente en un mapa
Leaflet 1.9.4 con teselas OpenStreetMap y atribución visible. No se geocodifica
automáticamente el texto: el cliente debe comprobar que el pin corresponde a su
dirección. «Usar mi ubicación actual» es opcional y requiere el permiso del navegador;
se recomienda HTTPS para producción. Si falla, se puede marcar manualmente.
El sitio y la capa del mapa usan `strict-origin-when-cross-origin` para identificar
el origen ante el proveedor de mapas sin compartir rutas ni parámetros privados.

«Calcular envío» consulta al servidor. La cotización está firmada, dura 15 minutos
y vincula dirección, coordenadas, centro del local y tarifa. Si cambian la dirección
o el punto, hay que recalcular. Django vuelve a validar cobertura y tarifa al
registrar y guarda coordenadas, distancia, envío y total junto con el pedido.
No acepta un importe de envío enviado libremente por el navegador. Desde el panel
se puede abrir el punto en Google Maps. Pedidos anteriores sin cotización conservan
sus importes históricos. El mapa necesita conexión a sus proveedores externos;
si no carga, no se habilita un envío sin ubicación y se ofrece retiro.

## Registro de pedidos

«Registrar pedido» guarda el pedido y sus productos en PostgreSQL, con número y
estado pendiente de pago. El nombre, los aderezos, los extras y los importes se
conservan como eran al comprar aunque luego cambie el menú. Se comprueban precios
y disponibilidad en el servidor; si cambiaron, hay que volver al carrito.
Los reintentos de la misma solicitud no crean pedidos duplicados. Al registrar
correctamente, el carrito se vacía. Los datos personales no se conservan en
localStorage. El pago online sigue sin estar disponible: registrar un pedido
no realiza cobros ni confirma su preparación.

En `/admin/`, «Pedidos» permite consultar los datos y actualizar el estado de
preparación. Los productos y el estado de pago son de solo lectura para conservar
el registro. La integración de Mercado Pago Checkout Pro se hará en otra etapa.

Pruebas del carrito: `python manage.py test menu`.

## Panel privado de pedidos

Entrá a `http://127.0.0.1:8000/gestion/pedidos/`. El ingreso está en
`/gestion/ingresar/`. Un superusuario existente puede entrar con su misma cuenta.
No hay registro público: hace falta una cuenta activa con permiso `menu.view_order`;
para cambiar estados también se exige `menu.change_order`. Ser staff por sí solo
no da acceso. El cierre de sesión se hace con el botón «Salir».

Para crear una cuenta limitada para el dueño, ejecutá en una terminal:

```powershell
.\.venv\Scripts\python.exe manage.py create_owner dueno
```

La contraseña se pide de forma privada en la terminal y se valida con las reglas
de Django. El comando no acepta contraseñas por argumento. Si el usuario ya existe,
conserva su contraseña y sus permisos anteriores. El grupo «Dueño del local» da
acceso a pedidos y edición del catálogo desde `/admin/`, sin otorgar superusuario,
administración de usuarios ni eliminación de pedidos.

El panel muestra detalle, teléfono, modalidad, precios y pago; permite buscar por
número, cliente o teléfono, filtrar por estado o modalidad y navegar de a 12 pedidos.
El botón «Actualizar pedidos» consulta los datos nuevos; no hay actualización
automática. Los cambios de preparación son nuevo → en preparación → listo → entregado;
se permite cancelar un pedido no finalizado con una confirmación visible. No se
reabren pedidos finalizados desde este panel. Si el estado cambió en otra pantalla,
se pide revisar el estado actual para no sobrescribirlo.

Cambiar la preparación no marca pagos como aprobados. Los pedidos pendientes de
pago tienen un aviso visible. Este panel no cobra ni modifica los datos originales
del pedido. Usa plantillas de Django y CSS propio, sin React.

Las estadisticas quedan desactivadas en la primera version. Su implementacion,
plantilla y pruebas se conservan comentadas para retomarlas mas adelante.

<!--
## Estadísticas privadas

Desde el panel, «Estadísticas» abre `/gestion/estadisticas/`, con el mismo ingreso
y permiso de consulta de pedidos. Por defecto muestra desde el primer día del mes
hasta hoy. Permite elegir hasta 366 días y filtrar por una hamburguesa del catálogo,
incluidas las no disponibles. Usa la fecha de creación del pedido en hora argentina,
no la fecha de acreditación del dinero.

Solo cuenta pedidos con pago confirmado y no cancelados. Muestra cantidad de
pedidos pagados, unidades, ingresos de productos, promedio por pedido, ranking y
evolución diaria (mensual en períodos mayores a 62 días). Los pedidos pendientes
y cancelados se muestran separados. Al filtrar por hamburguesa, suma solo sus
renglones y extras; cuenta una vez cada pedido aunque tenga varios renglones de
la misma hamburguesa. Los importes y nombres provienen del detalle histórico del
pedido, por lo que los cambios de precios actuales no alteran los informes.

Los ingresos no incluyen envíos, costos, comisiones ni impuestos y no representan
ganancia neta. Todavía no se registran costos ni gastos. Mientras Mercado Pago
no esté integrado, no habrá confirmaciones automáticas de pago: es esperable ver
cero ventas y los pedidos registrados como pendientes. No se modifican estados de
pago para poblar las estadísticas.

-->

## Checkout Pro: preparado, pendiente de pruebas con Mercado Pago

Se implementó Checkout Pro mediante Orders API (`POST /v1/orders`), con solicitudes
HTTP del backend. Los pagos están desactivados por defecto (`MP_ENABLED=false`).
No se han enviado solicitudes reales a Mercado Pago ni se han realizado cobros.
Las pruebas usan respuestas simuladas; no sustituyen la validación de la integración.

Para conectar pruebas, crear una aplicación de Checkout Pro vía Orders en Mercado
Pago Developers y configurar privadamente en `.env` las variables documentadas en
`.env.example`: `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET`, `MP_SELLER_ID` (vendedor de
prueba), `MP_APPLICATION_ID` y `MP_PUBLIC_BASE_URL` (origen HTTPS público sin ruta).
Mantener `MP_ENVIRONMENT=test`. La firma secreta se obtiene en la configuración
de Webhooks de esa aplicación. Nunca compartir contraseñas de cuenta, tokens ni
firmas por chat ni incluirlos en Git. Esta integración por redirección no usa una
Public Key en el navegador.

Para probar localmente las notificaciones hace falta un túnel HTTPS hacia Django,
agregar su host exacto a `DJANGO_ALLOWED_HOSTS` y su origen a
`DJANGO_CSRF_TRUSTED_ORIGINS`. Configurar Webhooks de **order** en el entorno de
pruebas apuntando a `https://HOST-DEL-TUNEL/pagos/notificaciones/`. Si cambia el
host del túnel, actualizar esas variables y Webhooks. No habilitar hosts comodín.
No se creó ni publicó un túnel automáticamente.

Se puede abrir un túnel de prueba tras autorizarlo expresamente. La configuración
temporal queda en `.local/payment-tunnel.json`; el servidor dedicado se inicia
con `--settings=config.payment_test_settings` en `127.0.0.1:8001`, sin autorecarga.
Ese perfil fuerza DEBUG desactivado, cookies Secure, el host exacto del túnel y una
lista de rutas públicas que excluye administración y gestión. Sirve únicamente
los archivos estáticos del menú y las fotos públicas para esta prueba. Nunca usarlo
como servidor definitivo de producción. Después de cambiar `.env`, hay que reiniciar
esa instancia para que tome las credenciales nuevas.

Para apagar la instancia temporal y su túnel, sin detener el servidor habitual:

Después de reiniciar la computadora, ejecutar `.\iniciar-pruebas.cmd` para abrir
un túnel nuevo y su instancia protegida. El comando muestra la URL para el celular
y evita duplicar procesos activos o usar un puerto ocupado. Conserva registros
anteriores y deja los pagos desactivados en cada arranque nuevo, hasta actualizar
y verificar la URL en Mercado Pago. El enlace público anterior no se reutiliza.

```powershell
.\detener-pagos.cmd
```

El comando comprueba que los PID guardados sigan correspondiendo a esos procesos
antes de detenerlos. No borra datos ni archivos. La URL del túnel es temporal y
puede cambiar al abrir uno nuevo: habrá que actualizar también Mercado Pago.

Cuando esté completo, activar `MP_ENABLED=true` y comprobar sin mostrar secretos:

```powershell
.\.venv\Scripts\python.exe manage.py check_payments
```

Al habilitarlo, el cliente verá «Pagar con Mercado Pago». Se guarda primero el
pedido y luego un intento con clave de idempotencia persistente. Una desconexión
reutiliza la misma clave; un intento rechazado permite uno nuevo sobre el mismo
pedido. Los importes se obtienen de los renglones históricos y el envío guardado.
Se exige coincidencia de importe, ARS, vendedor, aplicación y referencia. Las
orders de prueba deben identificarse como `ORDTST...`; el modo de producción se
configura por separado cuando llegue esa etapa.

El webhook valida HMAC, identificador, marca temporal y entorno, y luego consulta
la Orders API con el token del backend. No confía en importes del webhook ni en
parámetros de retorno. Usa fechas de actualización para ignorar eventos antiguos;
las notificaciones repetidas no crean pagos nuevos y un error transitorio devuelve
503 para permitir reintentos. Cambiar la preparación no cambia el pago y, con pagos
activados, se bloquea preparar pedidos sin pago confirmado.

El retorno permite consultar el estado y reintentar un pago rechazado desde la
misma sesión del comprador. Las URLs privadas no se deben compartir. El administrador
puede inspeccionar los intentos, de solo lectura, desde Django. Los reembolsos que
informa Mercado Pago se reflejan en el pedido; este código no permite solicitar
reembolsos ni revierte automáticamente un cobro al cancelar la preparación. Eso
se gestiona por separado en Mercado Pago. Casos de pago inconsistente, parcial o
duplicado quedan para revisión.

Antes de producción: probar aprobados, pendientes, rechazos, abandono, reintentos,
notificaciones repetidas y recuperación de conexión; después configurar aplicación
y credenciales del dueño, HTTPS estable, secretos de producción, alertas y respaldo.

### Recuperación de notificaciones pendientes

Si se interrumpe el túnel o falta una notificación final, se puede consultar el
estado directamente al proveedor y sincronizarlo sin crear ni cobrar operaciones:

```powershell
.\.venv\Scripts\python.exe manage.py reconcile_payments --order 19 --settings=config.payment_test_settings
```

Sin `--order`, consulta hasta 20 intentos pendientes del entorno configurado.
`--limit` admite de 1 a 100. No ejecuta llamadas de creación ni cambia estados
por lo que diga una captura: usa las mismas validaciones de identidad, importe,
referencia y fecha de actualización que las notificaciones.

El evento `order.transaction_attempt_failed` no implica por sí solo que la order
ya esté en estado final `failed`. Si la consulta oficial devuelve `processing`,
se conserva pendiente y se impide preparar el pedido. La recepción HTTP 200 solo
indica que la notificación fue recibida, no que el pago fue aprobado o rechazado.

## Para producción

En `config/settings.py` poné `DEBUG = False`, completá `ALLOWED_HOSTS`, cambiá `SECRET_KEY`
y corré `python manage.py collectstatic` (se recomienda servir estáticos con WhiteNoise o nginx).

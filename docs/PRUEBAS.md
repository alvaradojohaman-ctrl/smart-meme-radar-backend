# Informe de pruebas — v0.4E

## Resultado

**27 pruebas funcionales aprobadas; tres pruebas de concurrencia nativa pendientes de ejecutar en PostgreSQL nativo.** Prueba de navegador con API local aprobada. No se ha desplegado en la cuenta del usuario ni se ha hecho una prueba real de duración 24 horas. Esto es una entrega preparada para despliegue y aceptación, no una certificación de servicio 24/7 operativo.

## Entorno y alcance

Python 3.12.14; dependencias fijadas en `backend/requirements.txt`; pytest 9.1.1. Base de pruebas: PostgreSQL compilado a WebAssembly, PGlite 0.5.8, mediante socket PostgreSQL 0.2.11 y cliente psycopg. Se ejecutaron SQL, restricciones, transacciones, JSONB y triggers del paquete, no una base SQLite sustitutiva. PGlite utiliza una conexión interna multiplexada: **no demuestra la corrección de locks entre sesiones nativas independientes**. Las tres pruebas que necesitan ese comportamiento fueron deseleccionadas deliberadamente, no contadas como aprobadas.

El entorno impidió crear un usuario de servicio para PostgreSQL nativo y no dispone de Docker. Se incluye `compose.test.yaml` para repetir la suite completa de 30 pruebas con PostgreSQL 16 en una base desechable. El Blueprint Render pasó validación contra su JSON Schema oficial. Docker/Compose/Render se entregan preparados, pero su construcción y despliegue no se ejecutaron aquí.

La suite mostró un aviso de deprecación de Starlette sobre su cliente de pruebas basado en HTTPX. No produjo fallos; las versiones usadas quedan fijadas. No implica una advertencia de rendimiento ni de operación del worker.

## Cobertura comprobada

| Prueba | Resultado |
|---|---|
| Seis objetivos exactos y tolerancia fija de 60 segundos | Aprobada |
| Observación independiente en 5m, 15m, 30m, 1h, 6h y 24h | Aprobada con reloj de prueba, sin esperar un día real |
| Límites +0s y +60s aceptados; +61s y +5h rechazados | Aprobada |
| Lectura solicitada antes del objetivo | Rechazada |
| Caída de dos días, sin rellenar checkpoints vencidos | Aprobada por simulación de tiempo |
| Reintento después de error y recuperación de reserva vencida | Aprobada |
| Respuesta de reserva obsoleta y doble finalización | Rechazadas |
| Token ausente del radar, consulta directa por dirección | Aprobada con proveedor controlado |
| Dirección errónea, precio cero/NaN y ausencia de par | Rechazados |
| Selección del par válido con más liquidez | Aprobada |
| HTTP 429 activa espera y registra el fallo | Aprobada con respuesta controlada |
| Importación de 68 casos, igualdad del contenido original e idempotencia | Aprobada con 68 casos sintéticos |
| Recuento diferente y segunda cohorte distinta | Rechazados |
| Trigger contra modificación de histórico | Aprobado |
| Ausentes fuera del denominador, no convertidos en pérdidas | Aprobada |
| Autenticación, CORS, paginación e importación/exportación de API | Aprobadas |
| Migración de esquema repetida conserva datos | Aprobada |
| Score y riesgo Python vs JavaScript original, 1,003 entradas | Coincidencia exacta |
| Archivos originales comparados con el ZIP recibido | 6/6 idénticos por SHA-256 |

Las 1,003 entradas incluyen 1,000 datos aleatorios reproducibles y tres casos de referencia. No se usaron resultados históricos para ajustar la fórmula.

## Interfaz

Chromium 153, controlado mediante Playwright, con frontend servido localmente y API FastAPI real contra la base de pruebas. Se verificó:

- Pantalla de escritorio (1280×960) y móvil (390×844), sin desbordamiento horizontal del cuerpo; tablas con desplazamiento propio.
- Conexión autenticada, estado del recolector, lectura de casos y capital virtual.
- Importación real de 68 registros sintéticos a través de la interfaz/API.
- Guion, NULL y cero numérico diferenciados; histórico sin modificación de localStorage.
- Clave API no guardada en localStorage.
- Símbolo malicioso presentado como texto, sin insertar imagen ni ejecutar código.
- Checkpoints observados, pendientes y perdidos, con detalle de tiempos.
- Exportador independiente y descarga con igualdad del JSON original.
- Sin errores JavaScript durante el recorrido.

El texto del detalle se presenta en lenguaje sencillo; las horas se convierten explícitamente a ISO UTC. La revisión visual mantuvo el diseño oscuro y las pestañas de la base v0.4D.

## Fuente real

Una petición HTTP real al endpoint `token-profiles/latest/v1` de DEX Screener respondió 200 con un arreglo. Las pruebas de errores/ventanas utilizan respuestas controladas para ser reproducibles. Una respuesta real aislada no demuestra disponibilidad constante ni puntualidad durante 24 horas.

## Pendiente antes de dar por aceptada la operación

1. Ejecutar las tres pruebas nativas: admisión concurrente sin duplicados, reserva concurrente de un job y exclusión del líder entre sesiones PostgreSQL.
2. Construir y arrancar los servicios del proveedor elegido; verificar CORS/HTTPS y `/readyz`.
3. Exportar e importar **los 68 casos reales** desde el navegador original y cotejar BRAIN, TTP y varios guiones. No pudieron verificarse porque el ZIP no trae esos datos.
4. Observar al menos un ciclo real de 24 horas con el navegador cerrado y revisar retrasos y faltantes. Reiniciar el worker y confirmar continuidad.
5. Configurar alertas y copias, y ensayar restauración PostgreSQL en una base separada.

No se ha optimizado el score, demostrado rentabilidad, conectado Helius/Smart Money ni implementado dinero real.

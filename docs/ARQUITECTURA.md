# Smart Meme Radar v0.4E — contrato del experimento

## Base exacta

`archive/v04d/` conserva los seis archivos del ZIP recibido, sin cambios. El código original sirve como referencia, no como página que deba abrirse durante la migración: al abrirlo podría actualizar el almacenamiento del navegador.

El ZIP no contiene los 68 casos, BRAIN ni TTP. Son datos de `localStorage` del navegador original. Esta entrega incluye el mecanismo para exportarlos e importarlos; no afirma haber recuperado datos que no fueron suministrados. Se exige una cohorte de exactamente 68 IDs distintos y una importación atómica. Los datos originales y sus cadenas JSON se conservan. Una segunda importación igual no duplica casos; una diferente se rechaza. Triggers impiden UPDATE/DELETE en las tablas históricas. Un administrador de PostgreSQL sigue teniendo privilegios para alterar su propia base; no es un archivo externo a prueba de manipulación.

## Componentes

- Netlify: conserva radar, riesgo, snapshots, comparación por grupos, historial anterior y capital virtual. Ahora consulta FastAPI. No crea casos ni completa checkpoints.
- FastAPI: autenticación por clave privada, CORS restringido, lectura de resultados, importación histórica y exportación de auditoría.
- Worker Python: proceso permanente independiente del navegador. Dos tareas: descubrimiento y medición. Una conexión con advisory lock limita a un recolector activo; las reservas de trabajos en PostgreSQL permiten recuperarse de caídas.
- PostgreSQL: casos, seis trabajos por caso, observaciones auditadas, histórico inmutable, estado del recolector y cuenta virtual.
- `MarketProvider`: interfaz para desacoplar la fuente. DEX Screener es la única implementación activa. Helius/Solana y Smart Money requieren nuevos adaptadores, tablas de eventos y otra versión de protocolo; no están implementados ni influyen en el score.

## Reglas prospectivas v04e-observation-1

El nombre visible del ZIP es Market Score; se considera el Smart Score referido en la solicitud. Se trasladó su fórmula sin optimización. La suite compara Python contra las funciones originales JavaScript en 1,003 entradas sintéticas. Mismos umbrales de mercado ≥75, riesgo y grupos APROBADO/BLOQUEADO. Selección: hasta 24 perfiles Solana recientes, par de mayor liquidez por dirección base, mejores 20 scores; un caso por dirección cada 24 horas. La cobertura sigue siendo una muestra de perfiles, no todo Solana. Cambiar la frecuencia de descubrimiento desde una acción manual a 60 segundos cambia la selección temporal: por eso v0.4E es una cohorte nueva y no una réplica estadística idéntica.

Cada caso fija entrada, precio, par, score, riesgo, snapshot, modelo y protocolo. La fecha de entrada es la recepción de la consulta que produjo el snapshot. Los seis objetivos son entrada +5m, +15m, +30m, +1h, +6h y +24h. Cada ventana, definida antes de observar resultados, es [objetivo, objetivo +60 segundos]. El retraso es recepción − objetivo, sin redondeo. Una petición iniciada antes del objetivo tampoco se acepta.

Estados:

| Estado | Precio/retorno de checkpoint | Interpretación |
|---|---|---|
| pending | NULL | Todavía no hay lectura válida; puede reintentarse dentro de la ventana |
| observed | Solo lectura recibida dentro de ventana | Dato válido bajo este protocolo; no prueba frescura del precio de origen |
| missed | NULL | Ventana vencida; no se rellena retrospectivamente |

Se conserva `target_at`, `deadline_at`, `observed_at`, `delay_seconds`, `finalized_at`, par y fuente. Un checkpoint perdido no tiene hora de observación porque no hubo observación aceptada. Si llegó una respuesta tarde, su hora real, precio y motivo se guardan en `observations`, con `accepted=false`. El precio tardío nunca aparece como retorno de ese horizonte. Si el proceso estuvo apagado, los objetivos vencidos se marcan perdidos sin consultar precios para ellos. Los horizontes futuros siguen pendientes.

No se usa el precio de una dirección distinta o de un token que solo coincida en símbolo. Para conservar la selección original se elige el par con más liquidez de la dirección en cada lectura, registrando su dirección; puede cambiar de pool. No se presenta la serie como una única ejecución negociable. DEX Screener no da un timestamp garantizado del precio: `source_quote_at` permanece NULL; `received_at` mide cuándo recibimos el proveedor. No se inventan velas ni precios históricos. La conservación de huecos evita una imputación sesgada, pero los datos faltantes todavía pueden introducir sesgo de selección.

## Recuperación y límites

Jobs guardados antes de consultarlos; transacción atómica para crear caso + seis checkpoints. Reservas de 30 segundos, token único y bloqueo de fila; una respuesta de una reserva obsoleta solo queda en auditoría. Hasta 12 consultas de checkpoints por ciclo; bucle cada 2 segundos. Límite compartido de 4 peticiones/segundo (240/minuto), perfiles una vez por ciclo de descubrimiento ≥60 segundos. Timeout HTTP 10 segundos, reintentos con espera 2–16 segundos, respeto de Retry-After numérico en 429, con límite de 120 segundos. No se promete una medición si el proveedor o el servidor falla: se expone el hueco.

Las reservas pueden prolongarse en la práctica por la cola del limitador o un 429; el recolector no acepta resultados después del límite, aunque produzca más perdidos. Para escalar, medir backlog y retrasos antes de cambiar concurrencia. No levantar varios workers: el líder impide duplicar consumo del proveedor. El despliegue con dos instancias temporalmente superpuestas puede hacer que la nueva espere/reintente mediante el supervisor hasta que la anterior libere el lock.

`/healthz` confirma API y base; `/readyz` devuelve 503 si no hay heartbeat del recolector en 120 segundos. La interfaz muestra por separado estado del descubrimiento y última consulta. Para alertas externas se debe configurar un monitor de `/readyz`; esta entrega no manda correos ni mensajes. Los timestamps son UTC en la base; la interfaz muestra hora local y ofrece detalle UTC al pulsar cada checkpoint.

## Histórico, comparación y validación

Los 68 casos se muestran tal como estaban: no recalculamos sus porcentajes ni validamos retrospectivamente su puntualidad. Guion, NULL, checkpoint ausente y 0 numérico no se confunden. La comparación v0.4E cuenta únicamente `observed` y muestra n válido, total programado, pendientes y perdidos por grupo/horizonte. Ganadores significa retorno estrictamente >0. No existe retorno real realizado ni costes de transacción modelados. No se mezclan cohortes.

Antes de una evaluación fuera de muestra: fijar por escrito fechas de inicio/fin o tamaño de muestra, criterio de comparación, horizonte principal y tratamiento de faltantes. No se optimizará con estos 68 casos. Cualquier score nuevo necesita otro modelo/protocolo y una muestra futura reservada. La versión actual recopila datos; no demuestra rentabilidad ni capacidad predictiva.

## Paper Trading y seguridad

v0.4D contiene una tarjeta de capital virtual (por defecto Q9,000), pero no órdenes, posiciones, salidas ni cálculo de P&L de una cartera. v0.4E conserva ese alcance y migra `smr_capital` a PostgreSQL. Los precios son USD y la tarjeta de capital GTQ; no se convierten ni usan para supuestas operaciones. No se añaden wallets, claves privadas, firma, exchanges ni ejecución real. Una futura simulación de cartera deberá definir tamaño, costes, cambio GTQ/USD y reglas de salida antes de medir resultados.

Clave API de al menos 32 caracteres, enviada por Authorization sobre HTTPS, no en la URL ni en archivos públicos; el frontend la conserva solo en memoria. CORS no sustituye la autenticación. Este paquete es de un solo usuario, sin roles ni multiusuario. Base de datos sin acceso público en Render; en Docker no se publica su puerto. Mantener backups y rotar secretos si se comparten. La exportación JSON es para auditoría, no sustituye `pg_dump` ni una restauración probada.

## Esquema y evolución

`schema.sql` inicializa v1 de forma idempotente bajo un lock; `schema_versions` registra su instalación. En futuras versiones, añadir migraciones numeradas explícitas en vez de modificar silenciosamente columnas o protocolos. La inserción histórica es la única escritura permitida desde el frontend. El recolector no escribe en el histórico. No hay endpoint para cambiar el score ni modificar retornos.

Fuentes oficiales consultadas el 24/09/2026 (hora Guatemala):
- https://docs.dexscreener.com/api/reference
- https://render.com/docs/blueprint-spec
- https://render.com/docs/background-workers

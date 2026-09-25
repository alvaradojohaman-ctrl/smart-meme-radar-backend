# Operación técnica

## Desarrollo local

Requisitos: Docker con Compose. Copiar `.env.example` a `.env` y sustituir secretos. Para evitar problemas de codificación de la URL de PostgreSQL, generar la contraseña con caracteres hexadecimales; por ejemplo `python -c "import secrets; print(secrets.token_hex(32))"`. Nunca usar los valores de ejemplo en un servidor expuesto.

```sh
docker compose up --build -d
```

Frontend: http://localhost:8080. API: http://localhost:8000. Los puertos se publican solo en loopback. Un servidor público necesita HTTPS y proxy inverso; la ruta recomendada para el usuario es Render + Netlify.

```sh
docker compose logs --tail=100 worker
docker compose restart worker
```

No ejecutar `docker compose down -v`: elimina el volumen de datos. `docker compose down` sin `-v` conserva el volumen. El schema se instala automáticamente de forma idempotente en el inicio de API/worker. En futuros cambios usar migraciones explícitas.

## Backups y restauración comprobable

Con los servicios Compose activos, crear una copia PostgreSQL:

```sh
docker compose exec -T db pg_dump -U smr -d smr -Fc > smr-backup.dump
```

Ver el índice sin modificar datos:

```sh
docker compose exec -T db pg_restore -l < smr-backup.dump
```

Restaurar **en una base nueva** para ensayar recuperación; estos nombres no sustituyen la base productiva:

```sh
docker compose exec -T db createdb -U smr smr_restore_check
docker compose exec -T db pg_restore -U smr -d smr_restore_check --no-owner --exit-on-error < smr-backup.dump
docker compose exec -T db psql -U smr -d smr_restore_check -c "SELECT count(*) FROM historical_cases; SELECT count(*) FROM checkpoints;"
```

Verificar 68 históricos cuando se hayan importado y comparar conteos con el origen. En Render usar su procedimiento vigente de backup/restauración o las credenciales de acceso apropiadas desde un entorno autorizado; la configuración suministrada no expone PostgreSQL a Internet. Cambiar `DATABASE_URL` a una copia ensayada es una intervención del operador. No se ha realizado una restauración en la cuenta del usuario.

## Ejecutar la suite sobre PostgreSQL nativo

Opción recomendada, en una máquina con Docker: desde la raíz del paquete, ejecutar:

```sh
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
```

Ese archivo crea una base PostgreSQL 16 desechable en memoria, sin exponer puertos y sin tocar el volumen productivo. El resultado esperado es 30 pruebas aprobadas, incluidas tres de concurrencia. El contenedor necesita descargar dependencias al construirse. Este comando se entrega preparado; no se ejecutó en este entorno porque Docker no está disponible.

Alternativa con una base de pruebas ya disponible:


**La suite borra y recrea el schema public. Jamás apuntarla a producción.** La doble condición `DATABASE_URL` + `SMR_TEST_DATABASE=yes` es obligatoria. Usar una base dedicada vacía. Requiere Python 3.12 y Node para comprobar equivalencia con v0.4D.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
export DATABASE_URL='postgresql://usuario:clave@localhost:5432/smr_test'
export SMR_TEST_DATABASE=yes
pytest -q
```

Si el socket local del entorno de pruebas usa PGlite, ejecutar únicamente `pytest -q -m 'not native'` y declarar ese límite. Las pruebas `native` necesitan procesos y conexiones reales PostgreSQL para comprobar exclusión/locks. No confundir PGlite con la plataforma propuesta de producción.

El directorio `tests/browser` contiene la prueba de interfaz reproducible con Playwright y datos sintéticos. No copia datos del usuario. El archivo de reporte detalla el entorno usado.

## Monitoreo y respuesta

- `/healthz`: API + PostgreSQL. Usado por Render para estado del servicio web.
- `/readyz`: 200 solo cuando el heartbeat del worker tiene menos de 120 segundos; no verifica la disponibilidad del proveedor.
- `/api/status`: autenticado; heartbeat, descubrimiento, última muestra, cuenta virtual y conteos.
- La tabla `observations` conserva intentos, errores, pares y respuestas. `checkpoints.last_error` describe el último fallo. Respuestas 429/timeout pueden causar huecos y no implican resultado financiero.
- Configure alerta sobre `/readyz`, errores de descubrimiento, retrasos, porcentaje de perdidos, disco/conexiones y backups. Estos servicios externos no quedan contratados por el ZIP.
- Mantenga un solo worker. Si necesita cambiar tolerancias, score, fuente o política de selección, cree un protocolo/cohorte nuevo y registre el cambio antes de observar resultados.
- No eliminar observaciones para mejorar métricas. Exporte una copia y planifique retención/archivado de auditoría a medida que crezca.

## Adaptadores futuros

`providers.MarketProvider` es el contrato de datos de mercado. Las señales Helius y Smart Money deben llegar a un módulo separado (identificador de wallet, transacción, slot, hora del evento y recepción, fuente, estado de confirmación). Evitar look-ahead: solo usar eventos disponibles al snapshot. No se incluye API key Helius ni se hacen solicitudes a Solana en esta versión. Diseñar una nueva estrategia y un experimento fuera de muestra antes de conectarlas al score.

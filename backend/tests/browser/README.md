# Prueba de navegador

Se ejecuta sobre una base desechable. Instalar Playwright (`npm install playwright`, `npx playwright install chromium`), exportar DATABASE_URL, SMR_TEST_DATABASE=yes y API_KEY de prueba. Desde backend, ejecutar `python tests/browser/seed.py`, arrancar `uvicorn smr.api:app --port 8000` y servir `frontend` con `python -m http.server 8080 --directory ../frontend` en otro proceso. Ejecutar `node tests/browser/ui.cjs` con NODE_PATH si Playwright se instaló fuera del directorio actual.

`CHROMIUM_EXECUTABLE` permite indicar Chromium instalado; `SCREENSHOT_DIR` define dónde escribir capturas. La prueba carga 68 registros **sintéticos** para probar importación y exportación. No son los casos reales del usuario. No usar la base de producción.

# Toolteach — versión Android

Reescritura en Kivy del programa de escritorio (Tkinter). `logic.py` contiene toda la
base de datos, cifrado y cálculos (compatible con los respaldos del programa de escritorio);
`main.py` contiene únicamente la interfaz táctil.

## Cómo obtener el APK (sin instalar nada en tu laptop)

1. Crea una cuenta gratuita en [github.com](https://github.com) si no tienes una.
2. Crea un repositorio nuevo (puede ser privado) y sube estos archivos tal cual están
   (arrastrando la carpeta completa en la web de GitHub, o con `git push`).
3. Entra a la pestaña **Actions** de tu repositorio. Debe aparecer el flujo
   "Compilar APK de Toolteach".
4. Haz clic en **Run workflow** (botón verde) para lanzar la compilación.
   Tarda entre 15 y 40 minutos la primera vez.
5. Cuando termine (círculo verde ✓), entra a esa ejecución y baja hasta
   **Artifacts** → descarga `toolteach-apk`. Es un .zip que contiene el `.apk`.
6. Pasa el `.apk` a tu teléfono (cable, Drive, etc.) y ábrelo para instalarlo
   (Android pedirá permitir "instalar de fuentes desconocidas" la primera vez).

## Probar la lógica antes de compilar (opcional, en tu laptop)

```
pip install cryptography openpyxl
python test_logic.py
```

Esto no requiere Kivy ni Android — solo verifica que la base de datos, el cifrado,
los cálculos de notas/asistencia y la importación/exportación funcionan igual que
en el programa de escritorio.

## Notas

- No se necesita Android Studio en ningún paso.
- Cada vez que quieras una nueva versión del APK, sube los cambios al repositorio
  y vuelve a correr el workflow (o se ejecuta solo al hacer `push` a `main`).
- Si quieres un ícono propio, coloca un PNG cuadrado (512×512) como `ico.png` en la
  carpeta y descomenta la línea `icon.filename` en `buildozer.spec`.

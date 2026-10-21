[app]
title = Toolteach
package.name = toolteach
package.domain = org.toolteach

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ico,ttf

version = 1.0

requirements = python3,kivy==2.3.0,openpyxl,cryptography,pillow

orientation = portrait
fullscreen = 0

# Si agregas un ícono (PNG cuadrado, ideal 512x512), descomenta esta línea:
# icon.filename = %(source.dir)s/ico.png

android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# API objetivo (Android 13). android.minapi 24 = compatible desde Android 7.0
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a

android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1

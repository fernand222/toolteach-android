
# -*- coding: utf-8 -*-
"""
Toolteach - Sistema de Gestión Estudiantil (versión Android, hecha con Kivy).

Es la misma aplicación del programa de escritorio (Tkinter), reorganizada para pantallas táctiles.
Los datos y las reglas están en logic.py; este archivo solo contiene la interfaz.
"""
import calendar
import os
import shutil
import traceback
from datetime import date, datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup, get_color_from_hex, platform

import logic as L

# ----------------------------------------------------------------------------------------------
# Colores (los mismos del programa de escritorio)
# ----------------------------------------------------------------------------------------------
def _c(h):
    return get_color_from_hex(h)


FONDO = _c('#ECF0F1')
ENCABEZADO = _c('#2C3E50')
AZUL = _c('#2980B9')
VERDE = _c('#27AE60')
ROJO = _c('#E74C3C')
MORADO = _c('#8E44AD')
NARANJA = _c('#F39C12')
TEXTO = _c('#2C3E50')
GRIS = _c('#7F8C8D')
BORDE = _c('#BDC3C7')
BLANCO = (1, 1, 1, 1)
FILA_NORMAL = _c('#FFFFFF')
FILA_SELECCION = _c('#AED6F1')
FILA_BIEN = _c('#D5F5E3')
FILA_MAL = _c('#FADBD8')
COLORES_TAG = {'bien': FILA_BIEN, 'mal': FILA_MAL, 'presente': FILA_BIEN, 'ausente': FILA_MAL}

esc = escape_markup


def app():
    return App.get_running_app()


# ----------------------------------------------------------------------------------------------
# Utilidades de dibujo
# ----------------------------------------------------------------------------------------------
def poner_fondo(w, color):
    with w.canvas.before:
        w._color_fondo = Color(*color)
        w._rect_fondo = Rectangle(pos=w.pos, size=w.size)

    def actualizar(*_):
        w._rect_fondo.pos = w.pos
        w._rect_fondo.size = w.size
    w.bind(pos=actualizar, size=actualizar)


def cambiar_fondo(w, color):
    w._color_fondo.rgba = color


def poner_borde(w):
    with w.canvas.after:
        Color(*BORDE)
        w._linea_borde = Line(rectangle=(w.x, w.y, w.width, w.height), width=1)

    def actualizar(*_):
        w._linea_borde.rectangle = (w.x, w.y, w.width, w.height)
    w.bind(pos=actualizar, size=actualizar)


# ----------------------------------------------------------------------------------------------
# Manejo de errores: cualquier acción del usuario muestra el problema en un aviso, sin cerrar la app
# ----------------------------------------------------------------------------------------------
def seguro(fn):
    def envoltura(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except L.ErrorApp as e:
            aviso('Advertencia', str(e))
        except Exception as e:  # noqa
            traceback.print_exc()
            aviso('Error', 'Ocurrió un error inesperado:\n%s' % e)
    return envoltura


# ----------------------------------------------------------------------------------------------
# Widgets básicos
# ----------------------------------------------------------------------------------------------
class Etiqueta(Label):
    """Texto que se ajusta al ancho disponible y crece en alto según su contenido."""

    def __init__(self, **kw):
        kw.setdefault('color', TEXTO)
        kw.setdefault('markup', True)
        kw.setdefault('halign', 'left')
        kw.setdefault('valign', 'middle')
        kw.setdefault('size_hint_y', None)
        kw.setdefault('font_size', sp(15))
        super().__init__(**kw)
        self.bind(width=self._ajustar_ancho, texture_size=self._ajustar_alto)
        self._ajustar_ancho()

    def _ajustar_ancho(self, *_):
        self.text_size = (self.width, None)

    def _ajustar_alto(self, *_):
        self.height = max(self.texture_size[1] + dp(6), dp(24))


class Boton(Button):
    def __init__(self, color=AZUL, alto=46, al_tocar=None, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', color)
        kw.setdefault('color', BLANCO)
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(alto))
        kw.setdefault('font_size', sp(15))
        kw.setdefault('halign', 'center')
        kw.setdefault('valign', 'middle')
        super().__init__(**kw)
        self.bind(size=self._ajustar_texto)
        if al_tocar is not None:
            self.bind(on_release=lambda *_: seguro(al_tocar)())

    def _ajustar_texto(self, *_):
        self.text_size = (max(self.width - dp(10), 1), self.height)


class Campo(TextInput):
    def __init__(self, solo_digitos=False, max_len=None, **kw):
        kw.setdefault('multiline', False)
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(46))
        kw.setdefault('font_size', sp(16))
        kw.setdefault('padding', [dp(10), dp(12), dp(10), dp(8)])
        kw.setdefault('background_normal', '')
        kw.setdefault('background_active', '')
        kw.setdefault('background_color', BLANCO)
        kw.setdefault('foreground_color', TEXTO)
        kw.setdefault('cursor_color', AZUL)
        kw.setdefault('write_tab', False)
        if solo_digitos:
            kw.setdefault('input_type', 'number')
        self.solo_digitos = solo_digitos
        self.max_len = max_len
        super().__init__(**kw)
        poner_borde(self)

    def insert_text(self, substring, from_undo=False):
        if self.solo_digitos:
            substring = ''.join(ch for ch in substring if ch.isdigit())
        if self.max_len:
            cupo = self.max_len - len(self.text)
            substring = substring[:max(cupo, 0)]
        return super().insert_text(substring, from_undo=from_undo)


POPUPS = []


class Ventana(Popup):
    """Ventana emergente que recuerda si está abierta (para que el botón Atrás de Android la cierre)."""
    cerrable_con_atras = True

    def __init__(self, **kw):
        kw.setdefault('title_color', TEXTO)
        kw.setdefault('background', '')
        kw.setdefault('background_color', FONDO)
        kw.setdefault('separator_color', AZUL)
        kw.setdefault('auto_dismiss', False)
        super().__init__(**kw)

    def on_open(self):
        POPUPS.append(self)

    def on_dismiss(self):
        if self in POPUPS:
            POPUPS.remove(self)


def _alto_segun_texto(texto):
    n = len(texto)
    return 0.34 if n < 110 else 0.5 if n < 320 else 0.8


def aviso(titulo, texto, al_cerrar=None, color=AZUL):
    caja = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(6))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    cuerpo = GridLayout(cols=1, size_hint_y=None)
    cuerpo.bind(minimum_height=cuerpo.setter('height'))
    cuerpo.add_widget(Etiqueta(text=esc(texto)))
    scroll.add_widget(cuerpo)
    caja.add_widget(scroll)
    ventana = Ventana(title=titulo, content=caja, size_hint=(0.92, _alto_segun_texto(texto)))

    def cerrar():
        ventana.dismiss()
        if al_cerrar:
            al_cerrar()
    caja.add_widget(Boton(text='Aceptar', color=color, al_tocar=cerrar))
    ventana.open()
    return ventana


def confirmar(titulo, texto, si, texto_si='Sí', color_si=ROJO):
    caja = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(6))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    cuerpo = GridLayout(cols=1, size_hint_y=None)
    cuerpo.bind(minimum_height=cuerpo.setter('height'))
    cuerpo.add_widget(Etiqueta(text=esc(texto)))
    scroll.add_widget(cuerpo)
    caja.add_widget(scroll)
    ventana = Ventana(title=titulo, content=caja, size_hint=(0.92, _alto_segun_texto(texto)))
    fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))

    def aceptar():
        ventana.dismiss()
        si()
    fila.add_widget(Boton(text='Cancelar', color=GRIS, al_tocar=ventana.dismiss))
    fila.add_widget(Boton(text=texto_si, color=color_si, al_tocar=aceptar))
    caja.add_widget(fila)
    ventana.open()


def mostrar_codigo(codigo, titulo, texto, al_cerrar=None):
    """Muestra un código de recuperación una sola vez."""
    caja = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(6))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    cuerpo = GridLayout(cols=1, size_hint_y=None, spacing=dp(10))
    cuerpo.bind(minimum_height=cuerpo.setter('height'))
    cuerpo.add_widget(Etiqueta(text=esc(texto)))
    cuerpo.add_widget(Etiqueta(text='[b]%s[/b]' % esc(codigo), font_size=sp(26), halign='center', color=AZUL))
    scroll.add_widget(cuerpo)
    caja.add_widget(scroll)
    ventana = Ventana(title=titulo, content=caja, size_hint=(0.94, 0.7))
    ventana.cerrable_con_atras = False

    def copiar():
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(codigo)
            aviso('Copiado', 'El código se copió al portapapeles. Anótelo también en papel.')
        except Exception:
            aviso('No se pudo copiar', 'Anote el código a mano.')

    def cerrar():
        ventana.dismiss()
        if al_cerrar:
            al_cerrar()
    caja.add_widget(Boton(text='Copiar código', color=NARANJA, al_tocar=copiar))
    caja.add_widget(Boton(text='Ya lo guardé, continuar', color=VERDE, al_tocar=cerrar))
    ventana.open()


class Opcion(Button):
    """Fila de la lista de opciones de un Selector."""

    def __init__(self, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', BLANCO)
        kw.setdefault('color', TEXTO)
        kw.setdefault('size_hint_y', None)
        kw.setdefault('halign', 'left')
        kw.setdefault('valign', 'middle')
        kw.setdefault('font_size', sp(15))
        kw.setdefault('markup', False)
        super().__init__(**kw)
        self.bind(width=self._ancho, texture_size=self._alto)
        self._ancho()

    def _ancho(self, *_):
        self.text_size = (max(self.width - dp(20), 1), None)

    def _alto(self, *_):
        self.height = max(self.texture_size[1] + dp(20), dp(46))


class Selector(Button):
    """Lista desplegable con búsqueda, pensada para pantallas táctiles."""

    def __init__(self, opciones=None, placeholder='Seleccione', valor=None, al_cambiar=None, buscable=True, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', BLANCO)
        kw.setdefault('color', TEXTO)
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(46))
        kw.setdefault('font_size', sp(15))
        kw.setdefault('halign', 'left')
        kw.setdefault('valign', 'middle')
        super().__init__(**kw)
        self._opciones = opciones if opciones is not None else []
        self.placeholder = placeholder
        self.valor = valor
        self.al_cambiar = al_cambiar
        self.buscable = buscable
        self.bind(size=self._ajustar, pos=self._dibujar_triangulo)
        poner_borde(self)
        with self.canvas.after:
            Color(*GRIS)
            self._tri = Triangle(points=[0, 0, 0, 0, 0, 0])
        self._refrescar_texto()
        self.bind(on_release=lambda *_: seguro(self.abrir)())

    def _ajustar(self, *_):
        self.text_size = (max(self.width - dp(40), 1), self.height)
        self._dibujar_triangulo()

    def _dibujar_triangulo(self, *_):
        cx = self.right - dp(18)
        cy = self.center_y
        t = dp(6)
        self._tri.points = [cx - t, cy + t / 2, cx + t, cy + t / 2, cx, cy - t / 2]

    def _refrescar_texto(self):
        if self.valor:
            self.text = str(self.valor).strip()
            self.color = TEXTO
        else:
            self.text = self.placeholder
            self.color = GRIS

    def establecer(self, valor):
        self.valor = valor
        self._refrescar_texto()

    def lista_opciones(self):
        o = self._opciones() if callable(self._opciones) else self._opciones
        return list(o)

    def abrir(self):
        opciones = self.lista_opciones()
        if self.valor and self.valor not in opciones:
            opciones = [self.valor] + opciones
        caja = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(4))
        campo = None
        if self.buscable and len(opciones) > 8:
            campo = Campo(hint_text='Escriba para filtrar...')
            caja.add_widget(campo)
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        lista = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        lista.bind(minimum_height=lista.setter('height'))
        scroll.add_widget(lista)
        caja.add_widget(scroll)
        ventana = Ventana(title=self.placeholder, content=caja, size_hint=(0.94, 0.85))
        caja.add_widget(Boton(text='Cancelar', color=GRIS, al_tocar=ventana.dismiss))

        def elegir(valor):
            self.establecer(valor)
            ventana.dismiss()
            if self.al_cambiar:
                self.al_cambiar(valor)

        def llenar(filtro=''):
            lista.clear_widgets()
            f = L.normalizar_texto(filtro)
            coincidencias = [o for o in opciones if not f or f in L.normalizar_texto(o)]
            for o in coincidencias[:80]:
                b = Opcion(text=str(o).strip())
                b.bind(on_release=lambda _b, o=o: elegir(o))
                lista.add_widget(b)
            if len(coincidencias) > 80:
                lista.add_widget(Etiqueta(text='Hay más resultados: escriba para filtrar.', color=GRIS, font_size=sp(13)))
            if not coincidencias:
                lista.add_widget(Etiqueta(text='Sin resultados.', color=GRIS))
        llenar()
        if campo is not None:
            campo.bind(text=lambda _w, t: llenar(t))
        ventana.open()


class SelectorFecha(Button):
    """Botón que muestra una fecha y permite elegir día, mes y año."""

    def __init__(self, valor=None, **kw):
        kw.setdefault('background_normal', '')
        kw.setdefault('background_down', '')
        kw.setdefault('background_color', BLANCO)
        kw.setdefault('color', TEXTO)
        kw.setdefault('size_hint_y', None)
        kw.setdefault('height', dp(46))
        kw.setdefault('font_size', sp(15))
        kw.setdefault('halign', 'left')
        kw.setdefault('valign', 'middle')
        super().__init__(**kw)
        self.valor = valor or date.today()
        self.bind(size=lambda *_: setattr(self, 'text_size', (max(self.width - dp(20), 1), self.height)))
        poner_borde(self)
        self._refrescar_texto()
        self.bind(on_release=lambda *_: seguro(self.abrir)())

    def _refrescar_texto(self):
        f = self.valor
        self.text = '%d de %s de %d' % (f.day, L.NOMBRES_MESES[f.month - 1], f.year)

    def establecer(self, valor):
        if valor is not None:
            self.valor = valor
            self._refrescar_texto()

    def abrir(self):
        hoy = date.today()
        anios = list(range(hoy.year - 6, hoy.year + 4))
        if self.valor.year not in anios:
            anios.append(self.valor.year)
            anios.sort()
        meses = [m.capitalize() for m in L.NOMBRES_MESES]
        caja = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(6))
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        sp_dia = Spinner(text=str(self.valor.day), values=[str(i) for i in range(1, 32)], size_hint_x=0.25)
        sp_mes = Spinner(text=meses[self.valor.month - 1], values=meses, size_hint_x=0.45)
        sp_anio = Spinner(text=str(self.valor.year), values=[str(a) for a in anios], size_hint_x=0.3)
        for s in (sp_dia, sp_mes, sp_anio):
            fila.add_widget(s)
        caja.add_widget(Etiqueta(text='Elija el día, el mes y el año', color=GRIS))
        caja.add_widget(fila)
        caja.add_widget(BoxLayout())
        ventana = Ventana(title='Fecha', content=caja, size_hint=(0.94, 0.4))

        def aceptar():
            m = meses.index(sp_mes.text) + 1
            a = int(sp_anio.text)
            d = min(int(sp_dia.text), calendar.monthrange(a, m)[1])
            self.establecer(date(a, m, d))
            ventana.dismiss()

        def hoy_():
            self.establecer(date.today())
            ventana.dismiss()
        botones = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        botones.add_widget(Boton(text='Cancelar', color=GRIS, al_tocar=ventana.dismiss))
        botones.add_widget(Boton(text='Hoy', color=NARANJA, al_tocar=hoy_))
        botones.add_widget(Boton(text='Aceptar', color=VERDE, al_tocar=aceptar))
        caja.add_widget(botones)
        ventana.open()


class Formulario(GridLayout):
    """Construye un formulario a partir de una lista de campos (diccionarios)."""

    def __init__(self, campos, **kw):
        super().__init__(cols=1, spacing=dp(6), padding=dp(4), size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter('height'))
        self.campos = {}
        self.widgets = {}
        for c in campos:
            self.campos[c['clave']] = c
            self.add_widget(Etiqueta(text=esc(c['etiqueta']), color=GRIS, font_size=sp(13)))
            tipo = c.get('tipo', 'texto')
            if tipo == 'seleccion':
                w = Selector(opciones=c['opciones'], placeholder=c.get('placeholder', 'Seleccione'), buscable=c.get('buscable', True))
            elif tipo == 'fecha':
                w = SelectorFecha()
            else:
                w = Campo(hint_text=c.get('pista', ''), password=(tipo == 'clave'),
                          solo_digitos=c.get('solo_digitos', False), max_len=c.get('max_len'))
            self.widgets[c['clave']] = w
            self.add_widget(w)

    def valor(self, clave):
        w = self.widgets[clave]
        if isinstance(w, (Selector, SelectorFecha)):
            return w.valor
        return w.text

    def valores(self):
        return {k: self.valor(k) for k in self.widgets}

    def poner(self, clave, valor):
        w = self.widgets[clave]
        if isinstance(w, (Selector, SelectorFecha)):
            w.establecer(valor)
        else:
            w.text = '' if valor is None else str(valor)

    def limpiar(self, claves=None):
        for k in (claves if claves is not None else list(self.widgets)):
            w = self.widgets[k]
            if isinstance(w, Selector):
                w.establecer(None)
            elif isinstance(w, SelectorFecha):
                pass
            else:
                w.text = ''


def dialogo_formulario(titulo, campos, valores=None, al_guardar=None, texto_guardar='Guardar', alto=0.88):
    """Ventana con un formulario. al_guardar(valores) puede devolver un mensaje de éxito o lanzar ErrorApp."""
    form = Formulario(campos)
    for k, v in (valores or {}).items():
        form.poner(k, v)
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
    scroll.add_widget(form)
    caja = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(4))
    caja.add_widget(scroll)
    ventana = Ventana(title=titulo, content=caja, size_hint=(0.94, alto))

    def guardar():
        mensaje = al_guardar(form.valores())
        ventana.dismiss()
        if mensaje:
            aviso('Éxito', mensaje)
    fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    fila.add_widget(Boton(text='Cancelar', color=GRIS, al_tocar=ventana.dismiss))
    fila.add_widget(Boton(text=texto_guardar, color=VERDE, al_tocar=guardar))
    caja.add_widget(fila)
    ventana.open()
    return ventana


# ----------------------------------------------------------------------------------------------
# Listas de tarjetas
# ----------------------------------------------------------------------------------------------
class Tarjeta(ButtonBehavior, BoxLayout):
    def __init__(self, dato, texto, tag=None, seleccionable=True, **kw):
        super().__init__(orientation='horizontal', size_hint_y=None, padding=dp(10), **kw)
        self.dato = dato
        self.tag = tag
        self.seleccionable = seleccionable
        self.seleccionada = False
        self.color_base = COLORES_TAG.get(tag, FILA_NORMAL)
        poner_fondo(self, self.color_base)
        self.etiqueta = Etiqueta(text=texto)
        self.add_widget(self.etiqueta)
        self.etiqueta.bind(height=self._ajustar_alto)
        self._ajustar_alto()

    def _ajustar_alto(self, *_):
        self.height = max(self.etiqueta.height + dp(20), dp(56))

    def on_release(self):
        if self.seleccionable:
            self.seleccionada = not self.seleccionada
            cambiar_fondo(self, FILA_SELECCION if self.seleccionada else self.color_base)


class ListaTarjetas(GridLayout):
    """Lista vertical de tarjetas. Va dentro de un ScrollView."""

    def __init__(self, seleccionable=True, **kw):
        super().__init__(cols=1, spacing=dp(6), padding=[dp(2), dp(4)], size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter('height'))
        self.seleccionable = seleccionable
        self.tarjetas = []
        self.al_cambiar = None

    def poner(self, items):
        self.clear_widgets()
        self.tarjetas = []
        for it in items:
            self._agregar(it)
        self._notificar()

    def agregar_item(self, item):
        self._agregar(item)
        self._notificar()

    def _agregar(self, it):
        t = Tarjeta(it['dato'], it['texto'], it.get('tag'), self.seleccionable)
        self.tarjetas.append(t)
        self.add_widget(t)

    def quitar_seleccionadas(self):
        for t in [t for t in self.tarjetas if t.seleccionada]:
            self.tarjetas.remove(t)
            self.remove_widget(t)
        self._notificar()

    def seleccionados(self):
        return [t.dato for t in self.tarjetas if t.seleccionada]

    def datos(self):
        return [t.dato for t in self.tarjetas]

    def __len__(self):
        return len(self.tarjetas)

    def _notificar(self):
        if self.al_cambiar:
            self.al_cambiar()


# ----------------------------------------------------------------------------------------------
# Archivos: exportar a Documentos / elegir un archivo para importar
# ----------------------------------------------------------------------------------------------
def carpeta_exportar():
    ruta = os.path.join(app().user_data_dir, 'exportados')
    os.makedirs(ruta, exist_ok=True)
    return ruta


def nombre_con_fecha(base, extension):
    return '%s_%s.%s' % (base, datetime.now().strftime('%Y%m%d_%H%M'), extension)


def publicar_archivo(ruta_privada):
    """Copia el archivo a una carpeta visible para el usuario y devuelve un texto que explica dónde quedó."""
    nombre = os.path.basename(ruta_privada)
    if platform == 'android':
        try:
            from androidstorage4kivy import SharedStorage
            SharedStorage().copy_to_shared(ruta_privada)
            return 'Se guardó el archivo "%s".\n\nBúsquelo con la app "Archivos" en la carpeta Documentos > Toolteach.' % nombre
        except Exception:
            traceback.print_exc()
            return 'No se pudo copiar a Documentos. El archivo quedó dentro de la app:\n%s' % ruta_privada
    destino = os.path.join(os.path.expanduser('~'), 'Toolteach_exportados')
    os.makedirs(destino, exist_ok=True)
    shutil.copy(ruta_privada, os.path.join(destino, nombre))
    return 'Se guardó el archivo "%s" en:\n%s' % (nombre, destino)


def exportar_excel(hoja, columnas, filas, base_nombre):
    if not filas:
        aviso('Advertencia', 'No hay datos para descargar.')
        return
    ruta = os.path.join(carpeta_exportar(), nombre_con_fecha(base_nombre, 'xlsx'))
    L.escribir_xlsx(ruta, hoja, columnas, filas)
    aviso('Éxito', publicar_archivo(ruta))


def elegir_archivo(al_elegir):
    """Abre el selector de archivos de Android y llama a al_elegir(ruta_local)."""
    if platform == 'android':
        from androidstorage4kivy import Chooser, SharedStorage

        def resultado(lista):
            if not lista:
                return
            try:
                ruta = SharedStorage().copy_from_shared(lista[0])
            except Exception as e:  # noqa
                traceback.print_exc()
                Clock.schedule_once(lambda dt: aviso('Error', 'No se pudo abrir el archivo: %s' % e))
                return
            Clock.schedule_once(lambda dt: seguro(al_elegir)(ruta))
        app()._chooser = Chooser(resultado)
        app()._chooser.choose_content('*/*')
    else:
        # En la computadora (para pruebas): se escribe la ruta del archivo
        dialogo_formulario('Importar', [dict(clave='ruta', etiqueta='Ruta del archivo de respaldo')],
                           al_guardar=lambda v: al_elegir(v['ruta'].strip()) and None, texto_guardar='Aceptar', alto=0.4)


# ----------------------------------------------------------------------------------------------
# Pantallas base
# ----------------------------------------------------------------------------------------------
class BarraSuperior(BoxLayout):
    def __init__(self, titulo, atras=True, derecha='', **kw):
        super().__init__(orientation='horizontal', size_hint_y=None, height=dp(54), padding=[dp(6), dp(6)], spacing=dp(6), **kw)
        poner_fondo(self, ENCABEZADO)
        if atras:
            self.add_widget(Boton(text='<', color=AZUL, size_hint_x=None, width=dp(46), size_hint_y=1,
                                  al_tocar=lambda: app().volver(), font_size=sp(20)))
        self.titulo = Label(text=titulo, bold=True, color=BLANCO, font_size=sp(18), halign='left', valign='middle', shorten=True)
        self.titulo.bind(size=lambda w, _: setattr(w, 'text_size', (w.width, w.height)))
        self.add_widget(self.titulo)
        if derecha:
            lbl = Label(text=derecha, color=_c('#BDC3C7'), font_size=sp(12), halign='right', valign='middle',
                        size_hint_x=None, width=dp(120), shorten=True)
            lbl.bind(size=lambda w, _: setattr(w, 'text_size', (w.width, w.height)))
            self.add_widget(lbl)


class Pantalla(Screen):
    def __init__(self, titulo='', atras=True, derecha='', **kw):
        super().__init__(**kw)
        self.raiz = BoxLayout(orientation='vertical')
        poner_fondo(self.raiz, FONDO)
        self.barra = BarraSuperior(titulo, atras, derecha)
        self.raiz.add_widget(self.barra)
        self.cuerpo = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
        self.raiz.add_widget(self.cuerpo)
        self.add_widget(self.raiz)


class PantallaScroll(Pantalla):
    def __init__(self, titulo='', atras=True, derecha='', **kw):
        super().__init__(titulo, atras, derecha, **kw)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.col = GridLayout(cols=1, spacing=dp(8), padding=dp(4), size_hint_y=None)
        self.col.bind(minimum_height=self.col.setter('height'))
        self.scroll.add_widget(self.col)
        self.cuerpo.add_widget(self.scroll)

    def limpiar(self):
        self.col.clear_widgets()

    def agregar(self, w):
        self.col.add_widget(w)
        return w


class PantallaLista(Pantalla):
    """Lista con tarjetas seleccionables, botones de acción y descarga a Excel."""

    def __init__(self, titulo, cargar, formato, botones=(), excel=None, vacio='No hay datos.', seleccionable=True, **kw):
        super().__init__(titulo, **kw)
        self.cargar = cargar
        self.formato = formato
        self.excel = excel
        self.vacio = vacio
        self.filas = []
        self.contador = Etiqueta(text='', color=GRIS, font_size=sp(13))
        self.cuerpo.add_widget(self.contador)
        self.scroll = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.lista = ListaTarjetas(seleccionable)
        self.scroll.add_widget(self.lista)
        self.cuerpo.add_widget(self.scroll)
        todos = [('Actualizar', AZUL, lambda p: p.recargar())] + list(botones)
        if excel:
            todos.append(('Descargar en Excel', VERDE, lambda p: p.descargar_excel()))
        filas_botones = (len(todos) + 1) // 2
        rejilla = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=filas_botones * dp(46) + (filas_botones - 1) * dp(6))
        for texto, color, fn in todos:
            rejilla.add_widget(Boton(text=texto, color=color, al_tocar=lambda fn=fn: fn(self)))
        if len(todos) % 2:
            rejilla.add_widget(BoxLayout())
        self.cuerpo.add_widget(rejilla)
        self.recargar()

    def recargar(self):
        self.filas = list(self.cargar())
        items = []
        for fila in self.filas:
            texto, tag = self.formato(fila)
            items.append(dict(dato=fila, texto=texto, tag=tag))
        self.lista.poner(items)
        if items:
            self.contador.text = '%d registro(s)' % len(items)
        else:
            self.contador.text = esc(self.vacio)

    def refrescar(self):
        self.recargar()

    def seleccion(self):
        return self.lista.seleccionados()

    def descargar_excel(self):
        e = self.excel
        filas = self.filas
        if e.get('filas'):
            filas = [e['filas'](f) for f in filas]
        exportar_excel(e['hoja'], e['columnas'], filas, e['archivo'])


class PantallaLote(PantallaScroll):
    """Formulario para preparar varios registros y guardarlos todos juntos."""

    def __init__(self, titulo, ayuda, campos, validar, guardar, limpiar=None, extras=(), texto_agregar='Agregar a la lista', **kw):
        super().__init__(titulo, **kw)
        self.validar = validar
        self.guardar_fn = guardar
        self.limpiar_claves = limpiar
        self.agregar(Etiqueta(text=esc(ayuda), color=GRIS, font_size=sp(13)))
        self.form = Formulario(campos)
        self.agregar(self.form)
        self.agregar(Boton(text=texto_agregar, color=AZUL, al_tocar=self.agregar_a_lista))
        for texto, color, fn in extras:
            self.agregar(Boton(text=texto, color=color, al_tocar=lambda fn=fn: fn(self)))
        self.contador = self.agregar(Etiqueta(text='', color=GRIS, font_size=sp(13)))
        self.lista = ListaTarjetas(True)
        self.lista.al_cambiar = self._actualizar_contador
        self.agregar(self.lista)
        self.agregar(Boton(text='Quitar seleccionados', color=ROJO, al_tocar=self.quitar))
        self.agregar(Boton(text='Guardar todos', color=VERDE, alto=54, al_tocar=self.guardar_todos))
        self._actualizar_contador()

    def _actualizar_contador(self):
        n = len(self.lista)
        self.contador.text = 'Pendientes por guardar: %d (toque una tarjeta para seleccionarla)' % n if n else 'La lista está vacía.'

    def agregar_a_lista(self):
        dato, texto, tag = self.validar(self.form.valores(), self)
        self.lista.agregar_item(dict(dato=dato, texto=texto, tag=tag))
        self.form.limpiar(self.limpiar_claves)

    def quitar(self):
        if not self.lista.seleccionados():
            aviso('Advertencia', 'Seleccione una tarjeta de la lista para quitarla')
            return
        self.lista.quitar_seleccionadas()

    def guardar_todos(self):
        filas = self.lista.datos()
        mensaje = self.guardar_fn(filas)
        self.lista.poner([])
        aviso('Éxito', mensaje)


# ----------------------------------------------------------------------------------------------
# Estudiantes
# ----------------------------------------------------------------------------------------------
def campos_estudiante():
    return [
        dict(clave='carnet', etiqueta='Carnet de Identidad (11 dígitos)', pista='11 dígitos', solo_digitos=True, max_len=11),
        dict(clave='nombre', etiqueta='Nombre'),
        dict(clave='ap1', etiqueta='Primer Apellido'),
        dict(clave='ap2', etiqueta='Segundo Apellido (opcional)'),
        dict(clave='sexo', etiqueta='Sexo', tipo='seleccion', opciones=L.SEXOS, placeholder='Seleccione sexo', buscable=False),
        dict(clave='municipio', etiqueta='Municipio', tipo='seleccion', opciones=L.MUNICIPIOS_CAMAGUEY, placeholder='Seleccione municipio'),
        dict(clave='anno', etiqueta='Año de Carrera', tipo='seleccion', opciones=L.ANNOS_CARRERA, placeholder='Seleccione año', buscable=False),
    ]


def nombre_completo(nombre, ap1, ap2):
    return ('%s %s %s' % (nombre, ap1, ap2 or '')).strip()


def fmt_estudiante(f):
    id_, carnet, nombre, ap1, ap2, sexo, municipio, anno = f
    texto = '[b]%s[/b]\nCarnet: %s\n%s · %s · %s año   [color=#7F8C8D](ID %s)[/color]' % (
        esc(nombre_completo(nombre, ap1, ap2)), esc(carnet or '-'), esc(sexo or '-'), esc(municipio or '-'), esc(str(anno)), id_)
    return texto, None


def fila_estudiante_lote(v):
    carnet, nombre, ap1, ap2, sexo, municipio, anno = L.validar_estudiante(
        v['carnet'], v['nombre'], v['ap1'], v['ap2'], v['sexo'], v['municipio'], v['anno'])
    return (carnet, nombre, ap1, ap2, sexo, municipio, anno)


def pantalla_agregar_estudiantes():
    def validar(v, pantalla):
        fila = fila_estudiante_lote(v)
        if L.carnet_existe(fila[0]) or any(d[0] == fila[0] for d in pantalla.lista.datos()):
            raise L.ErrorApp('Ya existe un estudiante con ese carnet de identidad')
        carnet, nombre, ap1, ap2, sexo, municipio, anno = fila
        texto = '[b]%s[/b]\nCarnet: %s\n%s · %s · %s año' % (esc(nombre_completo(nombre, ap1, ap2)), esc(carnet), esc(sexo), esc(municipio), esc(anno))
        return fila, texto, None

    def guardar(filas):
        n = L.guardar_estudiantes(filas)
        return 'Estudiante guardado correctamente' if n == 1 else '%d estudiantes guardados correctamente' % n

    return PantallaLote(
        'Agregar estudiantes',
        'Complete los datos y presione "Agregar a la lista" por cada estudiante. Al terminar, presione "Guardar todos".',
        campos_estudiante(), validar, guardar)


def pantalla_estudiantes(criterio=None):
    if criterio:
        cargar = lambda: L.buscar_estudiantes(criterio)  # noqa
        titulo = 'Búsqueda: %s' % criterio
        hoja, archivo = 'Resultados de Búsqueda', 'resultados_busqueda'
    else:
        cargar = L.listar_estudiantes
        titulo = 'Lista general de estudiantes'
        hoja, archivo = 'Estudiantes', 'estudiantes'
    botones = [
        ('Ver información', NARANJA, accion_ver_informacion),
        ('Editar', MORADO, accion_editar_estudiante),
        ('Eliminar seleccionados', ROJO, accion_eliminar_estudiante),
    ]
    return PantallaLista(titulo, cargar, fmt_estudiante, botones,
                         excel=dict(hoja=hoja, columnas=L.COLUMNAS_ESTUDIANTES, archivo=archivo),
                         vacio='No se encontraron estudiantes.')


def accion_ver_informacion(p):
    sel = p.seleccion()
    if not sel:
        raise L.ErrorApp('Seleccione un estudiante para ver su información')
    if len(sel) > 1:
        raise L.ErrorApp('Seleccione un solo estudiante para ver su información')
    f = sel[0]
    app().ir(pantalla_info_estudiante(f[0], nombre_completo(f[2], f[3], f[4])))


def accion_editar_estudiante(p):
    sel = p.seleccion()
    if not sel:
        raise L.ErrorApp('Seleccione un estudiante para editar')
    f = sel[0]

    def guardar(v):
        L.editar_estudiante(f[0], v['carnet'], v['nombre'], v['ap1'], v['ap2'], v['sexo'], v['municipio'], v['anno'])
        p.recargar()
        return 'Estudiante editado correctamente.'
    valores = dict(carnet=f[1] or '', nombre=f[2], ap1=f[3], ap2=f[4] or '',
                   sexo=f[5] if f[5] in L.SEXOS else None,
                   municipio=f[6] if f[6] in L.MUNICIPIOS_CAMAGUEY else None,
                   anno=str(f[7]) if str(f[7]) in L.ANNOS_CARRERA else None)
    dialogo_formulario('Editar estudiante', campos_estudiante(), valores, guardar)


def accion_eliminar_estudiante(p):
    sel = p.seleccion()
    if not sel:
        raise L.ErrorApp('Seleccione un estudiante')
    uno = len(sel) == 1
    mensaje = ('¿Seguro que desea eliminar %s? También se eliminarán todas sus evaluaciones y su participación en '
               'actividades extraescolares.') % ('el estudiante seleccionado' if uno else 'los estudiantes seleccionados')

    def hacer():
        L.eliminar_estudiantes([f[0] for f in sel])
        p.recargar()
        aviso('Éxito', ('Estudiante y toda su información relacionada (evaluaciones y participaciones) eliminados correctamente'
                        if uno else 'Estudiantes y toda su información relacionada (evaluaciones y participaciones) eliminados correctamente'))
    confirmar('Confirmar eliminación', mensaje, hacer, 'Eliminar')


def fmt_mensual_estudiante(f):
    _id, _nombre, mes, evaluacion, motivo, etiqueta = f
    return '[b]%s[/b]  ·  [b]%s[/b]\n%s' % (esc(mes), esc(evaluacion), esc(motivo)), etiqueta


def pantalla_info_estudiante(id_est, nombre):
    return PantallaLista('Información de %s' % nombre, lambda: L.evaluacion_mensual(id_est), fmt_mensual_estudiante,
                         seleccionable=False, vacio='Este estudiante todavía no tiene evaluaciones ni participaciones registradas.')


def pantalla_mensual():
    def fmt(f):
        _id, nombre, mes, evaluacion, motivo, etiqueta = f
        return '[b]%s[/b]  (ID %s)\n%s  ·  [b]%s[/b]\n%s' % (esc(nombre), _id, esc(mes), esc(evaluacion), esc(motivo)), etiqueta
    return PantallaLista('Información de estudiantes', L.evaluacion_mensual, fmt, seleccionable=False,
                         excel=dict(hoja='Información de Estudiantes', columnas=L.COLUMNAS_MENSUAL,
                                    archivo='informacion_estudiantes', filas=lambda f: f[:5]),
                         vacio='Todavía no hay evaluaciones ni asistencias registradas.')


# ----------------------------------------------------------------------------------------------
# Asignaturas
# ----------------------------------------------------------------------------------------------
def campos_asignatura():
    return [dict(clave='nombre', etiqueta='Asignatura'),
            dict(clave='anno', etiqueta='Año', tipo='seleccion', opciones=L.ANNOS_CARRERA, placeholder='Seleccione año', buscable=False)]


def pantalla_agregar_asignaturas():
    def validar(v, pantalla):
        nombre, anno = L.validar_asignatura(v['nombre'], v['anno'])
        return (nombre, anno), '[b]%s[/b] · %s año' % (esc(nombre), esc(anno)), None

    def guardar(filas):
        n = L.guardar_asignaturas(filas)
        return 'Asignatura guardada correctamente' if n == 1 else '%d asignaturas guardadas correctamente' % n
    return PantallaLote('Agregar asignaturas',
                        'Complete los datos y presione "Agregar a la lista" por cada asignatura. Al terminar, presione "Guardar todos".',
                        campos_asignatura(), validar, guardar)


def pantalla_asignaturas():
    def fmt(f):
        return '[b]%s[/b] · %s año   [color=#7F8C8D](ID %s)[/color]' % (esc(f[1]), esc(str(f[2])), f[0]), None

    def editar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una asignatura para editar')
        f = sel[0]

        def guardar(v):
            L.editar_asignatura(f[0], v['nombre'], v['anno'])
            p.recargar()
            return 'Asignatura editada correctamente.'
        dialogo_formulario('Editar asignatura', campos_asignatura(),
                           dict(nombre=f[1], anno=str(f[2]) if str(f[2]) in L.ANNOS_CARRERA else None), guardar, alto=0.6)

    def eliminar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una asignatura')

        def hacer():
            L.eliminar_asignaturas([f[0] for f in sel])
            p.recargar()
            aviso('Éxito', 'Asignatura eliminada correctamente' if len(sel) == 1 else 'Asignaturas eliminadas correctamente')
        confirmar('Confirmar eliminación', '¿Seguro que desea eliminar %s?' % ('la asignatura seleccionada' if len(sel) == 1 else 'las asignaturas seleccionadas'), hacer, 'Eliminar')
    return PantallaLista('Lista de asignaturas', L.listar_asignaturas, fmt,
                         [('Editar', MORADO, editar), ('Eliminar seleccionadas', ROJO, eliminar)],
                         excel=dict(hoja='Asignaturas', columnas=('ID', 'Asignatura', 'Año'), archivo='asignaturas'),
                         vacio='No existen asignaturas en la base de datos.')


# ----------------------------------------------------------------------------------------------
# Actividades extraescolares y asistencia
# ----------------------------------------------------------------------------------------------
def pantalla_agregar_actividades():
    campos = [dict(clave='nombre', etiqueta='Actividad extraescolar'), dict(clave='fecha', etiqueta='Fecha', tipo='fecha')]

    def validar(v, pantalla):
        nombre, fecha = L.validar_actividad(v['nombre'], v['fecha'])
        return (nombre, fecha), '[b]%s[/b]\n%s' % (esc(nombre), esc(fecha)), None

    def guardar(filas):
        n = L.guardar_actividades(filas)
        return 'Actividad guardada correctamente' if n == 1 else '%d actividades guardadas correctamente' % n
    return PantallaLote('Agregar actividades',
                        'Escriba el nombre y elija la fecha (puede ser futura: las actividades se pueden planificar). '
                        'Presione "Agregar a la lista" por cada una y "Guardar todos" al terminar.',
                        campos, validar, guardar, limpiar=['nombre'])


def pantalla_actividades():
    def fmt(f):
        return '[b]%s[/b]\n%s   [color=#7F8C8D](ID %s)[/color]' % (esc(f[1]), esc(str(f[2])), f[0]), None

    def editar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una actividad para editar')
        f = sel[0]

        def guardar(v):
            L.editar_actividad(f[0], v['nombre'])
            p.recargar()
            return 'Actividad editada correctamente.'
        dialogo_formulario('Editar actividad', [dict(clave='nombre', etiqueta='Actividad')], dict(nombre=f[1]), guardar, alto=0.4)

    def eliminar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una actividad')

        def hacer():
            L.eliminar_actividades([f[0] for f in sel])
            p.recargar()
            aviso('Éxito', 'Actividad eliminada correctamente' if len(sel) == 1 else 'Actividades eliminadas correctamente')
        confirmar('Confirmar eliminación', '¿Seguro que desea eliminar %s?' % ('la actividad seleccionada' if len(sel) == 1 else 'las actividades seleccionadas'), hacer, 'Eliminar')
    return PantallaLista('Actividades extraescolares', L.listar_actividades, fmt,
                         [('Editar', MORADO, editar), ('Eliminar seleccionadas', ROJO, eliminar)],
                         excel=dict(hoja='Actividades Extraescolares', columnas=('ID', 'Actividad', 'Fecha'), archivo='actividades_extraescolares'),
                         vacio='No existen actividades en la base de datos.')


def opciones_actividades_texto():
    return [t for t, _f in L.opciones_actividades()]


def campos_asistencia():
    return [
        dict(clave='actividad', etiqueta='Actividad', tipo='seleccion', opciones=opciones_actividades_texto, placeholder='Seleccione actividad'),
        dict(clave='estudiante', etiqueta='Estudiante', tipo='seleccion', opciones=L.opciones_estudiantes, placeholder='Seleccione estudiante'),
        dict(clave='asistencia', etiqueta='Asistencia', tipo='seleccion', opciones=L.ASISTENCIA_OPCIONES, placeholder='Presente o Ausente', buscable=False),
    ]


def _tarjeta_asistencia(actividad, estudiante, participacion):
    tag = 'presente' if participacion == 'Presente' else 'ausente'
    return '[b]%s[/b]\n%s\n[b]%s[/b]' % (esc(estudiante.strip()), esc(actividad), esc(participacion)), tag


def pantalla_tomar_asistencia():
    def validar(v, pantalla):
        actividad, estudiante, part = L.validar_asistencia(v['actividad'], v['estudiante'], v['asistencia'])
        if any(d[0] == actividad and d[1] == estudiante for d in pantalla.lista.datos()):
            raise L.ErrorApp('Ese estudiante ya está en la lista para esta actividad')
        texto, tag = _tarjeta_asistencia(actividad, estudiante, part)
        return (actividad, estudiante, part), texto, tag

    def guardar(filas):
        n = L.guardar_asistencias(filas)
        return 'Asistencia guardada correctamente para %d estudiante(s)' % n

    def marcar_todos(p):
        actividad = p.form.valor('actividad')
        L.validar_actividad_asistencia(actividad)
        ya = {d[1] for d in p.lista.datos() if d[0] == actividad}
        agregados = 0
        for est in L.opciones_estudiantes():
            if est in ya:
                continue
            texto, tag = _tarjeta_asistencia(actividad, est, 'Presente')
            p.lista.agregar_item(dict(dato=(actividad, est, 'Presente'), texto=texto, tag=tag))
            agregados += 1
        if agregados == 0:
            aviso('Aviso', 'Todos los estudiantes ya están en la lista para esta actividad')

    return PantallaLote('Tomar asistencia',
                        'Seleccione la actividad y agregue estudiantes uno por uno, o use "Marcar todos presentes" para agilizar '
                        '(luego quite y vuelva a agregar como "Ausente" a quienes faltaron). Solo se permite en actividades pasadas o de hoy. '
                        'Al terminar, presione "Guardar todos".',
                        campos_asistencia(), validar, guardar, limpiar=['estudiante', 'asistencia'],
                        extras=[('Marcar todos presentes', NARANJA, marcar_todos)])


def pantalla_participaciones():
    def fmt(f):
        return _tarjeta_asistencia(str(f[2]), str(f[1]), str(f[3]))

    def editar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione un registro para editar')
        f = sel[0]

        def guardar(v):
            L.editar_participacion(f[0], v['estudiante'], v['actividad'], v['asistencia'])
            p.recargar()
            return 'Datos editados correctamente.'
        dialogo_formulario('Editar asistencia', campos_asistencia(),
                           dict(estudiante=f[1], actividad=str(f[2]), asistencia=str(f[3]).strip().capitalize()), guardar, alto=0.7)

    def eliminar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione lo que desea eliminar')

        def hacer():
            L.eliminar_participaciones([f[0] for f in sel])
            p.recargar()
            aviso('Éxito', 'Dato eliminado correctamente' if len(sel) == 1 else 'Datos eliminados correctamente')
        confirmar('Confirmar eliminación', '¿Seguro que desea eliminar %s?' % ('el dato seleccionado' if len(sel) == 1 else 'las líneas seleccionadas'), hacer, 'Eliminar')
    return PantallaLista('Presentes y ausentes', L.listar_participaciones, fmt,
                         [('Editar', MORADO, editar), ('Eliminar seleccionados', ROJO, eliminar)],
                         excel=dict(hoja='Asistencia', columnas=L.COLUMNAS_PARTICIPACION, archivo='asistencia'),
                         vacio='No existe asistencia registrada en la base de datos.')


# ----------------------------------------------------------------------------------------------
# Evaluaciones
# ----------------------------------------------------------------------------------------------
def campos_evaluacion():
    return [
        dict(clave='estudiante', etiqueta='Estudiante', tipo='seleccion', opciones=L.opciones_estudiantes, placeholder='Seleccione estudiante'),
        dict(clave='asignatura', etiqueta='Asignatura', tipo='seleccion', opciones=L.opciones_asignaturas, placeholder='Seleccione asignatura'),
        dict(clave='nota', etiqueta='Nota', tipo='seleccion', opciones=L.NOTAS, placeholder='Seleccione nota', buscable=False),
        dict(clave='ausencias', etiqueta='Ausencias (%)', tipo='seleccion', opciones=L.AUSENCIAS, placeholder='Seleccione el porcentaje'),
        dict(clave='fecha', etiqueta='Fecha de la evaluación', tipo='fecha'),
    ]


def pantalla_agregar_evaluaciones():
    def validar(v, pantalla):
        est, asig, fecha, nota, aus = L.validar_evaluacion(v['estudiante'], v['asignatura'], v['fecha'], v['nota'], v['ausencias'])
        texto = '[b]%s[/b]\n%s · %s\nNota: %s · Ausencias: %s%%' % (esc(est.strip()), esc(asig), esc(fecha), nota, aus)
        return (est, asig, fecha, nota, aus), texto, None

    def guardar(filas):
        n = L.guardar_evaluaciones(filas)
        return 'Evaluación guardada correctamente' if n == 1 else '%d evaluaciones guardadas correctamente' % n
    return PantallaLote('Agregar evaluaciones',
                        'Complete los datos y presione "Agregar a la lista" por cada evaluación. Puede repetir con el mismo estudiante '
                        '(otra asignatura) o cambiar de estudiante. No se permiten fechas futuras. Al terminar, presione "Guardar todos".',
                        campos_evaluacion(), validar, guardar, limpiar=['nota', 'ausencias'])


def pantalla_evaluaciones():
    def fmt(f):
        return '[b]%s[/b]\n%s · %s\nNota: %s · Ausencias: %s   [color=#7F8C8D](ID %s)[/color]' % (
            esc(str(f[1]).strip()), esc(str(f[2])), esc(str(f[3])), esc(str(f[4])), esc(str(f[5])), f[0]), None

    def editar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una evaluación para editar')
        f = sel[0]

        def guardar(v):
            L.editar_evaluacion(f[0], v['estudiante'], v['asignatura'], v['fecha'], v['nota'], v['ausencias'])
            p.recargar()
            return 'Evaluación editada correctamente.'
        dialogo_formulario('Editar evaluación', campos_evaluacion(),
                           dict(estudiante=f[1], asignatura=f[2], nota=str(f[4]), ausencias=str(f[5]).replace('%', ''),
                                fecha=L.texto_a_fecha(f[3])), guardar)

    def eliminar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione una evaluación')

        def hacer():
            L.eliminar_evaluaciones([f[0] for f in sel])
            p.recargar()
            aviso('Éxito', 'Evaluación eliminada correctamente' if len(sel) == 1 else 'Evaluaciones eliminadas correctamente')
        confirmar('Confirmar eliminación', '¿Seguro que desea eliminar %s?' % ('la evaluación seleccionada' if len(sel) == 1 else 'las evaluaciones seleccionadas'), hacer, 'Eliminar')
    return PantallaLista('Lista de evaluaciones', L.listar_evaluaciones, fmt,
                         [('Editar', MORADO, editar), ('Eliminar seleccionadas', ROJO, eliminar)],
                         excel=dict(hoja='Evaluaciones', columnas=L.COLUMNAS_EVALUACIONES, archivo='evaluaciones'),
                         vacio='No existen evaluaciones en la base de datos.')


# ----------------------------------------------------------------------------------------------
# Datos: exportar / importar / restaurar
# ----------------------------------------------------------------------------------------------
def accion_exportar():
    ruta = os.path.join(carpeta_exportar(), nombre_con_fecha('toolteach_respaldo', 'db'))
    L.exportar_cifrado(ruta)
    aviso('Éxito', 'La información se exportó correctamente (cifrada).\n\n' + publicar_archivo(ruta))


def accion_importar():
    def continuar():
        elegir_archivo(importar_desde)
    confirmar('Confirmar importación',
              'Se agregará a este programa toda la información del archivo que elija y que todavía no exista aquí '
              '(estudiantes, evaluaciones, asignaturas, actividades extraescolares y asistencias).\n\n'
              'La información que ya tiene cargada no se modifica ni se duplica.\n\n¿Desea continuar?',
              continuar, 'Elegir archivo', AZUL)


def importar_desde(ruta):
    r = L.importar_cifrado(ruta)
    aviso('Éxito', 'Importación completada. Se agregó lo siguiente:\n\n'
                   '- Estudiantes nuevos: %d\n- Asignaturas nuevas: %d\n- Actividades extraescolares nuevas: %d\n'
                   '- Evaluaciones nuevas: %d\n- Asistencias nuevas: %d' % (
                       r['estudiantes'], r['asignaturas'], r['extraescolares'], r['evaluaciones'], r['participaciones']))


def accion_restaurar():
    if not app().es_admin:
        raise L.ErrorApp('Acceso denegado: solo el Administrador puede restaurar el programa de fábrica.')

    def hacer():
        L.restaurar_de_fabrica()
        aviso('Éxito', 'El programa se restauró a su estado de fábrica correctamente.')
    confirmar('Restaurar programa de fábrica',
              'Esta acción eliminará TODA la información cargada:\n\n- Estudiantes\n- Evaluaciones\n- Asignaturas\n'
              '- Actividades extraescolares\n- Asistencias\n\nLas cuentas de los profesores NO se eliminarán.\n\n'
              'Esta acción no se puede deshacer. ¿Desea continuar?', hacer, 'Restaurar')


def accion_descargar_evaluaciones():
    exportar_excel('Evaluaciones', L.COLUMNAS_EVALUACIONES, L.listar_evaluaciones(), 'evaluaciones')


# ----------------------------------------------------------------------------------------------
# Profesores y cuenta
# ----------------------------------------------------------------------------------------------
def pantalla_profesores():
    def fmt(f):
        return '[b]%s[/b]\n%s   [color=#7F8C8D](ID %s)[/color]' % (esc(f[1]), esc(f[2]), f[0]), ('bien' if f[2] == 'Administrador' else None)

    def agregar(p):
        campos = [dict(clave='usuario', etiqueta='Usuario'), dict(clave='clave', etiqueta='Contraseña', tipo='clave'),
                  dict(clave='confirmar', etiqueta='Confirmar contraseña', tipo='clave')]

        def guardar(v):
            L.agregar_profesor(app().es_admin, v['usuario'], v['clave'], v['confirmar'])
            p.recargar()
            return 'Profesor "%s" agregado correctamente' % v['usuario'].strip()
        dialogo_formulario('Agregar profesor', campos, None, guardar, alto=0.7)

    def eliminar(p):
        sel = p.seleccion()
        if not sel:
            raise L.ErrorApp('Seleccione un profesor para eliminar')
        f = sel[0]
        if f[2] == 'Administrador':
            raise L.ErrorApp('No se puede eliminar la cuenta de Administrador.')

        def hacer():
            L.eliminar_profesor(app().es_admin, f[0])
            p.recargar()
            aviso('Éxito', 'Profesor "%s" eliminado correctamente' % f[1])
        confirmar('Confirmar eliminación', '¿Eliminar al profesor "%s"? Esta acción no se puede deshacer.' % f[1], hacer, 'Eliminar')
    return PantallaLista('Gestión de profesores', L.listar_profesores, fmt,
                         [('Agregar profesor', VERDE, agregar), ('Eliminar seleccionado', ROJO, eliminar)],
                         vacio='No hay profesores registrados.')


class PantallaCambiarAdmin(PantallaScroll):
    def __init__(self):
        super().__init__('Cambiar Administrador')
        self.modo = 'promover'
        self.render()

    def cambiar_modo(self, modo):
        self.modo = modo
        self.render()

    def render(self):
        self.limpiar()
        a = app()
        self.agregar(Etiqueta(text='Administrador actual: [b]%s[/b]' % esc(a.usuario)))
        fila = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(58))
        fila.add_widget(Boton(text='Convertir a un profesor existente', color=AZUL if self.modo == 'promover' else GRIS,
                              alto=58, al_tocar=lambda: self.cambiar_modo('promover')))
        fila.add_widget(Boton(text='Registrar una cuenta nueva', color=AZUL if self.modo == 'nuevo' else GRIS,
                              alto=58, al_tocar=lambda: self.cambiar_modo('nuevo')))
        self.agregar(fila)
        if self.modo == 'promover':
            self._promover()
        else:
            self._nuevo()

    def _terminar(self, usuario_nuevo):
        a = app()
        a.es_admin = False

        def volver_inicio():
            a.reemplazar_todo(PantallaPrincipal())
        aviso('Éxito', '"%s" ahora es el Administrador del programa.\n\nUsted pasó a ser un profesor normal.' % usuario_nuevo, volver_inicio)

    def _promover(self):
        candidatos = L.candidatos_admin()
        if not candidatos:
            self.agregar(Etiqueta(text='No hay otros profesores registrados para convertir en Administrador.', color=GRIS))
            return
        self.agregar(Etiqueta(text='Profesor a convertir en Administrador:', color=GRIS, font_size=sp(13)))
        selector = self.agregar(Selector(opciones=candidatos, placeholder='Seleccione profesor', buscable=False))

        def confirmar_promocion():
            elegido = selector.valor
            if not elegido:
                raise L.ErrorApp('Seleccione un profesor')

            def hacer():
                L.promover_admin(app().es_admin, app().usuario, elegido)
                self._terminar(elegido)
            confirmar('Confirmar cambio de administrador',
                      '¿Convertir a "%s" en el nuevo Administrador?\n\nUsted ("%s") pasará a ser un profesor normal.' % (elegido, app().usuario),
                      hacer, 'Confirmar', AZUL)
        self.agregar(Boton(text='Confirmar', color=VERDE, al_tocar=confirmar_promocion))

    def _nuevo(self):
        form = self.agregar(Formulario([dict(clave='usuario', etiqueta='Usuario'),
                                        dict(clave='clave', etiqueta='Contraseña', tipo='clave'),
                                        dict(clave='confirmar', etiqueta='Confirmar contraseña', tipo='clave')]))

        def confirmar_nuevo():
            v = form.valores()
            usuario = v['usuario'].strip()
            if not usuario or not v['clave']:
                raise L.ErrorApp('El usuario y la contraseña son obligatorios')
            if len(v['clave']) < 4:
                raise L.ErrorApp('La contraseña debe tener al menos 4 caracteres')
            if v['clave'] != v['confirmar']:
                raise L.ErrorApp('Las contraseñas no coinciden')

            def hacer():
                codigo = L.registrar_nuevo_admin(app().es_admin, app().usuario, usuario, v['clave'], v['confirmar'])
                mostrar_codigo(codigo, 'Código de recuperación',
                               'Guarde el código de recuperación de "%s". Es la única forma de recuperar la contraseña de esta cuenta '
                               'si se olvida. No se volverá a mostrar.' % usuario, lambda: self._terminar(usuario))
            confirmar('Confirmar cambio de administrador',
                      '¿Registrar a "%s" como el nuevo Administrador?\n\nUsted ("%s") pasará a ser un profesor normal.' % (usuario, app().usuario),
                      hacer, 'Confirmar', AZUL)
        self.agregar(Boton(text='Confirmar', color=VERDE, al_tocar=confirmar_nuevo))


def accion_mi_cuenta():
    a = app()
    campos = [dict(clave='actual', etiqueta='Contraseña actual', tipo='clave'),
              dict(clave='usuario', etiqueta='Nuevo usuario'),
              dict(clave='nueva', etiqueta='Nueva contraseña (déjela vacía si no desea cambiarla)', tipo='clave'),
              dict(clave='confirmar', etiqueta='Confirmar nueva contraseña', tipo='clave')]

    def guardar(v):
        usuario, codigo = L.cambiar_mi_cuenta(a.usuario, a.es_admin, v['actual'], v['usuario'], v['nueva'], v['confirmar'])
        a.usuario = usuario
        if codigo:
            mostrar_codigo(codigo, 'Nuevo código de recuperación',
                           'Sus datos se actualizaron correctamente. Como cambió su contraseña de Administrador, también se generó un '
                           'nuevo código de recuperación (el anterior ya no sirve). Guárdelo en un lugar seguro; no se volverá a mostrar.')
            return None
        return 'Sus datos se actualizaron correctamente. El cambio de usuario se reflejará por completo la próxima vez que inicie sesión.'
    dialogo_formulario('Mi cuenta', campos, dict(usuario=a.usuario), guardar, alto=0.85)


# ----------------------------------------------------------------------------------------------
# Ayuda
# ----------------------------------------------------------------------------------------------
AYUDA = [
    ("1. Inicio de sesión",
     "La primera vez que abra la aplicación se le pedirá crear la cuenta de Administrador (usuario y contraseña de al menos 4 caracteres). "
     "Esa cuenta es la única con privilegios de Administrador. No pueden existir dos cuentas con el mismo usuario.\n"
     "Al crearla recibirá un CÓDIGO DE RECUPERACIÓN (algo como X7K2-9F4D-P8QW-Z3ML). Guárdelo fuera de la aplicación (escrito a mano): "
     "es la única forma de recuperar su contraseña y no se vuelve a mostrar.\n"
     "Si el Administrador olvidó su contraseña, toque \"¿Olvidaste tu contraseña?\", escriba su usuario y luego su código; al establecer la nueva "
     "contraseña se le entrega un código NUEVO. Si un profesor normal olvida su contraseña, el Administrador debe eliminar su cuenta y crearle otra "
     "desde \"Gestionar profesores\". Cualquier profesor puede cambiar su usuario y contraseña desde \"Mi cuenta\"."),
    ("2. Agregar estudiantes",
     "Inicio > \"Agregar estudiante(s)\". Complete Carnet de Identidad (obligatorio, exactamente 11 dígitos), Nombre, Primer Apellido, Segundo Apellido "
     "(opcional), Sexo, Municipio y Año de Carrera. Toque \"Agregar a la lista\" por cada estudiante y, al terminar, \"Guardar todos\". "
     "No se permiten dos estudiantes con el mismo carnet."),
    ("3. Buscar estudiantes",
     "En Inicio escriba en \"Buscar estudiante\" cualquier dato (ID, carnet, nombre, apellido, sexo, municipio o año; no hace falta el dato completo ni las tildes) "
     "y toque \"Buscar\". Toque una tarjeta para seleccionarla y use: Ver información, Editar, Eliminar o Descargar en Excel."),
    ("4. Editar y eliminar estudiantes",
     "Desde la \"Lista general de estudiantes\" o desde los resultados de una búsqueda, seleccione y toque \"Editar\" o \"Eliminar seleccionados\". "
     "IMPORTANTE: al eliminar un estudiante también se eliminan sus evaluaciones y su participación en actividades. No se puede deshacer."),
    ("5. Asignaturas",
     "\"Agregar asignaturas\": escriba el nombre y el año, agregue a la lista y guarde. \"Lista de asignaturas\": permite Actualizar, Editar, Eliminar y Descargar en Excel."),
    ("6. Evaluaciones",
     "\"Agregar evaluaciones\": elija estudiante, asignatura, nota (2, 3, 4 o 5), porcentaje de ausencias y fecha. No se permiten fechas futuras. "
     "Puede agregar varias a la lista y guardarlas juntas. \"Ver evaluaciones\" lista todas, con Editar, Eliminar y Excel."),
    ("7. Información de estudiantes (evaluación mensual)",
     "Calcula, mes por mes, el promedio de notas, el porcentaje de ausencias y la participación en actividades extraescolares. Un estudiante queda "
     "\"Aprobado\" (verde) si su promedio de notas está entre 3 y 5, sus ausencias son 20% o menos y su participación es 50% o más. Si incumple alguna "
     "condición queda en \"Riesgo de Deserción\" (rojo) y se explica el motivo. Los estudiantes sin datos ese mes no aparecen."),
    ("8. Actividades extraescolares y asistencia",
     "\"Agregar actividades\": nombre y fecha (puede ser futura). \"Tomar asistencia\": elija la actividad y agregue estudiantes como Presente o Ausente, "
     "o use \"Marcar todos presentes\". Solo se puede tomar asistencia de actividades cuya fecha ya pasó o es hoy. "
     "\"Presentes y ausentes\" muestra toda la asistencia registrada."),
    ("9. Exportar e importar",
     "Inicio > Datos > \"Exportar\" guarda toda la información (sin las cuentas de profesores) en un archivo cifrado dentro de la carpeta Documentos > Toolteach "
     "de su teléfono; puede enviarlo por WhatsApp, Bluetooth, correo, etc. \"Importar\" agrega a esta app únicamente lo que todavía no existe (los estudiantes se "
     "reconocen por su carnet), sin borrar ni duplicar nada. Los respaldos son compatibles con el programa de escritorio, en ambos sentidos."),
    ("10. Descargar en Excel",
     "Las listas tienen el botón \"Descargar en Excel\". El archivo .xlsx queda en Documentos > Toolteach y se abre con Excel, Google Sheets o WPS Office."),
    ("11. Administración (solo Administrador)",
     "\"Gestionar profesores\": ver, agregar y eliminar cuentas (la del Administrador nunca se elimina). \"Cambiar administrador\": ceder el rol a otro profesor o "
     "registrar una cuenta nueva como Administrador. \"Restaurar de fábrica\": borra TODA la información (no las cuentas); pide confirmación."),
    ("12. Consejos",
     "- Los IDs se renumeran automáticamente al eliminar registros.\n- La búsqueda ignora acentos y mayúsculas.\n"
     "- Toque una tarjeta para seleccionarla (se marca en azul) y otra vez para quitar la selección.\n"
     "- Haga respaldos con \"Exportar\" con frecuencia, sobre todo antes de cambiar de teléfono o desinstalar la aplicación."),
]


class PantallaAyuda(PantallaScroll):
    def __init__(self):
        super().__init__('Ayuda - Cómo usar Toolteach')
        for titulo, texto in AYUDA:
            self.agregar(Etiqueta(text='[b]%s[/b]' % esc(titulo), font_size=sp(17), color=AZUL))
            self.agregar(Etiqueta(text=esc(texto)))


# ----------------------------------------------------------------------------------------------
# Pantalla principal
# ----------------------------------------------------------------------------------------------
class PantallaPrincipal(PantallaScroll):
    def __init__(self):
        a = app()
        rol = 'Administrador' if a.es_admin else 'Profesor'
        super().__init__('Toolteach', atras=False, derecha='%s (%s)' % (a.usuario, rol))
        self.agregar(Etiqueta(text='Sistema de Gestión Estudiantil', color=GRIS, font_size=sp(13)))
        fila = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.buscar_campo = Campo(hint_text='Buscar estudiante (nombre, carnet, año...)')
        self.buscar_campo.bind(on_text_validate=lambda *_: seguro(self.buscar)())
        fila.add_widget(self.buscar_campo)
        fila.add_widget(Boton(text='Buscar', color=AZUL, size_hint_x=None, width=dp(90), al_tocar=self.buscar))
        self.agregar(fila)

        self.seccion('Estudiantes', [
            ('Agregar estudiante(s)', VERDE, lambda: a.ir(pantalla_agregar_estudiantes())),
            ('Lista general de estudiantes', AZUL, lambda: a.ir(pantalla_estudiantes())),
            ('Información de estudiantes', AZUL, lambda: a.ir(pantalla_mensual())),
        ])
        self.seccion('Evaluación', [
            ('Agregar evaluaciones', VERDE, self.abrir_agregar_evaluaciones),
            ('Ver evaluaciones', AZUL, lambda: a.ir(pantalla_evaluaciones())),
            ('Descargar evaluaciones (Excel)', AZUL, accion_descargar_evaluaciones),
        ])
        self.seccion('Asignaturas', [
            ('Agregar asignaturas', VERDE, lambda: a.ir(pantalla_agregar_asignaturas())),
            ('Lista de asignaturas', AZUL, lambda: a.ir(pantalla_asignaturas())),
        ])
        self.seccion('Actividades extraescolares', [
            ('Agregar actividades', VERDE, lambda: a.ir(pantalla_agregar_actividades())),
            ('Lista de actividades', AZUL, lambda: a.ir(pantalla_actividades())),
            ('Tomar asistencia', VERDE, self.abrir_asistencia),
            ('Presentes y ausentes', AZUL, lambda: a.ir(pantalla_participaciones())),
        ])
        self.seccion('Datos', [
            ('Exportar (respaldo)', NARANJA, accion_exportar),
            ('Importar (respaldo)', NARANJA, accion_importar),
        ])
        if a.es_admin:
            self.seccion('Administración', [
                ('Gestionar profesores', MORADO, lambda: a.ir(pantalla_profesores())),
                ('Cambiar administrador', MORADO, lambda: a.ir(PantallaCambiarAdmin())),
                ('Restaurar de fábrica', ROJO, accion_restaurar),
            ])
        self.seccion('Cuenta', [
            ('Mi cuenta', AZUL, accion_mi_cuenta),
            ('Ayuda', AZUL, lambda: a.ir(PantallaAyuda())),
            ('Cerrar sesión', GRIS, self.cerrar_sesion),
        ])

    def seccion(self, titulo, botones):
        self.agregar(Etiqueta(text='[b]%s[/b]' % esc(titulo), font_size=sp(17), color=ENCABEZADO))
        filas = (len(botones) + 1) // 2
        rejilla = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=filas * dp(58) + (filas - 1) * dp(6))
        for texto, color, fn in botones:
            rejilla.add_widget(Boton(text=texto, color=color, alto=58, al_tocar=fn))
        if len(botones) % 2:
            rejilla.add_widget(BoxLayout())
        self.agregar(rejilla)

    def buscar(self):
        criterio = self.buscar_campo.text.strip()
        resultados = L.buscar_estudiantes(criterio)  # lanza ErrorApp si está vacío
        if not resultados:
            aviso('Sin resultados', 'No se encontraron estudiantes que coincidan con "%s"' % criterio)
            return
        app().ir(pantalla_estudiantes(criterio))

    def abrir_agregar_evaluaciones(self):
        if not L.hay_estudiantes():
            raise L.ErrorApp('No hay estudiantes en la base de datos. Por favor, agregue estudiantes primero')
        if not L.hay_asignaturas():
            raise L.ErrorApp('No hay asignaturas en la base de datos. Por favor, agregue asignaturas primero')
        app().ir(pantalla_agregar_evaluaciones())

    def abrir_asistencia(self):
        if not L.hay_estudiantes():
            raise L.ErrorApp('No hay estudiantes en la base de datos. Por favor, agregue estudiantes primero')
        if not L.hay_actividades():
            raise L.ErrorApp('No hay actividades en la base de datos. Por favor, agregue actividades primero')
        app().ir(pantalla_tomar_asistencia())

    def cerrar_sesion(self):
        a = app()
        a.usuario = None
        a.es_admin = False
        a.reemplazar_todo(PantallaAcceso())


# ----------------------------------------------------------------------------------------------
# Acceso: iniciar sesión, primer Administrador y recuperación de contraseña
# ----------------------------------------------------------------------------------------------
class PantallaAcceso(PantallaScroll):
    def __init__(self):
        super().__init__('Toolteach - Acceso de profesores', atras=False)
        if L.hay_profesores():
            self.mostrar_login()
        else:
            self.mostrar_registro()

    def _base(self, titulo, subtitulo=None):
        self.limpiar()
        self.agregar(Etiqueta(text='[b]Toolteach[/b]', font_size=sp(30), halign='center', color=ENCABEZADO))
        self.agregar(Etiqueta(text='Sistema de Gestión Estudiantil', halign='center', color=GRIS))
        self.agregar(Etiqueta(text='[b]%s[/b]' % esc(titulo), font_size=sp(19), halign='center'))
        if subtitulo:
            self.agregar(Etiqueta(text=esc(subtitulo), halign='center', color=GRIS, font_size=sp(13)))

    def _error(self):
        self.error = self.agregar(Etiqueta(text='', color=ROJO, halign='center'))

    def _mostrar_error(self, e):
        self.error.text = esc(str(e))

    def _enlace(self, texto, fn):
        self.agregar(Boton(text=texto, color=GRIS, alto=40, al_tocar=fn))

    def mostrar_login(self):
        self._base('Inicio de sesión')
        form = self.agregar(Formulario([dict(clave='usuario', etiqueta='Usuario'), dict(clave='clave', etiqueta='Contraseña', tipo='clave')]))
        self._error()

        def entrar():
            try:
                usuario, es_admin = L.iniciar_sesion(form.valor('usuario'), form.valor('clave'))
            except L.ErrorApp as e:
                self._mostrar_error(e)
                form.limpiar(['clave'])
                return
            a = app()
            a.usuario, a.es_admin = usuario, es_admin
            a.reemplazar_todo(PantallaPrincipal())
        form.widgets['clave'].bind(on_text_validate=lambda *_: entrar())
        self.agregar(Boton(text='Iniciar sesión', color=VERDE, alto=52, al_tocar=entrar))
        self._enlace('¿Olvidaste tu contraseña?', self.mostrar_rec_usuario)

    def mostrar_registro(self):
        self._base('Crear cuenta de Administrador',
                   'Es la primera vez que se usa el programa. Esta cuenta será la única con privilegios de Administrador. '
                   'Al terminar se le entregará un código de recuperación para usar si olvida su contraseña.')
        form = self.agregar(Formulario([dict(clave='usuario', etiqueta='Usuario'),
                                        dict(clave='clave', etiqueta='Contraseña (mínimo 4 caracteres)', tipo='clave'),
                                        dict(clave='confirmar', etiqueta='Confirmar contraseña', tipo='clave')]))
        self._error()

        def crear():
            try:
                codigo = L.crear_primer_admin(form.valor('usuario'), form.valor('clave'), form.valor('confirmar'))
            except L.ErrorApp as e:
                self._mostrar_error(e)
                return
            a = app()
            a.usuario, a.es_admin = form.valor('usuario').strip(), True
            mostrar_codigo(codigo, 'Guarde su código de recuperación',
                           'Este código es la única forma de recuperar su contraseña si la olvida. Guárdelo en un lugar seguro '
                           '(escrito a mano, por ejemplo). No se volverá a mostrar.',
                           lambda: a.reemplazar_todo(PantallaPrincipal()))
        self.agregar(Boton(text='Crear cuenta', color=VERDE, alto=52, al_tocar=crear))

    def mostrar_rec_usuario(self):
        self._base('Recuperar contraseña', 'Esta opción solo está disponible para la cuenta de Administrador. Escriba su usuario para continuar.')
        form = self.agregar(Formulario([dict(clave='usuario', etiqueta='Usuario')]))
        self._error()

        def siguiente():
            try:
                usuario, codigo_hash = L.recuperacion_paso_usuario(form.valor('usuario'))
            except L.ErrorApp as e:
                self._mostrar_error(e)
                return
            self.mostrar_rec_codigo(usuario, codigo_hash)
        self.agregar(Boton(text='Siguiente', color=AZUL, alto=52, al_tocar=siguiente))
        self._enlace('Volver al inicio de sesión', self.mostrar_login)

    def mostrar_rec_codigo(self, usuario, codigo_hash):
        self._base('Código de recuperación', 'Escriba el código de recuperación que guardó al crear su cuenta.')
        form = self.agregar(Formulario([dict(clave='codigo', etiqueta='Código (XXXX-XXXX-XXXX-XXXX)')]))
        self._error()

        def verificar():
            try:
                L.verificar_codigo_recuperacion(codigo_hash, form.valor('codigo'))
            except L.ErrorApp as e:
                self._mostrar_error(e)
                form.limpiar()
                return
            self.mostrar_rec_nueva(usuario)
        self.agregar(Boton(text='Verificar', color=AZUL, alto=52, al_tocar=verificar))
        self._enlace('Volver al inicio de sesión', self.mostrar_login)

    def mostrar_rec_nueva(self, usuario):
        self._base('Nueva contraseña')
        form = self.agregar(Formulario([dict(clave='clave', etiqueta='Nueva contraseña', tipo='clave'),
                                        dict(clave='confirmar', etiqueta='Confirmar contraseña', tipo='clave')]))
        self._error()

        def guardar():
            try:
                nuevo = L.establecer_nueva_contrasena(usuario, form.valor('clave'), form.valor('confirmar'))
            except L.ErrorApp as e:
                self._mostrar_error(e)
                return
            mostrar_codigo(nuevo, 'Guarde su nuevo código de recuperación',
                           'Su contraseña se cambió. El código anterior ya no sirve; guarde este nuevo código. No se volverá a mostrar.',
                           self.mostrar_login)
        self.agregar(Boton(text='Guardar nueva contraseña', color=VERDE, alto=52, al_tocar=guardar))


# ----------------------------------------------------------------------------------------------
# Aplicación
# ----------------------------------------------------------------------------------------------
class ToolteachApp(App):
    title = 'Toolteach'

    def build(self):
        Window.clearcolor = FONDO
        try:
            Window.softinput_mode = 'below_target'
        except Exception:
            pass
        L.set_db_path(os.path.join(self.user_data_dir, 'estudiantes.db'))
        L.init_db()
        self.usuario = None
        self.es_admin = False
        self.pila = []
        self._contador = 0
        self._chooser = None
        self.sm = ScreenManager(transition=NoTransition())
        Window.bind(on_keyboard=self._tecla)
        self.ir(PantallaAcceso())
        return self.sm

    def on_pause(self):
        return True

    def ir(self, pantalla):
        self._contador += 1
        pantalla.name = 'p%d' % self._contador
        self.sm.add_widget(pantalla)
        self.sm.current = pantalla.name
        self.pila.append(pantalla)

    def volver(self):
        if len(self.pila) <= 1:
            return False
        actual = self.pila.pop()
        anterior = self.pila[-1]
        self.sm.current = anterior.name
        Clock.schedule_once(lambda dt: self.sm.remove_widget(actual), 0.2)
        if hasattr(anterior, 'refrescar'):
            anterior.refrescar()
        return True

    def reemplazar_todo(self, pantalla):
        viejas = list(self.pila)
        self.pila = []
        self.ir(pantalla)
        Clock.schedule_once(lambda dt: [self.sm.remove_widget(p) for p in viejas], 0.2)

    def _tecla(self, ventana, tecla, *args):
        if tecla != 27:  # 27 = botón Atrás de Android / Esc
            return False
        if POPUPS:
            p = POPUPS[-1]
            if p.cerrable_con_atras:
                p.dismiss()
            return True
        return self.volver()


if __name__ == '__main__':
    ToolteachApp().run()

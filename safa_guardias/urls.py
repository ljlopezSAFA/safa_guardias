from django.urls import path

from . import views

urlpatterns = [
    path("", views.pagina_inicio, name="index"),
    path("profesores/", views.ver_profesores, name="mostrar_profesores"),
    path("horarios/", views.visor_horarios, name="visor_horarios"),
    path('importar/', views.central_importar_csv, name='central_importar'),
    path('guardias/', views.visor_guardias, name='visor_guardias'),

    # Gestión Principal
    path('ausencias/', views.gestion_ausencias, name='gestion_ausencias'),

    # CRUD Bajas (Rojo)
    path('ausencias/baja/nueva/', views.gestionar_baja, name='crear_baja'),
    path('ausencias/baja/editar/<int:pk>/', views.gestionar_baja, name='editar_baja'),
    path('ausencias/baja/eliminar/<int:pk>/', views.eliminar_baja, name='eliminar_baja'),

    # CRUD Ausencias Puntuales / Por Horas (Amarillo/Warning)
    path('ausencias/puntual/nueva/', views.gestionar_ausencia_puntual, name='crear_ausencia_puntual'),
    path('ausencias/puntual/editar/<int:pk>/', views.gestionar_ausencia_puntual, name='editar_ausencia'),
    path('ausencias/puntual/eliminar/<int:pk>/', views.eliminar_ausencia_puntual, name='eliminar_ausencia'),

    # CRUD Salidas / Excursiones (Verde/Success)
    path('ausencias/salida/nueva/', views.gestionar_salida, name='crear_salida'),
    path('ausencias/salida/editar/<int:pk>/', views.gestionar_salida, name='editar_salida'),
    path('ausencias/salida/eliminar/<int:pk>/', views.eliminar_salida, name='eliminar_salida'),

    # Centro de Control de Guardias
    path('gestion-guardias/', views.gestion_guardias_global, name='gestion_guardias_global'),

    # Ruta para asignar (la que pusimos en el botón del dashboard)
    path('asignar-guardia/<int:registro_id>/', views.asignar_guardia, name='asignar_guardia'),

]

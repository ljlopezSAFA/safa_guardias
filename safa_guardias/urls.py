from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.pagina_inicio, name="index"),
    path("profesores/", views.ver_profesores, name="mostrar_profesores"),
    path("horarios/", views.visor_horarios, name="visor_horarios"),
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

    path('login/', auth_views.LoginView.as_view(template_name='login.html', redirect_authenticated_user=True),
         name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('centro_datos/plantilla/<str:tipo>/', views.descargar_plantilla_csv, name='descargar_plantilla'),

    path('crear-cuenta/', views.crear_cuenta_usuario, name='crear_cuenta_usuario'),

    path('cambiar-centro/', views.cambiar_centro_sesion, name='cambiar_centro_sesion'),

    path('centro-datos/', views.panel_central_datos, name='centro_datos'),

    path('datos/tramos/', views.gestionar_tramos, name='gestionar_tramos'),

    path('centro-datos/importar/', views.central_importar, name='central_importar'),
    path('datos/etapas/', views.gestionar_etapas, name='gestionar_etapas'),
    path('datos/grupos/', views.gestionar_grupos, name='gestionar_grupos'),

    path('datos/materias/', views.gestionar_materias, name='gestionar_materias'),

    path('datos/aulas/', views.gestionar_aulas, name='gestionar_aulas'),
    path('datos/horarios/', views.gestionar_horarios, name='gestionar_horarios'),

    path('datos/guardias/', views.gestionar_guardias, name='gestionar_guardias'),

    path('datos/profesores/', views.gestionar_profesores, name='gestionar_profesores'),

]

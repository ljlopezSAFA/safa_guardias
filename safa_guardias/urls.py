from django.urls import path

from . import views

urlpatterns = [
    path("", views.pagina_inicio, name="index"),
    path("profesores/", views.ver_profesores, name="mostrar_profesores"),
    path("horarios/", views.visor_horarios, name="visor_horarios"),
    path('importar/', views.central_importar_csv, name='central_importar'),
    path('guardias/', views.visor_guardias, name='visor_guardias'),
    path('ausencias-salidas/', views.gestion_ausencias, name='gestion_ausencias'),
    path('bajas/nueva/', views.gestionar_baja, name='crear_baja'),
    path('bajas/editar/<int:pk>/', views.gestionar_baja, name='editar_baja'),
    path('bajas/eliminar/<int:pk>/', views.eliminar_baja, name='eliminar_baja'),

    path('salidas/nueva/', views.gestionar_salida, name='crear_salida'),
    path('salidas/editar/<int:pk>/', views.gestionar_salida, name='editar_salida'),
    path('salidas/eliminar/<int:pk>/', views.eliminar_salida, name='eliminar_salida'),
]

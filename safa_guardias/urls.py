from django.urls import path

from . import views

urlpatterns = [
    path("", views.pagina_inicio, name="index"),
    path("profesores/", views.ver_profesores, name="mostrar_profesores"),
    path("horarios/", views.visor_horarios, name="visor_horarios"),
    path('importar/', views.central_importar_csv, name='central_importar'),
    path('guardias/', views.visor_guardias, name='visor_guardias')
]

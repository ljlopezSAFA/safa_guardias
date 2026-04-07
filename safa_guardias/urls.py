from django.urls import path

from . import views

urlpatterns = [
    path("", views.pagina_inicio, name="index"),

    path("/profesores", views.ver_profesores, name="mostrar_profesores"),
    path("/aulas", views.ver_aulas, name="mostrar_aulas"),
]
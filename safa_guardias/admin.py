from django.contrib import admin
from .models import CentroEscolar, Profesor, Aula, Materia, Grupo, TramoHorario, Horario, HorarioGuardia

# Registramos el Centro Escolar
@admin.register(CentroEscolar)
class CentroEscolarAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'localidad')
    search_fields = ('nombre', 'codigo')

# Registramos el Profesor con campos útiles de búsqueda
@admin.register(Profesor)
class ProfesorAdmin(admin.ModelAdmin):
    list_display = ('apellidos', 'nombre', 'abreviatura', 'rol', 'centro', 'usuario')
    list_filter = ('rol', 'centro')
    search_fields = ('nombre', 'apellidos', 'abreviatura')
    # Opcional: raw_id_fields hace que sea más fácil buscar al User a enlazar si tienes muchos
    raw_id_fields = ('usuario',)
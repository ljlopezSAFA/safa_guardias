from django.shortcuts import render
from safa_guardias.models import Profesor


# Create your views here.
def pagina_inicio(request):
    return render(request, 'inicio.html')


def ver_profesores(request):

    profesores =  Profesor.objects.all()

    return render(request, "profesores.html", { "lista_profesores": profesores })


def ver_aulas(request):
    return render(request, "aulas.html")
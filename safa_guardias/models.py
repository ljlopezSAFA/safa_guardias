from django.db import models


# Create your models here.
class Profesor(models.Model):
    nombre= models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    email = models.EmailField()


class Etapa(models.Model):
    nombre = models.CharField(max_length=100)


class Aula(models.Model):
    nombre = models.CharField(max_length=100)
    pabellon = models.CharField(max_length=250)


class Materia(models.Model):
    nombre = models.CharField(max_length=100)
    abrev = models.CharField(max_length=10)




from django.db import models


# Create your models here.
class Profesor(models.Model):
    nombre= models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    abreviatura = models.CharField(max_length=10, default='', unique=True)


class Aula(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    pabellon = models.CharField(max_length=250)
    abrev = models.CharField(max_length=10, default='', unique=True)


class Materia(models.Model):
    nombre = models.CharField(max_length=100)
    abrev = models.CharField(max_length=10, unique=True)


class Grupo(models.Model):
    # Lista de tuplas simple: (valor_db, etiqueta_legible)
    ETAPAS_CHOICES = [
        ('INF', 'Infantil'),
        ('PRI', 'Primaria'),
        ('ESO', 'ESO'),
        ('BAC', 'Bachillerato'),
        ('CIC', 'Ciclos'),
        ('OTR', 'Otros'),
    ]

    nombre = models.CharField(max_length=100)
    curso = models.CharField(max_length=250)
    etapa = models.CharField(
        max_length=3,
        choices=ETAPAS_CHOICES,
        default='ESO'
    )

    def __str__(self):
        return f"{self.curso} {self.nombre} ({self.get_etapa_display()})"


class TramoHorario(models.Model):
    # Definimos las opciones como constantes
    DIAS_CHOICES = [
        ('L', 'Lunes'),
        ('M', 'Martes'),
        ('X', 'Miércoles'),
        ('J', 'Jueves'),
        ('V', 'Viernes'),
        ('S', 'Sábado'),
        ('D', 'Domingo'),
    ]

    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    dia_semana = models.CharField(
        max_length=1,
        choices=DIAS_CHOICES,
        default='L'
    )

    class Meta:
        verbose_name = "Tramo Horario"
        verbose_name_plural = "Tramos Horarios"
        # Ordenar por defecto por día y hora
        ordering = ['dia_semana', 'hora_inicio']

    def __str__(self):
        return f"{self.get_dia_semana_display()} ({self.hora_inicio} - {self.hora_fin})"



class Horario(models.Model):
    tramo_horario = models.ForeignKey(TramoHorario, on_delete=models.CASCADE)
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE)
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE)
    aula = models.ForeignKey(Aula, on_delete=models.CASCADE)
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE)


# models.py
class HorarioGuardia(models.Model):
    tramo_horario = models.ForeignKey(TramoHorario, on_delete=models.CASCADE)
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE)
    tipo_guardia = models.CharField(max_length=50)  # Ej: GU-CO, OA-GU, HC
    prioridad = models.IntegerField(default=0)

    def __str__(self):
        return f"Guardia {self.tipo_guardia} - {self.profesor.abreviatura} ({self.tramo_horario})"

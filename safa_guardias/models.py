from datetime import time

from django.db import models
from django.utils import timezone


# Create your models here.
class Profesor(models.Model):
    nombre= models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    abreviatura = models.CharField(max_length=10, default='', unique=True)

    class Meta:
        ordering = ['apellidos', 'nombre']


    def __str__(self):
        return f"{self.apellidos} , {self.nombre}"


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


class BajaProfesor(models.Model):
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='bajas')
    fecha_inicio = models.DateField(default=timezone.now, verbose_name="Fecha de inicio")
    # Al permitir null=True y blank=True, si no se rellena, la baja es "indefinida" (sigue activa)
    fecha_fin = models.DateField(null=True, blank=True, verbose_name="Fecha de fin",
                                 help_text="Dejar en blanco si la baja sigue activa")
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        estado = "Activa" if not self.fecha_fin else f"hasta el {self.fecha_fin.strftime('%d/%m/%Y')}"
        return f"Baja: {self.profesor.abreviatura} - {estado}"

    @property
    def esta_activa(self):
        """Método útil para saber si la baja está operativa en el día actual"""
        hoy = timezone.now().date()
        if self.fecha_inicio <= hoy:
            if self.fecha_fin is None or self.fecha_fin >= hoy:
                return True
        return False


class SalidaExcursion(models.Model):
    descripcion = models.CharField(max_length=255, verbose_name="Actividad / Excursión")

    # Fechas por defecto el día actual
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(default=timezone.now)

    # Horas por defecto (puedes ajustar el 8:00 y 14:30 a la jornada de tu centro)
    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(21, 30))

    # Relaciones Mucho a Mucho: una excursión tiene varios profes y grupos, y viceversa
    profesores_acompanantes = models.ManyToManyField(Profesor, related_name='excursiones_asignadas')
    grupos_implicados = models.ManyToManyField(Grupo, related_name='excursiones_asignadas')

    def __str__(self):
        return f"{self.descripcion} ({self.fecha_inicio.strftime('%d/%m/%Y')})"


class AusenciaPuntual(models.Model):
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='ausencias_puntuales')
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha de la ausencia")

    # Rango de horas de la ausencia
    hora_inicio = models.TimeField(verbose_name="Desde las...")
    hora_fin = models.TimeField(verbose_name="Hasta las...")

    motivo = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Ausencia Puntual"
        verbose_name_plural = "Ausencias Puntuales"

    def __str__(self):
        return f"Ausencia: {self.profesor.abreviatura} el {self.fecha.strftime('%d/%m')}"

    @property
    def esta_activa_ahora(self):
        """Comprueba si la ausencia está ocurriendo en este preciso momento"""
        ahora = timezone.now()
        hoy = ahora.date()
        hora_actual = ahora.time()

        if self.fecha == hoy:
            return self.hora_inicio <= hora_actual <= self.hora_fin
        return False


class RegistroGuardia(models.Model):
    ESTADO_CHOICES = [
        ('PENT', 'Pendiente'),
        ('COB', 'Cubierta'),
        ('AUTO', 'Autogestionada (Sin profesor)'),
    ]

    fecha = models.DateField(default=timezone.now)
    tramo_horario = models.ForeignKey(TramoHorario, on_delete=models.CASCADE)
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE)
    aula = models.ForeignKey(Aula, on_delete=models.CASCADE)
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE)

    profesor_ausente = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='clases_perdidas')
    profesor_guardia = models.ForeignKey(Profesor, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='guardias_atendidas')

    estado = models.CharField(max_length=4, choices=ESTADO_CHOICES, default='PENT')
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "Registro de Guardia"
        verbose_name_plural = "Seguimiento de Guardias Diarias"
        unique_together = ['fecha', 'tramo_horario', 'grupo', 'profesor_ausente']

    def __str__(self):
        return f"{self.fecha} - {self.tramo_horario} - {self.grupo}"
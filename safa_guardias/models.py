from datetime import time
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

# 1. MODELO BASE SAAS (NUEVO)
# Al heredar de este modelo, todas tus tablas tendrán el campo centro automáticamente.
class CentroSaaSModel(models.Model):
    centro = models.ForeignKey(
        'CentroEscolar',
        on_delete=models.CASCADE,
        null=True, # Lo dejamos nullable por ahora para que no te dé error al hacer makemigrations con datos existentes
        blank=True
    )

    class Meta:
        abstract = True

# --- MODELOS PRINCIPALES ---

class CentroEscolar(models.Model):
    nombre = models.CharField(max_length=200, verbose_name="Nombre del Centro")
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código del Centro (ej. 23000000)")
    localidad = models.CharField(max_length=100, blank=True, null=True)
    provincia = models.CharField(max_length=100, blank=True, null=True)
    comunidad_autonoma = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Centro Escolar"
        verbose_name_plural = "Centros Escolares"

    def __str__(self):
        return f"{self.nombre} ({self.localidad})"


class Profesor(CentroSaaSModel):
    ROLES_CHOICES = [
        ('ADMIN', 'Administrador del Sistema'),
        ('DIRECCION', 'Dirección'),
        ('JEFATURA', 'Jefatura de Estudios'),
        ('PROFESOR', 'Profesorado'),
    ]

    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    abreviatura = models.CharField(max_length=10)
    email = models.EmailField(blank=True, null=True)
    usuario = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='perfil_profesor')
    rol = models.CharField(max_length=20, choices=ROLES_CHOICES, default='PROFESOR')

    # Añadimos related_name a centro porque al heredar no lo tiene explícito
    centro = models.ForeignKey(CentroEscolar, on_delete=models.CASCADE, related_name='profesores', null=True, blank=True)

    def __str__(self):
        return f"{self.apellidos}, {self.nombre}"

    def es_equipo_directivo(self):
        return self.rol in ['DIRECCION', 'JEFATURA', 'ADMIN']


class Aula(CentroSaaSModel):
    nombre = models.CharField(max_length=100)
    pabellon = models.CharField(max_length=250)
    abrev = models.CharField(max_length=10, default='')

    class Meta:
        unique_together = ['centro', 'abrev'] # Bien! Un centro no puede tener dos aulas con la misma abrev

    def __str__(self):
        return self.nombre


class Materia(CentroSaaSModel):
    nombre = models.CharField(max_length=100)
    abrev = models.CharField(max_length=10)

    class Meta:
        unique_together = ['centro', 'abrev']

    def __str__(self):
        return self.nombre


class Grupo(CentroSaaSModel):
    ETAPAS_CHOICES = [
        ('INF', 'Infantil'), ('PRI', 'Primaria'), ('ESO', 'ESO'),
        ('BAC', 'Bachillerato'), ('CIC', 'Ciclos'), ('OTR', 'Otros'),
    ]

    nombre = models.CharField(max_length=100)
    curso = models.CharField(max_length=250)
    etapa = models.CharField(max_length=3, choices=ETAPAS_CHOICES, default='ESO')

    class Meta:
        # NUEVO: Evitamos que se creen dos "1ºA ESO" en el mismo colegio
        unique_together = ['centro', 'nombre', 'curso', 'etapa']

    def __str__(self):
        return f"{self.curso} {self.nombre} ({self.get_etapa_display()})"


class TramoHorario(CentroSaaSModel):
    DIAS_CHOICES = [
        ('L', 'Lunes'), ('M', 'Martes'), ('X', 'Miércoles'),
        ('J', 'Jueves'), ('V', 'Viernes'), ('S', 'Sábado'), ('D', 'Domingo'),
    ]

    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    dia_semana = models.CharField(max_length=1, choices=DIAS_CHOICES, default='L')

    class Meta:
        verbose_name = "Tramo Horario"
        verbose_name_plural = "Tramos Horarios"
        ordering = ['dia_semana', 'hora_inicio']
        # NUEVO: Un centro no debería tener tramos duplicados el mismo día a la misma hora
        unique_together = ['centro', 'dia_semana', 'hora_inicio', 'hora_fin']

    def __str__(self):
        return f"{self.get_dia_semana_display()} ({self.hora_inicio} - {self.hora_fin})"


# --- TABLAS TRANSACCIONALES (AHORA HEREDAN DE CentroSaaSModel) ---

class Horario(CentroSaaSModel):
    tramo_horario = models.ForeignKey(TramoHorario, on_delete=models.CASCADE)
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE)
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE)
    aula = models.ForeignKey(Aula, on_delete=models.CASCADE)
    grupo = models.ForeignKey(Grupo, on_delete=models.CASCADE)


class HorarioGuardia(CentroSaaSModel):
    tramo_horario = models.ForeignKey(TramoHorario, on_delete=models.CASCADE)
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE)
    tipo_guardia = models.CharField(max_length=50)
    prioridad = models.IntegerField(default=0)

    def __str__(self):
        return f"Guardia {self.tipo_guardia} - {self.profesor.abreviatura} ({self.tramo_horario})"


class BajaProfesor(CentroSaaSModel):
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='bajas')
    fecha_inicio = models.DateField(default=timezone.now, verbose_name="Fecha de inicio")
    fecha_fin = models.DateField(null=True, blank=True, verbose_name="Fecha de fin")
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    # Resto de tus métodos delete() y propiedades se mantienen igual...


class SalidaExcursion(CentroSaaSModel):
    descripcion = models.CharField(max_length=255, verbose_name="Actividad / Excursión")
    fecha_inicio = models.DateField(default=timezone.now)
    fecha_fin = models.DateField(default=timezone.now)
    hora_inicio = models.TimeField(default=time(8, 0))
    hora_fin = models.TimeField(default=time(21, 30))
    profesores_acompanantes = models.ManyToManyField(Profesor, related_name='excursiones_asignadas')
    grupos_implicados = models.ManyToManyField(Grupo, related_name='excursiones_asignadas')

    # Resto de tus métodos se mantienen igual...


class AusenciaPuntual(CentroSaaSModel):
    profesor = models.ForeignKey(Profesor, on_delete=models.CASCADE, related_name='ausencias_puntuales')
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha de la ausencia")
    hora_inicio = models.TimeField(verbose_name="Desde las...")
    hora_fin = models.TimeField(verbose_name="Hasta las...")
    motivo = models.CharField(max_length=255, blank=True, null=True)

    # Resto de tus métodos se mantienen igual...


class RegistroGuardia(CentroSaaSModel):
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
    profesor_guardia = models.ForeignKey(Profesor, on_delete=models.SET_NULL, null=True, blank=True, related_name='guardias_atendidas')
    estado = models.CharField(max_length=4, choices=ESTADO_CHOICES, default='PENT')
    observaciones = models.TextField(blank=True)

    baja_origen = models.ForeignKey('BajaProfesor', on_delete=models.SET_NULL, null=True, blank=True, related_name='guardias_generadas')
    excursion_origen = models.ForeignKey('SalidaExcursion', on_delete=models.SET_NULL, null=True, blank=True, related_name='guardias_generadas')
    ausencia_origen = models.ForeignKey('AusenciaPuntual', on_delete=models.SET_NULL, null=True, blank=True, related_name='guardias_generadas')
    motivo_ausencia = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        verbose_name = "Registro de Guardia"
        verbose_name_plural = "Seguimiento de Guardias Diarias"
        unique_together = ['fecha', 'tramo_horario', 'grupo', 'profesor_ausente']

    def __str__(self):
        return f"{self.fecha} - {self.tramo_horario} - {self.grupo}"
from django import forms

from safa_guardias.models import *


class CentralImportForm(forms.Form):
    TIPO_OPCIONES = [
        ('profesor', 'Profesores'),
        ('aula', 'Aulas'),
        ('materia', 'Materias'),
        ('grupo', 'Grupos'),
        ('tramo', 'Tramos Horarios'),
        ('horario', 'Horarios (Asignaciones)'),
        ('guardia', 'Horas de Guardia'),
    ]

    tipo_dato = forms.ChoiceField(
        choices=TIPO_OPCIONES,
        label="¿Qué vas a importar?",
        widget=forms.Select(attrs={'class': 'form-select rounded-pill'})
    )
    archivo = forms.FileField(
        label="Archivo CSV",
        widget=forms.FileInput(attrs={'class': 'form-control rounded-pill'})
    )



class BajaProfesorForm(forms.ModelForm):
    class Meta:
        model = BajaProfesor
        fields = ['profesor', 'fecha_inicio', 'fecha_fin', 'observaciones']
        widgets = {
            'profesor': forms.Select(attrs={'class': 'form-select'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Ej. Baja por enfermedad...'}),
        }



class SalidaExcursionForm(forms.ModelForm):
    class Meta:
        model = SalidaExcursion
        fields = ['descripcion', 'fecha_inicio', 'fecha_fin', 'hora_inicio', 'hora_fin', 'profesores_acompanantes',
                  'grupos_implicados']
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la actividad'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fin': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'profesores_acompanantes': forms.SelectMultiple(attrs={'class': 'tom-select'}),
            'grupos_implicados': forms.SelectMultiple(attrs={'class': 'tom-select'}),
        }



class AusenciaPuntualForm(forms.ModelForm):
    class Meta:
        model = AusenciaPuntual
        fields = ['profesor', 'fecha', 'hora_inicio', 'hora_fin', 'motivo']
        widgets = {
            'profesor': forms.Select(attrs={'class': 'form-select'}),
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hora_inicio': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'hora_fin': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Breve explicación'}),
        }
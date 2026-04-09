from django import forms


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
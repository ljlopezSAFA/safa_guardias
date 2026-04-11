from django import forms

from safa_guardias.models import *


class CentralImportForm(forms.Form):
    TIPOS_CHOICES = [
        ('centro', 'Centros Escolares (Solo Admin)'),
        ('profesor', 'Profesores'),
        ('aula', 'Aulas'),
        ('materia', 'Materias'),
        ('grupo', 'Grupos'),
        ('tramo', 'Tramos Horarios'),
        ('horario', 'Horario Lectivo'),
        ('guardia', 'Horario de Guardias'),
    ]

    tipo_dato = forms.ChoiceField(choices=TIPOS_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    archivo = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}))


class BajaProfesorForm(forms.ModelForm):
    class Meta:
        model = BajaProfesor
        fields = ['profesor', 'fecha_inicio', 'fecha_fin', 'observaciones']
        widgets = {
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d',
                                            attrs={'type': 'date', 'class': 'form-control shadow-sm'}),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control shadow-sm'}),
            'profesor': forms.Select(attrs={'class': 'form-select tom-select'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control shadow-sm', 'rows': 3}),
        }

    # Sobrescribimos el init para filtrar por centro
    def __init__(self, *args, **kwargs):
        # Extraemos el centro de los kwargs (y lo borramos para que super().__init__ no de error)
        centro = kwargs.pop('centro', None)
        super(BajaProfesorForm, self).__init__(*args, **kwargs)

        if centro:
            # Filtramos el desplegable de profesores
            self.fields['profesor'].queryset = Profesor.objects.filter(centro=centro).order_by('apellidos', 'nombre')


class SalidaExcursionForm(forms.ModelForm):
    class Meta:
        model = SalidaExcursion
        # EXCLUIMOS el centro, se lo asignaremos por debajo en el views.py
        exclude = ['centro']
        widgets = {
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d',
                                            attrs={'type': 'date', 'class': 'form-control shadow-sm'}),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control shadow-sm'}),
            'hora_inicio': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control shadow-sm'}),
            'hora_fin': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control shadow-sm'}),
            'descripcion': forms.TextInput(attrs={'class': 'form-control shadow-sm'}),
            'profesores_acompanantes': forms.SelectMultiple(attrs={'class': 'form-select tom-select'}),
            'grupos_implicados': forms.SelectMultiple(attrs={'class': 'form-select tom-select'}),
        }

    def __init__(self, *args, **kwargs):
        centro = kwargs.pop('centro', None)
        super(SalidaExcursionForm, self).__init__(*args, **kwargs)

        if centro:
            # Filtramos profesores y grupos por el centro del usuario
            self.fields['profesores_acompanantes'].queryset = Profesor.objects.filter(centro=centro).order_by(
                'apellidos')
            self.fields['grupos_implicados'].queryset = Grupo.objects.filter(centro=centro).order_by('nombre')


class AusenciaPuntualForm(forms.ModelForm):
    class Meta:
        model = AusenciaPuntual
        fields = '__all__'
        widgets = {
            'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control shadow-sm'}),
            'hora_inicio': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control shadow-sm'}),
            'hora_fin': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control shadow-sm'}),
            'profesor': forms.Select(attrs={'class': 'form-select tom-select'}),
            'motivo': forms.TextInput(attrs={'class': 'form-control shadow-sm'}),
        }

    def __init__(self, *args, **kwargs):
        centro = kwargs.pop('centro', None)
        super(AusenciaPuntualForm, self).__init__(*args, **kwargs)

        if centro:
            self.fields['profesor'].queryset = Profesor.objects.filter(centro=centro).order_by('apellidos')

class GestorUsuarioForm(forms.Form):
    # 1. Datos de Acceso (Django User)
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="Contraseña")

    # 2. Selector de modo
    TIPO_ASIGNACION = [
        ('nuevo', 'Crear nuevo perfil de Profesor'),
        ('existente', 'Vincular a Profesor existente (Sin cuenta)'),
    ]
    tipo = forms.ChoiceField(
        choices=TIPO_ASIGNACION,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='nuevo'
    )

    # 3. Campos para Profesor Existente
    profesor_existente = forms.ModelChoiceField(
        # Filtramos: Solo profesores que NO tienen cuenta de usuario asignada
        queryset=Profesor.objects.filter(usuario__isnull=True),
        required=False,
        empty_label="--- Selecciona el profesor a vincular ---",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 4. Campos para Nuevo Profesor
    nombre = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    apellidos = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    abreviatura = forms.CharField(max_length=10, required=False,
                                  widget=forms.TextInput(attrs={'class': 'form-control'}))
    rol = forms.ChoiceField(choices=Profesor.ROLES_CHOICES, required=False, initial='PROFESOR',
                            widget=forms.Select(attrs={'class': 'form-select'}))
    centro = forms.ModelChoiceField(
        queryset=CentroEscolar.objects.all(),
        required=False,
        empty_label="--- Selecciona el centro destino ---",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')

        # Comprobar si el username ya existe (User no es unique_together con email por defecto en Django)
        if User.objects.filter(username=cleaned_data.get('username')).exists():
            self.add_error('username', 'Este nombre de usuario ya está en uso.')

        # Validación condicional según el radio button
        if tipo == 'existente':
            if not cleaned_data.get('profesor_existente'):
                self.add_error('profesor_existente', 'Debes seleccionar un profesor para vincular.')
        elif tipo == 'nuevo':
            for campo in ['nombre', 'apellidos', 'abreviatura', 'centro', 'rol']:
                if not cleaned_data.get(campo):
                    self.add_error(campo, f'Este campo es obligatorio para crear un perfil nuevo.')

        return cleaned_data


class GeneradorTramosForm(forms.Form):
    etapas = forms.ModelMultipleChoiceField(
        queryset=Etapa.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input me-2'}),
        label="Etapas a las que aplica este horario",
        required=True
    )

    borrar_anteriores = forms.BooleanField(
        label="Borrar tramos de estas etapas antes de generar",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
        if centro:
            self.fields['etapas'].queryset = Etapa.objects.filter(centro=centro)



class EtapaForm(forms.ModelForm):
    class Meta:
        model = Etapa
        fields = ['nombre', 'siglas']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Educación Secundaria Obligatoria'
            }),
            'siglas': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: ESO'
            }),
        }


class GrupoForm(forms.ModelForm):
    class Meta:
        model = Grupo
        fields = ['curso', 'nombre', 'etapa']
        widgets = {
            'curso': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 1º, 2º, 1º FPB...'
            }),
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: A, B, PMAR...'
            }),
            'etapa': forms.Select(attrs={
                'class': 'form-select'
            }),
        }

    def __init__(self, *args, **kwargs):
        centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
        if centro:
            # Filtramos para que solo salgan las etapas del centro actual
            self.fields['etapa'].queryset = Etapa.objects.filter(centro=centro).order_by('nombre')
            self.fields['etapa'].empty_label = "--- Selecciona una etapa ---"



class MateriaForm(forms.ModelForm):
    class Meta:
        model = Materia
        fields = ['nombre', 'abrev']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Matemáticas Orientadas a las Enseñanzas Académicas'
            }),
            'abrev': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: MAT'
            }),
        }


class AulaForm(forms.ModelForm):
    class Meta:
        model = Aula
        fields = ['nombre', 'pabellon', 'abrev']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Aula 101, Laboratorio de Física...'
            }),
            'pabellon': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Edificio Principal, Planta Baja...'
            }),
            'abrev': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: A101, LABFIS'
            }),
        }
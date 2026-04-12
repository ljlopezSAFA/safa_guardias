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
        queryset=Profesor.objects.none(),  # Lo inicializamos vacío, lo llenamos en el __init__
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

    def __init__(self, *args, **kwargs):
        # Capturamos el centro que le pasaremos desde la vista
        self.centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)

        if self.centro:
            # Filtramos: Solo profesores del centro del admin que NO tienen cuenta asignada
            self.fields['profesor_existente'].queryset = Profesor.objects.filter(
                centro=self.centro,
                usuario__isnull=True
            ).order_by('apellidos', 'nombre')

            # Opcional: Si quieres que al crear un nuevo perfil también se pre-seleccione el centro del admin
            self.fields['centro'].initial = self.centro

    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')

        if User.objects.filter(username=cleaned_data.get('username')).exists():
            self.add_error('username', 'Este nombre de usuario ya está en uso.')

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

class TramoIndividualForm(forms.ModelForm):
    class Meta:
        model = TramoHorario
        fields = ['dia_semana', 'hora_inicio', 'hora_fin', 'es_recreo', 'etapas']
        widgets = {
            'dia_semana': forms.Select(attrs={'class': 'form-select'}),
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'hora_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'es_recreo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'etapas': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
        if centro:
            self.fields['etapas'].queryset = Etapa.objects.filter(centro=centro)


class HorarioForm(forms.ModelForm):
    # Campos "virtuales" que no van directos a la BD del Horario, sino que nos sirven para buscar el Tramo
    dia_semana = forms.ChoiceField(choices=TramoHorario.DIAS_CHOICES, widget=forms.Select(attrs={'class': 'form-select select-buscador'}))
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}))
    hora_fin = forms.TimeField(widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}))
    etapa = forms.ModelChoiceField(queryset=Etapa.objects.none(), widget=forms.Select(attrs={'class': 'form-select select-buscador'}))

    class Meta:
        model = Horario
        # Hemos quitado 'tramo_horario' de aquí porque lo calcularemos en el clean()
        fields = ['grupo', 'materia', 'profesor', 'aula']
        widgets = {
            'profesor': forms.Select(attrs={'class': 'form-select select-buscador'}),
            'materia': forms.Select(attrs={'class': 'form-select select-buscador'}),
            'aula': forms.Select(attrs={'class': 'form-select select-buscador'}),
            'grupo': forms.Select(attrs={'class': 'form-select select-buscador'}),
        }

    def __init__(self, *args, **kwargs):
        self.centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
        if self.centro:
            # Filtramos todos los selectores por centro
            self.fields['profesor'].queryset = Profesor.objects.filter(centro=self.centro)
            self.fields['materia'].queryset = Materia.objects.filter(centro=self.centro).order_by('nombre')
            self.fields['aula'].queryset = Aula.objects.filter(centro=self.centro).order_by('nombre')
            self.fields['grupo'].queryset = Grupo.objects.filter(centro=self.centro).order_by('curso', 'nombre')
            self.fields['etapa'].queryset = Etapa.objects.filter(centro=self.centro)

        # Si estamos editando un horario que ya existe, rellenamos los campos virtuales
        if self.instance and self.instance.pk:
            tramo = self.instance.tramo_horario
            self.initial['dia_semana'] = tramo.dia_semana
            self.initial['hora_inicio'] = tramo.hora_inicio
            self.initial['hora_fin'] = tramo.hora_fin
            # Asignamos la etapa basándonos en el grupo
            if self.instance.grupo:
                self.initial['etapa'] = self.instance.grupo.etapa

    def clean(self):
        cleaned_data = super().clean()
        dia = cleaned_data.get('dia_semana')
        inicio = cleaned_data.get('hora_inicio')
        fin = cleaned_data.get('hora_fin')
        etapa = cleaned_data.get('etapa')

        # Si el usuario ha rellenado los 4 campos de tiempo, buscamos el tramo
        if dia and inicio and fin and etapa:
            try:
                # Buscamos el TramoHorario que coincida
                tramo = TramoHorario.objects.get(
                    centro=self.centro,
                    dia_semana=dia,
                    hora_inicio=inicio,
                    hora_fin=fin,
                    etapas=etapa # Comprobamos que el tramo aplique a esta etapa
                )
                # ¡Magia! Se lo inyectamos a la instancia antes de que Django la guarde
                self.instance.tramo_horario = tramo
            except TramoHorario.DoesNotExist:
                raise forms.ValidationError("No existe un tramo horario configurado con ese día, horas y etapa en este centro. Créalo primero en la gestión de tramos.")
            except TramoHorario.MultipleObjectsReturned:
                # Por si acaso hay duplicados en BD
                tramo = TramoHorario.objects.filter(centro=self.centro, dia_semana=dia, hora_inicio=inicio, hora_fin=fin, etapas=etapa).first()
                self.instance.tramo_horario = tramo

        return cleaned_data


class HorarioGuardiaForm(forms.ModelForm):
    # Campos "virtuales" para buscar el Tramo
    dia_semana = forms.ChoiceField(choices=TramoHorario.DIAS_CHOICES, widget=forms.Select(attrs={'class': 'form-select select-buscador'}))
    hora_inicio = forms.TimeField(widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}))
    hora_fin = forms.TimeField(widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}))
    etapa = forms.ModelChoiceField(queryset=Etapa.objects.none(), widget=forms.Select(attrs={'class': 'form-select select-buscador'}))

    class Meta:
        model = HorarioGuardia
        fields = ['profesor', 'tipo_guardia', 'prioridad']
        widgets = {
            'profesor': forms.Select(attrs={'class': 'form-select select-buscador'}),
            'tipo_guardia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: GU-CO, GU-TU , OAL ...'}),
            'prioridad': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
        if self.centro:
            self.fields['profesor'].queryset = Profesor.objects.filter(centro=self.centro)
            self.fields['etapa'].queryset = Etapa.objects.filter(centro=self.centro)

        # Rellenar campos si estamos editando
        if self.instance and self.instance.pk:
            tramo = self.instance.tramo_horario
            self.initial['dia_semana'] = tramo.dia_semana
            self.initial['hora_inicio'] = tramo.hora_inicio
            self.initial['hora_fin'] = tramo.hora_fin
            # Como el tramo puede tener varias etapas, pillamos la primera para el formulario
            if tramo.etapas.exists():
                self.initial['etapa'] = tramo.etapas.first()

    def clean(self):
        cleaned_data = super().clean()
        dia = cleaned_data.get('dia_semana')
        inicio = cleaned_data.get('hora_inicio')
        fin = cleaned_data.get('hora_fin')
        etapa = cleaned_data.get('etapa')

        if dia and inicio and fin and etapa:
            try:
                # Buscamos el tramo que coincida con esos datos exactos en ese centro
                tramo = TramoHorario.objects.get(
                    centro=self.centro,
                    dia_semana=dia,
                    hora_inicio=inicio,
                    hora_fin=fin,
                    etapas=etapa
                )
                self.instance.tramo_horario = tramo
            except TramoHorario.DoesNotExist:
                raise forms.ValidationError("No existe un tramo horario configurado con ese día, horas y etapa en este centro. Créalo primero.")
            except TramoHorario.MultipleObjectsReturned:
                tramo = TramoHorario.objects.filter(centro=self.centro, dia_semana=dia, hora_inicio=inicio, hora_fin=fin, etapas=etapa).first()
                self.instance.tramo_horario = tramo

        return cleaned_data


class ProfesorForm(forms.ModelForm):
    class Meta:
        model = Profesor
        fields = ['nombre', 'apellidos', 'abreviatura', 'email', 'rol'] # <-- Quitamos 'usuario'
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Laura'}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: García López'}),
            'abreviatura': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: LGL'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@colegio.com'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
            # Ya no necesitamos el widget de usuario aquí
        }

    def __init__(self, *args, **kwargs):
        self.centro = kwargs.pop('centro', None)
        super().__init__(*args, **kwargs)
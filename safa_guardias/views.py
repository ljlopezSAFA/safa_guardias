import csv
import io
from datetime import datetime

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.shortcuts import render, redirect, get_object_or_404

from .forms import *


# Create your views here.
def pagina_inicio(request):
    # CLAVE: Usar localtime para obtener la hora de España (UTC+2 ahora mismo)
    ahora = timezone.localtime(timezone.now())
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    # Mapeo de día de la semana (0 es Lunes en Python)
    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_hoy.weekday()]

    # Buscamos el tramo comparando con la hora local real
    tramo_actual = TramoHorario.objects.filter(
        dia_semana=dia_sem,
        hora_inicio__lte=hora_actual,
        hora_fin__gte=hora_actual
    ).first()

    # Generamos/Actualizamos las guardias para el tramo detectado
    if tramo_actual:
        generar_guardias_del_dia(fecha_hoy)

    # Obtenemos las guardias y los profes disponibles usando el tramo correcto
    guardias_pendientes = RegistroGuardia.objects.filter(
        fecha=fecha_hoy,
        tramo_horario=tramo_actual
    ).select_related('profesor_ausente', 'grupo', 'aula') if tramo_actual else []

    disponibles = obtener_profesores_disponibles(tramo_actual, fecha_hoy) if tramo_actual else []

    context = {
        'tramo_actual': tramo_actual,
        'guardias_pendientes': guardias_pendientes,
        'profesores_disponibles': disponibles,
        'hora_servidor_iso': ahora.isoformat(),  # Esto también irá con el +2 al JS
        'conteo_pendientes': len([g for g in guardias_pendientes if g.estado == 'PENT']) if tramo_actual else 0
    }

    return render(request, 'inicio.html', context)


def ver_profesores(request):
    profesores = Profesor.objects.all()

    return render(request, "profesores.html", {"lista_profesores": profesores})


def ver_aulas(request):
    return render(request, "aulas.html")


def central_importar_csv(request):
    if request.method == 'POST':
        form = CentralImportForm(request.POST, request.FILES)
        if form.is_valid():
            tipo = form.cleaned_data['tipo_dato']
            archivo = request.FILES['archivo']

            try:
                decoded_file = archivo.read().decode('UTF-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string, delimiter=',', quotechar='"')

                # Intentar saltar la cabecera
                try:
                    next(reader)
                except StopIteration:
                    messages.error(request, "El archivo CSV está vacío.")
                    return redirect('central_importar')

                creados, actualizados, errores = 0, 0, 0

                # Usamos atomic para asegurar integridad, pero manejamos errores por fila
                with transaction.atomic():
                    for row in reader:
                        if not row: continue  # Saltar líneas vacías

                        created = False  # Resetear en cada iteración
                        try:
                            if tipo == 'profesor':
                                obj, created = Profesor.objects.update_or_create(
                                    email=row[2].strip().lower(),
                                    defaults={
                                        'nombre': row[0].strip(),
                                        'apellidos': row[1].strip(),
                                        'abreviatura': row[3].strip().upper()
                                    }
                                )
                            elif tipo == 'aula':
                                obj, created = Aula.objects.update_or_create(
                                    nombre=row[0].strip(),
                                    defaults={
                                        'pabellon': row[1].strip(),
                                        'abrev': row[2].strip()
                                    }
                                )
                            elif tipo == 'materia':
                                obj, created = Materia.objects.update_or_create(
                                    abrev=row[1].strip().upper(),
                                    defaults={'nombre': row[0].strip()}
                                )
                            elif tipo == 'grupo':
                                obj, created = Grupo.objects.update_or_create(
                                    nombre=row[0].strip().upper(),
                                    curso=row[1].strip(),
                                    etapa=row[2].strip()
                                )
                            elif tipo == 'tramo':
                                obj, created = TramoHorario.objects.get_or_create(
                                    hora_inicio=row[0].strip(),
                                    hora_fin=row[1].strip(),
                                    dia_semana=row[2].strip().upper()
                                )
                            elif tipo == 'horario':
                                # --- Lógica de Horario con búsqueda segura ---
                                try:
                                    tramo = TramoHorario.objects.get(
                                        dia_semana=row[0].strip().upper(),
                                        hora_inicio=row[1].strip(),
                                        hora_fin=row[2].strip()
                                    )
                                    materia = Materia.objects.get(abrev=row[3].strip().upper())
                                    profesor = Profesor.objects.get(abreviatura=row[4].strip().upper())
                                    aula = Aula.objects.get(abrev=row[5].strip())
                                    grupo = Grupo.objects.get(nombre=row[6].strip().upper())

                                    # Clave de unicidad: Tramo + Grupo + Profesor
                                    obj, created = Horario.objects.update_or_create(
                                        tramo_horario=tramo,
                                        grupo=grupo,
                                        profesor=profesor,
                                        defaults={
                                            'materia': materia,
                                            'aula': aula
                                        }
                                    )

                                except (TramoHorario.DoesNotExist, Materia.DoesNotExist,
                                        Profesor.DoesNotExist, Aula.DoesNotExist,
                                        Grupo.DoesNotExist) as e:
                                    print(f"Error en fila {row}: {e}")
                                    errores += 1
                                    continue  # Salta a la siguiente fila del CSV

                            elif tipo == 'guardia':
                                try:
                                    # Formato esperado: dia, h_ini, h_fin, tipo_guardia, prof_abr, prioridad
                                    tramo = TramoHorario.objects.get(
                                        dia_semana=row[0].strip().upper(),
                                        hora_inicio=row[1].strip(),
                                        hora_fin=row[2].strip()
                                    )
                                    profesor = Profesor.objects.get(abreviatura=row[4].strip().upper())

                                    prioridad_val = int(row[5].strip()) if len(row) > 5 else 0

                                    obj, created = HorarioGuardia.objects.update_or_create(
                                        tramo_horario=tramo,
                                        profesor=profesor,
                                        defaults={
                                            'tipo_guardia': row[3].strip().upper(),
                                            'prioridad': prioridad_val
                                        }
                                    )
                                except (TramoHorario.DoesNotExist, Profesor.DoesNotExist) as e:
                                    print(f"Error en fila guardia {row}: {e}")
                                    errores += 1
                                    continue
                                except ValueError:
                                    print(f"Error de formato numérico en prioridad: {row}")
                                    errores += 1
                                    continue

                            # Contabilizar después de cada operación exitosa
                            if created:
                                creados += 1
                            else:
                                actualizados += 1

                        except IntegrityError as e:
                            print(f"Conflicto de integridad en fila {row}: {e}")
                            errores += 1
                            continue
                        except Exception as e:
                            print(f"Error inesperado en fila {row}: {e}")
                            errores += 1
                            continue

                # Notificaciones finales
                if errores > 0:
                    messages.warning(request,
                                     f'Importación terminada con avisos. {creados} creados, {actualizados} actualizados, {errores} errores. Revisa la consola.')
                else:
                    messages.success(request, f'¡Importación exitosa! {creados} creados y {actualizados} actualizados.')

                return redirect('central_importar')

            except Exception as e:
                messages.error(request, f'Error crítico procesando el archivo: {e}')
                return redirect('central_importar')
    else:
        form = CentralImportForm()

    return render(request, 'importar_csv.html', {'form': form})


def visor_horarios(request):
    etapas = Grupo.ETAPAS_CHOICES
    grupos = Grupo.objects.all().order_by('etapa', 'curso', 'nombre')

    # IMPORTANTE: Pasamos todas las materias para generar los estilos de colores
    materias_todas = Materia.objects.all()

    grupo_id = request.GET.get('grupo')
    etapa_seleccionada = request.GET.get('etapa')

    # Obtenemos los tramos únicos para construir las filas de la tabla
    tramos = TramoHorario.objects.all().order_by('hora_inicio')
    horas_filas = []
    seen_horas = set()
    for t in tramos:
        if (t.hora_inicio, t.hora_fin) not in seen_horas:
            horas_filas.append(t)
            seen_horas.add((t.hora_inicio, t.hora_fin))

    dias_semana = ['L', 'M', 'X', 'J', 'V']
    horario_tabla = []

    if grupo_id:
        clases_grupo = Horario.objects.filter(grupo_id=grupo_id).select_related(
            'materia', 'profesor', 'aula', 'tramo_horario'
        )

        for tramo in horas_filas:
            fila = {'tramo': tramo, 'celdas': []}
            for dia in dias_semana:
                clases_celda = [
                    c for c in clases_grupo
                    if c.tramo_horario.hora_inicio == tramo.hora_inicio and
                       c.tramo_horario.dia_semana == dia
                ]
                fila['celdas'].append(clases_celda)
            horario_tabla.append(fila)

    return render(request, 'visor_horarios.html', {
        'etapas': etapas,
        'grupos': grupos,
        'materias_todas': materias_todas,  # Añadido
        'horario_tabla': horario_tabla,
        'dias_semana': dias_semana,
        'grupo_seleccionado': int(grupo_id) if grupo_id and grupo_id.isdigit() else None,
        'etapa_seleccionada': etapa_seleccionada,
    })


def visor_guardias(request):
    # 1. Obtenemos todos los tramos únicos (horas) para las filas
    # Usamos distinct en hora_inicio para no repetir filas si hay varios días
    tramos_referencia = TramoHorario.objects.values('hora_inicio', 'hora_fin').distinct().order_by('hora_inicio')

    dias = ['L', 'M', 'X', 'J', 'V']
    cuadrante = []

    for tramo in tramos_referencia:
        fila = {
            'inicio': tramo['hora_inicio'],
            'fin': tramo['hora_fin'],
            'columnas': []
        }

        for dia in dias:
            # Buscamos todas las guardias para este tramo y este día
            guardias_celda = HorarioGuardia.objects.filter(
                tramo_horario__hora_inicio=tramo['hora_inicio'],
                tramo_horario__dia_semana=dia
            ).select_related('profesor')

            fila['columnas'].append(guardias_celda)

        cuadrante.append(fila)

    return render(request, 'visor_guardias.html', {
        'cuadrante': cuadrante,
        'dias': dias
    })


def gestion_ausencias(request):
    hoy = timezone.now().date()

    # 1. Obtenemos las bajas activas:
    # Empezaron hoy o antes, Y (no tienen fecha fin O su fecha fin es hoy o posterior)
    bajas_activas = BajaProfesor.objects.filter(
        fecha_inicio__lte=hoy
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)
    ).select_related('profesor')

    # 2. Obtenemos excursiones activas hoy o en el futuro
    excursiones = SalidaExcursion.objects.filter(
        fecha_fin__gte=hoy
    ).prefetch_related('profesores_acompanantes', 'grupos_implicados').order_by('fecha_inicio')

    context = {
        'bajas_activas': bajas_activas,
        'excursiones': excursiones,
    }

    return render(request, 'gestion_ausencias.html', context)


# --- CRUD PARA BAJAS ---
def gestionar_baja(request, pk=None):
    baja = get_object_or_404(BajaProfesor, pk=pk) if pk else None
    titulo = "Editar Baja de Profesor" if pk else "Registrar Nueva Baja"

    if request.method == 'POST':
        form = BajaProfesorForm(request.POST, instance=baja)
        if form.is_valid():
            form.save()
            messages.success(request, f"Baja {'actualizada' if pk else 'registrada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        form = BajaProfesorForm(instance=baja)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-person-dash-fill', 'color': 'danger'})


def eliminar_baja(request, pk):
    baja = get_object_or_404(BajaProfesor, pk=pk)
    baja.delete()
    messages.success(request, "Baja eliminada del sistema.")
    return redirect('gestion_ausencias')


# --- CRUD PARA EXCURSIONES ---
def gestionar_salida(request, pk=None):
    salida = get_object_or_404(SalidaExcursion, pk=pk) if pk else None
    titulo = "Editar Salida/Excursión" if pk else "Programar Nueva Salida"

    if request.method == 'POST':
        form = SalidaExcursionForm(request.POST, instance=salida)
        if form.is_valid():
            form.save()
            messages.success(request, f"Excursión {'actualizada' if pk else 'programada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        form = SalidaExcursionForm(instance=salida)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-bus-front-fill', 'color': 'success'})


def eliminar_salida(request, pk):
    salida = get_object_or_404(SalidaExcursion, pk=pk)
    salida.delete()
    messages.success(request, "Salida/Excursión cancelada y eliminada.")
    return redirect('gestion_ausencias')


def gestion_ausencias(request):
    hoy = timezone.now().date()

    bajas = BajaProfesor.objects.filter(
        fecha_inicio__lte=hoy
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)
    )

    # Añadimos la consulta de ausencias puntuales de hoy
    ausencias_hoy = AusenciaPuntual.objects.filter(fecha=hoy).order_by('hora_inicio')

    excursiones = SalidaExcursion.objects.filter(fecha_fin__gte=hoy).order_by('fecha_inicio')

    return render(request, 'gestion_ausencias.html', {
        'bajas_activas': bajas,
        'ausencias_hoy': ausencias_hoy,
        'excursiones': excursiones
    })


# CRUD para Ausencia Puntual (mismo patrón que los anteriores)
def gestionar_ausencia_puntual(request, pk=None):
    ausencia = get_object_or_404(AusenciaPuntual, pk=pk) if pk else None
    if request.method == 'POST':
        form = AusenciaPuntualForm(request.POST, instance=ausencia)
        if form.is_valid():
            form.save()
            messages.success(request, "Ausencia puntual registrada.")
            return redirect('gestion_ausencias')
    else:
        form = AusenciaPuntualForm(instance=ausencia)

    return render(request, 'formulario_ausencias.html', {
        'form': form,
        'titulo': "Permiso por Horas" if pk else "Nueva Ausencia Puntual",
        'color': 'warning',  # Usamos el amarillo pastel que configuramos
        'icono': 'bi-clock-history'
    })


def eliminar_ausencia_puntual(request, pk):
    ap = get_object_or_404(SalidaExcursion, pk=pk)
    ap.delete()
    messages.success(request, "Ausencia puntual cancelada y eliminada.")
    return redirect('gestion_ausencias')


def generar_guardias_del_dia(fecha_consulta=None):
    if not fecha_consulta:
        fecha_consulta = timezone.now().date()

    # 1. Mapeo de día de la semana para el modelo TramoHorario
    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_consulta.weekday()]

    # 2. Obtener IDs de grupos que NO están en el centro (Excursiones)
    excursiones_hoy = SalidaExcursion.objects.filter(
        fecha_inicio__lte=fecha_consulta,
        fecha_fin__gte=fecha_consulta
    )
    ids_grupos_fuera = []
    for exc in excursiones_hoy:
        ids_grupos_fuera.extend(exc.grupos_implicados.values_list('id', flat=True))

    # 3. Obtener IDs de profesores ausentes
    # Por Baja
    bajas_ids = BajaProfesor.objects.filter(
        fecha_inicio__lte=fecha_consulta
    ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_consulta)).values_list('profesor_id', flat=True)

    # Por Excursión
    profes_exc_ids = []
    for exc in excursiones_hoy:
        profes_exc_ids.extend(exc.profesores_acompanantes.values_list('id', flat=True))

    # Combinamos ausencias totales
    total_ausentes_ids = set(list(bajas_ids) + profes_exc_ids)

    # 4. Escanear Horario y crear registros de guardia
    # Solo miramos clases de grupos que SÍ están en el centro
    clases_hoy = Horario.objects.filter(
        tramo_horario__dia_semana=dia_sem
    ).exclude(grupo_id__in=ids_grupos_fuera)

    registros_creados = 0
    for clase in clases_hoy:
        necesita_guardia = False

        # ¿El profe está ausente (baja o excursión)?
        if clase.profesor.id in total_ausentes_ids:
            necesita_guardia = True

        # ¿El profe tiene una ausencia puntual en este tramo?
        # (Aquí habría que comparar las horas del tramo con las de la ausencia puntual)
        ausencia_puntual = AusenciaPuntual.objects.filter(
            profesor=clase.profesor,
            fecha=fecha_consulta,
            hora_inicio__lte=clase.tramo_horario.hora_inicio,
            hora_fin__gte=clase.tramo_horario.hora_fin
        ).exists()

        if ausencia_puntual:
            necesita_guardia = True

        if necesita_guardia:
            RegistroGuardia.objects.get_or_create(
                fecha=fecha_consulta,
                tramo_horario=clase.tramo_horario,
                grupo=clase.grupo,
                aula=clase.aula,
                materia=clase.materia,
                profesor_ausente=clase.profesor
            )
            registros_creados += 1

    return registros_creados


def obtener_profesores_disponibles(tramo, fecha):
    if not tramo:
        return []

    # 1. Profesores que tienen asignada una guardia en este tramo (HorarioGuardia)
    en_guardia_ids = HorarioGuardia.objects.filter(
        tramo_horario=tramo
    ).values_list('profesor_id', flat=True)

    # 2. Profesores "liberados" porque su grupo está de excursión
    # (Ellos se quedan en el centro pero no tienen a su grupo)
    grupos_fuera_ids = SalidaExcursion.objects.filter(
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('grupos_implicados__id', flat=True)

    liberados_ids = Horario.objects.filter(
        tramo_horario=tramo,
        grupo_id__in=grupos_fuera_ids
    ).values_list('profesor_id', flat=True)

    # Combinamos ambos grupos de candidatos
    candidatos_ids = set(list(en_guardia_ids) + list(liberados_ids))

    # 3. FILTRAR QUIÉNES NO ESTÁN REALMENTE (Los que están de baja o excursión)
    # Profesores de baja
    bajas_ids = BajaProfesor.objects.filter(
        fecha_inicio__lte=fecha
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
    ).values_list('profesor_id', flat=True)

    # Profesores que han salido de excursión
    profes_fuera_ids = SalidaExcursion.objects.filter(
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('profesores_acompanantes__id', flat=True)

    # Profesores con ausencia puntual en este tramo exacto
    ausencias_puntuales_ids = AusenciaPuntual.objects.filter(
        fecha=fecha,
        hora_inicio__lte=tramo.hora_inicio,
        hora_fin__gte=tramo.hora_fin
    ).values_list('profesor_id', flat=True)

    # Unificamos todos los IDs de gente que NO está en el centro
    total_ausentes_ids = set(list(bajas_ids) + list(profes_fuera_ids) + list(ausencias_puntuales_ids))

    # 4. Resultado final: Candidatos que NO están en la lista de ausentes
    disponibles = Profesor.objects.filter(
        id__in=candidatos_ids
    ).exclude(
        id__in=total_ausentes_ids
    ).distinct()

    return disponibles


def gestion_guardias_global(request):
    # 1. Recibir parámetros del formulario (fecha y tramo)
    fecha_str = request.GET.get('fecha')
    tramo_id = request.GET.get('tramo')

    # 2. Configurar la fecha a consultar (por defecto, hoy)
    if fecha_str:
        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_consulta = timezone.localtime().date()
    else:
        fecha_consulta = timezone.localtime().date()

    # 3. Determinar el día de la semana para los tramos
    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_consulta.weekday()]

    # 4. Obtener todos los tramos de ESE DÍA para el selector
    tramos_del_dia = TramoHorario.objects.filter(dia_semana=dia_sem).order_by('hora_inicio')

    # 5. Configurar el tramo a consultar
    tramo_seleccionado = None
    if tramo_id:
        tramo_seleccionado = tramos_del_dia.filter(id=tramo_id).first()

    if not tramo_seleccionado and tramos_del_dia.exists():
        tramo_seleccionado = tramos_del_dia.first()

    # 6. GENERAR GUARDIAS para la fecha solicitada
    # ¡Importante! Esto evalúa quién estará de baja/excursión ese día futuro
    generar_guardias_del_dia(fecha_consulta)

    # 7. Obtener datos para la vista
    guardias_dia = RegistroGuardia.objects.filter(fecha=fecha_consulta).select_related('profesor_ausente', 'grupo',
                                                                                       'tramo_horario')

    # Guardias específicas del tramo seleccionado
    guardias_tramo = guardias_dia.filter(tramo_horario=tramo_seleccionado) if tramo_seleccionado else []

    # Profesores disponibles para el tramo seleccionado
    disponibles = obtener_profesores_disponibles(tramo_seleccionado, fecha_consulta) if tramo_seleccionado else []

    # Resumen para los "badges" de los tramos (para ver rápido dónde hay jaleo)
    resumen_tramos = guardias_dia.values('tramo_horario').annotate(
        pendientes=Count('id', filter=Q(estado='PENT')),
        total=Count('id')
    )

    # Convertimos el resumen a un diccionario para usarlo fácil en el template
    info_tramos = {item['tramo_horario']: item for item in resumen_tramos}

    context = {
        'fecha_consulta': fecha_consulta,
        'tramos_del_dia': tramos_del_dia,
        'tramo_seleccionado': tramo_seleccionado,
        'guardias_tramo': guardias_tramo,
        'profesores_disponibles': disponibles,
        'info_tramos': info_tramos,
    }
    return render(request, 'gestion_guardias_global.html', context)


def calcular_porcentaje_compatibilidad(profesores_disponibles, registro, fecha):
    """
    Calcula el % de idoneidad de cada profesor integrando: prioridad, horas impartidas al grupo y etapa educativa.
    """
    lista_evaluada = []
    tramo = registro.tramo_horario
    grupo_afectado = registro.grupo
    etapa_afectada = grupo_afectado.etapa

    # 1. Preparamos los IDs para la consulta optimizada
    profes_ids = [p.id for p in profesores_disponibles]

    # 2. Obtenemos TODOS los horarios de estos profesores disponibles en la semana
    # para saber cuántas horas le dan al grupo y en qué etapas enseñan.
    horarios_profes = Horario.objects.filter(profesor_id__in=profes_ids).select_related('grupo')

    datos_docencia = {pid: {'horas_grupo': 0, 'etapas': set()} for pid in profes_ids}
    for h in horarios_profes:
        datos_docencia[h.profesor_id]['etapas'].add(h.grupo.etapa)
        if h.grupo_id == grupo_afectado.id:
            datos_docencia[h.profesor_id]['horas_grupo'] += 1

    # 3. Diccionario con la prioridad de las guardias asignadas en este tramo
    guardias_dict = {
        hg.profesor_id: hg.prioridad
        for hg in HorarioGuardia.objects.filter(tramo_horario=tramo)
    }

    # 4. Conjunto de profesores liberados por excursiones en este tramo
    grupos_fuera_ids = SalidaExcursion.objects.filter(
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('grupos_implicados__id', flat=True)

    liberados_ids = set(Horario.objects.filter(
        tramo_horario=tramo,
        grupo_id__in=grupos_fuera_ids
    ).values_list('profesor_id', flat=True))

    # 5. EVALUACIÓN Y CÁLCULO
    for prof in profesores_disponibles:
        porcentaje = 0

        # A) FACTOR BASE (Disponibilidad / Prioridad) -> Max 70%
        if prof.id in liberados_ids:
            porcentaje += 70
        elif prof.id in guardias_dict:
            prioridad = guardias_dict[prof.id]
            # Fórmula: P0=70, P1=60, P2=50, P3=40, P4=30, P5=20
            puntos_base = max(20, 70 - (prioridad * 10))
            porcentaje += puntos_base

        # B) FACTOR AFINIDAD DE GRUPO Y HORAS -> Max ~20%
        horas_grupo = datos_docencia[prof.id]['horas_grupo']
        if horas_grupo > 0:
            porcentaje += 10  # +10% por conocer al grupo
            porcentaje += (horas_grupo * 2)  # +2% por cada hora impartida a la semana
            prof.conoce_grupo = True
            prof.horas_grupo = horas_grupo
        else:
            prof.conoce_grupo = False
            prof.horas_grupo = 0

        # C) FACTOR ETAPA EDUCATIVA (Misma etapa) -> Max 10%
        if etapa_afectada in datos_docencia[prof.id]['etapas']:
            porcentaje += 10
            prof.misma_etapa = True
        else:
            prof.misma_etapa = False

        # Limitamos a 100% máximo
        prof.porcentaje = min(100, porcentaje)
        lista_evaluada.append(prof)

    # 6. Ordenamos la lista de mayor a menor porcentaje
    lista_evaluada.sort(key=lambda x: x.porcentaje, reverse=True)

    return lista_evaluada


def asignar_guardia(request, registro_id):
    registro = get_object_or_404(RegistroGuardia, id=registro_id)

    if request.method == 'POST':
        profesor_id = request.POST.get('profesor_id')

        if profesor_id:
            profesor = get_object_or_404(Profesor, id=profesor_id)
            registro.profesor_guardia = profesor
            registro.estado = 'COB'
            registro.observaciones = request.POST.get('observaciones', '')
            registro.save()
            messages.success(request, f'Guardia asignada a {profesor.abreviatura}')

        elif 'autogestion' in request.POST:
            registro.profesor_guardia = None
            registro.estado = 'AUTO'
            registro.observaciones = request.POST.get('observaciones', '')
            registro.save()
            messages.info(request, 'Guardia marcada como autogestionada')

        return redirect(f"/gestion-guardias/?fecha={registro.fecha.isoformat()}&tramo={registro.tramo_horario.id}")

    # Si es GET, mostramos el formulario
    disponibles_crudos = obtener_profesores_disponibles(registro.tramo_horario, registro.fecha)

    # PASAMOS LOS PROFESORES POR NUESTRA FUNCIÓN DE PORCENTAJES
    disponibles_con_porcentaje = calcular_porcentaje_compatibilidad(disponibles_crudos, registro, registro.fecha)

    context = {
        'registro': registro,
        'profesores_disponibles': disponibles_con_porcentaje,
    }
    return render(request, 'asignar_guardia.html', context)
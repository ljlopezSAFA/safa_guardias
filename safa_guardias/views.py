import csv, io

from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone

from .models import *
from .forms import CentralImportForm


# Create your views here.
def pagina_inicio(request):
    ahora = timezone.localtime()
    hora_actual = ahora.time()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_actual = dias_map[ahora.weekday()]

    tramo_actual = TramoHorario.objects.filter(
        dia_semana=dia_actual,
        hora_inicio__lte=hora_actual,
        hora_fin__gte=hora_actual
    ).first()

    profes_de_guardia = []
    if tramo_actual:
        # Buscamos quiénes tienen asignada guardia en este tramo
        profes_de_guardia = HorarioGuardia.objects.filter(
            tramo_horario=tramo_actual
        ).select_related('profesor')

    context = {
        'tramo_actual': tramo_actual,
        'profes_de_guardia': profes_de_guardia,
        'hora_servidor_iso': ahora.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    return render(request, 'inicio.html', context)


def ver_profesores(request):

    profesores =  Profesor.objects.all()

    return render(request, "profesores.html", { "lista_profesores": profesores })


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
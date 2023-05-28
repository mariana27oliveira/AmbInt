# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


# This is a simple example for a custom action which utters "Hello World!"

# from typing import Any, Text, Dict, List
#
# from rasa_sdk import Action, Tracker
# from rasa_sdk.executor import CollectingDispatcher
#
#
# class ActionHelloWorld(Action):
#
#     def name(self) -> Text:
#         return "action_hello_world"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         dispatcher.utter_message(text="Hello World!")
#
#         return []


import locale
from datetime import timedelta, datetime, date
from typing import Any, Text, Dict, List

import dateparser
import pymongo
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

locale.setlocale(locale.LC_TIME, 'pt_PT.UTF-8')

SLOT_NOME = "nome"
SLOT_ESPECICALIDADE = "especialidade"
SLOT_UTENTE = "nr_utente"
SLOT_DATA = "data"
SLOT_NOVA_DATA = "nova_data"
SLOT_HORA = "hora"
SLOT_TURNO = "preferencia"

DBNAME = "ClinicaSaudeTotal"
AGENDA = "Agenda"
HORARIO = "Horario"
ESPECIALIDADE = ['Cardiologia', 'Dermatologia', 'Ginecologia', 'Ortopedia',
                 'Oftalmologia', 'Pediatria', 'Psicologia', 'Fisioterapia']

horarios_clinica = {
    "manha": ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30"],
    "tarde": ["14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00"]
}


class AgendarConsultaAction(Action):
    def name(self) -> Text:
        return "agendar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)
        data = tracker.get_slot(SLOT_DATA)
        nome = tracker.get_slot(SLOT_NOME)
        numero_utente = tracker.get_slot(SLOT_UTENTE)
        turno = tracker.get_slot(SLOT_TURNO)


        parsed_date = valida_data(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet(SLOT_DATA, None)]

        # Ligar à base de dados
        client, db = fetch_connection()
        try:
            # Verificar disponibilidade da data
            horario_livre = procura_horario_livre(self, parsed_date, especialidade, turno, db)
            if not horario_livre:
                dias = procura_dias_livres(self, parsed_date, especialidade, turno, db)
                if len(dias) > 0:
                    mensagem = f"\nLamento, mas não há disponibilidade para a data pretendida. " \
                               f"Aqui estão alguns dias com disponibilidade para de {turno}:\n - " + "\n - ".join(
                        dias) + \
                               f"\nPor favor, indique qual o dia que pretende agendar."
                else:
                    mensagem = f"Lamento, mas não há mais disponibilidade em {especialidade} nos próximos 15 dias. " \
                               f"\nPretende sugerir uma data posterior a isso?"

                dispatcher.utter_message(text=mensagem)
                return [SlotSet(SLOT_DATA, None)]

            # Agendar a consulta
            agendar_consulta(db, parsed_date, horario_livre, numero_utente, especialidade)
        finally:
            # Fechar a ligação
            client.close()

        # Mensagem de resposta
        mensagem = f"{nome}, a sua consulta de {especialidade} foi agendada para o dia {parsed_date} às {horario_livre}."
        dispatcher.utter_message(text=mensagem)

        return []


def agendar_consulta(db, data, hora, numero_utente, especialidade):
    consulta = {
        "especialidade": especialidade,
        "data": data,
        "hora": hora,
        "numero_utente": numero_utente
    }
    db[AGENDA].insert_one(consulta)


def procura_horario_livre(self, parsed_date, especialidade, turno, db):
    hora, todos = procura_todos_horarios_livre(self, parsed_date, especialidade, turno, db)
    return hora


def procura_todos_horarios_livre(self, parsed_date, especialidade, turno, db, procura_todos=False):
    horarios = None
    if turno is None:
        horarios = horarios_clinica["manha"] + horarios_clinica["tarde"]
    elif turno.lower() == "manha" or turno.lower() == "manhã":
        horarios = horarios_clinica["manha"]
    elif turno.lower() == "tarde":
        horarios = horarios_clinica["tarde"]

    proximo_horario_livre = None
    todos = []
    for horario in horarios:
        agendamento = db[AGENDA].find_one(
            {
                "especialidade": especialidade,
                "data": parsed_date,
                "hora": horario
            }
        )
        if agendamento is None:
            # Horário livre
            proximo_horario_livre = horario
            if (procura_todos):
                todos.append(proximo_horario_livre)
            else:
                break
    return proximo_horario_livre, todos


def procura_dias_livres(self, data, especialidade, turno, db):
    dias = []
    data_obj = datetime.strptime(data, "%d-%m-%Y")
    data_obj += timedelta(days=1)

    for _ in range(15):
        horario_livre = procura_horario_livre(self, data_obj.strftime("%d-%m-%Y"), especialidade, turno, db)
        if horario_livre:
            dias.append(formata_data(data_obj.strftime("%d-%m-%Y")))
            if len(dias) == 7:
                return dias
            data_obj += timedelta(days=1)

    return dias


def procura_horarios_livres(self, data, especialidade, turno, db):
    horarios = []
    data_obj = datetime.strptime(data, "%d-%m-%Y")
    data_limite = data_obj + timedelta(days=15)

    while data_obj <= data_limite:
        _, todos = procura_todos_horarios_livre(self, data_obj.strftime("%d-%m-%Y"), especialidade, turno, db,
                                                procura_todos=True)
        if todos:
            for hora in todos:
                data = formata_data(data_obj.strftime("%d-%m-%Y"))
                horarios.append(f"- {data} às {hora}\n")
                if len(horarios) == 7:
                    return horarios
            data_obj += timedelta(days=1)

    return horarios


def valida_data(self, data, dispatcher):
    # Converter a data num objeto data
    try:
        parsed_date = dateparser.parse(data, languages=["pt"])
    except:
        parsed_date = None

    # Verificar se a conversão foi bem-sucedida
    if parsed_date is not None:
        if parsed_date.date() >= date.today():
            return parsed_date.strftime("%d-%m-%Y")
        else:
            # Caso a conversão da data tenha falhado ou a data seja no passado
            mensagem = "A data fornecida deve ser superior a hoje. Por favor, indique uma nova data."
            dispatcher.utter_message(text=mensagem)
            return None
    else:
        # Caso a conversão da data tenha falhado
        mensagem = f"Peço desculpa, não consegui entender a data [{data}] fornecida. " \
                   f"Por favor, utilize por exemplo o formato dia-mês."
        dispatcher.utter_message(text=mensagem)
        return None


class ValidaEspecialidade(Action):
    def name(self) -> Text:
        return "valida_especialidade"
    
    def run (self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)

        if especialidade not in ESPECIALIDADE:
            mensagem = f"Lamento, mas não temos a especialidade [{especialidade}] na Clínica Saúde Total. " \
                   f"Dispomos apenas das seguintes especialidades médicas: \t\n" + \
                   "\n\t".join(ESPECIALIDADE) + "\nQual das especialidades pretende?"
            dispatcher.utter_message(text=mensagem)
            return [SlotSet("especialidade", None)]
        else:
            dispatcher.utter_message(text=f"A especialidade é {especialidade}")
            return []

class CancelarConsultaAction(Action):
    def name(self) -> Text:
        return "cancelar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)
        data = tracker.get_slot(SLOT_DATA)
        nome = tracker.get_slot(SLOT_NOME)
        numero_utente = tracker.get_slot(SLOT_UTENTE)

        valida = valida_especialidade(self, especialidade, dispatcher)
        if not valida:
            return [SlotSet(SLOT_ESPECICALIDADE, None)]

        parsed_date = valida_data(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet(SLOT_DATA, None)]

        client, db = fetch_connection()
        try:
            # Verificar se existe uma marcação para o dia referido pelo utilizador
            marcacao = get_marcacao_do_utente(parsed_date, especialidade, numero_utente, db)
            if marcacao:
                # remover marcação
                remover_consulta(db, especialidade, numero_utente, parsed_date)
                # Mensagem de resposta
                hora = marcacao["hora"]
                mensagem = f"{nome}, a sua consulta de {especialidade} marcada para o dia {parsed_date} às {hora} foi cancelada."
                dispatcher.utter_message(text=mensagem)

            else:

                mensagem = f"Não existe nenhuma marcação para si no dia {parsed_date} em {especialidade}. Pode repetir a data da sua marcação?"
                dispatcher.utter_message(text=mensagem)
                return [SlotSet(SLOT_DATA, None)]

        finally:
            # Fechar a ligação
            client.close()

        return [SlotSet(SLOT_ESPECICALIDADE, None)]


def remover_consulta(db, especialidade, numero_utente, parsed_date):
    consulta = {
        "especialidade": especialidade,
        "data": parsed_date,
        "numero_utente": numero_utente
    }
    db[AGENDA].delete_one(consulta)


def get_marcacao_do_utente(data, especialidade, numero_utente, db):
    # Verificar se existe algum registo para o utente no dia referiado
    marcacao = db[AGENDA].find_one(
        {"data": data, "especialidade": especialidade, "numero_utente": numero_utente})
    if marcacao:
        return marcacao
    return None


class ActionResetSlots(Action):
    def name(self) -> Text:
        return "action_reset_slots"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        return [SlotSet(SLOT_NOME, None), SlotSet(SLOT_ESPECICALIDADE, None), SlotSet(SLOT_DATA, None),
                SlotSet(SLOT_UTENTE, None)]


def fetch_connection():
    # Ligar à base de dados
    client = pymongo.MongoClient("mongodb://localhost:9000")
    try:
        db = client[DBNAME]
        return client, db
    except:
        # Fechar a ligação
        client.close()


class ActionPreferencia(Action):
    def name(self) -> Text:
        return "action_preferencia"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        preferencia = tracker.get_slot("preferencia")

        if preferencia not in ['manha', 'tarde']:
            dispatcher.utter_message(text="Só pode inserir: manha ou tarde")
            return [SlotSet("preferencia", None)]
        else:
            dispatcher.utter_message(text=f"Ok!! A Preferência é {preferencia}")
            return []


class ListarConsultasAction(Action):
    def name(self) -> Text:
        return "action_listar_consultas"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        numero_utente = tracker.get_slot(SLOT_UTENTE)

        client, db = fetch_connection()
        try:
            consultas = list(db[AGENDA].find({"numero_utente": numero_utente}).sort("data", 1))

            if len(consultas) == 0:
                dispatcher.utter_message("Neste momento não tem consultas agendadas. O que pretende fazer?")
            else:
                consultas_por_especialidade = {}
                for consulta in consultas:
                    especialidade = consulta["especialidade"]
                    if especialidade not in consultas_por_especialidade:
                        consultas_por_especialidade[especialidade] = []

                    consultas_por_especialidade[especialidade].append(consulta)

                message = "Aqui estão as suas consultas agendadas:\n"

                for especialidade, consultas_em_especialidade in consultas_por_especialidade.items():
                    message += f"\n{especialidade}:\n"
                    for consulta in consultas_em_especialidade:
                        data = formata_data(consulta["data"])
                        hora = consulta["hora"]
                        message += f"- {data} às {hora}\n"

                dispatcher.utter_message(message)
        finally:
            client.close()
        return []


def formata_data(data_str):
    data_obj = datetime.strptime(data_str, "%d-%m-%Y")
    data_formatada = data_obj.strftime("%d de %B")
    return data_formatada


class ConfirmarReagendarConsultaAction(Action):
    def name(self) -> Text:
        return "action_confirmar_reagendar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        nome = tracker.get_slot(SLOT_NOME)
        numero_utente = tracker.get_slot(SLOT_UTENTE)
        data = tracker.get_slot(SLOT_DATA)
        nova_data = tracker.get_slot(SLOT_NOVA_DATA)
        turno = tracker.get_slot(SLOT_TURNO)

        parsed_date = valida_data(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet(SLOT_DATA, None)]

        new_parsed_date = valida_data(self, nova_data, dispatcher)
        if new_parsed_date is None:
            return [SlotSet(SLOT_NOVA_DATA, None)]

        client, db = fetch_connection()
        try:
            # Verificar se existe uma marcação para o dia referido pelo utilizador
            marcacao = db[AGENDA].find_one({"data": parsed_date, "numero_utente": numero_utente})
            if marcacao:
                especialidade = marcacao["especialidade"]
                hora = procura_horario_livre(self, new_parsed_date, especialidade, turno, db)

                mensagem = f"Com certeza {nome}! \nEstive a verificar e tenho uma vaga a disponível para uma consulta de {especialidade} no dia {new_parsed_date} às {hora}. \nDeseja fazer a remarcação da consulta?"
                dispatcher.utter_message(text=mensagem)
                # Atualizar os slots com a nova data e horário
                return [
                    SlotSet(SLOT_NOVA_DATA, new_parsed_date),
                    SlotSet("hora", hora),
                    SlotSet(SLOT_ESPECICALIDADE, especialidade)]
            else:
                mensagem = f"Peço desculpa {nome}, não encontrei nenhuma marcação para si no dia {parsed_date}. Pode repetir a data da sua marcação?"
                dispatcher.utter_message(text=mensagem)
                return [SlotSet(SLOT_DATA, None)]
        finally:
            client.close()


class ReagendarConsultaAction(Action):
    def name(self) -> Text:
        return "action_reagendar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        nome = tracker.get_slot(SLOT_NOME)
        numero_utente = tracker.get_slot(SLOT_UTENTE)
        data = tracker.get_slot(SLOT_DATA)
        nova_data = tracker.get_slot(SLOT_NOVA_DATA)
        hora = tracker.get_slot(SLOT_HORA)
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)

        parsed_date = valida_data(self, data, dispatcher)
        if data is None:
            return [SlotSet(SLOT_DATA, None)]

        new_parsed_date = valida_data(self, nova_data, dispatcher)
        if new_parsed_date is None:
            return [SlotSet(SLOT_NOVA_DATA, None)]

        client, db = fetch_connection()
        try:
            # agendar nova
            agendar_consulta(db, new_parsed_date, hora, numero_utente, especialidade)
            # remover antiga
            remover_consulta(db, especialidade, numero_utente, parsed_date)
            mensagem = f"Muito bem {nome}! \nConforme o seu pedido, a sua consulta de {especialidade} foi então " \
                       f"reagendada para o dia {new_parsed_date} às {hora}.\nPosso ajudar em mais alguma coisa?"
            dispatcher.utter_message(text=mensagem)
            return [SlotSet(SLOT_DATA, None), SlotSet(SLOT_NOVA_DATA, None), SlotSet(SLOT_HORA, None),
                    SlotSet(SLOT_ESPECICALIDADE, None), SlotSet(SLOT_TURNO, None)]

        except ValueError as e:
            mensagem = f"Ocorreu um erro na remarcação da sua consulta: {str(e)}. Por favor, tente novamente."
            dispatcher.utter_message(text=mensagem)

        except Exception as e:
            mensagem = f"Ocorreu um erro na remarcação da sua consulta! Por favor, tente novamente."
            dispatcher.utter_message(text=mensagem)
        finally:
            client.close()


class ActionListarDisponibilidade(Action):
    def name(self) -> Text:
        return "action_listar_disponibilidade"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        nome = tracker.get_slot(SLOT_NOME)
        nova_data = tracker.get_slot(SLOT_NOVA_DATA)
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)
        turno = tracker.get_slot(SLOT_TURNO)

        new_parsed_date = valida_data(self, nova_data, dispatcher)
        if new_parsed_date is None:
            return [SlotSet(SLOT_NOVA_DATA, None)]

        client, db = fetch_connection()
        try:
            horarios = procura_horarios_livres(self, new_parsed_date, especialidade, turno, db)
            if len(horarios) > 0:
                mensagem = f"Nesse caso {nome}, posso sugerir alguns horários que temos disponíveis:\n" + \
                           "".join(horarios) + "\nAlgum deles seria indicado para si?"
            else:
                mensagem = f"Lamento, mas não tenho disponibilidade para {especialidade} nos próximos 15 dias. " \
                           f"\nPretende sugerir uma nova data?"
            dispatcher.utter_message(text=mensagem)

            return [SlotSet(SLOT_NOVA_DATA, None), SlotSet(SLOT_HORA, None)]
        finally:
            client.close()

'''
def valida_especialidade(self, especialidade, dispatcher):
    if especialidade not in ESPECIALIDADE:
        mensagem = f"Lamento, mas não temos a especialidade [{especialidade}] na Clínica Saúde Total. " \
                   f"Dispomos apenas das seguintes especialidades médicas: \t\n" + \
                   "\n\t".join(ESPECIALIDADE) + "\nQual das especialidades pretende?"
        dispatcher.utter_message(text=mensagem)
        return False
    return True



valida = valida_especialidade(self, especialidade, dispatcher)
        if not valida:
            return [SlotSet(SLOT_ESPECICALIDADE, None)]    


'''
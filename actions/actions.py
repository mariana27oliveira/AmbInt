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


from datetime import datetime, timedelta
from typing import Any, Text, Dict, List

import dateparser
import pymongo
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

SLOT_NOME = "nome"
SLOT_ESPECICALIDADE = "especialidade"
SLOT_UTENTE = "nr_utente"
SLOT_DATA = "data"
SLOT_TURNO = "preferencia"

DBNAME = "ClinicaSaudeTotal"
AGENDA = "Agenda"
HORARIO = "Horario"
ESPECIALIDADE = ['Cardiologia', 'Dermatologia', 'Ginecologia', 'Ortopedia',
                 'Oftalmologia', 'Pediatria', 'Psicologia', 'Fisioterapia']


class AgendarConsultaAction(Action):
    def name(self) -> Text:
        return "agendar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot(SLOT_ESPECICALIDADE)
        data = tracker.get_slot(SLOT_DATA)
        nome = tracker.get_slot(SLOT_NOME)
        numero_utente = tracker.get_slot(SLOT_UTENTE)
        turno = tracker.get_slot(SLOT_TURNO)

        valida = valida_especialidade(self, especialidade, dispatcher)
        if not valida:
            return [SlotSet(SLOT_ESPECICALIDADE, None), SlotSet("requested_slot", SLOT_ESPECICALIDADE)]

        parsed_date = valida_data(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet(SLOT_DATA, None), SlotSet("requested_slot", SLOT_DATA)]

        # Ligar à base de dados
        client, db = fetch_connection()
        try:
            # Verificar disponibilidade da data
            horario_livre = procura_horario_livre(self, parsed_date, especialidade, turno, db)
            if not horario_livre:
                dias = procura_dias_livres(self, parsed_date, especialidade, turno, db)
                if len(dias) > 0:
                    mensagem = f"\nLamento, mas não há disponibilidade para a data pretendida. " \
                               f"Aqui estão alguns dias com disponibilidade para de {turno}:\n\t" + "\n\t".join(dias) + \
                               f"\nPor favor, indique qual o dia que pretende agendar."
                else:
                    mensagem = f"Lamento, mas não há mais disponibilidade em {especialidade} nos próximos 15 dias. " \
                               f"\nPretende sugerir uma data posterior a isso?"

                dispatcher.utter_message(text=mensagem)
                return [SlotSet(SLOT_DATA, None), SlotSet("requested_slot", SLOT_DATA)]

            # Agendar a consulta
            consulta = {
                "especialidade": especialidade,
                "data": parsed_date,
                "hora": horario_livre,
                "numero_utente": numero_utente
            }
            db[AGENDA].insert_one(consulta)
        finally:
            # Fechar a ligação
            client.close()

        # Mensagem de resposta
        mensagem = f"{nome}, a sua consulta de {especialidade} foi agendada para o dia {parsed_date} às {horario_livre}."
        dispatcher.utter_message(text=mensagem)

        return []


horarios_clinica = {
    "manha": ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30"],
    "tarde": ["14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00"]
}


def procura_horario_livre(self, parsed_date, especialidade, turno, db):
    horarios = None
    if turno is None:
        horarios = horarios_clinica["manha"] + horarios_clinica["tarde"]
    elif turno.lower() == "manha" or turno.lower() == "manhã":
        horarios = horarios_clinica["manha"]
    elif turno.lower() == "tarde":
        horarios = horarios_clinica["tarde"]

    proximo_horario_livre = None
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
            break
    return proximo_horario_livre


def procura_dias_livres(self, data, especialidade, turno, db):
    dias = []
    data_obj = datetime.strptime(data, "%d-%m-%Y")
    data_obj += timedelta(days=1)

    for _ in range(15):
        horario_livre = procura_horario_livre(self, data_obj.strftime("%d-%m-%Y"), especialidade, turno, db)
        if horario_livre:
            dias.append(data_obj.strftime("%d-%m-%Y"))
            if len(dias) == 7:
                return dias
            data_obj += timedelta(days=1)

    return dias


def valida_data(self, data, dispatcher):
    # Converter a data num objeto data
    try:
        parsed_date = dateparser.parse(data, languages=["pt"])
    except:
        parsed_date = None

    # Verificar se a conversão foi bem-sucedida
    if parsed_date is not None:
        return parsed_date.strftime("%d-%m-%Y")
    else:
        # Caso a conversão da data tenha falhado
        mensagem = f"Peço desculpa, não consegui entender a data [{data}] fornecida. " \
                   f"Por favor, utilize por exemplo o formato dia-mês."
        dispatcher.utter_message(text=mensagem)
        return None


def valida_especialidade(self, especialidade, dispatcher):
    if especialidade not in ESPECIALIDADE:
        mensagem = f"Lamento, mas não temos a especialidade [{especialidade}] na Clínica Saúde Total. " \
                   f"Dispomos apenas das seguintes especialidades médicas: \t\n" + \
                   "\n\t".join(ESPECIALIDADE) + "\nQual das especialidades pretende?"
        dispatcher.utter_message(text=mensagem)
        return False
    return True


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
            return [SlotSet(SLOT_ESPECICALIDADE, None), SlotSet("requested_slot", SLOT_ESPECICALIDADE)]

        parsed_date = valida_data(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet(SLOT_DATA, None), SlotSet("requested_slot", SLOT_DATA)]

        client, db = fetch_connection()
        try:
            # Verificar se existe uma marcação para o dia referido pelo utilizador
            marcacao = self.get_marcacao_do_utente(parsed_date, especialidade, numero_utente, db)
            if marcacao:
                # remover marcação
                consulta = {
                    "especialidade": especialidade,
                    "data": parsed_date,
                    "numero_utente": numero_utente
                }
                db[AGENDA].remove(consulta)
                # Mensagem de resposta
                hora = marcacao["hora"]
                mensagem = f"{nome}, a sua consulta de {especialidade} marcada para o dia {parsed_date} às {hora} foi cancelada."
                dispatcher.utter_message(text=mensagem)

            else:

                mensagem = f"Não existe nenhuma marcação para si no dia {parsed_date} em {especialidade}. Pode repetir a data da sua marcação?"
                dispatcher.utter_message(text=mensagem)
                return [SlotSet(SLOT_DATA, None), SlotSet("requested_slot", SLOT_DATA)]

        finally:
            # Fechar a ligação
            client.close()

        return [SlotSet(SLOT_ESPECICALIDADE, None), SlotSet(SLOT_DATA, None)]

    def get_marcacao_do_utente(self, data, especialidade, numero_utente, db):
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

#        if preferencia:
        if preferencia not in ['manha', 'tarde']:
          dispatcher.utter_message(text="Só pode inserir: manha ou tarde")
          return [SlotSet("preferencia", None)]
        else:
          dispatcher.utter_message(text=f"Ok!! A Preferência é {preferencia}")
          return []
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


from typing import Text, List, Any, Dict
from rasa_sdk import Tracker, Action
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet


ALLOWED_MANHA_TARDE = ['manha', 'tarde']

'''
class ValidateNameForm(Action):

    def name(self) -> Text:
        return "validate_name_form"

    def validate_manha_tarde(
          self,
          slot_value: Any,
          dispatcher: CollectingDispatcher,
          tracker: Tracker,
          domain: DomainDict,
    ) -> Dict[Text, Any]:
       """Validate 'manha_tarde' value."""
       if slot_value.lower() not in ALLOWED_MANHA_TARDE:
          dispatcher.utter_message(text=f"Só pode inserir: manha ou tarde")
          return {"manha_tarde": slot_value}
       dispatcher.utter_message(text=f"Ok! A Preferência é {slot_value}")
       return {"manha_tarde": slot_value}
'''


from datetime import datetime, timedelta
from typing import Any, Text, Dict, List

import dateparser
import pymongo
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher


class AgendarConsultaAction(Action):
    def name(self) -> Text:
        return "agendar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot("especialidade")
        data = tracker.get_slot("data")
        nome = tracker.get_slot("nome")
        numero_utente = tracker.get_slot("nr_utente")

        parsed_date = validaData(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet("data", None)]

        # Ligar à base de dados
        client, agenda_collection = fetch_connection(self)
        try:
            # Verificar disponibilidade da data
            disponivel = self.verificar_disponibilidade(parsed_date, especialidade, agenda_collection)
            if not disponivel:
                dias = self.procura_dias_livres(parsed_date, especialidade, agenda_collection)
                if len(dias) > 0:
                    mensagem = f"\nLamento, mas não há disponibilidade para a data pretendida. " \
                               "Aqui estão algumas opções disponíveis nos próximos dias:\n\t" + "\n\t".join(dias) + \
                               f"\nPor favor, indique qual o dia que pretende agendar."
                else:
                    mensagem = f"Lamento, mas não há mais disponibilidade em {especialidade} nos próximos 15 dias. " \
                               f"\nPretende sugerir uma data posterior a isso?"

                dispatcher.utter_message(text=mensagem)
                return [SlotSet("data", None)]

            # Agendar a consulta
            consulta = {
                "especialidade": especialidade,
                "data": parsed_date,
                "numero_utente": numero_utente
            }
            agenda_collection.insert_one(consulta)
        finally:
            # Fechar a ligação
            client.close()

        # Mensagem de resposta
        mensagem = f"{nome}, a sua consulta de {especialidade} foi agendada para o dia {parsed_date}."
        dispatcher.utter_message(text=mensagem)

        return []

    def verificar_disponibilidade(self, data, especialidade, agenda_collection):
        # Verificar se há disponibilidade na data pretendida
        ocupado = agenda_collection.find_one({"data": data, "especialidade": especialidade})
        if not ocupado:
            return True
        return False

    def procura_dias_livres(self, data, especialidade, agenda_collection):
        dias = []
        data_obj = datetime.strptime(data, "%d-%m-%Y")
        data_obj += timedelta(days=1)

        for _ in range(15):
            ocupado = agenda_collection.find_one(
                {"data": data_obj.strftime("%d-%m-%Y"), "especialidade": especialidade})
            if not ocupado:
                dias.append(data_obj.strftime("%d-%m-%Y"))
                if len(dias) == 7:
                    return dias
                data_obj += timedelta(days=1)

        return dias


def validaData(self, data, dispatcher):
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
        mensagem = "Peço desculpa, não consegui entender a data fornecida. " \
                   "Por favor, utilize por exemplo o formato dia/mês."
        dispatcher.utter_message(text=mensagem)
        return None


def fetch_connection(self):
    # Ligar à base de dados
    client = pymongo.MongoClient("mongodb://localhost:9000")
    try:
        db = client["ClinicaSaudeTotal"]
        agenda_collection = db["Agenda"]
        return client, agenda_collection
    except:
        # Fechar a ligação
        client.close()




class CancelarConsultaAction(Action):
    def name(self) -> Text:
        return "cancelar_consulta"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        especialidade = tracker.get_slot("especialidade")
        data = tracker.get_slot("data")
        nome = tracker.get_slot("nome")
        numero_utente = tracker.get_slot("nr_utente")

        parsed_date = validaData(self, data, dispatcher)
        if parsed_date is None:
            return [SlotSet("data", None)]

        client, agenda_collection = fetch_connection(self)
        try:
            # Verificar se existe uma marcação para o dia referido pelo utilizador
            marcado = self.existe_marcacao_do_utente(parsed_date, especialidade, numero_utente, agenda_collection)
            if marcado:
                # remover marcação
                consulta = {
                    "especialidade": especialidade,
                    "data": parsed_date,
                    "numero_utente": numero_utente
                }
                agenda_collection.remove(consulta)
                # Mensagem de resposta
                mensagem = f"{nome}, a sua consulta de {especialidade} marcada para o dia {parsed_date} foi cancelada."
                dispatcher.utter_message(text=mensagem)

            else:

                mensagem = f"Não existe nenhuma marcação para si no dia {parsed_date} em {especialidade}. Pode repetir a data da sua marcação?"
                dispatcher.utter_message(text=mensagem)
                return [SlotSet("data", None)]

        finally:
            # Fechar a ligação
            client.close()

        return []

    def existe_marcacao_do_utente(self, data, especialidade, numero_utente, agenda_collection):
        # Verificar se existe algum registo para o utente no dia referiado
        ocupado = agenda_collection.find_one(
            {"data": data, "especialidade": especialidade, "numero_utente": numero_utente})
        if ocupado:
            return True
        return False



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
    

'''
  - intent: schedule_name
  - action: utter_schedule_name
  - intent: name
  - action: utter_schedule_sns
  - intent: sns_number
  - action: utter_confirmation
  - intent: confirmation
  - action: utter_speciality
  - intent: speciality
  - action: utter_city
  - intent: city
  - action: utter_hospitals
  - intent: hospital
  - action: utter_date
  - intent: date_confirmation


    - intent: name
    entities:
    - name
  - slot_was_set:
    - name: "name"
  - action: action_save_name


POR ALGUMA COISA DA AULA DE DIREITO NO RELATÓRIO



- story: marcar consulta 
  steps:
  - intent: saudacao
  - action: utter_saudacao
  - intent: primeiro_nome
  - action: utter_questionar
  - intent: consulta
  - action: utter_numero_utente
  - intent: numero_utente
  - action: utter_ultimo_nome
  - intent: ultimo_nome
  - action: utter_especialidade
  - intent: especialidade
  - action: utter_data
  - intent: data
  - action: utter_confirmacao
  - intent: confirmacao
  - action: utter_despedida

  
- story: marcar consulta 
  steps:
  - intent: saudacao
  - action: utter_saudacao
  - intent: nome
  - action: utter_questionar
  - intent: consulta
  - action: utter_numero_utente
  - intent: numero_utente
  - action: utter_especialidade
  - intent: especialidade
  - action: utter_data
  - intent: data
  - action: utter_preferencia
  - intent: preferencia
  - action: action_preferencia
  - action: agendar_consulta
  - intent: despedida
  - action: utter_despedida

'''
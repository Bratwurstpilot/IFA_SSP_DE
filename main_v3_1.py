import streamlit as st
import numpy as np
import pandas as pd

from sqlalchemy import create_engine, MetaData, Table, update, delete, text, insert
from sqlalchemy.orm import sessionmaker

import requests
import datetime
import logging
import json
import time
import pyodbc
import re

import smtplib
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Streamlit app
def main():
    # Config
    st.set_page_config(layout="wide", page_title="IFA - SSP")

    # Initialize Session States
    if "disable_email" not in st.session_state:
        st.session_state.disable_email = True

    if "selection" in st.session_state:
        selection = st.session_state.selection

    # Title
    st.title("IFA Operation Schichtprotokoll")

    # Select date
    selected_date = st.date_input("Datum:", format='DD.MM.YYYY', max_value=datetime.date.today(), min_value=datetime.date.today()-datetime.timedelta(days=180))
    selected_date_str_de = selected_date.strftime('%d.%m.%Y')

    # Select Shift
    selected_shift = st.selectbox("Schicht:", ["Nachtschicht", "Frühschicht", "Spätschicht"], index=preselect_shift())
   
    # Translate selected shift
    if selected_shift == 'Nachtschicht':
        selected_shift_id = 'night_shift'
    elif selected_shift == 'Frühschicht':
        selected_shift_id = 'early_shift'
    elif selected_shift == 'Spätschicht':
        selected_shift_id = 'late_shift'

    # Select Department
    selected_department = st.selectbox("Abteilung:", list(hierarchy.keys()))

    # Select Line
    selected_line = st.selectbox("Linie:", list(hierarchy[selected_department].keys()))

    # Select Subline
    selected_subline = st.selectbox("Teillinie:", list(hierarchy[selected_department][selected_line].keys()))

    # Load Data
    if "data" in st.session_state:
        st.info("Beim erneuten Laden der Daten gehen nicht gespeicherte Änderungen verloren.")

    if st.button('Daten laden für: ' + selected_shift + ' - ' + selected_subline):

        # Set workplace_list for selected subline
        if selected_department in ['OP1', 'OP2']:   
            selected_workplaces = list(hierarchy[selected_department][selected_line][selected_subline])
        else:
            selected_workplaces = selected_workplaces_log
        
        # Preselect Workplaces OP
        selected_workplaces_list = ""
        for wpl in selected_workplaces:
            selected_workplaces_list += "'" + wpl + "',"
        selected_workplaces_list = selected_workplaces_list[:-1]             

        # Collect Selection
        selection = {
            'date': selected_date,
            'date_str_de': selected_date_str_de,
            'shift': selected_shift,
            'shift_id': selected_shift_id,
            'department': selected_department,
            'line': selected_line,
            'subline': selected_subline,
            'workplaces': selected_workplaces,
            'workplaces_list': selected_workplaces_list}

        st.session_state.selection = selection

        # Load Data for OP
        if selected_department in ['OP1', 'OP2']:     
            # Running Data Requests
            print("########## LOADING DATA ###################")
            print("Selection: " + str(selection))

            progressbar_text = "Lade Daten für das SSP..."
            progress_completion = 0
            progressbar = st.progress(progress_completion, text=progressbar_text)

            # Meta Data
            progressbar_text = "Sammle Meta Daten..."
            progressbar.progress(progress_completion, text=progressbar_text)
            data_meta = collect_data_meta_information(selection)
            progress_completion = 0.1

            # Quantitiy
            progressbar_text = "Berechne zurückgemeldete Mengen pro Maschine..."
            progressbar.progress(progress_completion, text=progressbar_text) 
            data_quantity_machine = collect_data_quantity_machine(selection, progressbar, progressbar_text)
            progress_completion = 0.5

            # Disturbance
            progressbar_text = "Suche nach Maschinenstörungen..."
            progressbar.progress(progress_completion, text=progressbar_text)       
            data_disturbance = collect_data_disturbance(selection, progressbar, progressbar_text)
            progress_completion = 0.9

            # General Data
            progressbar_text = "Kalkuliere Kennzahlen..."
            progressbar.progress(progress_completion, text=progressbar_text)
            data_general = collect_data_general(selection, data_quantity_machine)
            data_general_input = data_general
            progress_completion = 100
            
            # Close Progress Bar
            progressbar.progress(progress_completion, text=progressbar_text)
            time.sleep(1)
            progressbar.empty()
        
            st.session_state.data = {
                'data_meta': data_meta,
                'data_quantity_machine': data_quantity_machine,
                'data_disturbance': data_disturbance,
                'data_general': data_general,           
                'data_general_input': data_general_input            
            }
        
        # Load Data for LOG
        else:
            # Dummy DF
            data_quantity_machine = pd.DataFrame([{
                "workplace_id": '1',
                "output_relevant": False,
                "OK": 0,
                "NOK": 0}])
            
            data_disturbance = pd.DataFrame({
                'workplace_machine': [],
                'source': [],
                'problem': [],
                'start': [],
                'duration_minutes': [],
                'ssp_comment': [],
                'solution': [],
                'solved': []})
            
            data_disturbance['start'] = pd.to_datetime(data_disturbance['start'])
            data_disturbance['start'] = data_disturbance['start'].dt.time
            data_disturbance['solved'] = data_disturbance['solved'].astype(bool)
            data_disturbance['ssp_comment'] = data_disturbance['ssp_comment'].astype(str)
            data_disturbance['solution'] = data_disturbance['solution'].astype(str)

            # Load Data
            data_meta = collect_data_meta_information(selection)
            data_general = collect_data_general(selection, data_quantity_machine)
            data_general_input = data_general
            data_disturbance = collect_data_disturbance_log(selection)

            st.session_state.data = {
                'data_meta': data_meta,
                'data_quantity_machine': data_quantity_machine,
                'data_disturbance': data_disturbance,
                'data_general': data_general,           
                'data_general_input': data_general_input}
            
            print(st.session_state)
            data_quantity_machine.to_clipboard()

    
    # Show Form for Data Input
    if "data" in st.session_state:
        with st.form("ssp_form", clear_on_submit=False):
            # Get Data from session state
            data_meta = st.session_state.data['data_meta']
            data_quantity_machine = st.session_state.data['data_quantity_machine']
            data_disturbance = st.session_state.data['data_disturbance']
            data_general = st.session_state.data['data_general']
            data_general_input = st.session_state.data['data_general_input']

            # Header
            st.header('SSP: ' + selection['subline'] + ' - ' + selection['date'].strftime('%d.%m.%Y') + ' - ' + selection['shift'])
            st.divider()

            # Meta Data
            st.subheader("Allgemeine Informationen")
            data_schiko_name_input = st.text_input(label="Schichtleiter:", placeholder="Bitte Namen eintragen...", value=data_general['name'], max_chars=50)
            st.text("Teamleiter: " + data_meta['responsible'])
            st.text("Zeit bis Schichtende: " + data_meta['time_till_shift_end'])
            st.divider()

            # Display for OP
            if st.session_state.selection['department'] in ['OP1', 'OP2']:
                # KPI's
                st.subheader("KPI's")
                kpi = {'Kennzahl': ['Ausbringung', 'Ausschuss', 'Mitarbeiter Anwesend', 'Ausbringung pro Mitarbeiter'],
                        'Wert': [data_general['kpi_output_ok'], data_general['kpi_output_nok'], data_general['kpi_employees_present'], round(data_general['kpi_output_per_employee'], 1)]}
                data_df_kpi = pd.DataFrame(kpi)
                data_kpi_input = st.data_editor(data_df_kpi, hide_index=True, disabled=['Kennzahl'])

                st.divider()
                
                # Machine and Materialnumber
                st.subheader("Ausbringung pro Maschine")
                data_quantity_machine.sort_values(by=['output_relevant', 'workplace_id', 'OK'], ascending=[False, True, False], inplace=True)
                data_quantity_machine_input = st.data_editor(data_quantity_machine, hide_index=True,
                                                    column_order=["workplace_id", "machine_name", "output_relevant", "OK", "NOK", "production_time", "halt_time", "setup_time", "comment"],
                                                    column_config=
                                                    {"workplace_id": st.column_config.Column("Arbeitsplatz"),
                                                        "machine_name": st.column_config.Column("Maschine"),
                                                    "output_relevant": st.column_config.CheckboxColumn("Ausbringungsrelevant"),
                                                    "OK": st.column_config.NumberColumn("IO"),
                                                    "NOK": st.column_config.NumberColumn("NIO"),
                                                    "production_time": st.column_config.Column("Produktionszeit"),
                                                    "halt_time": st.column_config.Column("Verlustzeit"),
                                                    "setup_time": st.column_config.Column("Rüstzeit"),
                                                    "comment": st.column_config.TextColumn("Kommentar")},
                                                        disabled=['workplace_id', 'machine_name', 'output_relevant', 'OK', 'NOK', 'production_time', 'halt_time', 'setup_time'])
                st.divider()

                # Disturbances
                st.subheader("Maschinenstörungen")

                # Create Selection for workplace_id + machine names
                selected_workplaces_machine_names = df_wpl_info[df_wpl_info['workplace_id'].isin(selection['workplaces'])]
                selected_workplaces_machine_names.loc[:, 'machine_name'] = selected_workplaces_machine_names['machine_name'].fillna('NOT FOUND')
                selected_workplaces_machine_names = (selected_workplaces_machine_names['workplace_id'] + ' - ' + selected_workplaces_machine_names['machine_name']).tolist()

                # Create Data Editor
                data_disturbance['workplace_machine'] = data_disturbance['workplace_id'] + ' - ' + data_disturbance['machine_name']
                data_disturbance.sort_values(by=['workplace_machine', 'start'], ascending=True, inplace=True)
                data_disturbance.reset_index(drop=True, inplace=True)
                data_disturbance_input = st.data_editor(data_disturbance, num_rows="dynamic", hide_index=True,
                                                    column_order=["workplace_machine", "source", "problem", "start", "duration_minutes", "sf_comment", "ssp_comment", "solution", "solved"],
                                                    column_config=
                                                    {"workplace_machine": st.column_config.SelectboxColumn("Arbeitsplatz", options=selected_workplaces_machine_names, required=True),
                                                    "source": st.column_config.TextColumn("Quelle", default="SSP"),
                                                    "problem": st.column_config.Column("Problembeschreibung"),
                                                    "start":  st.column_config.TimeColumn("Beginn der Sörung"),
                                                    "duration_minutes": st.column_config.NumberColumn("Dauer in Minuten", format="%d min", min_value=0, max_value=480),
                                                    "sf_comment": st.column_config.Column("Forcam Kommentar"),
                                                    "ssp_comment": st.column_config.Column("SSP Kommentar"),
                                                    "solution": st.column_config.Column("Eingeleitete Maßnahme"),
                                                        "solved": st.column_config.CheckboxColumn("Erledigt", default=False)},
                                                        disabled=["source", "sf_comment"])
                
                # Clean Input Dataframe
                data_disturbance_input.dropna(subset=['workplace_machine'], inplace=True)
                if len(data_disturbance_input) != 0:
                    data_disturbance_input[['workplace_id', 'machine_name']] = data_disturbance_input['workplace_machine'].str.split(' - ', n=1, expand=True)
                data_disturbance_input = data_disturbance_input.drop('workplace_machine', axis=1)
                data_disturbance_input['date_id'] = selection['date'].strftime('%Y-%m-%d')
                data_disturbance_input['shift_id'] = selection['shift_id']
                st.divider()

            # Display for LOG
            else:

                # KPI's
                st.subheader("Personalinfo")
                kpi = {'Kennzahl': ['Mitarbeiter Anwesend (Schicht)', 'Krank (Tag)', 'Urlaub (Tag)'],
                        'Wert': [data_general['kpi_employees_present'], data_general['kpi_output_nok'], data_general['kpi_output_ok']]}
                data_df_kpi = pd.DataFrame(kpi)
                data_kpi_input = st.data_editor(data_df_kpi, hide_index=True, disabled=['Anwesend Schicht', 'Krank', 'Urlaub'])


                # Dummy DF quantity machine
                data_quantity_machine_input = pd.DataFrame()

                # LOG Table
                st.subheader("Übersicht")

                selected_problem_log = ['', 'Sonstiges']
                
                data_disturbance_input = st.data_editor(data_disturbance, num_rows="dynamic", hide_index=True,
                                                    column_order=["workplace_id", "source", "problem", "start", "duration_minutes", "ssp_comment", "solution", "solved"],
                                                    column_config=
                                                    {"workplace_id": st.column_config.SelectboxColumn("Bereich", options=selected_workplaces_log, required=True),
                                                    "source": st.column_config.TextColumn("Quelle", default="SSP"),
                                                    "problem": st.column_config.TextColumn("Problem", default=""),
                                                    "start":  st.column_config.TimeColumn("Beginn der Sörung"),
                                                    "duration_minutes": st.column_config.NumberColumn("Dauer in Minuten", format="%d min", min_value=0, max_value=480),
                                                    "ssp_comment": st.column_config.TextColumn("SSP Kommentar", default=""),
                                                    "solution": st.column_config.TextColumn("Eingeleitete Maßnahme", default=""),
                                                        "solved": st.column_config.CheckboxColumn("Erledigt", default=False)},
                                                        disabled=["source", "sf_comment"])
                # Clean DF
                data_disturbance_input['date_id'] = selection['date'].strftime('%Y-%m-%d')
                data_disturbance_input['shift_id'] = selection['shift_id']
                
                st.divider()
                

            # Nachricht für die Schichtübergabe
            st.subheader("Nachricht für die Schichtübergabe hinzufügen") 
            data_schichtubergabe_input = st.text_area(label="Nachricht Schichtübergabe", value=data_general['message'], label_visibility="collapsed", placeholder="Bei Bedarf hier eine Nachricht für die Schichtübergabe eingeben", max_chars=999)
            st.divider()

            # Save Data
            st.subheader("Speichern")
            submitted = st.form_submit_button("Daten speichern")
            if submitted:
                if len(data_schiko_name_input) == 0:
                    st.error("Bitte Namen eingeben! Das SSP wurde nicht gespeichert.")
                else:
                    print("SAVE submitted")
                    with st.spinner('Die Daten werden gespeichert...'):
                        # Save for OP
                        if st.session_state.selection['department'] in ['OP1', 'OP2']:
                            # Create General Input Data and save all
                            data_general_input['name'] = data_schiko_name_input
                            data_general_input['message'] = data_schichtubergabe_input
                            data_general_input['kpi_output_ok'] = data_kpi_input.iloc[0, 1]
                            data_general_input['kpi_output_nok'] = data_kpi_input.iloc[1, 1]
                            data_general_input['kpi_employees_present'] = data_kpi_input.iloc[2, 1]
                            if data_general_input['kpi_employees_present'] > 0:
                                data_general_input['kpi_output_per_employee'] = data_general_input['kpi_output_ok'] / data_general_input['kpi_employees_present']
                            else: data_general_input['kpi_output_per_employee'] = 0

                            
                        # Save for LOG
                        else:
                            # Create General Input Data and save all
                            data_general_input['name'] = data_schiko_name_input
                            data_general_input['message'] = data_schichtubergabe_input
                            data_general_input['kpi_employees_present'] = data_kpi_input.iloc[0, 1]
                            data_general_input['kpi_output_nok'] = data_kpi_input.iloc[1, 1]
                            data_general_input['kpi_output_ok'] = data_kpi_input.iloc[2, 1]
                            if data_general_input['kpi_employees_present'] > 0:
                                data_general_input['kpi_output_per_employee'] = 0
                            else: data_general_input['kpi_output_per_employee'] = 0

                        save_all_data(selection, data_general_input, data_quantity_machine_input, data_disturbance_input)

                        # Return Message
                        time.sleep(1)
                        st.success("Daten wurden erfolgreich zwischengespeichert.")

                        # Enable E-Mail
                        st.session_state.disable_email = False


        if "data" in st.session_state:
            # Send E-Mail and save_data
            st.subheader("E-Mail Versenden")
            st.text('Genutzter E-Mail Verteiler: ' + data_meta['mail'])

            email_cc = st.text_input(label="CC E-Mail Adresse:", placeholder="Bei mehreren Empfängern die Adressen per Komma trennen. z.B.: max.mustermann@ifa-group.com, jane.doe@ifa-group.com", max_chars=500)
            
            if st.session_state.disable_email:
                st.info('Damit das SSP versendet werden kann, müssen die Daten über den Button "Daten speichern" gesichert werden.')
            
            
            if st.button('E-Mail versenden', disabled=st.session_state.disable_email):
                if len(data_schiko_name_input) == 0:
                    st.error("Bitte Namen eingeben! Das SSP wurde nicht gespeichert.")
                else:
                    # Send E-Mail
                    create_and_send_email(selection, data_meta, email_cc, data_general_input, data_quantity_machine_input, data_disturbance_input)
                    print("EMAIL submitted")


def preselect_shift():
    now = datetime.datetime.today().time()

    # Determine the current shift based on the current time
    if now < datetime.time(6, 30, 0): 
        preselected_shift = 0
    elif datetime.time(6, 30, 0) <= now < datetime.time(14, 30, 0): 
        preselected_shift = 1
    elif datetime.time(14, 30, 0) <= now < datetime.time(22, 30, 0): 
        preselected_shift = 2
    else: 
        preselected_shift = 0

    return preselected_shift

def collect_data_meta_information(selection):
    data_meta = {}

    # Meta Data Table
    df_meta = pd.read_csv(r"E:\Webapp_SSP\meta_data.csv", delimiter=';', encoding='latin1')
    df_meta = df_meta[df_meta['subline_id'] == selection['subline']]
    if not df_meta.empty:
        data_meta['responsible'] = df_meta['responsible'].iloc[0]
        data_meta['mail'] = df_meta['email_verteiler'].iloc[0]
    else:
        data_meta['responsible'] = 'T. Stielau'  # Or some default value
        data_meta['mail'] = 'hdlp_ssp_as7@ifa-group.com'

    # Calculate time till shift ends
    current_datetime = datetime.datetime.today()
    
    # Calculate Shiftend
    if selection['shift_id'] == 'night_shift':
        shift_end = datetime.datetime.combine(selection['date'], datetime.time(6,0,0))
    elif selection['shift_id'] == 'early_shift':
        shift_end = datetime.datetime.combine(selection['date'], datetime.time(14,0,0))
    elif selection['shift_id'] == 'late_shift':
        shift_end = datetime.datetime.combine(selection['date'], datetime.time(22,0,0))

    # Calculate delta between end of shift and current datetime
    timedelta = shift_end - current_datetime

    if timedelta.total_seconds() < 0:
        data_meta['time_till_shift_end'] = 'Schicht beendet'
    else:
        data_meta['time_till_shift_end'] = str(int(timedelta.total_seconds() / 60)) + ' Minuten verbleibend'

    return data_meta

# General Input Data

def collect_data_general(selection, data_quantity_machine):
    print("General Data: Collecting General Data")

    # Load data from database
    sql_select = f"""
    SELECT * FROM [DWH].[utility].[ssp_webapp_input]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND shift_id = '{selection['shift_id']}'
        AND line_id = '{selection['subline']}'
    """
    df = pd.read_sql(sql_select, engine)

    if len(df) == 0:
        print("General Data: No records found for the Selection")
        # If no data exists, Initialize data dictionary with default values
        data_general = {
        'name': '',
        'message':'',
        'kpi_output_ok': 0,
        'kpi_output_nok': 0,
        'kpi_employees_present': 0,
        'kpi_output_per_employee': 0}

        # load employee data and update 'kpi_employees_present'
        data_employees = load_data_employees(selection)
        data_general['kpi_employees_present'] = data_employees['employee_present']
    else:
        # Otherwise use the existing data
        print("General Data: Found existing records for the Selection")
        data_general = df.to_dict(orient='records')[0]

        # load employee data and update 'kpi_employees_present'
        data_employees = load_data_employees(selection)
        data_general['kpi_employees_present'] = data_employees['employee_present']

    # Load output data and update 'kpi_output_ok' and 'kpi_output_nok'
    data_output = load_data_output(data_quantity_machine)
    data_general['kpi_output_ok'] = data_output['ok']
    data_general['kpi_output_nok'] = data_output['nok']

    # Calculate 'kpi_output_per_employee' based on available data
    if data_general['kpi_employees_present'] > 0:
        data_general['kpi_output_per_employee'] = data_general['kpi_output_ok'] / data_general['kpi_employees_present']
    else:
        data_general['kpi_output_per_employee'] = 0

    # Save General Input Data to DWH
    save_data_general(selection, data_general)

    # Read Data from DWH
    df = pd.read_sql(sql_select, engine)

    # Return Data from DWH
    data_general = {
        'name': df['name'].iloc[0],
        'message': df['message'].iloc[0],
        'kpi_output_ok': df['kpi_output_ok'].iloc[0],
        'kpi_output_nok': df['kpi_output_nok'].iloc[0],
        'kpi_employees_present': df['kpi_employees_present'].iloc[0],
        'kpi_output_per_employee': df['kpi_output_per_employee'].iloc[0]}

    # Adjust for LOG
    if selection['department'] == 'LOG':
        data_general = collect_data_general_log(selection, data_general)


    return data_general

def collect_data_general_log(selection, data_general):
    # SQL Select
    sql_select = f"""
    SELECT * FROM [DWH].[fact_production].[shopfloor_employees]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND line_id = 'LOG'"""
    
    df = pd.read_sql(sql_select, engine)

    try:
        # Try to extract employee attendance based on the selected shift
        if selection['shift_id'] == 'night_shift':
            present = df['present_night_shift'].iloc[0]
        elif selection['shift_id'] == 'early_shift':
            present = df['present_early_shift'].iloc[0]
        elif selection['shift_id'] == 'late_shift':
            present = df['present_late_shift'].iloc[0]

        # Add to data_general
        data_general['kpi_employees_present'] = present
        data_general['kpi_output_ok'] = df['vacation'].iloc[0]
        data_general['kpi_output_nok'] = df['sickness'].iloc[0]           

    except Exception as e:
        # Handle the case when no data is available for the selected parameters
        data_general['kpi_employees_present'] = np.nan
        data_general['kpi_output_ok'] = np.nan
        data_general['kpi_output_nok'] = np.nan
        #st.warning("Keine Daten für diese Teillinie verfügbar.")

    return data_general

def load_data_output(df):
    data_output = {}

    print("General Data: Loading Output Data")

    # Split to output relevant
    df_output = df[df['output_relevant']==True]

    if len(df_output) > 0:
        data_output['ok'] = df_output['OK'].sum()
        data_output['nok'] = df_output['NOK'].sum()
    else:
        data_output['ok'] = 0
        data_output['nok'] = 0
   
    return data_output

def load_data_employees(selection):
    print("General Data: Loading employee Data")
    data_employees = {}

    # SQL Select
    sql_select = f"""
    SELECT * FROM [DWH].[fact_production].[shopfloor_employees]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND line_id = '{selection['subline'].split(" - ")[0]}'"""
    
    # Sonderregel IHC IDF IHF
    if selection['subline'] == "op1.4.2 - ihc, idf, ihf":
        sql_select = f"""SELECT SUM(present_night_shift) AS present_night_shift, SUM(present_early_shift) AS present_early_shift, SUM(present_late_shift) AS present_late_shift FROM [DWH].[fact_production].[shopfloor_employees]
                    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
                    AND line_id IN ('op1.4.2', 'op1.4.3', 'op1.4.4')"""
    
    df = pd.read_sql(sql_select, engine)

    try:
        # Try to extract employee attendance based on the selected shift
        if selection['shift_id'] == 'night_shift':
            data_employees['employee_present'] = df['present_night_shift'].iloc[0]
        elif selection['shift_id'] == 'early_shift':
            data_employees['employee_present'] = df['present_early_shift'].iloc[0]
        elif selection['shift_id'] == 'late_shift':
            data_employees['employee_present'] = df['present_late_shift'].iloc[0]
    except Exception as e:
        # Handle the case when no data is available for the selected parameters
        data_employees['employee_present'] = np.nan
        #st.warning("Keine Daten für diese Teillinie verfügbar.")

    return data_employees

def save_data_general(selection, data_general):
    print("General Data: Saving General Data")

    # Define metadata and table
    metadata = MetaData()
    ssp_webapp_input = Table('ssp_webapp_input', metadata, schema='utility', autoload_with=engine)

    # Define condition for the update
    update_condition = (
        (ssp_webapp_input.c.date_id == selection['date'].strftime("%Y-%m-%d")) &
        (ssp_webapp_input.c.shift_id == selection['shift_id']) &
        (ssp_webapp_input.c.line_id == selection['subline'])
    )

    # Define update values
    update_values = {
        'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        'name': str(data_general['name']), 
        'message': str(data_general['message']),
        'kpi_output_ok': int(data_general['kpi_output_ok']), 
        'kpi_output_nok': int(data_general['kpi_output_nok']), 
        'kpi_employees_present': safe_int_conversion(data_general['kpi_employees_present']),
        'kpi_output_per_employee' : float(data_general['kpi_output_per_employee'])
    }

    # Create update statement
    stmt = update(ssp_webapp_input).where(update_condition).values(update_values)

    # Execute update and check the number of affected rows
    result = session.execute(stmt)
    session.commit()

    # Check the number of affected rows
    rows_updated = result.rowcount
    if rows_updated == 0:
        print("General Data: No Records for Update found. Inserting a new one.")

        # Create a single-row DataFrame from the dictionary
        new_entry = {
            'date_id': selection['date'].strftime("%Y-%m-%d"),
            'shift_id': str(selection['shift_id']),
            'line_id': str(selection['subline']),
            'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'name': str(data_general['name']),
            'message': str(data_general['message']),
            'kpi_output_ok': int(data_general['kpi_output_ok']),
            'kpi_output_nok': int(data_general['kpi_output_nok']),
            'kpi_employees_present': safe_int_conversion(data_general['kpi_employees_present']),
            'kpi_output_per_employee': float(data_general['kpi_output_per_employee'])
        }
        df = pd.DataFrame([new_entry])

        # Create insert statement
        stmt = insert(ssp_webapp_input).values(df.to_dict(orient='records')[0])

        # Execute insert
        session.execute(stmt)
        session.commit()

    else:
        print("General Data: General Data was updated")

    return

# Data Quantity Machine

def collect_data_quantity_machine(selection, progressbar, progressbar_text):
    print("Quantities: Collecting Machine Quantities")

    # Load Data
    if selection['subline'] == 'op1.2.3 - WL':
        # Data comes from SAP and is transmitted in the SQL-Datawarehouse with the Job "02_3_OP_reported_quantities"
        pass
    else:
        df_quantity = load_data_quantity_machine_forcam(selection, progressbar, progressbar_text) 

        if '11302121' in selection['workplaces']:
            print("Insert SAP Data for Quantities of 11302121")
            # Insert SAP Data for 11302121
            workplace_list = '11302121' # workplace_list needs to be a string, for multiple workplaces use a comma separated string
            df_quantity = insert_data_quantity_machine_sap(selection, workplace_list, df_quantity)
        
        save_data_quantity_machine(selection, df_quantity, save_style='update') 

    # Read Data
    sql_select= f"""
        SELECT * 
        FROM [DWH].[utility].[ssp_webapp_quantities] 
        WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}' 
        AND shift_id = '{selection['shift_id']}' 
        AND workplace_id IN ({selection['workplaces_list']})"""
    df_raw = pd.read_sql(sql_select, engine)

    # Add Meta Data
    df = pd.merge(df_raw, df_wpl_info, on='workplace_id', how='inner') 

    return df

def load_data_quantity_machine_forcam(selection, progressbar, progressbar_text):
    print("Quantities: Loading Machine Quantities from Forcam API")
    # Forcam API Request
    with requests.Session() as request:

        # Get Token
        with open(r"E:\Webapp_SSP\credentials.json") as json_file:
            pw_api = json.load(json_file)['forcam_api_user']
        user = "IT_TEST"
        password = pw_api
        urlToken = "https://force:25443/ffauth/oauth2.0/accessToken?client_id=" + user + "&client_secret=" + password + "&grant_type=client_credentials&scope=read"

        token = request.get(urlToken, verify=False).json()
        accessToken = token['access_token']

        # Request Header
        request_head = {'Accept-Language': 'en-EN', 
            'Accept': 'application/json;charset=UTF-8',  
            'Authorization': 'Bearer {}'.format(accessToken)}
        base_url = "https://force:24443/ffwebservices/customized/v3/ifareports/"
        report_url = "ssp/?limit=100&formatted=true&timeZoneId=Europe/Belgrade"

        # Workplace URL
        workplace_url = """"""
        for wpl in selection['workplaces']:
            try:
                workplace_url += "&workplace=" + ifa_wpl_to_forcam_uuid[wpl]
            except:
                continue

        # Time URL
        if selection['shift_id'] == 'night_shift':
            shift_start = datetime.datetime.combine(selection['date'] - datetime.timedelta(days=1), datetime.time(22,2,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(6,0,0))
        elif selection['shift_id'] == 'early_shift':
            shift_start = datetime.datetime.combine(selection['date'], datetime.time(6,0,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(14,0,0))
        elif selection['shift_id'] == 'late_shift':
            shift_start = datetime.datetime.combine(selection['date'], datetime.time(14,0,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(22,0,0))
        
        time_url = "&timeTimeType=HOUR&timeIncludeCurrent=true&timeStartDate="+shift_start.strftime("%Y-%m-%dT%H:%M:%S")+"&timeEndDate="+shift_end.strftime("%Y-%m-%dT%H:%M:%S")

        # Create Request
        request_url = base_url + report_url + workplace_url + time_url
        print("Quantities: Request URL: " + request_url)

        data_request = request.get(request_url, headers=request_head, verify=False).json()
        print("Quantities: Request Answer: " + str(data_request))
       
        # Extract Data
        result_list = []
        for r in extract_api_data_quantity_machine(data_request, selection):
            result_list.append(r)

        # Check amount of total Results
        total = data_request['pagination']['total']
        if total > 0:
            print("Quantities: Amount of Events: " + str(total))
            offset = 100
            progressbar_step_ratio = int(40 / (total / offset)) / 100
            progressbar_step = 0.1
            while offset < total:
                request_url = base_url + report_url + workplace_url + time_url + "&offset=" + str(offset)
                data_request = request.get(request_url, headers=request_head, verify=False).json()

                # Extract Data
                for r in extract_api_data_quantity_machine(data_request, selection):
                    result_list.append(r)
                # Increase Offset
                offset += 100
                # Increase Progressbar
                progressbar_step += progressbar_step_ratio
                progressbar.progress(progressbar_step, text=progressbar_text)

        # Create Dataframe from Results
        df_results = pd.DataFrame(result_list)

        # Add missing Workplaces
        # Find missing workplace_ids, if df_result empty return empty list
        if len(df_results) > 0:
            existing_workplaces = df_results['workplace_id'].unique()
        else:
            existing_workplaces = []
        missing_workplaces = list(set(selection['workplaces']) - set(existing_workplaces))

        # Create rows for missing workplaces
        new_rows = pd.DataFrame({
            'date_id': [selection['date']] * len(missing_workplaces),
            'shift_id': [selection['shift_id']] * len(missing_workplaces),
            'workplace_id': missing_workplaces,
            'comment': [''] * len(missing_workplaces),
            'target': [0] * len(missing_workplaces),
            'OK': [0] * len(missing_workplaces),
            'NOK': [0] * len(missing_workplaces),
            'production_time': ['00:00'] * len(missing_workplaces),
            'halt_time': ['00:00'] * len(missing_workplaces),
            'setup_time': ['00:00'] * len(missing_workplaces),
            'pause_time': ['00:00'] * len(missing_workplaces),
        })

        # Add them to the original df_results
        df_results_updated = pd.concat([df_results, new_rows], ignore_index=True)

        if len(df_results_updated) > 0:
            # Transform Dataframe
            # Ensure time columns are in hh:mm:ss format
            time_columns = ['production_time', 'halt_time', 'setup_time', 'pause_time']
            for col in time_columns:
                df_results_updated[col] = pd.to_timedelta(df_results_updated[col] + ':00')

            # Group by workplace_id and sum the relevant columns
            agg_df = df_results_updated.groupby(['date_id', 'shift_id', 'workplace_id', 'comment']).agg({
                'target': 'sum',
                'OK': 'sum',
                'NOK': 'sum',
                'production_time': 'sum',
                'halt_time': 'sum',
                'setup_time': 'sum',
                'pause_time': 'sum'
            }).reset_index()

            # Convert the timedelta columns back to hh:mm format
            for col in time_columns:
                agg_df[col] = agg_df[col].apply(lambda x: f"{int(x.total_seconds() // 3600):02}:{int((x.total_seconds() % 3600) // 60):02}")

            agg_df['last_updated'] = datetime.datetime.now()
            agg_df['target_time_per_part_seconds'] = 0
            agg_df['actual_time_per_part_seconds'] = 0.0
            agg_df['parts_per_hour'] = 0.0
            agg_df['operation_id'] = ""
            agg_df['materialnumber'] = ""
            
        else:
            agg_df = pd.DataFrame()

    return agg_df

def load_data_quantity_machine_dwh(selection, progressbar, progressbar_text):
    # SQL Select
    sql_select = f"""
    SELECT * FROM [DWH].[fact_production].[reported_quantities_workplace]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND workplace_id IN ({selection['workplaces_list']})"""
    
    df = pd.read_sql(sql_select, engine)

    # Create an empty DataFrame with these columns
    columns = ["date_id", "shift_id", "workplace_id", "comment", "target", "ok", "nok",
    "production_time", "halt_time", "setup_time", "pause_time", "last_updated",
    "target_time_per_art_seconds", "actual_time_per_part_seconds", 
    "parts_per_hour", "operation_id", "materialnumber"]
    agg_df = pd.DataFrame(columns=columns)

    # Mapping of df columns to agg_df columns
    if selection['shift_id'] == 'night_shift':
        ok_column = 'yield_night_shift'
        nok_column = 'scrap_night_shift'
    elif selection['shift_id'] == 'early_shift':
        ok_column = 'yield_early_shift'
        nok_column = 'scrap_early_shift'
    elif selection['shift_id'] == 'late_shift':
        ok_column = 'yield_late_shift'
        nok_column = 'scrap_late_shift'
    
    column_mapping = {
        "date_id": "date_id",
        "workplace_id": "workplace_id",
        ok_column: "ok",
        nok_column: "nok"}

    # Rename df2 columns based on the mapping
    df_renamed = df.rename(columns=column_mapping)
    df_aligned = df_renamed.reindex(columns=agg_df.columns)
    
    # Combine the data
    agg_df = pd.concat([agg_df, df_aligned], ignore_index=True)
    agg_df['last_updated'] = datetime.datetime.today()
    agg_df['shift_id'] = selection['shift_id']
    agg_df['comment'] = '-'
    
    return agg_df

def insert_data_quantity_machine_sap(selection, workplace_list, original_df):
    # SQL Select
    sql_select = f"""
    SELECT * FROM [DWH].[fact_production].[reported_quantities_workplace]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND workplace_id IN ({workplace_list})"""
    
    df = pd.read_sql(sql_select, engine)

    # Selection of Shift
    if selection['shift_id'] == 'night_shift':
        ok_column = 'yield_night_shift'
        nok_column = 'scrap_night_shift'
    elif selection['shift_id'] == 'early_shift':
        ok_column = 'yield_early_shift'
        nok_column = 'scrap_early_shift'
    elif selection['shift_id'] == 'late_shift':
        ok_column = 'yield_late_shift'
        nok_column = 'scrap_late_shift'

    # Replace Data in orignal_df
    for index, row in original_df.iterrows():
        # Find the matching row in df based on workplace_id and date_id
        matching_row = df[(df['workplace_id'] == row['workplace_id'])]

        if not matching_row.empty:
            # Update the values in the original_df with the values from df
            original_df.at[index, 'OK'] = matching_row[ok_column].values[0]
            original_df.at[index, 'NOK'] = matching_row[nok_column].values[0]

    return original_df        

def extract_api_data_quantity_machine(data_request, selection):
    result_list = []
    for i in range(len(data_request['_embedded']['ifareportsSsp'])):
        data = data_request['_embedded']['ifareportsSsp'][i]['properties']
        result = {
            'date_id': selection['date'].strftime("%Y-%m-%d"),
            'shift_id': selection['shift_id'],
            'operation_id': "", #data.get('operationId'),
            'workplace_id': forcam_uuid_to_ifa_wpl[data.get('workplaceId')],
            'materialnumber': "", #data.get('materialId'),
            'comment': '',
            'last_updated': '',
            'target': int(data.get('targetQuantity').replace('.00', '')),
            'OK': int(data.get('yieldQtyShift').replace('.00', '')),
            'NOK': int(data.get('scrapQtyShift').replace('.00', '')),
            'production_time': data.get('prodDuration'),
            'setup_time': data.get('setupDuration'),
            'halt_time': data.get('interuptDuration'),
            'pause_time': data.get('breakDuration'),
            'target_time_per_part_seconds': float(data.get('timePerUnitSec')),
            'actual_time_per_part_seconds': float(data.get('realTimePerUnitSec')),
            'parts_per_hour': float(data.get('pph'))
        }
        result_list.append(result)

    return result_list

def save_data_quantity_machine(selection, raw_df, save_style):
    print("Quantities: Saving Data in style: " + save_style)

    # Format the Dataframe like the SQL-Table
    sql_query = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ssp_webapp_quantities'"
    selected_columns = pd.read_sql(sql_query, engine)['COLUMN_NAME'].tolist()
    df = pd.DataFrame(columns=selected_columns)

    # Iterate over each column and check if it exists in the original DataFrame
    for col in selected_columns:
        if col in raw_df.columns:
            # If the column exists, copy it to the subselected DataFrame
            df[col] = raw_df[col]
        else:
            # If the column doesn't exist, add it with NaN values
            df[col] = np.nan

    # Save Style Replace
    if save_style == 'replace':

        # Define the SQL delete query using f-string and text
        delete_sql = text(f"""
                DELETE FROM utility.ssp_webapp_quantities 
                WHERE date_id = '{selection['date'].strftime('%Y-%m-%d')}' 
                AND shift_id = '{selection['shift_id']}' 
                AND workplace_id IN ({selection['workplaces_list']})""")

        # Execute the delete query
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(delete_sql)

        # Insert new DF
        df['last_updated'] = datetime.datetime.now()
        df.to_sql('ssp_webapp_quantities', engine, schema='utility', if_exists='append', index=False)

        print("Quantities: Values were replaced. Input Length: " + str(len(df)))
        return

    # Save Style Update
    elif save_style == 'update':

        # Define metadata and table
        metadata = MetaData()
        ssp_webapp_quantities = Table('ssp_webapp_quantities', metadata, schema='utility', autoload_with=engine)


        for index, row in df.iterrows():
            # Define condition for the update
            update_condition = (
                (ssp_webapp_quantities.c.date_id == row['date_id']) &
                (ssp_webapp_quantities.c.shift_id == row['shift_id']) &
                (ssp_webapp_quantities.c.workplace_id == row['workplace_id'])
            )

            # Create update values
            update_values = {
                'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'target': row['target'],
                'OK': row['OK'],
                'NOK': row['NOK'],
                'production_time': row['production_time'],
                'setup_time': row['setup_time'],
                'halt_time': row['halt_time'],
                'pause_time': row['pause_time'],
                'target_time_per_part_seconds': row['target_time_per_part_seconds'],
                'actual_time_per_part_seconds': row['actual_time_per_part_seconds'],
                'parts_per_hour': row['parts_per_hour']
            }

            # Create update statement
            stmt = update(ssp_webapp_quantities).where(update_condition).values(update_values)

            # Execute update
            result = session.execute(stmt)

            # Check if any rows were updated
            if result.rowcount == 0:
                print("Quantities: Inserting a new row because there is no matching value to update.")
                # Create insert statement
                stmt = insert(ssp_webapp_quantities).values(row.to_dict())

                # Execute insert
                session.execute(stmt)

            # Commit changes
            session.commit()

        print("Quantities: Values were updated.")
        return

# Data Disturbances

def collect_data_disturbance(selection, progressbar, progressbar_text):
    print("Disturbance: Collecting Machine Disturbance Data")

    # Load Data from Forcam 
    df = load_data_disturbance(selection, progressbar, progressbar_text)

    # Translate code to text
    df = pd.merge(df, df_operating_state_codes, on='code', how='left')
    df = df.rename(columns={'title_de': 'problem'})

    # Update Database with Forcam Data
    save_data_disturbance(selection, df, save_style='update')
        
    # Read DWH Table
    sql_select = """SELECT * FROM [utility].[ssp_webapp_disturbances] WHERE date_id = '""" + selection['date'].strftime("%Y-%m-%d") + "' AND shift_id = '" + selection['shift_id'] + "' AND workplace_id IN (" + selection['workplaces_list'] + ")" 
    df = pd.read_sql(sql_select, engine)

    # Add Meta Data
    df = pd.merge(df, df_wpl_info, on='workplace_id', how='inner')
    df['machine_name'] = df['machine_name'].fillna('NOT FOUND')

    return df


def collect_data_disturbance_log(selection):
    print("Disturbance: Collecting Disturbance for log")
        
    # Read DWH Table
    sql_select = """SELECT * FROM [utility].[ssp_webapp_disturbances] WHERE date_id = '""" + selection['date'].strftime("%Y-%m-%d") + "' AND shift_id = '" + selection['shift_id'] + "' AND workplace_id IN (" + selection['workplaces_list'] + ")" 
    df = pd.read_sql(sql_select, engine)

    return df

def load_data_disturbance(selection, progressbar, progressbar_text):
    print("Disturbance: Loading Machine Disturbance Data from Forcam API")
    # Forcam API Request
    with requests.Session() as request:

        # Get Token
        with open(r"E:\Webapp_SSP\credentials.json") as json_file:
            pw_api = json.load(json_file)['forcam_api_user']
        user = "IT_TEST"
        password = pw_api
        urlToken = "https://force:25443/ffauth/oauth2.0/accessToken?client_id=" + user + "&client_secret=" + password + "&grant_type=client_credentials&scope=read"

        token = request.get(urlToken, verify=False).json()
        accessToken = token['access_token']

        # Request Header
        request_head = {'Accept-Language': 'en-EN', 
            'accept': 'application/hal+json;charset=UTF-8',  
            'Authorization': 'Bearer {}'.format(accessToken)}
        base_url = "https://force:24443/ffwebservices/customized/v3/ifareports/"
        report_url = "operating_state_log/?limit=100&formatted=true&timeZoneId=Europe/Belgrade"

        # Workplace URL
        workplace_url = """"""
        for wpl in selection['workplaces']:
            try:
                workplace_url += "&workplace=" + ifa_wpl_to_forcam_uuid[wpl]
            except:
                continue

        # Time URL
        if selection['shift_id'] == 'night_shift':
            shift_start = datetime.datetime.combine(selection['date'] - datetime.timedelta(days=1), datetime.time(22,0,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(6,0,0))
        elif selection['shift_id'] == 'early_shift':
            shift_start = datetime.datetime.combine(selection['date'], datetime.time(6,0,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(14,0,0))
        elif selection['shift_id'] == 'late_shift':
            shift_start = datetime.datetime.combine(selection['date'], datetime.time(14,0,0))
            shift_end = datetime.datetime.combine(selection['date'], datetime.time(22,0,0))
        
        time_url = "&timeType=HOUR&includeCurrent=true&startDate="+shift_start.strftime("%Y-%m-%dT%H:%M:%S")+"&endDate="+shift_end.strftime("%Y-%m-%dT%H:%M:%S")

        # Create Request URL
        request_url = base_url + report_url + workplace_url + time_url

        # Add Filter for operating states (Rüsten, Störungen, Org. Stillstand, Musterproduktion, Material Logistik, Qualität)
        
        # Rüsten, Störungen, Org. Stillstand, Musterproduktion, Material Logistik, Qualität
        # operating_states_url = "&operationOperatingStatus=8098001&operationOperatingStatus=178652&operationOperatingStatus=867932451&operationOperatingStatus=2453935351&operationOperatingStatus=8098003&operationOperatingStatus=2236553651&operationOperatingStatus=8098002&operationOperatingStatus=178953&operationOperatingStatus=8098005&operationOperatingStatus=8098004&operationOperatingStatus=8098007&operationOperatingStatus=8098006&operationOperatingStatus=8098008&operationOperatingStatus=8098023&operationOperatingStatus=179357&operationOperatingStatus=766925901&operationOperatingStatus=8098012&operationOperatingStatus=164353801&operationOperatingStatus=8098011&operationOperatingStatus=179366&operationOperatingStatus=8098013&operationOperatingStatus=8098010&operationOperatingStatus=8098015&operationOperatingStatus=8098014&operationOperatingStatus=8098016&operationOperatingStatus=8098009&operationOperatingStatus=766925902&operationOperatingStatus=164353802&operationOperatingStatus=766925904&operationOperatingStatus=766925903&operationOperatingStatus=8098018&operationOperatingStatus=8098026&operationOperatingStatus=8098019&operationOperatingStatus=8098021&operationOperatingStatus=8098020"
        # Störungen, Org. Stillstand, Musterproduktion, Material Logistik, Qualität
        operating_states_url = "&operationOperatingStatus=8098005&operationOperatingStatus=8098004&operationOperatingStatus=8098007&operationOperatingStatus=8098006&operationOperatingStatus=8098008&operationOperatingStatus=8098023&operationOperatingStatus=179357&operationOperatingStatus=766925901&operationOperatingStatus=8098012&operationOperatingStatus=164353801&operationOperatingStatus=8098011&operationOperatingStatus=179366&operationOperatingStatus=8098013&operationOperatingStatus=8098010&operationOperatingStatus=8098015&operationOperatingStatus=8098014&operationOperatingStatus=8098016&operationOperatingStatus=8098009&operationOperatingStatus=766925902&operationOperatingStatus=164353802&operationOperatingStatus=766925904&operationOperatingStatus=766925903&operationOperatingStatus=8098018&operationOperatingStatus=8098026&operationOperatingStatus=8098019&operationOperatingStatus=8098021&operationOperatingStatus=8098020"

        request_url += operating_states_url
        print("Disturbance: Request URL: " + request_url)

        # Send Request to API
        data_request = request.get(request_url, headers=request_head, verify=False).json()
        print("Disturbance: Request Answer: " + str(data_request))

        # Extract Data
        result_list = []
        for r in extract_api_data_disturbances(data_request, selection):
            result_list.append(r)

        # Check amount of total Results
        total = data_request['pagination']['total']
        if total > 0:
            print("Disturbance: Amount of Events: " + str(total))
            offset = 100
            progressbar_step_ratio = int(40 / (total / offset)) / 100
            progressbar_step = 0.5
            while offset < total:
                request_url = base_url + report_url + workplace_url + time_url
                request_url += operating_states_url + "&offset=" + str(offset)
                print("Disturbance: Request URL: " + request_url)

                data_request = request.get(request_url, headers=request_head, verify=False).json()
                print("Disturbance: Request Answer: " + str(data_request))

                # Extract Data
                for r in extract_api_data_disturbances(data_request, selection):
                    result_list.append(r)
                # Increase Offset
                offset += 100
                # Increase Progressbar
                progressbar_step += progressbar_step_ratio
                progressbar.progress(progressbar_step, text=progressbar_text)
                
        # Create Dataframe from Results
        df_results = pd.DataFrame(result_list)

        # Filter Dataframes for states with 10 Minutes or longer
        try:
            df = df_results[df_results['duration_minutes'] >= 10]
            df = df.sort_values(['workplace_id', 'start'])

            df['start'] = df['start'].dt.strftime('%Y-%m-%d %H:%M:%S')
            df['end'] = df['end'].dt.strftime('%Y-%m-%d %H:%M:%S')
            df['source'] = 'Forcam'
            df['last_updated'] = datetime.datetime.now()

        except Exception as e:
            print("Disturbance: No Data found or Error happened, creating empty DF")
            print(e)
            df = pd.DataFrame(columns=['date_id', 'shift_id', 'workplace_id', 'start', 'end', 'code', 'status',
            'sf_comment', 'duration_minutes', 'source', 'last_updated'])

    return df

def extract_api_data_disturbances(data_request, selection):
    result_list = []
    for i in range(len(data_request['_embedded']['ifareportsOperating_state_log'])):
        data = data_request['_embedded']['ifareportsOperating_state_log'][i]['properties']
        result = {'date_id': selection['date'].strftime("%Y-%m-%d"),
                'shift_id': selection['shift_id'],
                'workplace_id': data.get('workplaceId').split(" ")[0],
                'start': datetime.datetime.strptime(data.get('startTs'), "%d/%m/%Y, %H:%M"),
                'end': datetime.datetime.strptime(data.get('endTs'), "%d/%m/%Y, %H:%M"),
                'code': data.get('operatingStatusMnemonic'),
                'status': data.get('operatingStatusText'),
                'sf_comment': data.get('ticketTitle')}
        result['duration_minutes'] = (result['end'] - result['start']).total_seconds()/60

        result_list.append(result)

    return result_list

def save_data_disturbance(selection, raw_df, save_style):
    print("Disturbance: Saving Data in style: " + save_style)
    # Format the Dataframe like the SQL-Table
    sql_query = "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ssp_webapp_disturbances'"
    selected_columns = pd.read_sql(sql_query, engine)['COLUMN_NAME'].tolist()
    df = pd.DataFrame(columns=selected_columns)

    # Create an empty DataFrame with the selected columns
    df = pd.DataFrame(columns=selected_columns)

    # Iterate over each column and check if it exists in the original DataFrame
    for col in selected_columns:
        if col in raw_df.columns:
            # If the column exists, copy it to the subselected DataFrame
            df[col] = raw_df[col]
        else:
            if col == 'solved':
                df[col] = False
            else:
                df[col] = ''

    # Save Style Replace
    if save_style == 'replace':

        # Delete old Entries
        delete_sql = text(f"""
        DELETE FROM utility.ssp_webapp_disturbances
        WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}' AND
            shift_id = '{selection['shift_id']}' AND
            workplace_id IN ({selection['workplaces_list']})
        """)

        # Execute the delete query
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(delete_sql)

        # Insert new DF
        df['last_updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_sql('ssp_webapp_disturbances', engine, schema='utility', if_exists='append', index=False)

        print("Disturbance: Values were replaced. Input Length: " + str(len(df)))
        return

    # Save Style Update
    elif save_style == 'update':

        # Define metadata and table
        metadata = MetaData()
        ssp_webapp_disturbances = Table('ssp_webapp_disturbances', metadata, schema='utility', autoload_with=engine)

        for index, row in df.iterrows():
            # Define condition for the update
            update_condition = (
                (ssp_webapp_disturbances.c.date_id == row['date_id']) &
                (ssp_webapp_disturbances.c.shift_id == row['shift_id']) &
                (ssp_webapp_disturbances.c.workplace_id == row['workplace_id']) &
                (ssp_webapp_disturbances.c.source == 'Forcam') &
                (ssp_webapp_disturbances.c.start == row['start']))
            
            # Create update values
            update_values = {
                'last_updated': datetime.datetime.now(),
                'end': row['end'],
                'code': row['code'],
                'duration_minutes': row['duration_minutes'],
                'sf_comment': row['sf_comment']}
            
            # Create update statement
            stmt = update(ssp_webapp_disturbances).where(update_condition).values(update_values)

            # Execute update
            result = session.execute(stmt)

            # Insert Row if nothing was updated
            if result.rowcount == 0:
                print("Disturbance: Inserting a new row because there is no matching value to update.")
                # Create insert statement
                stmt = insert(ssp_webapp_disturbances).values(row.to_dict())

                # Execute insert
                session.execute(stmt)


        # Commit changes
        session.commit()

        print("Disturbance: Values were updated.")
        return

# Send E-Mail

def save_all_data(selection, data_general_input, data_quantity_machine_input, data_disturbance_input):
    print("Saving all Data")

    save_data_general(selection, data_general_input)
    if len(data_quantity_machine_input) > 0:
        save_data_quantity_machine(selection, raw_df=data_quantity_machine_input, save_style='replace')
    if len(data_disturbance_input) > 0:
        save_data_disturbance(selection, raw_df=data_disturbance_input, save_style='replace')

    return

def create_and_send_email(selection, data_meta, email_cc, data_general_input, data_quantity_machine_input, data_disturbance_input):
    # Disable Button
    st.session_state.disable_email = True
    
    # Settings
    host = "webmail.ifa-group.com"
    port = 587
    email = "reporting_its.service@ifa-group.com"
    with open(r"E:\Webapp_SSP\credentials.json") as json_file:
        pw = json.load(json_file)['mailuser']
    mail_to = [data_meta['mail']]

    # CC Adress
    # Step 1: Split the string at commas to create a list of email addresses
    email_list = email_cc.split(',')
    # Step 2: Trim any whitespace around email addresses
    email_list = [email.strip() for email in email_list]
    # Step 3: Define the pattern to match email addresses in the form xxx.xxx@ifa-group.com
    pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    # Step 4: Filter the list to include only addresses that match the desired pattern
    mail_cc = [email for email in email_list if pattern.match(email) and email.endswith('@ifa-group.com')]


    # HTML Message
    message = MIMEMultipart("related")
    message["From"] = email
    message["To"] = ", ".join(mail_to)
    message["Subject"] = 'SSP: ' + selection['subline'] + ' - ' + selection['date_str_de'] + ' - ' + selection['shift']
    message["Cc"] = ", ".join(mail_cc)
    
    #mail_bcc = ['benedikt.wehrmeister@ifa-group.com']

    html = f"""<html>
            <meta http-equiv="content-type" content="text/html; charset=utf-8">
            <head></head>
            <body>
                <basefont face = "arial, verdana, sans-serif" size ="4">
                <h2 style='font-size: 20px'><br><u><strong>SSP: {selection['subline']} - {selection['date_str_de']} - {selection['shift']}</strong></u></br></h2>"""
    
    # Overview
    html += """<strong>Übersicht</strong>"""

    html += """<table border='1' style="width:40%;border-collapse:collapse;font-family:arial;font-size:80%">"""
    html += f"""<tr>
    <td style="text-align:left">Schichtleiter</td>
    <td style="text-align:center">{data_general_input['name']}</td>
    </tr>"""
    html += f"""<tr>
    <td style="text-align:left">Teamleiter</td>
    <td style="text-align:center">{data_meta['responsible']}</td>
    </tr>"""
    html += f"""<tr>
    <td style="text-align:left">Zeit bis Schichtende</td>
    <td style="text-align:center">{data_meta['time_till_shift_end']}</td>
    </tr>"""
    html += """</table>"""
    html += """<br></br>"""
    
    # Schiko Message
    html += """<strong>Nachricht Schichtübergabe</strong>"""
    html += """<table border='1' style="width:40%;border-collapse:collapse;font-family:arial;font-size:80%">"""
    html += f"""<tr>
    <td style="text-align:left">{data_general_input['message']}</td></tr>"""
    html += """</table>"""
    html += """<br></br>"""

    # OP-Email
    if selection['department'] in ['OP1', 'OP2']:
        # KPI
        html += """<strong>KPI's</strong>"""
        kpi = {'Kennzahl': ['Ausbringung', 'Ausschuss', 'Mitarbeiter Anwesend', 'Ausbringung pro Mitarbeiter'],
                'Wert': [int(data_general_input['kpi_output_ok']), int(data_general_input['kpi_output_nok']), int(data_general_input['kpi_employees_present']), round(data_general_input['kpi_output_per_employee'],1)]}
        html += dataframe_to_html(pd.DataFrame(kpi), width='40%', style_first_col='left')
        html += """<br></br>"""

        # Quantities by Machine
        html += """<strong>Ausbringung pro Maschine</strong>"""
        column_select = ['workplace_id', 'machine_name', 'output_relevant', 'OK', 'NOK', 'production_time', 'halt_time', 'setup_time', 'comment']
        column_names = ['Arbeitsplatz', 'Maschine', 'Ausbringungsrelevant', 'IO', 'NIO', 'Produktionszeit', 'Verlustzeit', 'Rüstzeit', 'Kommentar']
        html += dataframe_to_html(data_quantity_machine_input, column_select=column_select, header_names=column_names, width='80%')
        html += """<br></br>"""

        # Issues by Machine
        html += """<strong>Maschinenstörungen</strong>"""
        column_select = ['workplace_id', 'machine_name', 'source', 'problem','start', 'duration_minutes', 'sf_comment', 'ssp_comment', 'solution', 'solved']
        column_names = ['Arbeitsplatz', 'Maschine', 'Quelle', 'Problembeschreibung','Beginn der Störung', 'Dauer [min]', 'Kommentar Forcam', 'Kommentar SSP','Eingeleitete Maßnahme', 'Erledigt']
        html += dataframe_to_html(data_disturbance_input, column_select=column_select, header_names=column_names, width='80%')
        html += """<br></br>"""
    
        html += """
        <br>Maschinenstörungen mit einer Dauer von unter 10 Minuten werden nicht angezeigt.</br>"""

    # LOG E-Mail
    else:
        # KPI
        # KPI
        html += """<strong>Personalinfo</strong>"""
        kpi = {'Kennzahl': ['Mitarbeiter Anwesend (Schicht)', 'Krank (Tag)', 'Urlaub (Tag)'],
                        'Wert': [data_general_input['kpi_employees_present'], data_general_input['kpi_output_nok'], data_general_input['kpi_output_ok']]}
        html += dataframe_to_html(pd.DataFrame(kpi), width='40%', style_first_col='left')
        html += """<br></br>"""

        # Issues by Machine
        html += """<strong>Problemmeldungen</strong>"""
        column_select = ['workplace_id', 'source', 'problem','start', 'duration_minutes', 'ssp_comment', 'solution', 'solved']
        column_names = ['Bereich', 'Quelle', 'Problembeschreibung','Beginn der Störung', 'Dauer [min]', 'Kommentar SSP','Eingeleitete Maßnahme', 'Erledigt']
        html += dataframe_to_html(data_disturbance_input, column_select=column_select, header_names=column_names, width='80%')
        html += """<br></br>"""

    # E-Mail End
    html += """
    <br>Dies ist eine automatisch generierte E-Mail.</br>
    <br>Sollten Sie Fragen haben oder Fehler feststellen wenden Sie sich bitte an das Team ITS.</br>
    </body>
    </html>"""

    # Turn these into plain/html MIMEText objects
    mail_object = MIMEText(html, "html")
    message.attach(mail_object)

    # Create secure connection with server and send email
    receiver_email = mail_to + mail_cc #+ mail_bcc
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email, pw)
        server.sendmail(email, receiver_email, message.as_string())

    print("E-Mail was send")
    st.success("E-Mail erfolgreich versendet!")
    return

def dataframe_to_html(df, column_select=[], header_names=[], percentage_columns=[], width='100%', font='arial', font_size='80%', style='center', style_first_col='center'):
    # Column Selection
    if len(column_select) != 0:
        df = df[column_select]

    # Rename Header
    if len(header_names) != 0:
        df = df.rename(columns=dict(zip(df.columns, header_names)))

    header = df.columns.to_list()

    # Indicate Table & set headers
    html = f"""<table border='1' style="width:{width};border-collapse:collapse;font-family:{font};font-size:{font_size}">"""
    html += """<tr>"""
    for head in header:
        html += f"""<th>&nbsp{head}&nbsp</th>"""
    html += """</tr>"""
    # Write Values
    for index, row in df.iterrows():
        html += """<tr>"""
        col_index = 0
        for col in header:
            value = row[col]
            # Translate True / False
            if value is True:
                value = "Ja"
            elif value is False:
                value = "Nein"
            # Check Valuetypes
            if value is None or pd.isna(value) or value == 'nan':
                value = ""
            elif isinstance(value, float):
                # Check if the float is actually a whole number
                if value.is_integer():
                    value = str(int(value))
                else:
                    value = str(round(value, 1)).replace(".", ",")

            # Check percentage
            if col in percentage_columns:
                value = str("%.1f%%" % (row[col])).replace(".",",")
            # Write Value und adjust Style
            if col_index != 0:
                html += f"""<td style="text-align:{style}">{value}</td>"""
            else:
                html += f"""<td style="text-align:{style_first_col}">{value}</td>"""
            col_index +=1
        html += """</tr>"""
    # End Table
    html += """</table>"""
    return html

def safe_int_conversion(value, default=0):
    if pd.isna(value):
        return default
    return int(value)

if __name__ == "__main__":
    # Settings

    # SQL Settings
    with open(r"E:\Webapp_SSP\credentials.json") as json_file:
        pw_dwh = json.load(json_file)['dwh_user']

    sql_settings = {
        'server': 'S298A150\DWH',
        'database': 'DWH',
        'user': 'dwh_user',
        'password': pw_dwh}
    
    engine = create_engine("mssql+pyodbc://"+sql_settings['user']+":"+sql_settings['password']+"@"+sql_settings['server']+"/"+sql_settings['database']+"?driver=ODBC Driver 17 for SQL Server")
    Session = sessionmaker(bind=engine)
    session = Session()

    # Get Dictionary of department - line - subline
    df_hierarchy = pd.read_sql("SELECT DISTINCT department, line_id + ' - ' + line_name AS line_id, subline_id + ' - ' + subline_name AS subline_id FROM [DWH].[dim].[workplace] WHERE department IS NOT NULL AND plant = 'HdlP'", engine)
    df_wpl = pd.read_sql("SELECT DISTINCT workplace_id, line_id + ' - ' + line_name AS line_id, subline_id + ' - ' + subline_name AS subline_id FROM [DWH].[dim].[workplace] WHERE department IS NOT NULL AND plant = 'HdlP'", engine)

    # Combine line_id IHC, IDF and IHF to one
    df_hierarchy = df_hierarchy[~df_hierarchy['line_id'].isin(['op1.4.4 - ihf', 'op1.4.3 - idf', 'op1.4.2 - ihc'])]
    new_row = pd.DataFrame({
    'department': ['OP1'],
    'line_id': ['op1.4.2 - ihc, idf, ihf'],
    'subline_id': [None]})    
    df_hierarchy = pd.concat([df_hierarchy, new_row], ignore_index=True)
    df_hierarchy = df_hierarchy.sort_values(by=['department', 'line_id'])

    # Rewrite line_id in workplace data to combined line
    replace_list = ['op1.4.4 - ihf', 'op1.4.3 - idf', 'op1.4.2 - ihc']
    df_wpl['line_id'] = df_wpl['line_id'].replace(replace_list, 'op1.4.2 - ihc, idf, ihf')
        
    # Add LOG Department and line
    new_row = pd.DataFrame({
    'department': ['LOG'],
    'line_id': ['LOG3'],
    'subline_id': [None]})    
    df_hierarchy = pd.concat([df_hierarchy, new_row], ignore_index=True)
    #df_hierarchy = df_hierarchy.sort_values(by=['department', 'line_id'])

    # LOG Workplaces
    selected_workplaces_log = ['H158', 'H115', 'H111A', 'H116', 'Hof', 'Entladung', 'Abwicklung WE', 'BS Kanban', 'BS Kommi', 'BS Wäsche', 'PV Konvoi', 'PV Stapler', 'PV Cargo Runner', 'IXP', 'Verpackung', 'as2', 'as3', 'as4', 'as5', 'as6/7', 'MA1', 'Sonstiges']

    # Create hierarchy
    hierarchy = {}
    for index, row in df_hierarchy.iterrows():
        department = row['department']
        line_id = row['line_id']
        subline_id = row['subline_id']
        
        # Add department i
        if department not in hierarchy:
            hierarchy[department] = {}
        # Add line
        if line_id not in hierarchy[department]:
            hierarchy[department][line_id] = {}
        
        # Add Sublines & Workplaces
        # No Subline
        if subline_id is None and subline_id not in hierarchy[department][line_id]:
            hierarchy[department][line_id][line_id] = df_wpl[df_wpl['line_id'] == line_id]['workplace_id'].to_list()
        # Subline
        elif subline_id is not None and subline_id not in hierarchy[department][line_id]:
            hierarchy[department][line_id][subline_id] = df_wpl[df_wpl['subline_id'] == subline_id]['workplace_id'].to_list()

    # Forcam Workplace UUIDS
    df_forcam_uuid = pd.read_sql("SELECT DISTINCT workplace_ifa_id, workplace_forcam_uuid FROM [DWH].[dim].[forcam_hierarchy]", engine)
    ifa_wpl_to_forcam_uuid = df_forcam_uuid.set_index('workplace_ifa_id')['workplace_forcam_uuid'].to_dict()
    forcam_uuid_to_ifa_wpl = {v: k for k, v in ifa_wpl_to_forcam_uuid.items()}

    # Forcam Operating state codes
    df_operating_state_codes = pd.read_sql("SELECT DISTINCT code, title_de, color FROM [DWH].[dim].[forcam_operating_state_codes]", engine)

    # Workplace Infos
    df_wpl_info = pd.read_sql("""
                SELECT workplace_id, process, machine_name, output_relevant, line_name
                FROM [DWH].[dim].[workplace]
                WHERE plant = 'HdlP' AND (process != 'mes-logout' OR process IS NULL) AND line_name NOT IN ('pb1', 'pb2')
                """, engine) 
    wpl_info = df_wpl_info.set_index('workplace_id')[['process', 'machine_name', 'output_relevant']].to_dict()
    
    main()
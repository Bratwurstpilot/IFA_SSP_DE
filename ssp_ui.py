import datetime
import time

import pandas as pd
import streamlit as st

import ssp_state
from ssp_disturbance_data import collect_data_disturbance, collect_data_disturbance_log
from ssp_email import create_and_send_email, save_all_data
from ssp_general_data import collect_data_general
from ssp_meta_data import collect_data_meta_information, preselect_shift
from ssp_quantity_data import collect_data_quantity_machine


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
    selected_department = st.selectbox("Abteilung:", list(ssp_state.hierarchy.keys()))

    # Select Line
    selected_line = st.selectbox("Linie:", list(ssp_state.hierarchy[selected_department].keys()))

    # Select Subline
    selected_subline = st.selectbox("Teillinie:", list(ssp_state.hierarchy[selected_department][selected_line].keys()))

    # Load Data
    if "data" in st.session_state:
        st.info("Beim erneuten Laden der Daten gehen nicht gespeicherte Änderungen verloren.")

    if st.button('Daten laden für: ' + selected_shift + ' - ' + selected_subline):

        # Set workplace_list for selected subline
        if selected_department in ['OP1', 'OP2']:
            selected_workplaces = list(ssp_state.hierarchy[selected_department][selected_line][selected_subline])
        else:
            selected_workplaces = ssp_state.selected_workplaces_log

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
                selected_workplaces_machine_names = ssp_state.df_wpl_info[ssp_state.df_wpl_info['workplace_id'].isin(selection['workplaces'])]
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
                                                    {"workplace_id": st.column_config.SelectboxColumn("Bereich", options=ssp_state.selected_workplaces_log, required=True),
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

import json
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st

from ssp_disturbance_data import save_data_disturbance
from ssp_general_data import save_data_general
from ssp_quantity_data import save_data_quantity_machine


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

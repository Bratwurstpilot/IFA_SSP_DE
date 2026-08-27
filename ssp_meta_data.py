import datetime

import pandas as pd


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

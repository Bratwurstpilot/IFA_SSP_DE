import datetime

import numpy as np
import pandas as pd
from sqlalchemy import MetaData, Table, insert, update

import ssp_state
from utils import safe_int_conversion


def collect_data_general(selection, data_quantity_machine):
    print("General Data: Collecting General Data")

    # Load data from database
    sql_select = f"""
    SELECT * FROM [DWH].[utility].[ssp_webapp_input]
    WHERE date_id = '{selection['date'].strftime("%Y-%m-%d")}'
        AND shift_id = '{selection['shift_id']}'
        AND line_id = '{selection['subline']}'
    """
    df = pd.read_sql(sql_select, ssp_state.engine)

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
    df = pd.read_sql(sql_select, ssp_state.engine)

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

    df = pd.read_sql(sql_select, ssp_state.engine)

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

    df = pd.read_sql(sql_select, ssp_state.engine)

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
    ssp_webapp_input = Table('ssp_webapp_input', metadata, schema='utility', autoload_with=ssp_state.engine)

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
    result = ssp_state.session.execute(stmt)
    ssp_state.session.commit()

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
        ssp_state.session.execute(stmt)
        ssp_state.session.commit()

    else:
        print("General Data: General Data was updated")

    return

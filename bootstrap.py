import json

import pandas as pd
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import ssp_state


def bootstrap():
    """Connect to the DWH and load the reference/master data the app needs.

    Runs once per Streamlit script execution (Streamlit re-executes the
    whole script on every interaction), mirroring the original
    `if __name__ == "__main__":` startup block.
    """
    # SQL Settings
    with open(r"E:\Webapp_SSP\credentials.json") as json_file:
        pw_dwh = json.load(json_file)['dwh_user']

    sql_settings = {
        'server': 'S298A150\DWH',
        'database': 'DWH',
        'user': 'dwh_user',
        'password': pw_dwh}

    ssp_state.engine = create_engine("mssql+pyodbc://"+sql_settings['user']+":"+sql_settings['password']+"@"+sql_settings['server']+"/"+sql_settings['database']+"?driver=ODBC Driver 17 for SQL Server")
    Session = sessionmaker(bind=ssp_state.engine)
    ssp_state.session = Session()

    engine = ssp_state.engine

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
    ssp_state.selected_workplaces_log = ['H158', 'H115', 'H111A', 'H116', 'Hof', 'Entladung', 'Abwicklung WE', 'BS Kanban', 'BS Kommi', 'BS Wäsche', 'PV Konvoi', 'PV Stapler', 'PV Cargo Runner', 'IXP', 'Verpackung', 'as2', 'as3', 'as4', 'as5', 'as6/7', 'MA1', 'Sonstiges']

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

    ssp_state.hierarchy = hierarchy

    # Forcam Workplace UUIDS
    df_forcam_uuid = pd.read_sql("SELECT DISTINCT workplace_ifa_id, workplace_forcam_uuid FROM [DWH].[dim].[forcam_hierarchy]", engine)
    ssp_state.ifa_wpl_to_forcam_uuid = df_forcam_uuid.set_index('workplace_ifa_id')['workplace_forcam_uuid'].to_dict()
    ssp_state.forcam_uuid_to_ifa_wpl = {v: k for k, v in ssp_state.ifa_wpl_to_forcam_uuid.items()}

    # Forcam Operating state codes
    ssp_state.df_operating_state_codes = pd.read_sql("SELECT DISTINCT code, title_de, color FROM [DWH].[dim].[forcam_operating_state_codes]", engine)

    # Workplace Infos
    ssp_state.df_wpl_info = pd.read_sql("""
                SELECT workplace_id, process, machine_name, output_relevant, line_name
                FROM [DWH].[dim].[workplace]
                WHERE plant = 'HdlP' AND (process != 'mes-logout' OR process IS NULL) AND line_name NOT IN ('pb1', 'pb2')
                """, engine)

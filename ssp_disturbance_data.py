import datetime
import json

import pandas as pd
import requests
from sqlalchemy import MetaData, Table, insert, text, update

import ssp_state


def collect_data_disturbance(selection, progressbar, progressbar_text):
    print("Disturbance: Collecting Machine Disturbance Data")

    # Load Data from Forcam
    df = load_data_disturbance(selection, progressbar, progressbar_text)

    # Translate code to text
    df = pd.merge(df, ssp_state.df_operating_state_codes, on='code', how='left')
    df = df.rename(columns={'title_de': 'problem'})

    # Update Database with Forcam Data
    save_data_disturbance(selection, df, save_style='update')

    # Read DWH Table
    sql_select = """SELECT * FROM [utility].[ssp_webapp_disturbances] WHERE date_id = '""" + selection['date'].strftime("%Y-%m-%d") + "' AND shift_id = '" + selection['shift_id'] + "' AND workplace_id IN (" + selection['workplaces_list'] + ")"
    df = pd.read_sql(sql_select, ssp_state.engine)

    # Add Meta Data
    df = pd.merge(df, ssp_state.df_wpl_info, on='workplace_id', how='inner')
    df['machine_name'] = df['machine_name'].fillna('NOT FOUND')

    return df


def collect_data_disturbance_log(selection):
    print("Disturbance: Collecting Disturbance for log")

    # Read DWH Table
    sql_select = """SELECT * FROM [utility].[ssp_webapp_disturbances] WHERE date_id = '""" + selection['date'].strftime("%Y-%m-%d") + "' AND shift_id = '" + selection['shift_id'] + "' AND workplace_id IN (" + selection['workplaces_list'] + ")"
    df = pd.read_sql(sql_select, ssp_state.engine)

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
                workplace_url += "&workplace=" + ssp_state.ifa_wpl_to_forcam_uuid[wpl]
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
    selected_columns = pd.read_sql(sql_query, ssp_state.engine)['COLUMN_NAME'].tolist()
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
        with ssp_state.engine.connect() as conn:
            with conn.begin():
                conn.execute(delete_sql)

        # Insert new DF
        df['last_updated'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.to_sql('ssp_webapp_disturbances', ssp_state.engine, schema='utility', if_exists='append', index=False)

        print("Disturbance: Values were replaced. Input Length: " + str(len(df)))
        return

    # Save Style Update
    elif save_style == 'update':

        # Define metadata and table
        metadata = MetaData()
        ssp_webapp_disturbances = Table('ssp_webapp_disturbances', metadata, schema='utility', autoload_with=ssp_state.engine)

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
            result = ssp_state.session.execute(stmt)

            # Insert Row if nothing was updated
            if result.rowcount == 0:
                print("Disturbance: Inserting a new row because there is no matching value to update.")
                # Create insert statement
                stmt = insert(ssp_webapp_disturbances).values(row.to_dict())

                # Execute insert
                ssp_state.session.execute(stmt)


        # Commit changes
        ssp_state.session.commit()

        print("Disturbance: Values were updated.")
        return

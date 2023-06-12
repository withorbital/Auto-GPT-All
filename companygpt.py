import argparse
import csv
import os
from autogpt.main import run_auto_gpt
from google.cloud import storage
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

workspace_directory = './autogpt/auto_gpt_workspace'
single_op_fp = workspace_directory+"/output.tsv"
all_op_fp = workspace_directory+"/all_output.tsv"

parser = argparse.ArgumentParser()
parser.add_argument("spreadsheet_id",type=str)
parser.add_argument("bucket",type=str) 
parser.add_argument("prompt_path",type=str)
parser.add_argument("output_path",type=str)
parser.add_argument("input_col",type=str)
parser.add_argument("input_start",type=str)
parser.add_argument("input_end",type=str)
parser.add_argument("output_col",type=str)
parser.add_argument("output_size",type=str) 

def main(args):
    spreadsheetId = args.spreadsheetId
    input_col = args.input_col
    input_start = args.input_start
    input_end = args.input_end
    output_col = args.output_col
    output_size = int(args.output_size)

    promptTemplate = gsc_read_file(args.bucket,args.prompt_path)
    # companies = parse_csv(gsc_read_file(args.bucket,args.company_csv_path))
    
    result = get_spreadheet_values(spreadsheetId, input_col, input_start, input_end)
    print(result)
    companies = result["values"]
    print(f"{len(companies)} rows retrieved")
    #skip first row (header)
    companies = companies[1:]

    os.makedirs(workspace_directory, exist_ok=True)
    with open(all_op_fp,"w") as f: f.write("")

    current_row = int(input_start)
    for _company in companies:
        company = _company[0]
        print("Running Auto-GPT for company: ", company)

        prompt=promptTemplate.format(company_name=company)
        with open("ai_settings.yaml","w") as f: f.write(prompt)
        with open(single_op_fp,"w") as f: f.write("")

        try:
            run_auto_gpt(
                True, # continuous
                10, # continuous_limit
                "ai_settings.yaml", # ai_settings
                "prompt_settings.yaml", # prompt_settings
                True, # skip_reprompt
                False, # speak
                False, # debug
                True, # gpt3only
                False, # gpt4only
                "json_file", # memory_type
                "", #browser_name, use default
                True, # allow_downloads
                True, # skip_news
                workspace_directory, # workspace_directory
                False # install_plugin_deps
            )
        except NameError as e:
            if " success" not in str(e).lower():
                print("Error",e)
        except Exception as e:
            print("Error",e)
        
        with open(single_op_fp, "r") as fr, open(all_op_fp, "a") as fw:
                line = fr.readline()
                fw.write(f"{company}\t{line}\n")
                data = line.split("\t")
                if len(data) > output_size:
                    update_spreadsheet_values(spreadsheetId, f"{output_col}{current_row}", "RAW", [data[:output_size]])
                else:
                    update_spreadsheet_values(spreadsheetId, f"{output_col}{current_row}", "RAW", [data])

        current_row += 1

    with open(all_op_fp, "r") as f:
        gsc_write_file(args.bucket,args.output_path,f.read())


# --------- helper funcs ---------

def gsc_read_file(bucket,path):
    return storage.Client().bucket(bucket).blob(path).download_as_string().decode()

def gsc_write_file(bucket,path,content):
    with storage.Client().bucket(bucket).blob(path).open("w") as f:
        f.write(content)

def parse_csv(text):
    return list(csv.reader(text.split("\n")))

def get_spreadheet_values(spreadsheet_id, row, start, end):
    """
    Creates the batch_update the user has access to.
    Load pre-authorized user credentials from the environment.
    TODO(developer) - See https://developers.google.com/identity
    for guides on implementing OAuth2 for the application.
        """
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
    # pylint: disable=maybe-no-member
    try:
        service = build('sheets', 'v4', credentials=creds)

        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"{row}{start}:{row}{end}").execute()
        rows = result.get('values', [])
        print(f"{len(rows)} rows retrieved")
        return result
    except HttpError as error:
        print(f"An error occurred: {error}")
        return error

def update_spreadsheet_values(spreadsheet_id, range_name, value_input_option,
                  _values):
    """
    Creates the batch_update the user has access to.
    Load pre-authorized user credentials from the environment.
    TODO(developer) - See https://developers.google.com/identity
    for guides on implementing OAuth2 for the application.
        """
    creds, _ = google.auth.default()
    # pylint: disable=maybe-no-member
    try:

        service = build('sheets', 'v4', credentials=creds)
        body = {
            'values': _values
        }
        result = service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=range_name,valueInputOption=value_input_option, body=body).execute()
        print(f"{result.get('updatedCells')} cells updated.")
        return result
    except HttpError as error:
        print(f"An error occurred: {error}")
        return error
    
if __name__ == "__main__":
    main(parser.parse_args())
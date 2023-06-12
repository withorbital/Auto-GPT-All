import argparse
import csv
import os
from autogpt.main import run_auto_gpt
from google.cloud import storage

workspace_directory = './autogpt/auto_gpt_workspace'
single_op_fp = workspace_directory+"/output.tsv"
all_op_fp = workspace_directory+"/all_output.tsv"

parser = argparse.ArgumentParser()
parser.add_argument("bucket",type=str)
parser.add_argument("prompt_path",type=str)
parser.add_argument("company_csv_path",type=str)
parser.add_argument("output_path",type=str)

def main(args):
    print("Args:",args)
    promptTemplate = gsc_read_file(args.bucket,args.prompt_path)
    companies = parse_csv(gsc_read_file(args.bucket,args.company_csv_path))
    os.makedirs(workspace_directory, exist_ok=True)
    with open(all_op_fp,"w") as f: f.write("")

    for company in list(zip(*companies))[0]:
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

if __name__ == "__main__":
    main(parser.parse_args())
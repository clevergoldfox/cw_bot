import requests
import json
import re
import datetime
import time
import math
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from get_bid import get_bid

SLACK_BOT_TOKEN = "xoxb-9550131875088-10437907872661-5Q6WrFHd5lHkH7VZiMQUiDlA"
CHANNEL_ID = "C0ACHPMNU4F"

slack_client = WebClient(token=SLACK_BOT_TOKEN)

WEBHOOK_URL = "https://discord.com/api/webhooks/1451104714002399292/BU1JpSSJA6YYalAWyzyqEJHSRfFnqNyVIUI6oK6qBsw3CJpQO9VTcEw_sfEWI9aOl8ew"

def get_job_data_json(url=None, html_file=None):
    if html_file:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    elif url:
        response = requests.get(url)
        html_content = response.text
    else:
        raise ValueError("Either url or html_file must be provided")
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    vue_container = soup.find('div', {'id': 'vue-container'})
    
    if vue_container and vue_container.get('data'):
        return vue_container.get('data')
    else:
        raise ValueError("Could not find job data in HTML. Make sure the div with id='vue-container' has a 'data' attribute.")

def get_job_data_dict(url=None, html_file=None):
    json_string = get_job_data_json(url=url, html_file=html_file)
    return json.loads(json_string)

def extract_payment(job):
    payment = job.get("payment", {})

    if payment.get("fixed_price_payment"):
        fixed = payment["fixed_price_payment"]
        return {
            "payment_type": "fixed",
            "min_budget": fixed.get("min_budget", 0),
            "max_budget": fixed.get("max_budget", 0)
        }

    if payment.get("hourly_payment"):
        hourly = payment["hourly_payment"]
        return {
            "payment_type": "hourly",
            "min_budget": hourly.get("min_hourly_wage", 0),
            "max_budget": hourly.get("max_hourly_wage", 0)
        }

    return {
        "payment_type": "undefined",
        "min_budget": 0,
        "max_budget": 0
    }

def job_filter(job_json):
    try:
        if (job_json['status'] == 'released' and
            # job_json['last_released_at'] == datetime.now().strftime('%Y-%m-%d') and
            datetime.fromisoformat(job_json['last_released_at']).date() == date.today() and
            job_json['num_application_conditions'] < 10 and
            job_json['num_contracts'] < job_json['project_contract_hope_number'] and
            all(word not in job_json['title'].lower() for word in [
                '講師', 
                'pm', 
                '運営代行',
                '初心者ok',
                '初心者向け',
                'バナー制作',
                'バナー',
                '画像制作',
                'ロゴ',
                '韓国'
                # '記事',
                ]) and
            # all(not in job_json['user_id'] for in ['5340168']) and
            all(word not in job_json['username'].lower() for word in [
                'genba', 
                'sale', 
                'saesky', 
                'cw_agent', 
                'daijobu', 
                'consulting', 
                'クラウドワークス', 
                '(株)markeline', 
                '（株）メディアファースト', 
                '株式会社オレコン', 
                '清泉設備', 
                'mei734r76', 
                'atec_systems', 
                'support_3',
                '篠原美菜子',
                'ダックスカンパニー',
                'asahisystem',
                'tck_tokyo',
                'アオイ_デザイン事務所',
                'salondesign', 
                '株式会社kanoa',
                'カズキ_マーケティング'
                ])):
            if(job_json['payment']['payment_type'] == 'undefined'):
                return job_json
            elif(job_json['payment']['payment_type'] == "fixed"):
                if(isinstance(job_json['payment']['min_budget'], (int, float))):
                    if(job_json['payment']['min_budget'] >= 50000):
                        return job_json
                elif(isinstance(job_json['payment']['max_budget'], (int, float))):
                    if(job_json['payment']['max_budget'] >= 50000):
                        return job_json
                else:
                    return job_json
            elif(job_json['payment']['payment_type'] == "hourly"):
                if(isinstance(job_json['payment']['min_budget'], (int, float))):
                    if(job_json['payment']['min_budget'] >= 1500):
                        return job_json
                elif(isinstance(job_json['payment']['max_budget'], (int, float))):
                    if(job_json['payment']['max_budget'] >= 2000):
                        return job_json
                else:
                    return job_json
    except Exception as e:
        print(f"Error: {e}")
        print(f"Job JSON: {job_json}")
        
def show_noti(job_json, index):
    print(f"Title: {job_json['title']}")
    print(f"https://crowdworks.jp/public/jobs/{job_json['id']}")
    print(f"Payment: {job_json['payment']}")
    print(f"Last Released At: {job_json['last_released_at']}")
    if (index == 226):
        category = "System"
    elif (index == 230):
        category = "Homepage"
    elif (index == 311):
        category = "AI"
    elif (index == 242):
        category = "App"

    data = {
        "embeds": [
            {
                "title": "Crowdworks New Task\n" + category,
                "description": job_json['title']
    + "  ("
    + (
        job_json['payment']['payment_type']
        + "  "
        + str(job_json['payment']['min_budget']) + "円"
        if job_json['payment']['payment_type'] != 'undefined'
        else "Undefined"
      )
    + ")\n"
    + "https://crowdworks.jp/public/jobs/"
    + str(job_json['id'])
            }
        ]
    }

    try:
        main = slack_client.chat_postMessage(
            channel=CHANNEL_ID,
            text = (
                "Crowdworks New Task\n"
                + category + "\n"
                + job_json['title']
                + "  ("
                + (
                    job_json['payment']['payment_type']
                    + "  "
                    + str(job_json['payment']['min_budget']) + "円"
                    if job_json['payment']['payment_type'] != 'undefined'
                    else "Undefined"
                )
                + ")\n"
                + "https://crowdworks.jp/public/jobs/"
                + str(job_json['id'])
            )
        )

        # thread_ts = main["ts"]
        # job_description = get_bid(job_json['id'])

        # slack_client.chat_postMessage(
        #     channel=CHANNEL_ID,
        #     thread_ts=thread_ts,
        #     text="📋 Job title (copyable snippet below)"
        # )

        # slack_client.files_upload(
        #     channels=CHANNEL_ID,
        #     content=job_description,
        #     title="Job Title",
        #     filetype="text"
        # )

        # slack_client.chat_postMessage(
        #     channel=CHANNEL_ID,
        #     thread_ts=ts,
        #     text=f"""```*
        #     {job_json['title']}\n
        #     {job_description}
        #     *```"""
        # )
    except SlackApiError as e:
        print(f"Error: {e.response['error']}")
    
    # response = requests.post(WEBHOOK_URL, json=data)

    # if response.status_code == 204:
    #     print("Message sent successfully")
    # else:
    #     print("Failed:", response.text)

if __name__ == "__main__":
    print(datetime.now().strftime('%Y-%m-%d'))
    # show_noti({'id': 12861298, 'title': 'Test', 'status': 'released', 'expired_on': '2026-01-20', 'last_released_at': '2026-01-20T15:45:06+09:00', 'payment': {'payment_type': 'fixed', 'min_budget': 50000, 'max_budget': 100000}, 'num_contracts': 0, 'project_contract_hope_number': 0, 'num_application_conditions': 0, 'user_id': 12861298, 'username': 'ハッシュタグエンジニアリング', 'is_employer_certification': False}, 226)
    try:
        categories = [226, 230, 311, 242] #system, homepage, ai, app
        count = [0, 0, 0, 0]
        pre_systems = [[],[],[],[]]
        new_systems = []
        i = 0
        duration = 0
        pre_duration = 0
        while True:
            try:
                duration += pre_duration
                start = time.time()
                # print(f"Count: {count[i%4]}")
                if categories[i%4] == 226:
                    print()
                    print()
                    print(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    Count:{ (math.floor(i / 4)) + 1 }  Duration: {duration:.2f} S    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                    print()
                    print(f"================================= System   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[i%4] == 230:
                    print()
                    print(f"================================= Homepage   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[i%4] == 311:
                    print()
                    print(f"================================= AI   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[i%4] == 242:
                    print()
                    print(f"================================= App   Duration: {pre_duration:.2f} S  ================================")
                    print()
                    
                if i % 4 == 0:
                    duration = 0
                # print("pre_systems", pre_systems)
                # systems = pre_systems[i%4]
                # pre_systems[i%4] = []
                job_data = get_job_data_dict(url=f"https://crowdworks.jp/public/jobs/search?category_id={categories[i%4]}&order=new")
                jobs = job_data['searchResult']['job_offers']
                job_list = []
                for job in jobs:
                    # get_bid(job['job_offer']['id'])
                    job_json = {
                        'id': job['job_offer']['id'],
                        'title': job['job_offer']['title'],
                        'status': job['job_offer']['status'],
                        'expired_on': job['job_offer']['expired_on'],
                        'last_released_at': job['job_offer']['last_released_at'],
                        'payment': extract_payment(job),
                        'num_contracts': job['entry']['project_entry']['num_contracts'] if job.get('entry', {}).get('project_entry') else 0,
                        'project_contract_hope_number': job['entry']['project_entry']['project_contract_hope_number'] if job.get('entry', {}).get('project_entry') else 1,
                        'num_application_conditions': job['entry']['project_entry']['num_application_conditions'] if job.get('entry', {}).get('project_entry') else 0,
                        # 'num_contracts': 0,
                        # 'project_contract_hope_number': 1,
                        # 'num_application_conditions': 0,
                        'user_id': job['client']['user_id'],
                        'username': job['client']['username'],
                        'is_employer_certification': job['client']['is_employer_certification']
                    }
                    job_list.append(job_filter(job_json))
                
                for job in job_list:
                    if job:
                        if count[i%4] == 0:
                            pre_systems[i%4].append(job['id'])
                            print(job["title"])
                            print(job["last_released_at"])
                    if job and job['id'] not in pre_systems[i%4] and count[i%4] > 0:
                    # if job and job['id'] not in systems:
                        pre_systems[i%4].append(job['id'])
                        show_noti(job, categories[i%4])
                
                if len(pre_systems[i%4]) > 300:
                    pre_systems[i%4] = pre_systems[i%4][-300:]

                end = time.time()
                pre_duration = end - start
                count[i%4] += 1
                i += 1
            except Exception as e:
                time.sleep(1)
                count = [0,0,0,0]
                i = 0
                print(f"Error: {e}")
                continue
                    
    except Exception as e:
        print(f"Error: {e}")
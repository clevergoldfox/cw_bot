import requests
import json
import re
import datetime
import time
import math
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from openai import OpenAI

# import os
# os.environ["OPENAI_API_KEY"] = "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"

client = OpenAI()
def get_bid(id):
    print(id)
    url = "https://crowdworks.jp/public/jobs/" + str(id)
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    res = requests.get(url, headers=headers)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    desc_td = soup.select_one("td.confirm_outside_link")
    job_description = desc_td.get_text(separator="\n", strip=True)

    return job_description

# if __name__ == "__main__":
#     get_bid(12902646)
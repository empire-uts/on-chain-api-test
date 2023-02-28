from fastapi import FastAPI
from mangum import Mangum
from pydantic import BaseModel
from typing import Union
from datetime import datetime, timedelta, date
import requests
import json
import time

import boto3
import pandas as pd

headers = {
    "accept": "application/json",
    "X-API-KEY": "5aecfc59-6216-47cd-81f0-397093b41221"
}

app = FastAPI()
cache = {}
cash_time = 60

def get_cache(key, func, expiration_seconds = 60):
    import datetime
    global cache
    print(cache)
    # キャッシュから取得
    if key in cache:
        now = datetime.datetime.now()
        if (cache[key]["updated"] + datetime.timedelta(seconds=expiration_seconds)) > now:
            print("cashやで")
            a = 1
            return cache[key]["value"], a

    # キャッシュ更新
    value = func()
    now = datetime.datetime.now()
    cache[key] = {
        "updated" : now,
        "value"   : value
    }
    a = 0
    return value, a

class Athena(object):
    def __init__(self, session=None):
        self.client = session.client('athena')

    def execute_sql(self, sql):
        athena_client = self.client

        exec_id = athena_client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": 'astar'},
            ResultConfiguration={
                'OutputLocation': 's3://magpy-indexer-bucket-test/test'
            },
            WorkGroup='primary'
        )['QueryExecutionId']

        print('Athena Execution ID: {}'.format(exec_id))
        print('query: ')
        print(sql)

        status = athena_client.get_query_execution(QueryExecutionId=exec_id)['QueryExecution']['Status']

        # ポーリング
        while status['State'] not in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            print('{}: wait query running...'.format(status['State']))
            time.sleep(5)
            status = athena_client.get_query_execution(QueryExecutionId=exec_id)['QueryExecution']['Status']

        return status['State'], exec_id


def main(string: date0, string: date1):
    session = boto3.session.Session()

    athena = Athena(session)
    
    sql = 'select "token0_symbol", "token0_amount", "token1_symbol", "token1_amount" from "dex_trades" where "block_timestamp"<' + {date0} + ' and "block_timestamp">' + {date1} + ' order by "block_timestamp" asc limit 50;'

    status, exec_id = athena.execute_sql(sql)

    if status == 'SUCCEEDED':
        s3_client = session.client('s3')
        body = s3_client.get_object(Bucket='pyapi-practice',
                                    Key='athena-output/{0}.csv'.format(exec_id))['Body']

        df = pd.read_csv(body, lineterminator='n')

        print('[result]')
        print(df)


@app.get("/root")
def root():
    return {"message": "Hello World"}


@app.get("/dexTrades/{date0}/{date1}")
def dexTrades(date0, date1):
    f = f"main({date0}, {date1})"
    response = get_cache(f, main(date0, date1), cash_time)[0]
    return response

handler = Mangum(app)
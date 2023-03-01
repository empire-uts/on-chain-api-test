import boto3
import pandas as pd
from fastapi import FastAPI, HTTPException, Path
from mangum import Mangum
from datetime import datetime, timedelta

ATHENA_OUTPUT_BUCKET = '578420364049-ap-northeast-1-athena-results-bucket-e25440ffkt'
ATHENA_DB_NAME = 'enmai-check'

app = FastAPI()
handler = Mangum(app)

session = boto3.session.Session(profile_name='kii')
s3_client = session.client('s3')
athena_client = session.client('athena')

cache = {}
cache_time = {}

def poll_query_status(query_execution_id):
    response = athena_client.get_query_execution(QueryExecutionId=query_execution_id)
    state = response['QueryExecution']['Status']['State']

    if state == 'SUCCEEDED':
        return True
    elif state in ['FAILED', 'CANCELLED']:
        raise HTTPException(status_code=400, detail=f'Query failed with state {state}.')
    else:
        return False

def run_query(query):
    if query in cache:
        if datetime.utcnow() - cache_time[query] < timedelta(minutes=5):
            return cache[query]
        else:
            del cache[query]
            del cache_time[query]

    response = athena_client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': ATHENA_DB_NAME
        },
        ResultConfiguration={
            'OutputLocation': f's3://{ATHENA_OUTPUT_BUCKET}/'
        }
    )

    query_execution_id = response['QueryExecutionId']
    status = False

    while not status:
        status = poll_query_status(query_execution_id)

    s3_key = f'{query_execution_id}.csv'
    s3_path = f's3://{ATHENA_OUTPUT_BUCKET}/{s3_key}'

    try:
        s3_client.head_object(Bucket=ATHENA_OUTPUT_BUCKET, Key=s3_key)
    except:
        raise HTTPException(status_code=400, detail='Query results not found.')

    data = pd.read_csv(s3_path)
    json_result = data.to_json(orient='records')

    cache[query] = json_result
    cache_time[query] = datetime.utcnow()

    return json_result

@app.get("/query/{sql_query}")
async def query(sql_query: str = Path(..., description="SQL query to execute using Athena")):
    try:
        result = run_query(sql_query)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

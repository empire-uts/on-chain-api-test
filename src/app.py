import boto3
import pandas as pd
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from mangum import Mangum
from cachetools import TTLCache
from datetime import datetime, timedelta

app = FastAPI()
handler = Mangum(app)

# Set up Athena client and S3 bucket
s3_output = 's3://578420364049-ap-northeast-1-athena-results-bucket-e25440ffkt'
athena = boto3.client('athena')
database = 'enmai-check'
table = 'dex_trades'

# Set up cache
cache = TTLCache(maxsize=1024, ttl=60)

# Define Athena query
def run_query(date, address):
    query = f"""
        select 
            if("token0_address"='0x6a2d262d56735dba19dd70682b39f6be9a931d98' 
                or "token0_address"='0x3795c36e7d12a8c252a20c5a7b455f7c57b60283'
                or "token0_address"='0x733ebcc6df85f8266349defd0980f8ced9b45f35'
                or "token0_address"='0x4bf769b05e832fcdc9053fffbc78ca889acb5e1e',
                    abs("token0_amount" / "token1_amount"), 
                    abs("token1_amount" / "token0_amount"))
        from {table}
        where 
            "block_timestamp"<='{date}' 
            and "pair_stable"=1 
            and ("token0_address"='{address}' 
                or "token1_address"='{address}') 
            and ("token0_address"='0x6a2d262d56735dba19dd70682b39f6be9a931d98' 
                or "token0_address"='0x3795c36e7d12a8c252a20c5a7b455f7c57b60283'
                or "token0_address"='0x733ebcc6df85f8266349defd0980f8ced9b45f35'
                or "token0_address"='0x4bf769b05e832fcdc9053fffbc78ca889acb5e1e'
                or "token1_address"='0x6a2d262d56735dba19dd70682b39f6be9a931d98'
                or "token1_address"='0x3795c36e7d12a8c252a20c5a7b455f7c57b60283'
                or "token1_address"='0x733ebcc6df85f8266349defd0980f8ced9b45f35'
                or "token1_address"='0x4bf769b05e832fcdc9053fffbc78ca889acb5e1e')
        order by "block_timestamp" desc 
        limit 1;
    """
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': database
        },
        ResultConfiguration={
            'OutputLocation': s3_output,
        }
    )
    query_execution_id = response['QueryExecutionId']
    return query_execution_id

# Get results from Athena query and return as JSON
def get_results(query_execution_id):
    response = athena.get_query_execution(QueryExecutionId=query_execution_id)
    state = response['QueryExecution']['Status']['State']

    if state == 'SUCCEEDED':
        result = athena.get_query_results(QueryExecutionId=query_execution_id)
        columns = [col['VarCharValue'] for col in result['ResultSet']['Rows'][0]['Data']]
        data = []
        for row in result['ResultSet']['Rows'][1:]:
            data.append([cell['VarCharValue'] for cell in row['Data']])
        df = pd.DataFrame(data, columns=columns)
        return df.to_json(orient='records')
    elif state == 'FAILED':
        reason = response['QueryExecution']['Status']['StateChangeReason']
        raise ValueError(f'Query failed: {reason}')
    else:
        raise ValueError(f'Query still running: {state}')

# Define endpoint with caching and polling
@app.get("/dex_trades")
async def get_dex_trades(date: str, address: str):
    key = f"{date}:{address}"
    cached = cache.get(key)
    if cached:
        return JSONResponse(content=cached)
    else:
        query_execution_id = run_query(date, address)
        while True:
            response = athena.get_query_execution(QueryExecutionId=query_execution_id)
            state = response['QueryExecution']['Status']['State']
            if state == 'SUCCEEDED':
                results = get_results(query_execution_id)
                cache[key] = results
                return JSONResponse(content=results)
            elif state == 'FAILED':
                reason = response['QueryExecution']['Status']['StateChangeReason']
                raise ValueError(f'Query failed: {reason}')
            else:
                await asyncio.sleep(1)
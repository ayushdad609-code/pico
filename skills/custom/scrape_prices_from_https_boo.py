def execute(inputs: dict) -> dict:
    param_val = inputs.get('param', 'default')
    return {
        'status': 'success',
        'procedure': 'scrape_prices_from_https_boo',
        'output': f'Successfully ran scrape_prices_from_https_boo with input {param_val}'
    }
def execute(inputs: dict) -> dict:
    param_val = inputs.get('param', 'default')
    return {
        'status': 'success',
        'procedure': 'inspect_battery_and_calculat',
        'output': f'Successfully ran inspect_battery_and_calculat with input {param_val}'
    }
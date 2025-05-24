import jwt
from datetime import datetime, timedelta, timezone


SECRET_KEY = "r5YhKsJGfAvN9-t4Pd83Hshw4xq1mTtD5Cn12zU0bnNKX5qO7kQvI8gqykE99BdJ"

def generate_JWT_token(user_id, exp_minutes=36000):
    expiration_time = datetime.now() + timedelta(minutes=exp_minutes)
    expiration_time_str = expiration_time.isoformat()

    payload = {"user_id": user_id, "expiration_time": expiration_time_str}

    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    return token

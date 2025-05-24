from pydantic import BaseModel

class UserSchema(BaseModel):
    firstName: str
    lastName:str
    email: str
    email: str
    cel: str
    password: str
    gender: str

    class Config:
        orm_mode =True

class UserResponse(BaseModel):
    id: int
    email: str
    firstName: str
    lastName: str
    cel: str
    gender: str

    class Config:
        orm_mode = True

class OTPRequest(BaseModel):
    email: str
    codigo_otp: str
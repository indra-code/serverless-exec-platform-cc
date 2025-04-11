from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FunctionBase(BaseModel):
    name: str
    description: Optional[str] = None
    code_path: str
    runtime: Optional[str] = "python"
    timeout: Optional[int] = 30
    memory: Optional[int] = 128
    is_active: Optional[bool] = True

class FunctionCreate(FunctionBase):
    pass

class FunctionUpdate(FunctionBase):
    name: Optional[str] = None
    code_path: Optional[str] = None

class FunctionInDB(FunctionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True 
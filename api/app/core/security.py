from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime, timedelta

from ..db.session import get_db
from ..models.user import User
from ..core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Validate the access token and return the current user.
    If validation fails, raise an HTTPException.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode the JWT token
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get the user from the database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the current user has admin privileges.
    If not, raise an HTTPException.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this resource. Admin privileges required."
        )
    return current_user

# For basic authentication or temporary access to config endpoints
def get_temp_admin_user(
    db: Session = Depends(get_db),
) -> User:
    """
    Temporary admin access - ONLY FOR DEVELOPMENT
    Returns a mock admin user for development purposes
    """
    # This is a temporary solution for development/testing
    # In production, this should be removed
    admin_user = User(
        id=0,
        username="admin",
        email="admin@example.com",
        is_admin=True
    )
    return admin_user 
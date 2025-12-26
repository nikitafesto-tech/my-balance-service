from fastapi import Request
from sqlalchemy.orm import Session
from app.models import UserSession, UserWallet

def get_current_user(request: Request, db: Session):
    """
    Получает текущего пользователя на основе session_id из cookies.
    Используется и в main.py, и в routers/chats.py.
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    
    sess = db.query(UserSession).filter_by(session_id=session_id).first()
    if not sess:
        return None
        
    return db.query(UserWallet).filter_by(casdoor_id=sess.token).first()